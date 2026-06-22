import logging
from apscheduler.triggers.cron import CronTrigger

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, MessageChain, EventType
from astrbot.api.star import Context, Star

_logger = logging.getLogger("astrbot")

# 定时任务配置
TASKS = [
    {"enabled": True, "cron": "* * * * *", "message": "早上好！新的一天开始了"},
    {"enabled": False, "cron": "0 12 * * *", "message": "中午好！记得午休哦"},
]


class CronPushPlugin(Star):
    # config 参数设为可选，兼容有无 __conf_schema.json 的情况
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context, config)
        self._known_sessions = set()
        self._register_session_listener()
        self._register_builtin_tasks()

    def _register_session_listener(self):
        from astrbot.core.star.register.star_handler import get_handler_or_create

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

        # 调试：打印 cron_manager 的方法列表（可删除）
        # _logger.info(f"[CronPush] cron_manager 可用方法: {dir(cron_manager)}")

        for i, task in enumerate(TASKS):
            if not task.get("enabled"):
                continue
            try:
                trigger = CronTrigger.from_crontab(task["cron"])
                job_id = f"builtin_push_{i}"

                # 修正：使用 add 方法（而非 add_job）
                cron_manager.add(
                    func=self._push_task,
                    trigger=trigger,
                    id=job_id,
                    kwargs={"message": task["message"]}
                )
                _logger.info(f"[CronPush] 已注册 {job_id}: {task['cron']}")

            except AttributeError:
                # 如果 add 方法也不存在，尝试直接访问内部 scheduler
                try:
                    cron_manager.scheduler.add_job(
                        func=self._push_task,
                        trigger=trigger,
                        id=job_id,
                        kwargs={"message": task["message"]}
                    )
                    _logger.info(f"[CronPush] (通过scheduler) 已注册 {job_id}: {task['cron']}")
                except Exception as e2:
                    _logger.error(f"[CronPush] 注册失败（两种方式均失败）: {e2}")
            except Exception as e:
                _logger.error(f"[CronPush] 注册失败: {e}")

    async def _push_task(self, message: str):
        if not self._known_sessions:
            _logger.warning("[CronPush] 无会话，跳过推送")
            return
        chain = MessageChain()
        chain.message(message)
        for session_str in self._known_sessions:
            try:
                await self.context.send_message(session_str, chain)
                _logger.info(f"[CronPush] 推送到 {session_str}: {message}")
            except Exception as e:
                _logger.error(f"[CronPush] 推送失败 {session_str}: {e}", exc_info=True)

    async def terminate(self):
        cron_manager = self.context.cron_manager
        if cron_manager:
            for i in range(len(TASKS)):
                try:
                    # 移除任务时同样注意方法名
                    if hasattr(cron_manager, "remove"):
                        cron_manager.remove(f"builtin_push_{i}")
                    elif hasattr(cron_manager, "remove_job"):
                        cron_manager.remove_job(f"builtin_push_{i}")
                    else:
                        cron_manager.scheduler.remove_job(f"builtin_push_{i}")
                except Exception:
                    pass
        _logger.info("[CronPush] 插件已卸载")