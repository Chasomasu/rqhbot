"""
rqhspeech 插件 - 群聊发言统计管理程序

版本：6.0.0
特性：
1. 修复group_id类型不一致问题（统一转为字符串）
2. 修复设置用户名乱码键名bug
3. 统一命令格式（查询发言）
4. 封装公共函数（获取用户名、加载/保存数据）
5. 优化周切换函数参数
6. 使用logging模块替代手写日志
7. 代码结构拆分，更易维护
8. 添加管理员权限检查
9. 管理器全局单例，避免重复实例化
10. 命令处理函数独立到 command_handler.py
11. 支持按年分层的目录结构
12. 支持操作员权限管理
13. 签到功能迁入，签到数据以 JSON 文件存放于插件 data/checkin 目录
14. 存储层改为纯 JSON，移除 SQLite 与 sdk 中的业务实现
"""

import logging

from sdk.pluginsystem import PluginBase, filter_registry
from sdk.core.events import GroupMessageEvent, PrivateMessageEvent
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

from .speech_config import SpeechConfig
from .data_manager import (
    user_manager, log_manager,
    load_user_data, get_display_username,
    user_exists, check_and_handle_week_transition
)
from .archive_manager import DailyArchiver, auto_archive
from .command_handler import CommandHandler


class RqhSpeechPlugin(PluginBase):
    """rqhspeech 发言统计插件"""

    def __init__(self) -> None:
        super().__init__()
        self.name = "rqhspeech"
        self.version = "6.0.0"
        self.description = "群聊发言统计与每日签到"
        self.author = "rqh"
        # 管理器全局单例，避免重复实例化
        self.user_mgr = user_manager
        self.log_mgr = log_manager
        self.cmd_handler = None  # 在 on_load 中初始化

    async def on_load(self, api, event_bus, plugin_dir=None):
        """插件加载时调用"""
        await super().on_load(api, event_bus, plugin_dir)
        # 初始化命令处理器（需要 api）
        self.cmd_handler = CommandHandler(self.user_mgr, self.log_mgr, self.api)
            
        # 显示当前模式
        if SpeechConfig.USE_WHITELIST_MODE:
            logger.info(f"当前模式：白名单模式（仅允许 {len(SpeechConfig.ALLOWED_GROUPS)} 个群）")
        else:
            logger.info("当前模式：所有群可用")

    # ========== 核心消息处理 ==========

    @filter_registry.group_server()
    async def handle_message(self, event: GroupMessageEvent):
        """
        处理群消息
        1. group_id转为字符串
        2. 自动注册用户
        3. 更新发言统计
        """
        # 获取消息内容
        m = event.message.plain_text.strip()

        # group_id转为字符串
        group_id = str(event.group_id)
        user_id = str(event.user_id)
        username = event.user_name

        # 检查是否在允许群聊中
        if not SpeechConfig.is_allowed_group(group_id):
            return False

        # 检查用户是否存在，不存在则自动注册
        exists = user_exists(user_id)

        if not exists:
            # 自动注册新用户
            user_data = self.user_mgr.create_user(user_id, username)
            from .data_manager import save_user_data
            save_user_data(user_id, user_data)
            logger.info(f"自动为新用户 {username}({user_id}) 创建用户文件")
            exists = True

        # 更新发言统计
        if exists:
            self.user_mgr.update_user_message(user_id, group_id)

        # ========== 命令处理 ==========

        # 注册命令
        if m == "注册":
            return await self.cmd_handler.handle_register(event, user_id, username)

        # 签到
        elif m in {"签到", "每日签到", "打卡"}:
            return await self.cmd_handler.handle_checkin(event, user_id, username)

        # 发言日榜
        elif m == "发言日榜":
            return await self.cmd_handler.handle_daily_rank(event, group_id)

        # 历史日榜
        elif m.startswith("历史日榜"):
            return await self.cmd_handler.handle_history_rank(event, group_id, m)

        # 我的发言
        elif m == "我的发言":
            return await self.cmd_handler.handle_my_stats(event, user_id, group_id)

        # 发言周榜
        elif m == "发言周榜":
            return await self.cmd_handler.handle_weekly_rank(event, group_id)
        
        # 历史周榜
        elif m.startswith("历史周榜"):
            return await self.cmd_handler.handle_history_weekly_rank(event, group_id, m)
        
        # 发言月榜
        elif m == "发言月榜":
            return await self.cmd_handler.handle_monthly_rank(event, group_id)
        
        # 历史月榜
        elif m.startswith("历史月榜"):
            return await self.cmd_handler.handle_history_monthly_rank(event, group_id, m)
        
        # 发言季榜
        elif m == "发言季榜":
            return await self.cmd_handler.handle_seasonal_rank(event, group_id)
        
        # 发言年榜
        elif m == "发言年榜":
            return await self.cmd_handler.handle_yearly_rank(event, group_id)
        
        # 历史年榜
        elif m.startswith("历史年榜"):
            return await self.cmd_handler.handle_history_yearly_rank(event, group_id, m)

        # 设置用户名
        elif m.startswith("设置用户名"):
            return await self.cmd_handler.handle_set_username(event, user_id, m)

        # 查询发言
        elif m.startswith("查询发言") or m.startswith("查发言"):
            return await self.cmd_handler.handle_query_user(event, group_id, m)

        # 管理员命令
        elif m.startswith("删除用户"):
            return await self.cmd_handler.handle_delete_user(event, m)
        elif m == "自动归档":
            return await self.cmd_handler.handle_auto_archive(event)
        
        # 群管理命令
        elif m.startswith("加白名单") or m.startswith("加入白名单"):
            return await self.cmd_handler.handle_add_group(event, m)
        elif m.startswith("移除白名单") or m.startswith("移出白名单"):
            return await self.cmd_handler.handle_remove_group(event, m)
        elif m == "查看白名单":
            return await self.cmd_handler.handle_view_whitelist(event)
        elif m.startswith("切换白名单模式"):
            return await self.cmd_handler.handle_toggle_whitelist_mode(event)
        
        # 权限管理命令（仅Admin可用）- 添加"发言"前缀避免与其他插件冲突
        elif m.startswith("发言添加管理员"):
            return await self.cmd_handler.handle_add_admin(event, m)
        elif m.startswith("发言移除管理员"):
            return await self.cmd_handler.handle_remove_admin(event, m)
        elif m == "发言管理员名单":
            return await self.cmd_handler.handle_view_admins(event)
        elif m.startswith("发言添加操作员"):
            return await self.cmd_handler.handle_add_operator(event, m)
        elif m.startswith("发言移除操作员"):
            return await self.cmd_handler.handle_remove_operator(event, m)
        elif m == "发言操作员名单":
            return await self.cmd_handler.handle_view_operators(event)

        return True

    @filter_registry.private_server(regex=r"^(签到|每日签到|打卡)$")
    async def handle_private_checkin(self, event: PrivateMessageEvent):
        """私聊签到（签到数据与群聊共用统一用户库）"""
        user_id = str(event.user_id)
        username = event.user_name or f"用户{user_id[-4:]}"
        return await self.cmd_handler.handle_checkin(event, user_id, username)