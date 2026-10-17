"""
数据管理模块 - 纯 JSON 存储

用户发言数据、配置与签到均以 JSON 文件保存在插件自己的 data 目录内：
  - data/users/user_<user_id>.json  用户发言明细与周聚合
  - data/config/speech_config.json  白名单 / 管理员 / 操作员配置
  - data/checkin/<user_id>.json     签到数据
"""

import os
import json
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

from .speech_config import SpeechConfig
from .checkin_manager import checkin_manager

logger = logging.getLogger(__name__)

_USER_LOCKS: Dict[str, threading.Lock] = {}
_USER_LOCKS_GUARD = threading.Lock()


def _get_lock(user_id: str) -> threading.Lock:
    """获取单个用户文件的写锁"""
    with _USER_LOCKS_GUARD:
        lock = _USER_LOCKS.get(user_id)
        if lock is None:
            lock = threading.Lock()
            _USER_LOCKS[user_id] = lock
        return lock


def _week_key_of(date_str: str) -> str:
    """日期字符串 -> 周标识（以周一为起点）"""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    week_start = d - timedelta(days=d.weekday())
    return f"{week_start.year}-W{week_start.isocalendar()[1]:02d}"


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_user_file(user_id: str) -> str:
    """获取用户 JSON 文件路径"""
    return os.path.join(SpeechConfig.USERS_DIR, f"user_{user_id}.json")


def _new_user(user_id: str, username: str = "") -> Dict[str, Any]:
    now = _now_str()
    return {
        "user_id": user_id,
        "username": username or "",
        "created_at": now,
        "last_updated": now,
        "last_seen": now,
        "daily_records": {},
        "weekly_records": {},
        "summary": {},
    }


def _refresh_summary(data: Dict[str, Any]) -> None:
    """根据 weekly_records 重新计算 summary 缓存"""
    week_totals: Dict[str, int] = {}
    for weeks in (data.get("weekly_records") or {}).values():
        if not isinstance(weeks, dict):
            continue
        for week_key, count in weeks.items():
            try:
                week_totals[week_key] = week_totals.get(week_key, 0) + int(count)
            except (TypeError, ValueError):
                continue

    weeks = sorted(week_totals)
    total_messages = sum(week_totals.values())
    most_active_week = None
    if weeks:
        top_week = max(weeks, key=lambda k: week_totals[k])
        most_active_week = {"week_key": top_week, "messages": week_totals[top_week]}

    data["summary"] = {
        "user_id": data.get("user_id", ""),
        "username": data.get("username", ""),
        "total_weeks": len(weeks),
        "total_messages": total_messages,
        "avg_messages_per_week": round(total_messages / len(weeks), 2) if weeks else 0,
        "most_active_week": most_active_week,
        "first_week": weeks[0] if weeks else None,
        "last_week": weeks[-1] if weeks else None,
        "update_time": _now_str(),
    }


