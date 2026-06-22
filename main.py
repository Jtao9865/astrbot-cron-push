import logging
from apscheduler.triggers.cron import CronTrigger
import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api.event import MessageChain

_logger = logging.getLogger("astrbot")

# 定时任务配置（enabled=True 启用, cron 为 5 位表达式）
TASKS = [
    {"enabled": True, "cron": "* * * * *", "message": "早上好！新的一天开始了"},
    {"enabled": False, "cron": "0 12 * * *", "message": "中午好！记得午休哦"},
]

class CronPushPlugin(Star):
    # ✅ 正确签名：context 和 config
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._known_sessions = set()
        self._register_session_listener()
        self._register_builtin_tasks()

    def _register_session_listener(self):
        """监听所有收到的消息，自动记录会话地址（用于推送）"""
        from astrbot.core.star.register.star_handler import get_handler_or_create
        from astrbot.core.star.star_handler import EventType

        async def capture(event: AstrMessageEvent):
            if event.unified_msg_origin:
                self._known_sessions.add(event.unified_msg_origin)
                _logger.debug(f"[CronPush] 捕获会话: {event.unified_msg_origin}")

        get_handler_or_create(capture, EventType.AdapterMessageEvent)
        _logger.info("[CronPush] 会话监听器已注册")

    def _register_builtin_tasks(self):
        """注册所有内置定时任务（使用 CronManager.add_job）"""
        cron_manager = self.context.cron_manager
        if cron_manager is None:
            _logger.warning("[CronPush] CronManager 未初始化，无法注册定时任务")
            return

        for i, task in enumerate(TASKS):
            if not task.get("enabled"):
                continue
            try:
                trigger = CronTrigger.from_crontab(task["cron"])
                job_id = f"builtin_push_{i}"
                cron_manager.add_job(
                    func=self._push_task,
                    trigger=trigger,
                    id=job_id,
                    kwargs={"message": task["message"]},
                )
                _logger.info(f"[CronPush] ✅ 已注册任务 {job_id}: {task['cron']} -> {task['message']}")
            except Exception as e:
                _logger.error(f"[CronPush] 注册任务失败: {e}")

    async def _push_task(self, message: str):
        """定时任务执行体：向所有已知会话推送消息"""
        if not self._known_sessions:
            _logger.warning("[CronPush] 暂无已知会话，跳过推送")
            return

        chain = MessageChain()
        chain.chain.append(Comp.Plain(message))

        for session_str in self._known_sessions:
            try:
                await self.context.send_message(session_str, chain)
                _logger.info(f"[CronPush] ✅ 已推送 [{session_str}]: {message}")
            except Exception as e:
                _logger.debug(f"[CronPush] 推送失败 [{session_str}]: {e}")

    async def terminate(self):
        """插件卸载时清理所有定时任务"""
        cron_manager = self.context.cron_manager
        if cron_manager:
            for i in range(len(TASKS)):
                try:
                    cron_manager.remove_job(f"builtin_push_{i}")
                except Exception:
                    pass
        _logger.info("[CronPush] 插件已卸载，定时任务已清理")