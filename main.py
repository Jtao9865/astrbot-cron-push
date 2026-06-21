"""AstrBot 定时推送插件 —— 全内置模式，无条件推送。

所有任务在插件加载时自动注册，到点自动发送。
不依赖群号，遍历所有已连接的平台发送消息。
"""

import asyncio
import logging
import astrbot.api.message_components as Comp
from astrbot.core.platform import AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api.event import MessageChain
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType

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
        "cron": "* * * * *",     
        "message": "早上好！新的一天开始了",
    },
    {
        "enabled": False,
        "cron": "0 12 * * *",          
        "message": "中午好！记得午休哦",
    },
    {
        "enabled": False,
        "cron": "0 22 * * *",          
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
        # 记录已知的会话列表 (platform_name:message_type:session_id)
        self._known_sessions: set[str] = set()

        if self.ENABLE_BUILTIN_JOBS:
            _logger.info("[CronPush] 插件初始化完成，等待 initialize() 注册任务")

    async def initialize(self):
        """AstrBot 调用此方法进行插件初始化，此时可以安全访问事件循环。"""
        try:
            await self._register_builtin_tasks()
            # 注册一个事件监听器，用于捕获 incoming 消息的 session
            await self._register_session_listener()
        except Exception as e:
            _logger.error(f"[CronPush] 注册内置任务失败: {e}")

    async def _register_session_listener(self):
        """注册一个通用的消息接收监听器，用于收集已知会话。"""
        from astrbot.core.star.register.star_handler import (
            get_handler_or_create,
        )
        from astrbot.core.star.star_handler import EventType

        async def session_capture_handler(event: AstrMessageEvent):
            """捕获所有收到的消息，记录其 unified_msg_origin 到已知会话列表。"""
            umo = event.unified_msg_origin
            if umo:
                self._known_sessions.add(umo)
                _logger.debug(f"[CronPush] 捕获到会话: {umo}")

        get_handler_or_create(
            session_capture_handler,
            EventType.AdapterMessageEvent,
        )
        _logger.info("[CronPush] 已注册会话监听器")

    async def _register_builtin_tasks(self):
        """注册所有内置定时任务"""
        for i, task in enumerate(TASKS):
            if not task.get("enabled"):
                continue

            idx = self._next_index
            self._next_index += 1
            job_id = f"builtin_{i}"

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
        """执行推送：遍历所有已知会话发送消息"""
        if payload is None:
            payload = {}

        message = payload.get("message", "")

        chain = MessageChain()
        chain.chain.append(Comp.Plain(message))

        sent = False

        # 优先使用已捕获的已知会话
        if self._known_sessions:
            for session_str in sorted(self._known_sessions):
                try:
                    success = await self.context.send_message(session_str, chain)
                    if success:
                        _logger.info(
                            f'[CronPush] 已通过会话 [{session_str}] 推送: {message}'
                        )
                        sent = True
                    else:
                        _logger.debug(
                            f"[CronPush] 会话 [{session_str}] 推送返回 False，跳过"
                        )
                except Exception as e:
                    _logger.debug(
                        f"[CronPush] 通过会话 [{session_str}] 推送失败: {e}"
                    )
        else:
            # 没有已知会话时，尝试遍历所有平台
            for platform in self.context.platform_manager.platform_insts:
                meta = platform.meta()
                platform_id = meta.id
                platform_name = meta.name

                for msg_type in ("GroupMessage", "FriendMessage"):
                    try:
                        session = MessageSession(
                            platform_name=platform_id,
                            message_type=MessageType(msg_type),
                            session_id="",
                        )
                        success = await self.context.send_message(str(session), chain)
                        if success:
                            _logger.info(
                                f'[CronPush] 已通过 {platform_id}({platform_name}) '
                                f'[{msg_type}] 推送: {message}'
                            )
                            sent = True
                            break
                    except Exception as e:
                        _logger.debug(
                            f"[CronPush] 通过 {platform_id}[{msg_type}] 推送失败: {e}"
                        )

                if sent:
                    break

        if not sent:
            _logger.warning(
                f"[CronPush] 推送失败，未找到可用会话。"
                f"已知会话数: {len(self._known_sessions)}, "
                f"当前平台数: {len(self.context.platform_manager.platform_insts)}"
            )

    async def terminate(self):
        """插件卸载时清理所有定时任务"""
        for job_id in list(self._jobs.keys()):
            try:
                await self.context.cron_manager.delete_job(job_id)
            except Exception:
                pass
        self._jobs.clear()
        _logger.info("[CronPush] 插件已卸载，定时任务已清理")