def _write_raw(user_id: str, data: Dict[str, Any]) -> bool:
    """原子写入用户 JSON 文件"""
    path = get_user_file(user_id)
    tmp_path = path + ".tmp"
    try:
        os.makedirs(SpeechConfig.USERS_DIR, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
        return True
    except Exception as e:
        logger.error(f"写入用户文件失败 {user_id}: {e}")
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return False


def _read_raw(user_id: str) -> Optional[Dict[str, Any]]:
    """读取用户 JSON 文件"""
    path = get_user_file(user_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        data.setdefault("user_id", user_id)
        data.setdefault("username", "")
        data.setdefault("daily_records", {})
        data.setdefault("weekly_records", {})
        return data
    except Exception as e:
        logger.error(f"读取用户文件失败 {user_id}: {e}")
        return None


def iter_user_data():
    """遍历所有用户数据（只读）"""
    try:
        filenames = os.listdir(SpeechConfig.USERS_DIR)
    except FileNotFoundError:
        return
    for filename in filenames:
        if not filename.startswith("user_") or not filename.endswith(".json"):
            continue
        user_id = filename[5:-5]
        data = _read_raw(user_id)
        if data is not None:
            yield user_id, data


def load_user_data(user_id: str) -> Optional[Dict[str, Any]]:
    """读取用户数据（返回兼容旧接口的结构）"""
    data = _read_raw(user_id)
    if data is None:
        return None

    if not data.get("summary"):
        _refresh_summary(data)

    summary = data["summary"]
    return {
        "用户id": data.get("user_id", user_id),
        "用户名": data.get("username", ""),
        "创建时间": data.get("created_at", ""),
        "最后更新": data.get("last_updated", ""),
        "最后发言": data.get("last_seen", ""),
        "summary": summary,
        "daily_records": data.get("daily_records", {}),
        "weekly_records": data.get("weekly_records", {}),
    }


def save_user_data(user_id: str, data: Dict[str, Any]) -> bool:
    """保存用户数据（兼容接口）"""
    if not data:
        return False
    try:
        with _get_lock(user_id):
            raw = _read_raw(user_id) or _new_user(user_id)
            username = data.get("用户名", "") or data.get("username", "")
            if username:
                raw["username"] = username
            raw["last_updated"] = _now_str()
            _refresh_summary(raw)
            return _write_raw(user_id, raw)
    except Exception as e:
        logger.error(f"save_user_data 失败 {user_id}: {e}")
        return False


def get_display_username(user_info: Dict[str, Any], default: str = "未知用户") -> str:
    if not user_info:
        return default
    return (
        (user_info.get("summary", {}) or {}).get("username")
        or user_info.get("用户名")
        or user_info.get("username")
        or default
    )


def user_exists(user_id: str) -> bool:
    return os.path.isfile(get_user_file(user_id))


def delete_user_data(user_id: str) -> bool:
    """删除用户 JSON 文件及其全部发言数据"""
    path = get_user_file(user_id)
    if not os.path.isfile(path):
        return False
    try:
        with _get_lock(user_id):
            os.remove(path)
        return True
    except Exception as e:
        logger.error(f"删除用户数据失败 {user_id}: {e}")
        return False


def check_and_handle_week_transition(user_data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """兼容接口：返回原数据和当前周标识"""
    now = datetime.now()
    return user_data, _week_key_of(now.strftime("%Y-%m-%d"))


def _parse_week_key(identifier: str) -> Tuple[Optional[str], str]:
    """解析周标识符，返回 (week_key, week_info)"""
    if identifier.startswith(("W", "w")):
        try:
            week_num = int(identifier[1:])
            if not 1 <= week_num <= 53:
                return None, "无效的周数"
            year = datetime.now().year
            week_key = f"{year}-W{week_num:02d}"
            first = datetime.strptime(f"{year}-W{week_num:02d}-1", "%Y-W%W-%w")
            last = first + timedelta(days=6)
            return week_key, f"{year}年第{week_num}周 ({first.strftime('%Y-%m-%d')} 至 {last.strftime('%Y-%m-%d')})"
        except (ValueError, IndexError):
            return None, "周数格式错误"

    try:
        d = datetime.strptime(identifier, "%Y-%m-%d")
        week_start = d - timedelta(days=d.weekday())
        week_key = f"{week_start.year}-W{week_start.isocalendar()[1]:02d}"
        week_end = week_start + timedelta(days=6)
        return week_key, f"{week_start.strftime('%Y-%m-%d')} 至 {week_end.strftime('%Y-%m-%d')}"
    except ValueError:
        return None, "日期格式错误，请使用 YYYY-MM-DD 格式"


# ========== 用户管理类 ==========

class UserDataManager:
    """用户数据管理器 —— 全部基于 JSON 文件"""

    def create_user(self, user_id: str, username: str) -> Dict[str, Any]:
        """创建新用户（已存在则直接返回）"""
        with _get_lock(user_id):
            data = _read_raw(user_id)
            if data is None:
                data = _new_user(user_id, username)
                _refresh_summary(data)
                _write_raw(user_id, data)
        return load_user_data(user_id) or {}

    def update_user_message(self, user_id: str, group_id: str) -> bool:
        """用户发言 +1（同时更新日明细与周聚合）"""
        try:
            with _get_lock(user_id):
                data = _read_raw(user_id)
                if data is None:
                    data = _new_user(user_id)

                now = datetime.now()
                date = now.strftime("%Y-%m-%d")
                week_key = _week_key_of(date)
                group_id = str(group_id)

                daily = data.setdefault("daily_records", {}).setdefault(group_id, {})
                daily[date] = int(daily.get(date, 0)) + 1

                weekly = data.setdefault("weekly_records", {}).setdefault(group_id, {})
                weekly[week_key] = int(weekly.get(week_key, 0)) + 1

                data["last_updated"] = now.strftime("%Y-%m-%d %H:%M:%S")
                data["last_seen"] = data["last_updated"]
                _refresh_summary(data)
                return _write_raw(user_id, data)
        except Exception as e:
            logger.error(f"update_user_message 失败 {user_id}: {e}")
            return False

    def get_user_today_count(self, user_id: str, group_id: str) -> int:
        data = _read_raw(user_id) or {}
        today = datetime.now().strftime("%Y-%m-%d")
        return int((data.get("daily_records", {}).get(str(group_id), {}) or {}).get(today, 0))

    def get_user_week_count(self, user_id: str, group_id: str) -> int:
        data = _read_raw(user_id) or {}
        week_key = _week_key_of(datetime.now().strftime("%Y-%m-%d"))
        return int((data.get("weekly_records", {}).get(str(group_id), {}) or {}).get(week_key, 0))

    def get_user_group_stats(self, user_id: str, group_id: str) -> Dict[str, Any]:
        data = _read_raw(user_id) or {}
        group_id = str(group_id)
        dates = data.get("daily_records", {}).get(group_id, {}) or {}

        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        week_end = (now + timedelta(days=6 - now.weekday())).strftime("%Y-%m-%d")

        daily_details = {
            date: int(count)
            for date, count in sorted(dates.items())
            if week_start <= date <= week_end
        }
        return {
            "today": int(dates.get(today, 0)),
            "week_total": sum(daily_details.values()),
            "daily_details": daily_details,
            "total_messages": sum(int(c) for c in dates.values()),
            "total_weeks": len({_week_key_of(d) for d in dates}),
        }

    def get_user_month_count(self, user_id: str, group_id: str, year: int = None, month: int = None) -> int:
        if year is None or month is None:
            now = datetime.now()
            year = year or now.year
            month = month or now.month
        prefix = f"{year:04d}-{month:02d}-"
        data = _read_raw(user_id) or {}
        dates = data.get("daily_records", {}).get(str(group_id), {}) or {}
        return sum(int(c) for d, c in dates.items() if d.startswith(prefix))

    def get_user_year_count(self, user_id: str, group_id: str, year: int = None) -> int:
        if year is None:
            year = datetime.now().year
        prefix = f"{year:04d}-"
        data = _read_raw(user_id) or {}
        dates = data.get("daily_records", {}).get(str(group_id), {}) or {}
        return sum(int(c) for d, c in dates.items() if d.startswith(prefix))

    def get_daily_rankings(self, group_id: str, date_str: str = None) -> List[Tuple[str, int]]:
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        group_id = str(group_id)
        rankings = []
        for user_id, data in iter_user_data():
            count = int((data.get("daily_records", {}).get(group_id, {}) or {}).get(date_str, 0))
            if count > 0:
                rankings.append((user_id, count))
        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings

    def get_weekly_rankings(self, group_id: str) -> List[Tuple[str, int]]:
        week_key = _week_key_of(datetime.now().strftime("%Y-%m-%d"))
        group_id = str(group_id)
        rankings = []
        for user_id, data in iter_user_data():
            count = int((data.get("weekly_records", {}).get(group_id, {}) or {}).get(week_key, 0))
            if count > 0:
                rankings.append((user_id, count))
        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings

    def get_historical_weekly_rankings(self, group_id: str, week_identifier: str) -> Tuple[List[Tuple[str, int]], str]:
        week_key, week_info = _parse_week_key(week_identifier)
        if week_key is None:
            return [], week_info
        group_id = str(group_id)
        rankings = []
        for user_id, data in iter_user_data():
            count = int((data.get("weekly_records", {}).get(group_id, {}) or {}).get(week_key, 0))
            if count > 0:
                rankings.append((user_id, count))
        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings, week_info

    def get_monthly_rankings(self, group_id: str, year: int = None, month: int = None) -> List[Tuple[str, int]]:
        if year is None or month is None:
            now = datetime.now()
            year = year or now.year
            month = month or now.month
        prefix = f"{year:04d}-{month:02d}-"
        return self._rankings_by_date_prefix(group_id, prefix)

    def get_monthly_rankings_by_start_date(self, group_id: str, start_date_str: str) -> List[Tuple[str, int]]:
        try:
            dt = datetime.strptime(start_date_str, "%Y-%m-%d")
        except ValueError:
            return []
        return self.get_monthly_rankings(group_id, dt.year, dt.month)

    def get_yearly_rankings(self, group_id: str, year: int = None) -> List[Tuple[str, int]]:
        if year is None:
            year = datetime.now().year
        return self._rankings_by_date_prefix(group_id, f"{year:04d}-")

    def get_seasonal_rankings(self, group_id: str, year: int = None, season: int = None) -> List[Tuple[str, int]]:
        if year is None:
            year = datetime.now().year
        if season is None:
            season = (datetime.now().month - 1) // 3 + 1
        month_start = (season - 1) * 3 + 1
        month_end = month_start + 2
        group_id = str(group_id)

        rankings = []
        for user_id, data in iter_user_data():
            dates = data.get("daily_records", {}).get(group_id, {}) or {}
            count = 0
            for date_str, value in dates.items():
                try:
                    d = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    continue
                if d.year == year and month_start <= d.month <= month_end:
                    count += int(value)
            if count > 0:
                rankings.append((user_id, count))
        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings

    def _rankings_by_date_prefix(self, group_id: str, prefix: str) -> List[Tuple[str, int]]:
        group_id = str(group_id)
        rankings = []
        for user_id, data in iter_user_data():
            dates = data.get("daily_records", {}).get(group_id, {}) or {}
            count = sum(int(c) for d, c in dates.items() if d.startswith(prefix))
            if count > 0:
                rankings.append((user_id, count))
        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings

    def set_username(self, user_id: str, new_username: str) -> bool:
        try:
            with _get_lock(user_id):
                data = _read_raw(user_id)
                if data is None:
                    return False
                data["username"] = new_username
                data["last_updated"] = _now_str()
                data["last_seen"] = data["last_updated"]
                _refresh_summary(data)
                return _write_raw(user_id, data)
        except Exception as e:
            logger.error(f"设置用户名失败 {user_id}: {e}")
            return False

    def search_user_by_username(self, username: str) -> Optional[str]:
        for user_id, data in iter_user_data():
            if data.get("username") == username:
                return user_id
        return None

    def check_in(self, user_id: str, username: str = "") -> Dict[str, Any]:
        """每日签到（签到数据以 JSON 文件存放于插件 data/checkin 目录）"""
        return checkin_manager.check_in(user_id, username)


# ========== 日志管理类 ==========

class LogManager:
    """日志管理器"""

    def __init__(self):
        base_logs_dir = SpeechConfig.LOGS_DIR
        year = datetime.now().strftime("%Y")
        self.logs_dir = os.path.join(base_logs_dir, year)
        os.makedirs(self.logs_dir, exist_ok=True)
        self.log_file = os.path.join(self.logs_dir, SpeechConfig.get_log_filename())

    def log_message(self, user_id: str, username: str, group_id: str,
                    daily_count: int, week_total: int):
        """记录发言日志"""
        if not SpeechConfig.ENABLE_LOGGING:
            return

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        current_date = datetime.now().strftime("%Y-%m-%d")
        current_week_key = _week_key_of(current_date)

        log_entry = (
            f"[{current_time}] 用户 {username}({user_id}) 于 {current_date} "
            f"在群 {group_id} 发言，今日: {daily_count}, "
            f"本周({current_week_key}): {week_total}\n"
        )

        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            logger.error(f"写入日志失败: {e}")


# 全局实例
user_manager = UserDataManager()
log_manager = LogManager()
