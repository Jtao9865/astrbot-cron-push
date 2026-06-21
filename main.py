"""AstrBot 定时推送插件 —— 全内置模式，无需群内设置。

所有群号、用户、定时任务都已硬编码在下方 CONFIG 区域。
你只需要把占位符换成你自己的 QQ 群号即可。
"""

import asyncio
import astrbot.api.message_components as Comp
from astrbot.api.event import filter as event_filter
from astrbot.core.platform import AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api.event import MessageChain
from astrbot.core.message.message_event_result import CommandResult

# ================================================================ #
#  【硬编码配置区】—— 在这里填写你的群号和用户
# ================================================================ #

# 目标群列表
# 格式: { "group_id": 群号(int), "group_name": 群名称, "users": [推送的QQ号列表(str)] }
GROUPS = [
    # --- 群1: 在此修改为你自己的群号 ---
    {
        "group_id": 1234567890,       # <-- 替换为你的实际群号 (int)
        "group_name": "我的主力群",
        "users": ["2854203313"],       # <-- 替换为要 @ 的用户QQ号 (str)
    },
    # --- 群2: 复制下面的块添加更多群 ---
    # {
    #     "group_id": 0,              # <-- 替换为你的实际群号
    #     "group_name": "备用群",
    #     "users": ["1000000", "2000000"],  # <-- 替换为要 @ 的用户QQ号
    # },
]

# ================================================================ #
#  【内置定时任务】—— 所有 session 都指向硬编码的群
#  启用/禁用: 把 enabled 改为 True / False
#  cron 格式: 分 时 日 月 星期 (标准5位)
# ================================================================ #
TASKS = [
    {
        "enabled": True,
        "cron": "* * * * *",           # 每天 9:00 AM
        "group_id": GROUPS[0]["2156063317"],
        "users": GROUPS[0]["2854203313"],
        "message": "早上好！新的一天开始了",
    },
    {
        "enabled": False,
        "cron": "0 12 * * *",          # 每天 12:00 PM
        "group_id": GROUPS[0]["group_id"],
        "users": GROUPS[0]["users"],
        "message": "中午好！记得午休哦",
    },
    {
        "enabled": False,
        "cron": "0 22 * * *",          # 每天 10:00 PM
        "group_id": GROUPS[0]["group_id"],
        "users": GROUPS[0]["users"],
        "message": "晚安，好梦",
    },
]


