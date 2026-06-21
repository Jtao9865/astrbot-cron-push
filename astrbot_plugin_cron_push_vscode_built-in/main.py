"""AstrBot 定时推送插件 —— 使用 CronManager + MessageChain + At 组件实现精准 @ 人。

安装方式:
  将整个文件夹放入 AstrBot 的插件目录 (默认 ~/.astrbot/plugins/)，
  然后在 AstrBot 管理面板中启用即可。

指令列表:
  /cron-add <cron表达式> <用户ID> <消息内容>   添加定时推送任务
  /cron-list                                  列出所有定时任务
  /cron-del <任务序号>                        删除指定定时任务
  /cron-push <用户ID> <消息内容>              立即推送一条 @ 消息
  /cron-send <用户ID> <消息内容>              向任意会话发送 @ 消息（需 session）

内置任务说明:
  插件加载时会自动注册内置定时任务。在 CronPushPlugin 类中找到
  ENABLE_BUILTIN_JOBS 和 TASKS 配置块，按 TODO 注释填写即可。
"""

import asyncio
import astrbot.api.message_components as Comp
from astrbot.api.event import filter as event_filter
from astrbot.core.platform import AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api.event import MessageChain
from astrbot.core.message.message_event_result import CommandResult


class CronPushPlugin(Star):
    """定时推送消息并正确 @ 指定用户的 AstrBot 插件。

    核心机制:
      1. 使用 Context.cron_manager.add_basic_job() 注册 APScheduler Cron 任务
      2. 触发时用 MessageChain 构建包含 At(name="", qq=user_id) 的消息链
      3. 通过 Context.send_message(session, chain) 主动推送到目标会话
    """

    # ================================================================ #
    #  【内置定时任务配置】—— 插件加载时自动注册
    #
    #  使用说明:
    #    1. 将 ENABLE_BUILTIN_JOBS 改为 True 以启用内置任务
    #    2. 在 TASKS 列表中填写你的任务，每个任务包含:
    #       - cron:      Cron 表达式 (格式: 分 时 日 月 星期)
    #       - user_id:   目标 QQ 号 / 用户 ID
    #       - message:   要推送的消息内容
    #       - session:   目标会话 (None = 当前触发插件的会话)
    #    3. 可复制模板添加任意数量的任务
    #
    #  Cron 表达式示例:
    #    "0 9 * * *"      -> 每天 9:00 AM
    #    "0 12 * * 1"     -> 每周一 12:00 PM
    #    "0 */2 * * *"    -> 每 2 小时
    #    "@daily"         -> 每天午夜
    #    "0 8,12,18 * * *"-> 每天 8:00/12:00/18:00
    # ================================================================ #

    ENABLE_BUILTIN_JOBS = True  # TODO: 改为 True 以启用内置任务

    TASKS = [
        # --- 任务 1: 每日早安 ---
        # TODO: 将 enabled 改为 True，并填写 user_id 和 message
        {
            "enabled": True,          # <- 改为 True 启用此任务
            "cron": "* * * * *",      # 每天 9:00 AM
            "user_id": "2854203313",      # <- 替换为你的 QQ 号
            "message": "早上好！新的一天开始了",  # <- 替换为你想推送的内容
            "session": None,            # None = 当前会话
        },

        # --- 任务 2: 午间提醒 ---
        # TODO: 将 enabled 改为 True，并填写 user_id 和 message
        {
            "enabled": False,          # <- 改为 True 启用此任务
            "cron": "0 12 * * *",     # 每天 12:00 PM
            "user_id": "1000000",      # <- 替换为你的 QQ 号
            "message": "中午好！记得午休哦",   # <- 替换为你想推送的内容
            "session": None,
        },

        # --- 任务 3: 晚安 ---
        # TODO: 将 enabled 改为 True，并填写 user_id 和 message
        {
            "enabled": False,          # <- 改为 True 启用此任务
            "cron": "0 22 * * *",     # 每天 10:00 PM
            "user_id": "1000000",      # <- 替换为你的 QQ 号
            "message": "晚安，好梦",         # <- 替换为你想推送的内容
            "session": None,
        },

        # --- 复制上面的模板添加更多任务 ---
        # {
        #     "enabled": False,
        #     "cron": "0 8 * * 1-5",    # 工作日 8:00 AM
        #     "user_id": "1000000",
        #     "message": "开工啦！",
        #     "session": None,
        # },
    ]

    def __init__(self, context: Context):
        super().__init__(context)
        # job_index -> {cron, user_id, message, session, job_id}
        self._jobs: dict[int, dict] = {}
        self._next_index = 1

        # 自动注册内置任务
        if self.ENABLE_BUILTIN_JOBS:
            asyncio.create_task(self._register_builtin_jobs())

    async def _register_builtin_jobs(self):
        """插件加载时注册内置定时任务"""
        for task in self.TASKS:
            if not task.get("enabled", False):
                continue

            idx = self._next_index
            self._next_index += 1
            job_name = f"builtin_{idx}"
            session = task["session"]

            self._jobs[idx] = {
                "cron": task["cron"],
                "user_id": task["user_id"],
                "message": task["message"],
                "session": session,
                "job_name": job_name,
            }

            # 定义推送回调
            async def _push_handler(job_idx=idx):
                info = self._jobs.get(job_idx)
                if not info:
                    return
                try:
                    chain = MessageChain()
                    chain.at(name="", qq=info["user_id"])
                    chain.message(info["message"])
                    # 如果有固定 session 则推送，否则记录日志
                    if info["session"]:
                        await self.context.send_message(info["session"], chain)
                    self.context.logger.info(
                        f"[CronPush] 内置任务 #{job_idx} 触发: @{info['user_id']} - {info['message']}"
                    )
                except Exception as e:
                    self.context.logger.error(
                        f"[CronPush] 内置任务 {job_name} 推送失败: {e}"
                    )

            # 注册到 CronManager
            try:
                await self.context.cron_manager.add_basic_job(
                    name=job_name,
                    cron_expression=task["cron"],
                    handler=_push_handler,
                    description=f"内置: @{task['user_id']} - {task['message']}",
                    timezone="Asia/Shanghai",
                    payload={
                        "user_id": task["user_id"],
                        "message": task["message"],
                        "session": session,
                    },
                    enabled=True,
                    persistent=True,
                )
                self.context.logger.info(
                    f"[CronPush] 内置任务已注册 #{idx}: {task['message']}"
                )
            except Exception as e:
                self.context.logger.error(
                    f"[CronPush] 内置任务 #{idx} 注册失败: {e}"
                )

    # ================================================================ #
    #  指令: /cron-add 添加定时推送任务
    # ================================================================ #
    @event_filter.command("cron-add")
    async def cron_add(self, event: AstrMessageEvent):
        # 解析参数: /cron-add <cron> <user_id> <message>
        raw = event.message_str.strip()
        # 去掉命令前缀
        rest = raw[len("/cron-add"):].strip() if raw.startswith("/cron-add") else raw
        parts = rest.split(None, 2)  # max 3 splits: cron, user_id, message
        if len(parts) < 3:
            yield CommandResult().message(
                "用法: /cron-add <cron表达式> <用户ID> <消息内容>\n"
                "示例: /cron-add 0 9 * * * 1000000 早上好！今天天气不错"
            )
            return

        cron_expr = parts[0]
        user_id = parts[1]
        message_text = parts[2]
        session = event.unified_msg_origin

        idx = self._next_index
        self._next_index += 1
        job_name = f"cron_push_{idx}"

        # 保存任务元数据
        self._jobs[idx] = {
            "cron": cron_expr,
            "user_id": user_id,
            "message": message_text,
            "session": session,
            "job_name": job_name,
        }

        # 定义定时触发的回调
        async def _push_handler():
            info = self._jobs.get(idx)
            if not info:
                return
            try:
                # 构建消息链: At(点名) + Plain(文本)
                chain = MessageChain()
                chain.at(name="", qq=info["user_id"])
                chain.message(info["message"])
                # 主动发送到目标会话
                await self.context.send_message(info["session"], chain)
                self.context.logger.info(
                    f"[CronPush] 已推送 @{info['user_id']}: {info['message']}"
                )
            except Exception as e:
                self.context.logger.error(f"[CronPush] 任务 {job_name} 推送失败: {e}")

        # 注册到 CronManager (底层 APScheduler)
        try:
            await self.context.cron_manager.add_basic_job(
                name=job_name,
                cron_expression=cron_expr,
                handler=_push_handler,
                description=f"@{user_id}: {message_text}",
                timezone="Asia/Shanghai",
                payload={
                    "user_id": user_id,
                    "message": message_text,
                    "session": session,
                },
                enabled=True,
                persistent=True,
            )
            yield CommandResult().message(
                f"定时推送已添加 [#{idx}]\n"
                f"   Cron:   {cron_expr}\n"
                f"   目标:   @{user_id}\n"
                f"   内容:   {message_text}"
            )
        except Exception as e:
            yield CommandResult().message(f"添加定时任务失败: {e}")

    # ================================================================ #
    #  指令: /cron-list 列出所有定时任务
    # ================================================================ #
    @event_filter.command("cron-list")
    async def cron_list(self, event: AstrMessageEvent):
        if not self._jobs:
            yield CommandResult().message("当前没有定时任务。使用 /cron-add 添加。")
            return

        lines = ["当前定时任务:"]
        for idx in sorted(self._jobs.keys()):
            info = self._jobs[idx]
            lines.append(
                f"  #{idx}  cron={info['cron']}  @{info['user_id']}  {info['message']}"
            )
        yield CommandResult().message("\n".join(lines))

    # ================================================================ #
    #  指令: /cron-del 删除定时任务
    # ================================================================ #
    @event_filter.command("cron-del")
    async def cron_del(self, event: AstrMessageEvent):
        raw = event.message_str.strip()
        rest = raw[len("/cron-del"):].strip() if raw.startswith("/cron-del") else raw
        parts = rest.split(None, 1)

        if not parts:
            yield CommandResult().message("用法: /cron-del <任务序号>")
            return

        try:
            idx = int(parts[0])
        except ValueError:
            yield CommandResult().message("任务序号必须是数字")
            return

        info = self._jobs.get(idx)
        if not info:
            yield CommandResult().message(f"未找到任务 #{idx}")
            return

        # 从 CronManager 删除
        try:
            await self.context.cron_manager.delete_job(info["job_name"])
        except Exception as e:
            self.context.logger.error(f"[CronPush] 删除任务失败: {e}")

        del self._jobs[idx]
        yield CommandResult().message(f"已删除任务 #{idx}")

    # ================================================================ #
    #  指令: /cron-push 立即推送一条 @ 消息
    # ================================================================ #
    @event_filter.command("cron-push")
    async def cron_push(self, event: AstrMessageEvent):
        raw = event.message_str.strip()
        rest = raw[len("/cron-push"):].strip() if raw.startswith("/cron-push") else raw
        parts = rest.split(None, 1)

        if len(parts) < 2:
            yield CommandResult().message("用法: /cron-push <用户ID> <消息内容>")
            return

        user_id = parts[0]
        message_text = parts[1]
        session = event.unified_msg_origin

        # 构建消息链并立即发送
        chain = MessageChain()
        chain.at(name="", qq=user_id)
        chain.message(message_text)

        success = await self.context.send_message(session, chain)
        if success:
            yield CommandResult().message(f"已推送 @{user_id}: {message_text}")
        else:
            yield CommandResult().message("推送失败: 无法找到匹配的平台会话")

    # ================================================================ #
    #  指令: /cron-send 向任意会话发送 @ 消息
    # ================================================================ #
    @event_filter.command("cron-send")
    async def cron_send(self, event: AstrMessageEvent):
        """向指定的 session 发送 @ 消息，参数: /cron-send <session类型> <用户ID> <消息内容>

        session 类型可选: group / private
        示例: /cron-send group 123456 你好
        """
        raw = event.message_str.strip()
        rest = raw[len("/cron-send"):].strip() if raw.startswith("/cron-send") else raw
        parts = rest.split(None, 2)

        if len(parts) < 3:
            yield CommandResult().message(
                "用法: /cron-send <group|private> <群号/QQ号> <消息内容>\n"
                "示例: /cron-send group 123456 大家好"
            )
            return

        session_type = parts[0]
        target_id = parts[1]
        message_text = parts[2]

        if session_type not in ("group", "private"):
            yield CommandResult().message("session 类型必须是 group 或 private")
            return

        # 构造 session 字符串
        platform_name = event.platform_meta.id
        session_str = f"{platform_name}:{session_type.upper()}_MESSAGE:{target_id}"

        chain = MessageChain()
        chain.at(name="", qq=target_id)
        chain.message(message_text)

        try:
            success = await self.context.send_message(session_str, chain)
            if success:
                yield CommandResult().message(f"已向 @{target_id} 发送: {message_text}")
            else:
                yield CommandResult().message("推送失败: 找不到该平台会话")
        except Exception as e:
            yield CommandResult().message(f"发送失败: {e}")

    # ================================================================ #
    #  插件生命周期
    # ================================================================ #
    async def terminate(self):
        """插件卸载时清理所有定时任务"""
        for idx, info in list(self._jobs.items()):
            try:
                await self.context.cron_manager.delete_job(info["job_name"])
            except Exception:
                pass
        self._jobs.clear()
        self.context.logger.info("[CronPush] 插件已卸载，定时任务已清理")