# ==================== SDK 适配入口 ====================
from __future__ import annotations

import logging
import re
import random

from sdk.core.events import GroupMessageEvent
from sdk.pluginsystem import PluginBase, filter_registry

# ==================== 数据层导入 ====================
from .answer_manager import answer_manager, hmd, gly

logger = logging.getLogger("rqhwenda")


# ==================== 帮助文本 ====================

HELP_TEXT = """【问答插件使用说明】
• 精确问问题内容答答案内容 - 添加精确问答（管理员）
• 模糊问问题内容答答案内容 - 添加模糊问答（管理员）
• 修改原问题答新答案 - 修改问答（管理员）
• 删问答问题内容 - 删除问答（检查两库都删除）（管理员）
• 列出所有问答 - 查看全部问答（合并精确库和模糊库）（非黑名单用户）
• 列出部分问答 - 随机查看部分问答（合并两库后随机）（非黑名单用户）
• 清空所有问答 - 清空全部问答（清空两库）（管理员）
• 问答帮助 - 显示此帮助信息"""


# ==================== 命令前缀集合 ====================

_COMMAND_PREFIXES = ("精确问", "模糊问", "修改", "删问答", "列出", "清空", "问答帮助")


# ==================== 插件类 ====================

class RqhWendaPlugin(PluginBase):
    """rqhwenda 问答插件 —— 群内关键字自动问答

    支持两类匹配：
      - 精确匹配：消息内容与问题完全一致时回复
      - 模糊匹配：消息包含问题时回复（按相似度优先）
    """

    def __init__(self) -> None:
        super().__init__()
        self.name = "rqhwenda"
        self.version = "3.0.0"
        self.author = "Rqh"
        self.description = "群内关键字自动问答插件，支持精确匹配和模糊匹配"

    # ==================== 生命周期 ====================

    async def on_load(self, api, event_bus, plugin_dir=None) -> None:
        """插件加载回调"""
        await super().on_load(api, event_bus, plugin_dir)
        logger.info(f"已加载 v{self.version}")
        # 启动后台定时保存
        self.create_task(self._auto_save_loop())

    async def _auto_save_loop(self) -> None:
        """后台定时保存 —— 每 30 秒检查脏标记"""
        while True:
            await self.delay(30)
            try:
                answer_manager.save_if_dirty()
            except Exception as e:
                logger.error(f"自动保存问答数据失败: {e}")

    async def on_unload(self) -> None:
        """卸载时停止后台任务并最终落盘

        增删改只设置脏标记，依赖 30 秒一次的定时保存；若不在此处补一次保存，
        在下个周期前退出或热重载，已提示成功的修改会丢失、已删除的问答会复活。
        """
        await super().on_unload()
        try:
            if not answer_manager.save_if_dirty():
                logger.error("卸载时保存问答数据失败，内存中的修改可能未落盘")
        except Exception as e:
            logger.error(f"卸载时保存问答数据出错: {e}", exc_info=True)

    # ==================== 群消息处理（统一入口） ====================

    @filter_registry.group_server
    async def _on_group_message(self, event: GroupMessageEvent) -> None:
        """群消息统一路由

        命令类消息走 if-else 分支，普通消息走问答查询逻辑。
        """
        text = event.message.plain_text.strip()
        group_id = event.group_id
        uid = str(event.user_id)

        # 非命令消息 → 走问答查询
        if not text.startswith(_COMMAND_PREFIXES):
            if uid in hmd:
                return
            # 先精确匹配，再模糊匹配
            answer = answer_manager.search_precise(text)
            if answer:
                await self.api.send_group_message(group_id, answer)
                return
            answer = answer_manager.search_fuzzy(text)
            if answer:
                await self.api.send_group_message(group_id, answer)
            return

        # ---- 命令分支 ----

        # 帮助
        if text == "问答帮助" and uid in gly:
            await self.api.send_group_message(group_id, HELP_TEXT)
            return

        # 添加模糊问答
        if text.startswith("模糊问"):
            await self._add_fuzzy_answer(text, group_id, uid)
            return

        # 添加精确问答
        if text.startswith("精确问"):
            await self._add_precise_answer(text, group_id, uid)
            return

        # 修改问答
        if text.startswith("修改"):
            await self._update_answer(text, group_id, uid)
            return

        # 删除问答
        if text.startswith("删问答"):
            await self._delete_answer(text, group_id, uid)
            return

        # 列出所有问答
        if text.startswith("列出所有问答"):
            await self._list_all_answers(group_id, uid)
            return

        # 列出部分问答
        if text.startswith("列出部分问答"):
            await self._list_random_answers(group_id, uid)
            return

        # 清空所有问答
        if text.startswith("清空所有问答"):
            await self._clear_all_answers(group_id, uid)
            return

    # ==================== 命令实现 ====================

    async def _add_fuzzy_answer(self, text: str, group_id: int, uid: str) -> None:
        """模糊问答添加"""
        if uid in hmd:
            await self.api.send_group_message(group_id, "黑名单不能添加问答对")
            return
        if uid not in gly:
            return
        m = re.match(r"^模糊问 (.+?) 答 (.+)$", text, re.DOTALL)
        if m:
            q, a = m.groups()
            if answer_manager.add_normal_answer(q, a):
                await self.api.send_group_message(
                    group_id, f"ฅ^•ω•^ฅ 问答对添加成功喵～\n问：{q.strip()}\n答：{a.strip()}"
                )
            else:
                await self.api.send_group_message(
                    group_id, "问答保存失败，请稍后重试喵～"
                )
        else:
            await self.api.send_group_message(
                group_id, "格式错误，正确格式：模糊问 问题内容 答 答案内容"
            )

    async def _add_precise_answer(self, text: str, group_id: int, uid: str) -> None:
        """精确问答添加"""
        if uid in hmd:
            await self.api.send_group_message(group_id, "黑名单不能添加问答对")
            return
        if uid not in gly:
            return
        m = re.match(r"^精确问 (.+?) 答 (.+)$", text, re.DOTALL)
        if m:
            q, a = m.groups()
            if answer_manager.add_precise_answer(q, a):
                await self.api.send_group_message(
                    group_id, f"ฅ^•ω•^ฅ 精确问答对添加成功喵～\n精确问：{q.strip()}\n答：{a.strip()}"
                )
            else:
                await self.api.send_group_message(
                    group_id, "问答保存失败，请稍后重试喵～"
                )
        else:
            await self.api.send_group_message(
                group_id, "格式错误，正确格式：精确问 问题内容 答 答案内容"
            )

    async def _update_answer(self, text: str, group_id: int, uid: str) -> None:
        """修改问答"""
        if uid not in gly:
            return
        parts = text[2:].split("答", 1)
        if len(parts) == 2:
            old_q, new_a = parts[0].strip(), parts[1].strip()
            if not answer_manager.has_answer(old_q):
                await self.api.send_group_message(
                    group_id, f"没有找到问题『{old_q}』喵～"
                )
            elif not answer_manager.update_answer(old_q, new_a):
                await self.api.send_group_message(
                    group_id, "问答修改保存失败，请稍后重试喵～"
                )
            else:
                await self.api.send_group_message(
                    group_id, f"ฅ^•ω•^ฅ 问答修改成功喵～\n问：{old_q}\n新回答：{new_a}"
                )

    async def _delete_answer(self, text: str, group_id: int, uid: str) -> None:
        """删除问答"""
        if uid not in gly:
            await self.api.send_group_message(group_id, "你没有权限删除问答")
            return
        question = text[3:].strip()
        if not question:
            await self.api.send_group_message(
                group_id, "请指定要删除的问题，格式：删问答+问题内容"
            )
            return
        if not answer_manager.has_answer(question):
            await self.api.send_group_message(group_id, "未找到该问题")
            return
        if answer_manager.delete_answer(question):
            await self.api.send_group_message(
                group_id, f"问答已删除喵～\n问：{question}"
            )
        else:
            await self.api.send_group_message(group_id, "问答删除保存失败，请稍后重试喵～")

    async def _list_all_answers(self, group_id: int, uid: str) -> None:
        """列出所有问答"""
        if uid in hmd:
            await self.api.send_group_message(group_id, "你没有权限查看问答")
            return
        if not answer_manager.precise_data and not answer_manager.fuzzy_data:
            await self.api.send_group_message(group_id, "还没有任何问答记录")
            return

        parts: list[str] = []
        if answer_manager.precise_data:
            parts.append("【精确问答】")
            for q, a in answer_manager.precise_data.items():
                parts.append(f"[精确] 问：{q}\n答：{a}")
        if answer_manager.fuzzy_data:
            if answer_manager.precise_data:
                parts.append("")
            parts.append("【模糊问答】")
            for q, a in answer_manager.fuzzy_data.items():
                parts.append(f"[模糊] 问：{q}\n答：{a}")

        total = len(answer_manager.precise_data) + len(answer_manager.fuzzy_data)
        await self.api.send_group_message(
            group_id, f"当前问答列表（共{total}条）：\n" + "\n".join(parts)
        )

    async def _list_random_answers(self, group_id: int, uid: str) -> None:
        """随机列出部分问答"""
        if uid in hmd:
            await self.api.send_group_message(group_id, "你没有权限查看问答")
            return
        with answer_manager.lock:
            data = [("精确", q, a) for q, a in answer_manager.precise_data.items()]
            data.extend(("模糊", q, a) for q, a in answer_manager.fuzzy_data.items())
        if not data:
            await self.api.send_group_message(group_id, "还没有任何问答记录")
            return
        sample = random.sample(data, min(10, len(data)))
        lines = [f"[{kind}] 问：{q}\n答：{a}" for kind, q, a in sample]
        await self.api.send_group_message(group_id, f"随机选取的问答：\n" + "\n".join(lines))

    async def _clear_all_answers(self, group_id: int, uid: str) -> None:
        """清空所有问答"""
        if uid in hmd:
            await self.api.send_group_message(group_id, "你没有权限清空问答")
            return
        if uid not in gly:
            return
        if answer_manager.clear_all_answers():
            await self.api.send_group_message(group_id, "问答已清空")
        else:
            await self.api.send_group_message(group_id, "清空问答失败")