class CronPushPlugin(Star):
    """定时推送消息到硬编码群聊的 AstrBot 插件 (全内置模式)。"""

    ENABLE_BUILTIN_JOBS = True

    def __init__(self, context: Context):
        super().__init__(context)
        self._jobs: dict[int, dict] = {}
        self._next_index = 1
        self._platform_name = "graphql"  # 写死平台名

        # 插件加载时自动注册内置定时任务
        if self.ENABLE_BUILTIN_JOBS:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._register_builtin_tasks())
                loop.close()
            except Exception as e:
                self.context.logger.error(f"[CronPush] 注册内置任务失败: {e}")

    async def _register_builtin_tasks(self):
        """注册所有内置定时任务"""
        for i, task in enumerate(TASKS):
            if not task.get("enabled"):
                continue
            idx = self._next_index
            self._next_index += 1

            group_id = task["group_id"]
            session = f"{self._platform_name}:GROUP_MESSAGE:{group_id}"

            job = {
                "index": idx,
                "cron": task["cron"],
                "group_id": group_id,
                "users": task["users"],
                "message": task["message"],
                "session": session,
                "job_name": f"builtin_{i}",
            }
            self._jobs[idx] = job

            try:
                self.context.cron_manager.add_basic_job(
                    job["job_name"],
                    task["cron"],
                    self._push_task,
                    args=[job],
                    replace_existing=True,
                )
                self.context.logger.info(
                    f"[CronPush] 已注册内置任务 #{idx}: {task['message']} "
                    f"(群 {group_id}, cron={task['cron']})"
                )
            except Exception as e:
                self.context.logger.error(f"[CronPush] 注册内置任务失败: {e}")

    async def _push_task(self, job: dict):
        """执行推送：向指定群 @ 指定用户"""
        session = job["session"]
        users = job["users"]
        message = job["message"]

        chain = MessageChain()
        for uid in users:
            chain.append(Comp.At(qq=int(uid), name=f"@{uid}"))
        chain.append(Comp.Text(message))

        try:
            success = await self.context.send_message(session, chain)
            if success:
                self.context.logger.info(
                    f"[CronPush] 已推送到群 {job['group_id']}: {message}"
                )
            else:
                self.context.logger.warning(
                    f"[CronPush] 推送失败(找不到会话): 群 {job['group_id']}"
                )
        except Exception as e:
            self.context.logger.error(f"[CronPush] 推送异常: {e}")

    # ================================================================ #
    #  【用户指令】—— 以下命令可选保留
    #  如果你希望完全内置、不需要在群里输入指令，可以把下面三个
    #  @event_filter.command 装饰器及对应方法全部注释掉或删除。
    # ================================================================ #

    # @event_filter.command("cron-list")
    # async def cron_list(self, event: AstrMessageEvent):
    #     if not self._jobs:
    #         yield CommandResult().message("暂无定时任务。")
    #         return
    #     lines = []
    #     for idx, info in self._jobs.items():
    #         lines.append(
    #             f"#{idx} [{info['cron']}] 群:{info['group_id']} "
    #             f"@{info['users']} | {info['message']}"
    #         )
    #     yield CommandResult().message("\n".join(lines))

    # @event_filter.command("cron-del")
    # async def cron_del(self, event: AstrMessageEvent):
    #     raw = event.message_str.strip()
    #     rest = raw[len("/cron-del"):].strip() if raw.startswith("/cron-del") else raw
    #     parts = rest.split(None, 1)
    #     if not parts:
    #         yield CommandResult().message("用法: /cron-del <任务序号>")
    #         return
    #     try:
    #         idx = int(parts[0])
    #     except ValueError:
    #         yield CommandResult().message("任务序号必须是数字")
    #         return
    #     info = self._jobs.get(idx)
    #     if not info:
    #         yield CommandResult().message(f"未找到任务 #{idx}")
    #         return
    #     try:
    #         await self.context.cron_manager.delete_job(info["job_name"])
    #     except Exception as e:
    #         self.context.logger.error(f"[CronPush] 删除任务失败: {e}")
    #     del self._jobs[idx]
    #     yield CommandResult().message(f"已删除任务 #{idx}")

    # @event_filter.command("cron-push")
    # async def cron_push(self, event: AstrMessageEvent):
    #     raw = event.message_str.strip()
    #     rest = raw[len("/cron-push"):].strip() if raw.startswith("/cron-push") else raw
    #     parts = rest.split(None, 1)
    #     if len(parts) < 2:
    #         yield CommandResult().message("用法: /cron-push <用户ID> <消息内容>")
    #         return
    #     user_id = parts[0]
    #     message_text = parts[1]
    #     session = event.unified_msg_origin
    #     chain = MessageChain()
    #     chain.append(Comp.At(qq=int(user_id), name=f"@{user_id}"))
    #     chain.append(Comp.Text(message_text))
    #     success = await self.context.send_message(session, chain)
    #     if success:
    #         yield CommandResult().message(f"已推送 @{user_id}: {message_text}")
    #     else:
    #         yield CommandResult().message("推送失败: 无法找到匹配的平台会话")

    async def terminate(self):
        for idx, info in list(self._jobs.items()):
            try:
                await self.context.cron_manager.delete_job(info["job_name"])
            except Exception:
                pass
        self._jobs.clear()
        self.context.logger.info("[CronPush] 插件已卸载，定时任务已清理")
