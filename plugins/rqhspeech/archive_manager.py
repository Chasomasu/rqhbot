"""
归档管理模块 - 日榜与周榜归档

功能特性：
  - DailyArchiver: 每日数据归档，生成日榜 JSON/CSV 到 rankings/ 目录
  - WeeklyArchiver: 手动建周榜，生成周榜 JSON/CSV 到 weekly/ 目录
  - auto_archive(): 自动归档日榜（从上次归档日期到昨天）
  - auto_archive_weekly(): 自动归档所有未归档的周榜
"""

import json
import csv
import os
import shutil
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

from .speech_config import SpeechConfig
from .data_manager import load_user_data

logger = logging.getLogger(__name__)


class DailyArchiver:
    """每日归档管理器"""
    
    def __init__(self):
        """初始化"""
        self.users_dir = SpeechConfig.USERS_DIR
        self.archives_dir = SpeechConfig.ARCHIVES_DIR
        self.last_archive_file = os.path.join(self.archives_dir, "last_archive.json")
    
    def get_all_user_files(self) -> List[str]:
        """获取所有用户JSON文件"""
        user_files = []
        for file in os.listdir(self.users_dir):
            if file.endswith(SpeechConfig.USER_FILE_EXTENSION):
                user_files.append(file)
        return user_files
    
    def load_user_data(self, filename: str) -> Optional[Dict[str, Any]]:
        """加载用户数据"""
        filepath = os.path.join(self.users_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except Exception as e:
            logger.error(f"加载文件 {filename} 时出错: {e}")
            return None
    
    def collect_user_stats_for_date(self, target_date: str) -> List[Dict[str, Any]]:
        """收集指定日期的用户统计数据"""
        user_stats = []
        user_files = self.get_all_user_files()
        
        logger.info(f"正在收集 {len(user_files)} 个用户的统计数据...")
        
        for user_file in user_files:
            data = self.load_user_data(user_file)
            if data:
                # 提取用户信息
                user_id = data.get("user_id") or user_file[5:-5]
                username = data.get("username") or ""

                # 汇总该用户当天在所有群的发言数
                message_count = 0
                for dates in (data.get("daily_records") or {}).values():
                    if isinstance(dates, dict):
                        message_count += int(dates.get(target_date, 0))
                
                # 设置最后发言时间为目标日期
                target_date_obj = datetime.strptime(target_date, "%Y-%m-%d")
                message_time = target_date_obj.strftime(SpeechConfig.DISPLAY_DATE_FORMAT)
                
                # 计算活跃度得分
                activity_score = message_count * 1.0
                
                user_stat = {
                    "用户id": user_id,
                    "用户名": username,
                    "发言数量": message_count,
                    "最后发言时间": message_time,
                    "活跃度得分": activity_score,
                    "数据文件": user_file,
                    "收集时间": SpeechConfig.get_current_datetime()
                }
                
                user_stats.append(user_stat)
        
        return user_stats
    
    def generate_ranking(self, user_stats: List[Dict[str, Any]], 
                        top_n: int = None) -> Dict[str, Any]:
        """生成排行榜"""
        if top_n is None:
            top_n = SpeechConfig.RANKING_TOP_N
        
        # 按发言数量降序排序
        sorted_by_messages = sorted(
            user_stats, 
            key=lambda x: x["发言数量"], 
            reverse=True
        )
        
        # 按活跃度得分降序排序
        sorted_by_activity = sorted(
            user_stats, 
            key=lambda x: x["活跃度得分"], 
            reverse=True
        )
        
        # 过滤掉发言数为0的用户
        active_users = [u for u in user_stats 
                       if u["发言数量"] >= SpeechConfig.MIN_MESSAGES_FOR_RANKING]
        
        # 生成榜单数据
        ranking_data = {
            "生成时间": SpeechConfig.get_current_datetime(),
            "统计日期": SpeechConfig.get_current_date(),
            "总用户数": len(user_stats),
            "活跃用户数": len(active_users),
            "总发言数": sum(u["发言数量"] for u in user_stats),
            "榜单": {
                "按发言数量排名": [
                    {
                        "排名": i + 1,
                        "用户id": user["用户id"],
                        "用户名": user["用户名"],
                        "发言数量": user["发言数量"],
                        "最后发言时间": user["最后发言时间"]
                    }
                    for i, user in enumerate(sorted_by_messages[:top_n])
                ],
                "按活跃度排名": [
                    {
                        "排名": i + 1,
                        "用户id": user["用户id"],
                        "用户名": user["用户名"],
                        "活跃度得分": user["活跃度得分"],
                        "发言数量": user["发言数量"]
                    }
                    for i, user in enumerate(sorted_by_activity[:top_n])
                ]
            },
            "详细数据": active_users
        }
        
        return ranking_data
    
    def save_ranking_json(self, ranking_data: Dict[str, Any], 
                         date: str = None) -> str:
        """保存榜单为JSON文件（按年分层：rankings/YYYY/ranking_YYYY-MM-DD.json）"""
        if date is None:
            date = SpeechConfig.get_current_date()
        
        year = date.split("-")[0]
        year_dir = os.path.join(SpeechConfig.RANKINGS_DIR, year)
        os.makedirs(year_dir, exist_ok=True)
        
        filename = SpeechConfig.get_ranking_filename(date)
        filepath = os.path.join(year_dir, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(ranking_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"榜单已保存为JSON文件: {filename}")
            return filepath
            
        except Exception as e:
            logger.error(f"保存JSON榜单时出错: {e}")
            return ""
    
    def save_ranking_csv(self, ranking_data: Dict[str, Any], 
                        date: str = None) -> str:
        """保存榜单为CSV文件（按年分层：csv/YYYY/ranking_YYYY-MM-DD.csv）"""
        if date is None:
            date = SpeechConfig.get_current_date()
        
        year = date.split("-")[0]
        year_dir = os.path.join(SpeechConfig.CSV_DIR, year)
        os.makedirs(year_dir, exist_ok=True)
        
        filename = SpeechConfig.get_csv_filename(date)
        filepath = os.path.join(year_dir, filename)
        
        try:
            # 提取按发言数量排名的数据
            message_ranking = ranking_data["榜单"]["按发言数量排名"]
            
            with open(filepath, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                
                # 写入标题
                writer.writerow([
                    "排名", "用户ID", "用户名", 
                    "发言数量", "最后发言时间", "统计日期"
                ])
                
                # 写入数据
                for item in message_ranking:
                    writer.writerow([
                        item["排名"],
                        item["用户id"],
                        item["用户名"],
                        item["发言数量"],
                        item["最后发言时间"],
                        date
                    ])
            
            logger.info(f"榜单已保存为CSV文件: {filename}")
            return filepath
            
        except Exception as e:
            logger.error(f"保存CSV榜单时出错: {e}")
            return ""
    
    def archive_for_date(self, target_date: str) -> Tuple[bool, str]:
        """归档指定日期的数据"""
        logger.info(f"[归档] 开始为日期 {target_date} 执行数据归档...")
        
        try:
            # 收集指定日期的用户统计数据
            user_stats = self.collect_user_stats_for_date(target_date)
            
            if not user_stats:
                return False, f"日期 {target_date} 没有用户数据"
            
            # 生成榜单
            ranking_data = self.generate_ranking(user_stats)
            ranking_data["统计日期"] = target_date
            
            # 保存榜单文件
            json_file = self.save_ranking_json(ranking_data, target_date)
            csv_file = self.save_ranking_csv(ranking_data, target_date)
            
            if not json_file and not csv_file:
                return False, "榜单保存失败"
            
            # 生成归档报告
            report = self.generate_archive_report(ranking_data)
            
            # 更新最后归档日期
            self.update_last_archive_date(target_date)
            
            return True, f"成功归档 {target_date} 的数据\n{report}"
            
        except Exception as e:
            logger.error(f"[归档] 执行归档时出现异常: {e}")
            import traceback
            traceback.print_exc()
            return False, f"归档失败: {str(e)}"
    
    def backup_user_data(self, date: str = None) -> str:
        """备份用户数据（按年分层：backups/YYYY/backup_YYYY-MM-DD/）"""
        if date is None:
            date = SpeechConfig.get_current_date()
        
        year = date.split("-")[0]
        backup_dir = os.path.join(SpeechConfig.BACKUPS_DIR, year, f"backup_{date}")
        
        try:
            if os.path.exists(self.users_dir):
                # 创建备份目录
                os.makedirs(backup_dir, exist_ok=True)
                
                # 复制所有用户文件
                for file in os.listdir(self.users_dir):
                    if file.endswith(SpeechConfig.USER_FILE_EXTENSION):
                        src = os.path.join(self.users_dir, file)
                        dst = os.path.join(backup_dir, file)
                        shutil.copy2(src, dst)
                
                logger.info(f"用户数据已备份到: {backup_dir}")
                return backup_dir
                
        except Exception as e:
            logger.error(f"备份用户数据时出错: {e}")
        
        return ""
    
    def generate_archive_report(self, ranking_data: Dict[str, Any]) -> str:
        """生成归档报告"""
        total_users = ranking_data["总用户数"]
        active_users = ranking_data["活跃用户数"]
        total_messages = ranking_data["总发言数"]
        
        # 获取榜首用户
        top_user = ranking_data["榜单"]["按发言数量排名"][0] if ranking_data["榜单"]["按发言数量排名"] else {}
        
        report = f"""
📈 归档报告
══════════════════════════════════════
统计日期：{ranking_data["统计日期"]}
生成时间：{ranking_data["生成时间"]}
总用户数：{total_users} 人
活跃用户：{active_users} 人
总发言数：{total_messages} 条

🏆 榜首用户
══════════════════════════════════════
👑 用户名：{top_user.get("用户名", "无")}
🆔 用户ID：{top_user.get("用户id", "无")}
💬 发言数：{top_user.get("发言数量", 0)} 条
⏰ 最后发言：{top_user.get("最后发言时间", "无")}

📊 详细榜单已保存到：{SpeechConfig.RANKINGS_DIR}
        """
        
        logger.info(report)
        return report
    
    def get_last_archive_date(self) -> Optional[str]:
        """获取最后归档日期"""
        if not os.path.exists(self.last_archive_file):
            return None
        
        try:
            with open(self.last_archive_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get("last_archive_date")
        except Exception as e:
            logger.error(f"读取最后归档日期失败: {e}")
            return None
    
    def update_last_archive_date(self, date: str):
        """更新最后归档日期"""
        try:
            data = {"last_archive_date": date, "update_time": SpeechConfig.get_current_datetime()}
            with open(self.last_archive_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"更新最后归档日期失败: {e}")
    
    def get_dates_to_archive(self) -> List[str]:
        """获取需要归档的日期列表"""
        dates_to_archive = []
        
        # 获取最后归档日期
        last_archive_date = self.get_last_archive_date()
        
        # 计算开始日期
        if last_archive_date:
            start_date = datetime.strptime(last_archive_date, "%Y-%m-%d") + timedelta(days=1)
        else:
            # 如果没有最后归档日期，默认从7天前开始
            start_date = datetime.now() - timedelta(days=7)
        
        # 计算结束日期（昨天）
        end_date = datetime.now() - timedelta(days=1)
        
        # 生成日期列表
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            dates_to_archive.append(date_str)
            current_date += timedelta(days=1)
        
        return dates_to_archive
    
    def auto_archive(self) -> Tuple[bool, str]:
        """自动归档从上次备份后的所有日期"""
        logger.info("=" * 50)
        logger.info("开始自动归档处理")
        logger.info("=" * 50)
        
        # 获取需要归档的日期
        dates_to_archive = self.get_dates_to_archive()
        
        if not dates_to_archive:
            return True, "没有需要归档的日期"
        
        logger.info(f"找到 {len(dates_to_archive)} 个需要归档的日期:")
        for date in dates_to_archive:
            logger.info(f"  - {date}")
        
        # 备份用户数据
        if SpeechConfig.BACKUP_BEFORE_ARCHIVE:
            self.backup_user_data()
        
        # 逐个归档日期
        results = []
        for date in dates_to_archive:
            success, message = self.archive_for_date(date)
            results.append((date, success, message))
        
        # 生成汇总报告
        successful = sum(1 for _, success, _ in results if success)
        total = len(results)
        
        report = f"""
📊 自动归档汇总报告
══════════════════════════════════════
总处理日期：{total} 个
成功归档：{successful} 个
失败归档：{total - successful} 个

详细结果：
"""
        
        for date, success, message in results:
            status = "✅" if success else "❌"
            report += f"{status} {date}: {message.split(chr(10))[0]}\n"
        
        logger.info(report)
        return True, report
    
    def archive_today(self) -> Tuple[bool, str]:
        """归档今天的数据"""
        today = SpeechConfig.get_current_date()
        return self.archive_for_date(today)
    
    def display_today_ranking(self):
        """显示今日榜单"""
        today = SpeechConfig.get_current_date()
        year = today.split("-")[0]
        today_file = os.path.join(
            self.archives_dir,
            year,
            SpeechConfig.get_ranking_filename()
        )
        
        if not os.path.exists(today_file):
            logger.warning("今日榜单尚未生成，请先执行归档操作。")
            return
        
        try:
            with open(today_file, 'r', encoding='utf-8') as f:
                ranking_data = json.load(f)
            
            logger.info("=" * 60)
            logger.info("🏆 今日发言排行榜 🏆")
            logger.info("=" * 60)
            logger.info(f"📅 统计日期: {ranking_data['统计日期']}")
            logger.info(f"👥 总用户数: {ranking_data['总用户数']}")
            logger.info(f"💬 总发言数: {ranking_data['总发言数']}")
            logger.info("")
            
            # 显示按发言数量排名的前10名
            logger.info("📊 按发言数量排名（前10名）:")
            logger.info("-" * 60)
            for item in ranking_data['榜单']['按发言数量排名'][:10]:
                logger.info(f"🏅 第{item['排名']:2d}名: {item['用户名']:15s} "
                      f"| 💬 {item['发言数量']:4d}条 "
                      f"| ⏰ {item['最后发言时间']}")
            
            logger.info("")
            
            # 显示按活跃度排名的前5名
            logger.info("🚀 按活跃度排名（前5名）:")
            logger.info("-" * 60)
            for item in ranking_data['榜单']['按活跃度排名'][:5]:
                logger.info(f"⭐ 第{item['排名']:2d}名: {item['用户名']:15s} "
                      f"| 📈 {item['活跃度得分']:6.2f}分 "
                      f"| 💬 {item['发言数量']:4d}条")
            
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"读取榜单时出错: {e}")


class WeeklyArchiver:
    """每周归档管理器 - 手动生成周榜"""

    def __init__(self):
        self.users_dir = SpeechConfig.USERS_DIR
        self.rankings_dir = SpeechConfig.RANKINGS_DIR

    def _parse_week_key(self, identifier: str) -> Tuple[Optional[str], str]:
        """解析周标识符，返回 (week_key, week_info)"""
        if identifier.startswith('W') or identifier.startswith('w'):
            try:
                week_num = int(identifier[1:])
                if week_num < 1 or week_num > 53:
                    return None, "无效的周数"
                current_year = datetime.now().year
                week_key = f"{current_year}-W{week_num:02d}"
                week_first_day = datetime.strptime(f"{current_year}-W{week_num:02d}-1", "%Y-W%W-%w")
                week_end = week_first_day + timedelta(days=6)
                week_info = f"{current_year}年第{week_num}周 ({week_first_day.strftime('%Y-%m-%d')} 至 {week_end.strftime('%Y-%m-%d')})"
                return week_key, week_info
            except (ValueError, IndexError):
                return None, "周数格式错误"
        else:
            try:
                target_date = datetime.strptime(identifier, "%Y-%m-%d")
                week_start = target_date - timedelta(days=target_date.weekday())
                week_key = f"{week_start.year}-W{week_start.isocalendar()[1]:02d}"
                week_end = week_start + timedelta(days=6)
                week_info = f"{week_start.strftime('%Y-%m-%d')} 至 {week_end.strftime('%Y-%m-%d')}"
                return week_key, week_info
            except ValueError:
                return None, "日期格式错误，请使用 YYYY-MM-DD 格式"

    def collect_user_stats_for_week(self, week_key: str) -> List[Dict[str, Any]]:
        """收集指定周的用户统计数据"""
        user_stats = []

        if not os.path.exists(self.users_dir):
            logger.error(f"用户目录不存在: {self.users_dir}")
            return []

        for filename in os.listdir(self.users_dir):
            if not filename.startswith("user_") or not filename.endswith(".json"):
                continue

            user_id = filename[5:-5]
            data = load_user_data(user_id)
            if not data:
                continue

            username = data.get("用户名") or data.get("username") or user_id

            weekly_records = data.get("weekly_records", {})
            total_messages = 0
            for weeks in weekly_records.values():
                if isinstance(weeks, dict):
                    total_messages += int(weeks.get(week_key, 0))

            if total_messages > 0:
                user_stats.append({
                    "用户id": user_id,
                    "用户名": username,
                    "发言数量": total_messages,
                    "数据文件": filename,
                    "收集时间": SpeechConfig.get_current_datetime()
                })

        user_stats.sort(key=lambda x: x["发言数量"], reverse=True)
        return user_stats

    def generate_ranking(self, user_stats: List[Dict[str, Any]],
                         week_key: str, week_info: str,
                         top_n: int = None) -> Dict[str, Any]:
        """生成周榜数据"""
        if top_n is None:
            top_n = SpeechConfig.RANKING_WEEKLY_TOP_N

        total_messages = sum(u["发言数量"] for u in user_stats)
        total_users = len(user_stats)

        # 按发言数量排名
        top_list = [
            {
                "排名": i + 1,
                "用户id": user["用户id"],
                "用户名": user["用户名"],
                "发言数量": user["发言数量"]
            }
            for i, user in enumerate(user_stats[:top_n])
        ]

        ranking_data = {
            "生成时间": SpeechConfig.get_current_datetime(),
            "统计周期": week_info,
            "周标识": week_key,
            "总用户数": total_users,
            "总发言数": total_messages,
            "榜单": top_list,
            "详细数据": user_stats
        }

        return ranking_data

    def save_ranking_json(self, ranking_data: Dict[str, Any],
                          week_key: str) -> str:
        """保存周榜为JSON文件"""
        year = week_key.split("-W")[0]
        year_dir = os.path.join(SpeechConfig.RANKINGS_DIR, year)
        os.makedirs(year_dir, exist_ok=True)
        filename = SpeechConfig.get_weekly_ranking_filename(week_key)
        filepath = os.path.join(year_dir, filename)

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(ranking_data, f, ensure_ascii=False, indent=2)
            logger.info(f"周榜已保存为JSON文件: {filename}")
            return filepath
        except Exception as e:
            logger.error(f"保存JSON周榜时出错: {e}")
            return ""

    def save_ranking_csv(self, ranking_data: Dict[str, Any],
                         week_key: str) -> str:
        """保存周榜为CSV文件"""
        year = week_key.split("-W")[0]
        year_dir = os.path.join(SpeechConfig.CSV_DIR, year)
        os.makedirs(year_dir, exist_ok=True)
        filename = SpeechConfig.get_weekly_csv_filename(week_key)
        filepath = os.path.join(year_dir, filename)

        try:
            with open(filepath, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["排名", "用户ID", "用户名", "发言数量", "统计周期"])
                for item in ranking_data["榜单"]:
                    writer.writerow([
                        item["排名"],
                        item["用户id"],
                        item["用户名"],
                        item["发言数量"],
                        ranking_data["统计周期"]
                    ])
            logger.info(f"周榜已保存为CSV文件: {filename}")
            return filepath
        except Exception as e:
            logger.error(f"保存CSV周榜时出错: {e}")
            return ""

    def archive_for_week(self, identifier: str) -> Tuple[bool, str]:
        """归档指定周的数据"""
        week_key, week_info = self._parse_week_key(identifier)
        if week_key is None:
            return False, week_info

        logger.info(f"[周榜] 开始为 {week_info} 生成周榜...")

        user_stats = self.collect_user_stats_for_week(week_key)
        if not user_stats:
            return False, f"{week_info} 没有用户数据"

        ranking_data = self.generate_ranking(user_stats, week_key, week_info)

        json_file = self.save_ranking_json(ranking_data, week_key)
        csv_file = self.save_ranking_csv(ranking_data, week_key)

        if not json_file and not csv_file:
            return False, "周榜保存失败"

        report = (
            f"\n📊 周榜报告\n"
            f"══════════════════════════════════════\n"
            f"统计周期：{week_info}\n"
            f"总用户数：{ranking_data['总用户数']} 人\n"
            f"总发言数：{ranking_data['总发言数']} 条\n"
        )
        if ranking_data["榜单"]:
            top = ranking_data["榜单"][0]
            report += f"🏆 榜首：{top['用户名']}（{top['发言数量']} 条）\n"

        logger.info(report)
        return True, f"成功生成 {week_info} 周榜\n{report}"

    def archive_current_week(self) -> Tuple[bool, str]:
        """归档当前周的数据"""
        current_date = datetime.now()
        current_week_start = current_date - timedelta(days=current_date.weekday())
        week_key = f"{current_week_start.year}-W{current_week_start.isocalendar()[1]:02d}"
        week_end = current_week_start + timedelta(days=6)
        week_info = f"{current_week_start.strftime('%Y-%m-%d')} 至 {week_end.strftime('%Y-%m-%d')}"
        identifier = current_date.strftime("%Y-%m-%d")
        return self.archive_for_week(identifier)

    def _get_all_week_keys_from_users(self) -> set:
        """从用户文件中收集所有存在的周标识"""
        all_weeks = set()
        if not os.path.exists(self.users_dir):
            return all_weeks

        for filename in os.listdir(self.users_dir):
            if not filename.startswith("user_") or not filename.endswith(".json"):
                continue
            user_id = filename[5:-5]
            data = load_user_data(user_id)
            if data:
                for weeks in (data.get("weekly_records") or {}).values():
                    if isinstance(weeks, dict):
                        all_weeks.update(weeks.keys())

        return all_weeks

    def _get_archived_week_keys(self) -> set:
        """获取已归档的周标识"""
        archived = set()
        if not os.path.exists(self.rankings_dir):
            return archived

        for root, dirs, files in os.walk(self.rankings_dir):
            for filename in files:
                if filename.startswith("ranking_") and filename.endswith(".json"):
                    # 格式: ranking_2026-W19.json
                    week_key = filename[8:-5]
                    archived.add(week_key)

        return archived

    def auto_archive_weekly(self) -> Tuple[bool, str]:
        """自动归档所有未归档的周"""
        logger.info("=" * 50)
        logger.info("开始自动周榜归档")
        logger.info("=" * 50)

        all_weeks = self._get_all_week_keys_from_users()
        archived_weeks = self._get_archived_week_keys()
        to_archive = sorted(all_weeks - archived_weeks)

        if not to_archive:
            return True, "所有周已完成归档，无需处理"

        logger.info(f"找到 {len(to_archive)} 个未归档的周:")
        for wk in to_archive:
            logger.info(f"  - {wk}")

        results = []
        for week_key in to_archive:
            # 从 week_key 生成标识符（用该周周一的日期）
            try:
                parts = week_key.split("-W")
                year = int(parts[0])
                week_num = int(parts[1])
                monday = datetime.strptime(f"{year}-W{week_num:02d}-1", "%Y-W%W-%w")
                identifier = monday.strftime("%Y-%m-%d")
                success, message = self.archive_for_week(identifier)
                results.append((week_key, success, message))
            except Exception as e:
                results.append((week_key, False, str(e)))

        successful = sum(1 for _, s, _ in results if s)
        total = len(results)

        report = (
            f"\n📊 自动周榜归档汇总\n"
            f"══════════════════════════════════════\n"
            f"总处理周数：{total} 个\n"
            f"成功归档：{successful} 个\n"
            f"失败归档：{total - successful} 个\n\n"
            f"详细结果：\n"
        )
        for wk, success, msg in results:
            status = "✅" if success else "❌"
            report += f"{status} {wk}: {msg.split(chr(10))[0]}\n"

        logger.info(report)
        return True, report


def daily_archive():
    """执行日常归档"""
    today = SpeechConfig.get_current_date()
    logger.info(f"开始归档今天的数据: {today}")
    
    archiver = DailyArchiver()
    success, message = archiver.archive_for_date(today)
    
    if success:
        logger.info("日归档完成")
    else:
        logger.error(f"归档失败: {message}")
    
    return success

def auto_archive():
    """执行自动归档"""
    archiver = DailyArchiver()
    success, message = archiver.auto_archive()
    
    if success:
        logger.info("自动归档完成")
    else:
        logger.error(f"自动归档失败: {message}")
    
    return success

def main():
    """主函数"""
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == '--today':
            daily_archive()
        elif sys.argv[1] == '--auto':
            auto_archive()
        elif sys.argv[1] == '--date':
            if len(sys.argv) > 2:
                target_date = sys.argv[2]
                try:
                    datetime.strptime(target_date, "%Y-%m-%d")
                    archiver = DailyArchiver()
                    archiver.archive_for_date(target_date)
                except ValueError:
                    logger.error(f"日期格式错误: {target_date}. 请使用 YYYY-MM-DD 格式")
            else:
                logger.error("请指定日期: python archive_manager.py --date YYYY-MM-DD")
        elif sys.argv[1] == '--display':
            archiver = DailyArchiver()
            archiver.display_today_ranking()
        elif sys.argv[1] == '--weekly':
            archiver = WeeklyArchiver()
            archiver.archive_current_week()
        elif sys.argv[1] == '--weekly-date':
            if len(sys.argv) > 2:
                week_identifier = sys.argv[2]
                archiver = WeeklyArchiver()
                archiver.archive_for_week(week_identifier)
            else:
                logger.error("请指定周标识: python archive_manager.py --weekly-date YYYY-MM-DD")
        elif sys.argv[1] == '--weekly-auto':
            archiver = WeeklyArchiver()
            success, message = archiver.auto_archive_weekly()
            if success:
                logger.info("自动周榜归档完成")
            else:
                logger.error(f"自动周榜归档失败: {message}")
        else:
            logger.info("使用方法:")
            logger.info("  python archive_manager.py --today                  # 归档今天数据")
            logger.info("  python archive_manager.py --auto                   # 自动归档")
            logger.info("  python archive_manager.py --date DATE              # 归档指定日期数据")
            logger.info("  python archive_manager.py --display                # 显示今日榜单")
            logger.info("  python archive_manager.py --weekly                 # 归档本周周榜")
            logger.info("  python archive_manager.py --weekly-date IDENTIFIER # 归档指定周（日期或 W数字）")
            logger.info("  python archive_manager.py --weekly-auto            # 自动归档所有未归档周")
    else:
        # 默认执行自动归档
        logger.info("=" * 50)
        logger.info("执行日报自动归档...")
        logger.info("=" * 50)
        auto_archive()

        logger.info("=" * 50)
        logger.info("执行周报自动归档...")
        logger.info("=" * 50)
        archiver = WeeklyArchiver()
        archiver.auto_archive_weekly()


if __name__ == "__main__":
    main()