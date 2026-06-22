import logging
from apscheduler.triggers.cron import CronTrigger

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star

# 尝试兼容不同版本的 EventType 导入路径
try:
    from astrbot.core.event import EventType
except ImportError:
    try:
        from astrbot.api.event import EventType
    except ImportError:
        # 极端情况，定义一个默认值（实际可能无效，但避免崩溃）
        EventType = None
        _logger = logging.getLogger("astrbot")
        _logger.warning("[CronPush] 无法导入 EventType，将使用字符串替代（可能不兼容）")

_logger = logging.getLogger("astrbot")

# 定时任务配置（第一个默认开启，每分钟执行一次）
TASKS = [
    {"enabled": True, "cron": "* * * * *", "message": "定时推送测试消息"},
    {"enabled": False, "cron": "0 12 * * *", "message": "中午好！记得午休哦"},
]


class CronPushPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context, config)
        self._known_sessions = set()
        self._register_session_listener()
        self._register_builtin_tasks()

    def _register_session_listener(self):
        """使用 get_handler_or_create 手动注册消息监听器，捕获所有会话"""
        try:
            from astrbot.core.star.register.star_handler import get_handler_or_create
        except ImportError:
            _logger.error("[CronPush] 无法导入 get_handler_or_create，会话监听将失效")
            return

        async def capture(event: AstrMessageEvent):
            if event.unified_msg_origin:
                self._known_sessions.add(event.unified_msg_origin)
                _logger.debug(f"[CronPush] 捕获会话: {event.unified_msg_origin}")

        try:
            # 使用 EventType.AdapterMessageEvent 或字符串（兼容）
            event_type = EventType.AdapterMessageEvent if EventType else "adapter_message"
            get_handler_or_create(capture, event_type)
            _logger.info("[CronPush] 会话监听器注册成功")
        except Exception as e:
            _logger.error(f"[CronPush] 会话监听器注册失败: {e}", exc_info=True)

    def _register_builtin_tasks(self):
        """注册定时任务"""
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

                # 适配不同版本的 cron_manager API
                if hasattr(cron_manager, "add"):
                    cron_manager.add(
                        func=self._push_task,
                        trigger=trigger,
                        id=job_id,
                        kwargs={"message": task["message"]}
                    )
                elif hasattr(cron_manager, "scheduler") and hasattr(cron_manager.scheduler, "add_job"):
                    cron_manager.scheduler.add_job(
                        func=self._push_task,
                        trigger=trigger,
                        id=job_id,
                        kwargs={"message": task["message"]}
                    )
                else:
                    _logger.error(f"[CronPush] 无法注册任务，cron_manager 类型: {type(cron_manager)}")
                    continue

                _logger.info(f"[CronPush] 已注册定时任务 {job_id}: {task['cron']} -> {task['message']}")

            except Exception as e:
                _logger.error(f"[CronPush] 注册任务失败: {e}", exc_info=True)

    async def _push_task(self, message: str):
        """定时执行的推送任务"""
        if not self._known_sessions:
            _logger.warning("[CronPush] 无已知会话，跳过本次推送")
            return

        chain = MessageChain()
        chain.message(message)
        _logger.info(f"[CronPush] 开始向 {len(self._known_sessions)} 个会话推送: {message}")

        for session_str in self._known_sessions:
            try:
                await self.context.send_message(session_str, chain)
                _logger.info(f"[CronPush] 成功推送到 {session_str}")
            except Exception as e:
                _logger.error(f"[CronPush] 推送失败 {session_str}: {e}", exc_info=True)

    async def terminate(self):
        """插件卸载时清理定时任务"""
        cron_manager = self.context.cron_manager
        if cron_manager:
            for i in range(len(TASKS)):
                job_id = f"builtin_push_{i}"
                try:
                    if hasattr(cron_manager, "remove"):
                        cron_manager.remove(job_id)
                    elif hasattr(cron_manager, "remove_job"):
                        cron_manager.remove_job(job_id)
                    elif hasattr(cron_manager, "scheduler") and hasattr(cron_manager.scheduler, "remove_job"):
                        cron_manager.scheduler.remove_job(job_id)
                except Exception as e:
                    _logger.debug(f"[CronPush] 移除任务 {job_id} 时忽略异常: {e}")
        _logger.info("[CronPush] 插件已卸载")