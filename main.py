import asyncio
import logging
import astrbot.api.message_components as Comp
from astrbot.core.platform import AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api.event import MessageChain
from astrbot.core.platform.astr_message_event import MessageSesion
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
        # 缓存平台 ID 列表
        self._platform_ids: list[str] = []
        # 是否已完成懒加载初始化
        self._lazy_initialized = False

        if self.ENABLE_BUILTIN_JOBS:
            _logger.info("[CronPush] 插件初始化完成，等待 OnPluginLoadedEvent 触发延迟注册")

    async def initialize(self):
        """AstrBot 调用此方法进行插件初始化。
        
        注意：此方法在平台适配器初始化之前就被调用，因此不能在这里
        访问 platform_insts。改为注册 OnPluginLoadedEvent 监听器，
        在平台就绪后再执行实际的任务注册。
        """
        await self._register_session_listener()

    async def _lazy_register_tasks(self):
        """在平台适配器就绪后，延迟注册定时任务。"""
        if self._lazy_initialized:
            return
        self._lazy_initialized = True

        # 缓存平台 ID
        self._platform_ids = [p.meta().id for p in self.context.platform_manager.platform_insts]
        _logger.info(f"[CronPush] 已发现 {len(self._platform_ids)} 个平台: {self._platform_ids}")

        await self._register_builtin_tasks()
        _logger.info("[CronPush] 延迟初始化完成，定时任务已注册")

    async def _register_session_listener(self):
        """注册一个通用的消息接收监听器，用于收集已知会话。"""
        from astrbot.core.star.register.star_handler import (
            get_handler_or_create,
        )
        from astrbot.core.star.star_handler import EventType

        # 先尝试延迟注册任务（如果平台已经就绪）
        async def session_capture_handler(event: AstrMessageEvent):
            """捕获所有收到的消息，记录其 unified_msg_origin 到已知会话列表。"""
            # 首次收到消息时，尝试延迟初始化
            await self._lazy_register_tasks()

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
            _logger.warning("[CronPush] 暂无已知会话，尝试通过平台直接发送")
            sent = await self._fallback_push(chain, message)

        if not sent:
            _logger.warning(
                f"[CronPush] 推送失败，未找到可用会话。"
                f"已知会话数: {len(self._known_sessions)}, "
                f"当前平台数: {len(self._platform_ids)}"
            )

    async def _fallback_push(self, chain: MessageChain, message: str) -> bool:
        """当没有已知会话时，尝试向每个已注册平台发送广播消息。"""
        sent = False

        for platform_id in self._platform_ids:
            platform = self.context.get_platform_inst(platform_id)
            if not platform:
                _logger.debug(f"[CronPush] 未找到平台实例: {platform_id}")
                continue

            # 尝试向 FriendMessage 类型发送（私聊广播）
            try:
                if hasattr(platform, 'send_by_session'):
                    session = MessageSesion(
                        platform_name=platform_id,
                        message_type=MessageType.FRIEND_MESSAGE,
                        session_id="",
                    )
                    await platform.send_by_session(session, chain)
                    _logger.info(
                        f'[CronPush] 已通过平台 [{platform_id}] FRIEND_MESSAGE 推送: {message}'
                    )
                    sent = True
            except Exception as e:
                _logger.debug(
                    f"[CronPush] 通过平台 [{platform_id}] FRIEND_MESSAGE 推送失败: {e}"
                )

            # 再尝试 GROUP_MESSAGE
            if not sent and hasattr(platform, 'send_by_session'):
                try:
                    session = MessageSesion(
                        platform_name=platform_id,
                        message_type=MessageType.GROUP_MESSAGE,
                        session_id="",
                    )
                    await platform.send_by_session(session, chain)
                    _logger.info(
                        f'[CronPush] 已通过平台 [{platform_id}] GROUP_MESSAGE 推送: {message}'
                    )
                    sent = True
                except Exception as e:
                    _logger.debug(
                        f"[CronPush] 通过平台 [{platform_id}] GROUP_MESSAGE 推送失败: {e}"
                    )

        return sent

    async def terminate(self):
        """插件卸载时清理所有定时任务"""
        for job_id in list(self._jobs.keys()):
            try:
                await self.context.cron_manager.delete_job(job_id)
            except Exception:
                pass
        self._jobs.clear()
        _logger.info("[CronPush] 插件已卸载，定时任务已清理")