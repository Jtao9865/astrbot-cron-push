import logging
from apscheduler.triggers.cron import CronTrigger
import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api.event import MessageChain

_logger = logging.getLogger("astrbot")

# 定时任务配置（启用/禁用、cron表达式、消息内容）
TASKS = [
    {"enabled": True, "cron": "* * * * *", "message": "早上好！新的一天开始了"},
    {"enabled": False, "cron": "0 12 * * *", "message": "中午好！记得午休哦"},
]

class CronPushPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):   # ✅ 正确签名
        super().__init__(context)
        self.config = config
        self._known_sessions = set()
        self._register_session_listener()
        self._register_builtin_tasks()

    def _register_session_listener(self):
        from astrbot.core.star.register.star_handler import get_handler_or_create
        from astrbot.core.star.star_handler import EventType

        async def capture(event: AstrMessageEvent):
            if event.unified_msg_origin:
                self._known_sessions.add(event.unified_msg_origin)

        get_handler_or_create(capture, EventType.AdapterMessageEvent)
        _logger.info("[CronPush] 会话监听器已注册")

    def _register_builtin_tasks(self):
        cron_manager = self.context.cron_manager
        if cron_manager is None:
            _logger.warning("[CronPush] CronManager 未初始化")
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
                _logger.info(f"[CronPush] ✅ 已注册任务 {job_id}: {task['cron']}")
            except Exception as e:
                _logger.error(f"[CronPush] 注册任务失败: {e}")

    async def _push_task(self, message: str):
        """定时推送任务"""
        chain = MessageChain()
        chain.chain.append(Comp.Plain(message))

        if not self._known_sessions:
            _logger.warning("[CronPush] 暂无已知会话，跳过推送")
            return

        for session_str in self._known_sessions:
            try:
                await self.context.send_message(session_str, chain)
                _logger.info(f"[CronPush] ✅ 已推送 [{session_str}]: {message}")
            except Exception as e:
                _logger.debug(f"[CronPush] 推送失败 [{session_str}]: {e}")

    async def terminate(self):
        """插件卸载时清理任务"""
        cron_manager = self.context.cron_manager
        if cron_manager:
            for i in range(len(TASKS)):
                try:
                    cron_manager.remove_job(f"builtin_push_{i}")
                except Exception:
                    pass
        _logger.info("[CronPush] 插件已卸载")