"""AstrBot 定时推送插件 —— 全内置模式，无条件推送。

所有任务在插件加载时自动注册，到点自动发送。
"""

import asyncio
import logging
import astrbot.api.message_components as Comp
from astrbot.api.event import filter as event_filter
from astrbot.core.platform import AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api.event import MessageChain
from astrbot.core.message.message_event_result import CommandResult

# 使用 astrbot 统一的 logger
_logger = logging.getLogger("astrbot")


# ================================================================ #
#  【内置定时任务】
#  enabled: True=启用, False=禁用
#  cron: 标准5位 cron 表达式 (分 时 日 月 星期)
#  message: 要发送的内容
# ================================================================ #
TASKS = [
    {
        "enabled": True,
        "cron": "* * * * *",           # 每分钟
        "message": "早上好！新的一天开始了",
    },
    {
        "enabled": False,
        "cron": "0 12 * * *",          # 每天 12:00 PM
        "message": "中午好！记得午休哦",
    },
    {
        "enabled": False,
        "cron": "0 22 * * *",          # 每天 10:00 PM
        "message": "晚安，好梦",
    },
]


class CronPushPlugin(Star):
    """定时推送消息的 AstrBot 插件（无条件推送版）。"""

    ENABLE_BUILTIN_JOBS = True

    def __init__(self, context: Context):
        super().__init__(context)
        self._jobs: dict[str, dict] = {}
        self._next_index = 1

        if self.ENABLE_BUILTIN_JOBS:
            _logger.info("[CronPush] 插件初始化完成，等待 initialize() 注册任务")

    async def initialize(self):
        """AstrBot 调用此方法进行插件初始化，此时可以安全访问事件循环。"""
        try:
            await self._register_builtin_tasks()
        except Exception as e:
            _logger.error(f"[CronPush] 注册内置任务失败: {e}")

    async def _register_builtin_tasks(self):
        """注册所有内置定时任务"""
        for i, task in enumerate(TASKS):
            if not task.get("enabled"):
                continue

            idx = self._next_index
            self._next_index += 1
            job_id = f"builtin_{i}"

            # payload 存储推送所需的数据，cron_manager 会在触发时传入
            job_data = {
                "index": idx,
                "job_id": job_id,
                "cron": task["cron"],
                "message": task["message"],
            }
            self._jobs[job_id] = job_data

            try:
                await self.context.cron_manager.add_basic_job(
                    name=job_id,
                    cron_expression=task["cron"],
                    handler=self._push_task,
                    payload=job_data,
                    enabled=True,
                    persistent=False,
                )
                _logger.info(
                    f'[CronPush] 已注册内置任务 #{idx}: '
                    f'{task["message"]} (cron={task["cron"]})'
                )
            except Exception as e:
                _logger.error(f"[CronPush] 注册内置任务失败: {e}")

    async def _push_task(self, payload: dict | None = None, **kwargs):
        """执行推送：无条件发送消息
        
        AstrBot CronJobManager 触发时传入 payload 和额外 kwargs。
        """
        if payload is None:
            payload = {}

        message = payload.get("message", "")
        job_id = payload.get("job_id", "unknown")

        chain = MessageChain()
        chain.append(Comp.Text(message))

        # 尝试向所有可能的会话发送
        sessions_to_try = [
            "graphql:GROUP_MESSAGE:all",
            "onebot-v11:GROUP_MESSAGE:all",
            "qq_official:GROUP_MESSAGE:all",
            "telegram:GROUP_MESSAGE:all",
        ]

        sent = False
        for session in sessions_to_try:
            try:
                success = await self.context.send_message(session, chain)
                if success:
                    _logger.info(f'[CronPush] 已推送到 {session}: {message}')
                    sent = True
                    break
            except Exception as e:
                _logger.debug(f"[CronPush] 尝试会话 {session} 失败: {e}")

        if not sent:
            _logger.warning(f"[CronPush] 推送失败，未找到可用会话: {message}")

    async def terminate(self):
        """插件卸载时清理所有定时任务"""
        for job_id in list(self._jobs.keys()):
            try:
                await self.context.cron_manager.delete_job(job_id)
            except Exception:
                pass
        self._jobs.clear()
        _logger.info("[CronPush] 插件已卸载，定时任务已清理")