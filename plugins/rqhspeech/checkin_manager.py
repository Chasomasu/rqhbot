"""
签到数据管理 - JSON 文件版

签到数据以 {user_id}.json 的形式存放在插件自己的 data/checkin 目录内。
"""

import os
import json
import threading
import logging
from datetime import datetime, timedelta
from typing import Any, Dict

from .speech_config import SpeechConfig

logger = logging.getLogger(__name__)


class CheckinManager:
    """负责签到数据的读写与积分计算"""

    def __init__(self, data_dir: str = None, base_points: int = 10, consecutive_bonus: int = 5):
        self.data_dir = data_dir or os.path.join(SpeechConfig.DATA_DIR, "checkin")
        self.base_points = base_points
        self.consecutive_bonus = consecutive_bonus
        self._lock = threading.Lock()
        os.makedirs(self.data_dir, exist_ok=True)

    def get_user_file(self, user_id: str) -> str:
        return os.path.join(self.data_dir, f"{user_id}.json")

    def load_user_data(self, user_id: str) -> dict:
        path = self.get_user_file(user_id)
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"读取签到数据 {user_id} 失败: {e}")
            return {}

    def save_user_data(self, user_id: str, data: dict) -> None:
        path = self.get_user_file(user_id)
        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except Exception as e:
            logger.error(f"保存签到数据 {user_id} 失败: {e}")

    def check_in(self, user_id: str, username: str = "") -> Dict[str, Any]:
        """每日签到，返回签到结果（同日重复签到返回 success=False）"""
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        with self._lock:
            data = self.load_user_data(user_id)
            if not data:
                data = {
                    "user_id": user_id,
                    "user_name": username,
                    "first_checkin_time": now_str,
                    "total_checkins": 0,
                    "consecutive_checkins": 0,
                    "last_checkin_date": "",
                    "points": 0,
                    "checkin_history": [],
                    "last_checkin_time": "",
                }

            if data.get("last_checkin_date") == today:
                return {
                    "success": False,
                    "total_points": data.get("points", 0),
                    "consecutive_days": data.get("consecutive_checkins", 0),
                    "total_checkins": data.get("total_checkins", 0),
                    "last_checkin_time": data.get("last_checkin_time", ""),
                }

            if data.get("last_checkin_date") == yesterday:
                consecutive = data.get("consecutive_checkins", 0) + 1
            else:
                consecutive = 1
            earned = self.base_points + (consecutive - 1) * self.consecutive_bonus

            data["user_id"] = user_id
            data["user_name"] = username or data.get("user_name", "")
            data["last_checkin_date"] = today
            data["total_checkins"] = data.get("total_checkins", 0) + 1
            data["consecutive_checkins"] = consecutive
            data["points"] = data.get("points", 0) + earned
            data["last_checkin_time"] = now_str
            data["first_checkin_time"] = data.get("first_checkin_time") or now_str

            history = data.get("checkin_history", [])
            history.append({
                "date": today,
                "time": now.strftime("%H:%M:%S"),
                "points_earned": earned,
                "consecutive_days": consecutive,
            })
            data["checkin_history"] = history[-30:]
            self.save_user_data(user_id, data)

        return {
            "success": True,
            "points_earned": earned,
            "total_points": data["points"],
            "consecutive_days": consecutive,
            "total_checkins": data["total_checkins"],
            "checkin_time": now_str,
        }


checkin_manager = CheckinManager()
