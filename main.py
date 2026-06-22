import logging
from apscheduler.triggers.cron import CronTrigger

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, MessageChain, event
from astrbot.core.event import EventType
from astrbot.api.star import Context, Star

_logger = logging.getLogger("astrbot")

# 定时任务配置
TASKS = [
    {"enabled": True, "cron": "* * * * *", "message": "早上好！新的一天开始了"},
    {"enabled": False, "cron": "0 12 * * *", "message": "中午好！记得午休哦"},
]


class CronPushPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context, config)
        self._known_sessions = set()
        # 会话监听由 @event 装饰器自动注册，无需手动调用
        self._register_builtin_tasks()

    @event(EventType.AdapterMessageEvent)
    async def capture_session(self, event: AstrMessageEvent):
        """捕获所有消息，记录会话 unified_msg_origin"""
        if event.unified_msg_origin:
            self._known_sessions.add(event.unified_msg_origin)
            _logger.debug(f"[CronPush] 捕获会话: {event.unified_msg_origin}")

    def _register_builtin_tasks(self):
        cron_manager = self.context.cron_manager
        if cron_manager is None:
            _logger.warning("[CronPush] CronManager 未初始化，无法注册定时任务")
            return

        # 调试：打印 cron_manager 的可用方法（可删除此行）
        # _logger.info(f"[CronPush] cron_manager 可用属性: {dir(cron_manager)}")

        for i, task in enumerate(TASKS):
            if not task.get("enabled"):
                continue
            try:
                trigger = CronTrigger.from_crontab(task["cron"])
                job_id = f"builtin_push_{i}"

                # 尝试使用 add 方法（新版 AstrBot）
                if hasattr(cron_manager, "add"):
                    cron_manager.add(
                        func=self._push_task,
                        trigger=trigger,
                        id=job_id,
                        kwargs={"message": task["message"]}
                    )
                # 若不存在 add，则尝试使用内部 scheduler 的 add_job
                elif hasattr(cron_manager, "scheduler") and hasattr(cron_manager.scheduler, "add_job"):
                    cron_manager.scheduler.add_job(
                        func=self._push_task,
                        trigger=trigger,
                        id=job_id,
                        kwargs={"message": task["message"]}
                    )
                else:
                    _logger.error(f"[CronPush] 无法找到注册任务的方法，cron_manager 类型: {type(cron_manager)}")
                    continue

                _logger.info(f"[CronPush] 已注册定时任务 {job_id}: {task['cron']} -> {task['message']}")

            except Exception as e:
                _logger.error(f"[CronPush] 注册任务失败: {e}", exc_info=True)

    async def _push_task(self, message: str):
        """定时推送任务"""
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