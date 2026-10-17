"""
命令处理器模块 - 将所有命令处理函数独立出来
提高代码可维护性和模块化程度
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple
from sdk.core.events import GroupMessageEvent

from .speech_config import SpeechConfig
from .data_manager import (
    user_manager, log_manager,
    load_user_data, get_display_username,
    user_exists, check_and_handle_week_transition
)


class CommandHandler:
    """命令处理器类 - 封装所有命令处理逻辑"""
    
    def __init__(self, user_mgr, log_mgr, api=None):
        self.user_mgr = user_mgr
        self.log_mgr = log_mgr
        self.api = api
    
    async def _reply(self, event: GroupMessageEvent, content: str) -> None:
        """回复消息（根据事件类型自动选择发送方式）"""
        if self.api is None:
            return
        group_id = getattr(event, "group_id", None)
        if group_id is not None:
            await self.api.post_group_message(int(group_id), content)
            return
        user_id = getattr(event, "user_id", None)
        if user_id is not None:
            await self.api.post_private_message(int(user_id), content)

    @staticmethod
    def _format_ranking(rankings, title: str, top_n: int) -> str:
        """格式化排行榜文本（奖牌 + 用户名 + 发言数）"""
        text = f"{title}\n\n"
        for i, (uid, count) in enumerate(rankings[:top_n], 1):
            user_data = load_user_data(uid)
            username = get_display_username(user_data, uid) if user_data else uid
            if i == 1:
                medal = "🥇"
            elif i == 2:
                medal = "🥈"
            elif i == 3:
                medal = "🥉"
            else:
                medal = f"{i:2d}."
            text += f"{medal} [{username}]: {count}条\n"
        return text

    async def handle_register(self, event: GroupMessageEvent, user_id: str, username: str) -> bool:
        """处理注册命令"""
        if user_exists(user_id):
            await self._reply(event, "❌ 用户已注册")
            return True

        user_data = self.user_mgr.create_user(user_id, username)
        from .data_manager import save_user_data
        save_user_data(user_id, user_data)

        await self._reply(event, f"✅ 用户 {username} ({user_id}) 已注册")
        return True

    async def handle_checkin(self, event: GroupMessageEvent, user_id: str, username: str) -> bool:
        """处理签到命令（签到数据存放于统一用户库）"""
        result = self.user_mgr.check_in(user_id, username)

        if not result["success"]:
            await self._reply(
                event,
                f"今天已经签到过了哦！\n"
                f"🔥 连续签到: {result['consecutive_days']}天\n"
                f"💎 总积分: {result['total_points']}",
            )
            return True

        message = (
            f"✅ 签到成功！\n"
            f"👤 用户: {username}\n"
            f"📅 签到时间: {result['checkin_time']}\n"
            f"💰 获得积分: +{result['points_earned']}\n"
            f"🔥 连续签到: {result['consecutive_days']}天\n"
            f"📊 总签到: {result['total_checkins']}天\n"
            f"💎 总积分: {result['total_points']}"
        )
        await self._reply(event, message)
        return True

    async def handle_daily_rank(self, event: GroupMessageEvent, group_id: str) -> bool:
        """处理发言日榜命令"""
        rankings = self.user_mgr.get_daily_rankings(group_id)

        if not rankings:
            await self._reply(event, "暂无发言记录")
            return True

        ranking_text = "📊 发言日榜 (本群)\n\n"

        for i, (uid, count) in enumerate(rankings[:SpeechConfig.RANKING_DAILY_TOP_N], 1):
            user_data = load_user_data(uid)
            username = get_display_username(user_data, uid) if user_data else uid

            # 奖牌显示
            if i == 1:
                medal = "🥇"
            elif i == 2:
                medal = "🥈"
            elif i == 3:
                medal = "🥉"
            else:
                medal = f"{i:2d}."

            ranking_text += f"{medal} [{username}]: {count}条\n"

        await self._reply(event, ranking_text)
        return True

    async def handle_history_rank(self, event: GroupMessageEvent, group_id: str, m: str) -> bool:
        """处理历史日榜命令"""
        parts = m.split()
        if len(parts) != 2:
            await self._reply(event, "❌ 格式错误，请使用: 历史日榜 YYYY-MM-DD")
            return True

        target_date = parts[1]

        # 验证日期格式
        try:
            datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            await self._reply(event, "❌ 日期格式错误，请使用 YYYY-MM-DD 格式")
            return True

        rankings = self.user_mgr.get_daily_rankings(group_id, target_date)

        if not rankings:
            await self._reply(event, f"📅 {target_date} 暂无发言记录")
            return True

        ranking_text = self._format_ranking(rankings, f"📅 {target_date} 发言日榜 (本群)", SpeechConfig.RANKING_DAILY_TOP_N)
        await self._reply(event, ranking_text)
        return True

    async def handle_my_stats(self, event: GroupMessageEvent, user_id: str, group_id: str) -> bool:
        """处理我的发言命令"""
        if not user_exists(user_id):
            await self._reply(event, "❌ 你未注册，请发送「注册」")
            return True

        user_data = load_user_data(user_id)
        if not user_data:
            await self._reply(event, "❌ 获取数据失败")
            return True

        stats = self.user_mgr.get_user_group_stats(user_id, group_id)
        now = datetime.now()
        week_start = now - timedelta(days=now.weekday())
        week_key = f"{week_start.year}-W{week_start.isocalendar()[1]:02d}"
        today_count = stats["today"]
        week_total = stats["week_total"]
        daily_details = stats["daily_details"]
        
        # 获取本月发言数
        month_total = self.user_mgr.get_user_month_count(user_id, group_id)
        
        # 获取本年度发言数
        year_total = self.user_mgr.get_user_year_count(user_id, group_id)

        # 构建回复
        result_text = f"📊 你的发言统计（本群）\n\n"
        result_text += f"   今日发言: {today_count} 条\n"
        result_text += f"   本周发言: {week_total} 条\n"
        result_text += f"   本月发言: {month_total} 条\n"
        result_text += f"   本年发言: {year_total} 条\n\n"

        if daily_details:
            result_text += f"📅 本周每日明细 ({week_key}):\n"
            sorted_dates = sorted(daily_details.keys())
            for date in sorted_dates:
                messages = daily_details[date]
                weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
                    datetime.strptime(date, "%Y-%m-%d").weekday()
                ]
                result_text += f"   {date} ({weekday}): {messages} 条\n"

        result_text += f"\n📈 累计统计（本群）:\n"
        result_text += f"   总发言数: {stats['total_messages']} 条\n"
        result_text += f"   活跃周数: {stats['total_weeks']} 周\n"
        result_text += f"\n💪 继续努力！"

        await self._reply(event, result_text)
        return True

    async def handle_weekly_rank(self, event: GroupMessageEvent, group_id: str) -> bool:
        """处理发言周榜命令"""
        rankings = self.user_mgr.get_weekly_rankings(group_id)

        if not rankings:
            await self._reply(event, "暂无发言记录")
            return True

        ranking_text = self._format_ranking(rankings, "📊 发言周榜 (本群)", SpeechConfig.RANKING_WEEKLY_TOP_N)
        await self._reply(event, ranking_text)
        return True
    
    async def handle_history_weekly_rank(self, event: GroupMessageEvent, group_id: str, m: str) -> bool:
        """处理历史周榜命令"""
        # 解析命令格式: 历史周榜 YYYY-MM-DD 或 历史周榜 W数字
        parts = m.split()
        if len(parts) != 2:
            await self._reply(event, "❌ 格式错误，请使用:\n历史周榜 YYYY-MM-DD（日期格式）\n或\n历史周榜 W数字（如 W06）")
            return True
        
        week_identifier = parts[1]
        
        # 获取历史周榜数据
        rankings, week_info = self.user_mgr.get_historical_weekly_rankings(group_id, week_identifier)
        
        # 检查是否有错误信息
        if week_info in ["无效的周数", "周数格式错误", "日期格式错误，请使用 YYYY-MM-DD 格式"]:
            await self._reply(event, f"❌ {week_info}")
            return True
        
        if not rankings:
            await self._reply(event, f"📅 {week_info} 暂无发言记录")
            return True
        
        ranking_text = self._format_ranking(rankings, f"📊 {week_info} 发言周榜", SpeechConfig.RANKING_WEEKLY_TOP_N)
        await self._reply(event, ranking_text)
        return True
    
    async def handle_monthly_rank(self, event: GroupMessageEvent, group_id: str) -> bool:
        """处理发言月榜命令"""
        rankings = self.user_mgr.get_monthly_rankings(group_id)

        if not rankings:
            await self._reply(event, "暂无月榜记录")
            return True

        now = datetime.now()
        ranking_text = self._format_ranking(rankings, f"📊 发言月榜 ({now.year}年{now.month}月)", SpeechConfig.RANKING_MONTHLY_TOP_N)
        await self._reply(event, ranking_text)
        return True
    
    async def handle_history_monthly_rank(self, event: GroupMessageEvent, group_id: str, m: str) -> bool:
        """处理历史月榜命令"""
        # 解析命令格式: 历史月榜 YYYY-MM-DD（月份起始日）
        parts = m.split()
        if len(parts) != 2:
            await self._reply(event, "❌ 格式错误，请使用: 历史月榜 YYYY-MM-DD")
            return True
            
        target_date = parts[1]
        
        # 验证日期格式
        try:
            target_datetime = datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            await self._reply(event, "❌ 日期格式错误，请使用 YYYY-MM-DD 格式")
            return True
        
        # 获取指定月份的发言排行榜
        rankings = self.user_mgr.get_monthly_rankings_by_start_date(group_id, target_date)
        
        if not rankings:
            year = target_datetime.year
            month = target_datetime.month
            await self._reply(event, f"{year}年{month}月 暂无发言记录")
            return True

        year = target_datetime.year
        month = target_datetime.month
        ranking_text = self._format_ranking(rankings, f"📊 {year}年{month}月 发言月榜", SpeechConfig.RANKING_MONTHLY_TOP_N)
        await self._reply(event, ranking_text)
        return True
    
    async def handle_seasonal_rank(self, event: GroupMessageEvent, group_id: str) -> bool:
        """处理发言季榜命令"""
        current_date = datetime.now()
        current_season = (current_date.month - 1) // 3 + 1
        season_map = {1: "春季", 2: "夏季", 3: "秋季", 4: "冬季"}
        season_name = season_map[current_season]
        
        rankings = self.user_mgr.get_seasonal_rankings(group_id)

        if not rankings:
            await self._reply(event, "暂无发言记录")
            return True

        ranking_text = self._format_ranking(rankings, f"📊 发言季榜 ({current_date.year}年{season_name})", SpeechConfig.RANKING_SEASONAL_TOP_N)
        await self._reply(event, ranking_text)
        return True
    
    async def handle_yearly_rank(self, event: GroupMessageEvent, group_id: str) -> bool:
        """处理发言年榜命令"""
        rankings = self.user_mgr.get_yearly_rankings(group_id)

        if not rankings:
            await self._reply(event, "暂无年榜记录")
            return True

        current_year = datetime.now().year
        ranking_text = self._format_ranking(rankings, f"📊 发言年榜 ({current_year}年)", SpeechConfig.RANKING_YEARLY_TOP_N)
        await self._reply(event, ranking_text)
        return True
    
    async def handle_history_yearly_rank(self, event: GroupMessageEvent, group_id: str, m: str) -> bool:
        """处理历史年榜命令"""
        # 解析命令格式: 历史年榜 YYYY
        parts = m.split()
        if len(parts) != 2:
            await self._reply(event, "❌ 格式错误，请使用: 历史年榜 YYYY")
            return True
            
        target_year_str = parts[1]
        
        # 验证年份格式
        try:
            target_year = int(target_year_str)
            if target_year < 2000 or target_year > 9999:
                raise ValueError("年份超出范围")
        except ValueError:
            await self._reply(event, "❌ 年份格式错误，请使用 YYYY 格式（如 2026）")
            return True
        
        # 获取指定年份的发言排行榜
        rankings = self.user_mgr.get_yearly_rankings(group_id, target_year)
        
        if not rankings:
            await self._reply(event, f"{target_year}年 暂无发言记录")
            return True

        ranking_text = self._format_ranking(rankings, f"📊 {target_year}年 发言年榜", SpeechConfig.RANKING_YEARLY_TOP_N)
        await self._reply(event, ranking_text)
        return True

    async def handle_set_username(self, event: GroupMessageEvent, user_id: str, m: str) -> bool:
        """处理设置用户名命令"""
        if not user_exists(user_id):
            await self._reply(event, "❌ 你未注册，请先发送「注册」")
            return True

        # 提取新用户名（注意：这里是"设置用户名"5个字）
        new_username = m[5:].strip()

        if not new_username:
            await self._reply(event, "❌ 请提供要设置的用户名\n格式：设置用户名 你的新名字")
            return True

        if len(new_username) > 20:
            await self._reply(event, "❌ 用户名过长，请控制在20个字符以内")
            return True

        # 获取旧用户名
        user_data = load_user_data(user_id)
        old_username = get_display_username(user_data, f"用户{user_id}")

        # 更新用户名
        success = self.user_mgr.set_username(user_id, new_username)

        if success:
            await self._reply(event, f"✅ 用户名已更新：{old_username} → {new_username}")
        else:
            await self._reply(event, "❌ 更新用户名失败，请稍后再试")

        return True

    async def handle_query_user(self, event: GroupMessageEvent, group_id: str, m: str) -> bool:
        """处理查询发言命令"""
        # 检查是否有 @用户
        at_segments = event.message.filter_at()
        
        target_user_id = None
        search_type = ""
        
        if at_segments:
            # 有 @用户，提取第一个被 @ 用户的 QQ号
            target_user_id = str(at_segments[0].qq)
            if not target_user_id:
                await self._reply(event, "❌ 无法获取被 @用户的QQ号")
                return True
            search_type = "@用户"
        else:
            # 没有 @用户，使用文本参数
            # 判断是"查询发言"还是"查发言"
            if m.startswith("查询发言"):
                query_param = m[4:].strip()
            else:  # 查发言
                query_param = m[3:].strip()
            
            if not query_param:
                await self._reply(event, "❌ 请提供查询参数\n格式1：查询发言 QQ号\n格式2：查询发言 用户名\n格式3：查询发言 @用户")
                return True
            
            # 判断是QQ号还是用户名
            is_qq = query_param.isdigit()
            
            if is_qq:
                # 通过QQ号查询
                target_user_id = query_param
                search_type = "QQ号"
            else:
                # 通过用户名搜索
                target_user_id = self.user_mgr.search_user_by_username(query_param)
                search_type = "用户名"
        
        # 验证用户是否存在
        if not target_user_id or not user_exists(target_user_id):
            if search_type == "@用户":
                await self._reply(event, "❌ 未找到该用户（可能未注册）")
            else:
                await self._reply(event, f"❌ 未找到{search_type}为 {target_user_id if target_user_id else '未知'} 的用户")
            return True

        # 获取用户数据
        user_data = load_user_data(target_user_id)
        if not user_data:
            await self._reply(event, "❌ 获取用户数据失败")
            return True

        target_username = get_display_username(user_data, "未知用户")

        stats = self.user_mgr.get_user_group_stats(target_user_id, group_id)
        now = datetime.now()
        week_start = now - timedelta(days=now.weekday())
        week_key = f"{week_start.year}-W{week_start.isocalendar()[1]:02d}"
        today_count = stats["today"]
        week_total = stats["week_total"]
        daily_details = stats["daily_details"]
        active_days = sum(1 for count in daily_details.values() if count > 0)
        
        # 获取本月发言数
        month_total = self.user_mgr.get_user_month_count(target_user_id, group_id)
        
        # 获取本年度发言数
        year_total = self.user_mgr.get_user_year_count(target_user_id, group_id)

        # 构建回复
        result_text = f"👤 用户 {target_username} ({target_user_id})\n\n"
        result_text += f"📊 本群发言统计：\n"
        result_text += f"   今日发言: {today_count} 条\n"
        result_text += f"   本周发言: {week_total} 条\n"
        result_text += f"   本月发言: {month_total} 条\n"
        result_text += f"   本年发言: {year_total} 条\n"
        result_text += f"   活跃天数: {active_days} 天\n\n"

        if daily_details:
            result_text += f"📅 本周每日明细 ({week_key}):\n"
            sorted_dates = sorted(daily_details.keys())
            for date in sorted_dates:
                messages = daily_details[date]
                if messages > 0:  # 只显示有发言的日期
                    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
                        datetime.strptime(date, "%Y-%m-%d").weekday()
                    ]
                    result_text += f"   {date} ({weekday}): {messages} 条\n"

        # 添加汇总信息
        summary = user_data.get("summary", {})
        total_messages = summary.get("total_messages", 0)
        total_weeks = summary.get("total_weeks", 0)
        avg_per_week = summary.get("avg_messages_per_week", 0)

        result_text += f"\n📈 累计统计:\n"
        result_text += f"   总发言数: {total_messages} 条\n"
        result_text += f"   活跃周数: {total_weeks} 周\n"
        result_text += f"   周均发言: {avg_per_week} 条\n"

        await self._reply(event, result_text)
        return True

    async def handle_delete_user(self, event: GroupMessageEvent, m: str) -> bool:
        """处理删除用户命令（管理员专用）"""
        user_id = str(event.user_id)

        # 检查管理员权限
        if not SpeechConfig.is_admin(user_id):
            await self._reply(event, "❌ 只有管理员可以执行此操作")
            return True

        parts = m.split()
        if len(parts) != 2:
            await self._reply(event, "❌ 格式错误，请使用: 删除用户 QQ号")
            return True

        target_user_id = parts[1]

        if not user_exists(target_user_id):
            await self._reply(event, f"❌ 用户 {target_user_id} 不存在")
            return True

        # 删除用户及其全部数据（JSON）
        from .data_manager import delete_user_data

        if delete_user_data(target_user_id):
            await self._reply(event, f"✅ 用户 {target_user_id} 已删除")
        else:
            await self._reply(event, f"❌ 删除用户失败")

        return True

    async def handle_auto_archive(self, event: GroupMessageEvent) -> bool:
        """处理自动归档命令（管理员或操作员可用）"""
        user_id = str(event.user_id)
    
        # 检查权限（Admin和Operator都可以执行）
        if not SpeechConfig.is_any_admin(user_id):
            await self._reply(event, "❌ 你没有权限执行此操作")
            return True
    
        await self._reply(event, "🔄 开始执行自动归档...")
    
        # 执行自动归档
        from .archive_manager import auto_archive
        success, message = auto_archive()
    
        if success:
            # 发送归档结果（只发送前 500 字，避免消息过长）
            if len(message) > 500:
                reply_message = f"✅ 自动归档完成\n\n{message[:500]}...\n\n详细信息请查看控制台"
            else:
                reply_message = f"✅ 自动归档完成\n\n{message}"
        else:
            reply_message = f"❌ 自动归档失败\n\n{message}"
    
        await self._reply(event, reply_message)
        return True
    
    # ========== 群管理命令 ==========
    
    async def handle_add_group(self, event: GroupMessageEvent, m: str) -> bool:
        """处理加白名单命令（管理员专用）"""
        user_id = str(event.user_id)
    
        # 检查管理员权限（只有Admin可以管理白名单）
        if not SpeechConfig.is_admin(user_id):
            await self._reply(event, "❌ 只有管理员可以执行此操作")
            return True
    
        # 提取群号
        parts = m.split()
        if len(parts) != 2:
            await self._reply(event, "❌ 格式错误，请使用：加白名单 QQ 群号")
            return True
    
        group_id = parts[1]
    
        if not group_id.isdigit():
            await self._reply(event, "❌ 群号必须是数字")
            return True
    
        # 添加到白名单
        SpeechConfig.add_allowed_group(group_id)
        await self._reply(event, f"✅ 已将群 {group_id} 加入白名单")
        return True
    
    async def handle_remove_group(self, event: GroupMessageEvent, m: str) -> bool:
        """处理移除白名单命令（管理员专用）"""
        user_id = str(event.user_id)
    
        # 检查管理员权限（只有Admin可以管理白名单）
        if not SpeechConfig.is_admin(user_id):
            await self._reply(event, "❌ 只有管理员可以执行此操作")
            return True
    
        # 提取群号
        parts = m.split()
        if len(parts) != 2:
            await self._reply(event, "❌ 格式错误，请使用：移除白名单 QQ 群号")
            return True
    
        group_id = parts[1]
    
        if not group_id.isdigit():
            await self._reply(event, "❌ 群号必须是数字")
            return True
    
        # 从白名单移除
        SpeechConfig.remove_allowed_group(group_id)
        await self._reply(event, f"✅ 已将群 {group_id} 移出白名单")
        return True
    
    async def handle_view_whitelist(self, event: GroupMessageEvent) -> bool:
        """处理查看白名单命令（管理员或操作员可用）"""
        user_id = str(event.user_id)
    
        # 检查权限（Admin和Operator都可以查看）
        if not SpeechConfig.is_any_admin(user_id):
            await self._reply(event, "❌ 你没有权限执行此操作")
            return True
    
        # 获取白名单列表
        allowed_groups = SpeechConfig.get_allowed_groups_list()
            
        if not allowed_groups:
            await self._reply(event, "📋 当前白名单为空\n💡 使用「加白名单 QQ 群号」添加")
            return True
    
        # 构建回复
        reply_text = f"📋 白名单列表 ({len(allowed_groups)} 个群)\n\n"
        for i, gid in enumerate(sorted(allowed_groups), 1):
            reply_text += f"{i}. {gid}\n"
    
        reply_text += "\n💡 使用「移除白名单 QQ 群号」移除"
        await self._reply(event, reply_text)
        return True
    
    async def handle_toggle_whitelist_mode(self, event: GroupMessageEvent) -> bool:
        """处理切换白名单模式命令（管理员专用）"""
        user_id = str(event.user_id)
    
        # 检查管理员权限（只有Admin可以切换模式）
        if not SpeechConfig.is_admin(user_id):
            await self._reply(event, "❌ 只有管理员可以执行此操作")
            return True
    
        # 切换模式
        SpeechConfig.USE_WHITELIST_MODE = not SpeechConfig.USE_WHITELIST_MODE
            
        # 保存配置
        SpeechConfig._save_allowed_groups()
    
        mode_text = "✅ 已开启" if SpeechConfig.USE_WHITELIST_MODE else "❌ 已关闭"
        mode_desc = "仅白名单群可用" if SpeechConfig.USE_WHITELIST_MODE else "所有群可用"
            
        await self._reply(event, f"{mode_text}白名单模式\n当前状态：{mode_desc}")
        return True
    
    # ========== 权限管理命令（仅Admin可用） ==========
    
    async def handle_add_admin(self, event: GroupMessageEvent, m: str) -> bool:
        """处理添加管理员命令（仅Admin可用）"""
        user_id = str(event.user_id)
        
        # 检查是否为管理员
        if not SpeechConfig.is_admin(user_id):
            await self._reply(event, "❌ 只有管理员可以管理权限")
            return True
        
        # 提取用户ID
        parts = m.split()
        if len(parts) != 2:
            await self._reply(event, "❌ 格式错误，请使用：发言添加管理员 QQ号")
            return True
        
        target_user_id = parts[1]
        
        if not target_user_id.isdigit():
            await self._reply(event, "❌ QQ号必须是数字")
            return True
        
        # 如果已经是操作员，先移除
        if SpeechConfig.is_operator(target_user_id):
            SpeechConfig.remove_operator_user(target_user_id)
        
        # 添加为管理员
        SpeechConfig.add_admin_user(target_user_id)
        await self._reply(event, f"✅ 已将 {target_user_id} 添加为管理员")
        return True
    
    async def handle_remove_admin(self, event: GroupMessageEvent, m: str) -> bool:
        """处理移除管理员命令（仅Admin可用）"""
        user_id = str(event.user_id)
        
        # 检查是否为管理员
        if not SpeechConfig.is_admin(user_id):
            await self._reply(event, "❌ 只有管理员可以管理权限")
            return True
        
        # 提取用户ID
        parts = m.split()
        if len(parts) != 2:
            await self._reply(event, "❌ 格式错误，请使用：发言移除管理员 QQ号")
            return True
        
        target_user_id = parts[1]
        
        if not target_user_id.isdigit():
            await self._reply(event, "❌ QQ号必须是数字")
            return True
        
        # 移除管理员
        SpeechConfig.remove_admin_user(target_user_id)
        await self._reply(event, f"✅ 已移除管理员 {target_user_id}")
        return True
    
    async def handle_view_admins(self, event: GroupMessageEvent) -> bool:
        """处理查看管理员列表命令"""
        user_id = str(event.user_id)
        
        # 检查权限
        if not SpeechConfig.is_any_admin(user_id):
            await self._reply(event, "❌ 你没有权限执行此操作")
            return True
        
        admins = list(SpeechConfig.ADMIN_USERS)
        
        if not admins:
            await self._reply(event, "📝 暂无管理员")
            return True
        
        admin_list = "\n".join([f"- {uid}" for uid in sorted(admins)])
        await self._reply(event, f"👑 管理员名单：\n{admin_list}")
        return True
    
    async def handle_add_operator(self, event: GroupMessageEvent, m: str) -> bool:
        """处理添加操作员命令（仅Admin可用）"""
        user_id = str(event.user_id)
        
        # 检查是否为管理员
        if not SpeechConfig.is_admin(user_id):
            await self._reply(event, "❌ 只有管理员可以管理权限")
            return True
        
        # 提取用户ID
        parts = m.split()
        if len(parts) != 2:
            await self._reply(event, "❌ 格式错误，请使用：发言添加操作员 QQ号")
            return True
        
        target_user_id = parts[1]
        
        if not target_user_id.isdigit():
            await self._reply(event, "❌ QQ号必须是数字")
            return True
        
        # 如果已经是管理员，先移除
        if SpeechConfig.is_admin(target_user_id):
            SpeechConfig.remove_admin_user(target_user_id)
        
        # 添加为操作员
        SpeechConfig.add_operator_user(target_user_id)
        await self._reply(event, f"✅ 已将 {target_user_id} 添加为操作员")
        return True
    
    async def handle_remove_operator(self, event: GroupMessageEvent, m: str) -> bool:
        """处理移除操作员命令（仅Admin可用）"""
        user_id = str(event.user_id)
        
        # 检查是否为管理员
        if not SpeechConfig.is_admin(user_id):
            await self._reply(event, "❌ 只有管理员可以管理权限")
            return True
        
        # 提取用户ID
        parts = m.split()
        if len(parts) != 2:
            await self._reply(event, "❌ 格式错误，请使用：发言移除操作员 QQ号")
            return True
        
        target_user_id = parts[1]
        
        if not target_user_id.isdigit():
            await self._reply(event, "❌ QQ号必须是数字")
            return True
        
        # 移除操作员
        SpeechConfig.remove_operator_user(target_user_id)
        await self._reply(event, f"✅ 已移除操作员 {target_user_id}")
        return True
    
    async def handle_view_operators(self, event: GroupMessageEvent) -> bool:
        """处理查看操作员列表命令"""
        user_id = str(event.user_id)
        
        # 检查权限
        if not SpeechConfig.is_any_admin(user_id):
            await self._reply(event, "❌ 你没有权限执行此操作")
            return True
        
        operators = list(SpeechConfig.OPERATOR_USERS)
        
        if not operators:
            await self._reply(event, "📝 暂无操作员")
            return True
        
        operator_list = "\n".join([f"- {uid}" for uid in sorted(operators)])
        await self._reply(event, f"🔧 操作员名单：\n{operator_list}")
        return True
