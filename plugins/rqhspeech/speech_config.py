"""
配置管理模块 - 统一管理所有配置常量和目录结构

功能特性：
1. 统一配置管理
2. 按年分层的目录结构
3. 支持管理员和操作员权限
4. 支持白名单模式
5. 数据目录迁移功能
"""

import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class SpeechConfig:
    """配置类 - 封装所有配置常量"""

    def __init__(self):
        # ========== 基础目录 ==========
        self.BASE_DIR = os.path.dirname(os.path.abspath(__file__))

        # 执行旧数据迁移
        self._migrate_old_data()

        # 统一数据根目录
        self.DATA_DIR = os.path.join(self.BASE_DIR, "data")
        self.USERS_DIR = os.path.join(self.DATA_DIR, "users")

        # 历史归档
        self.ARCHIVES_DIR = os.path.join(self.DATA_DIR, "archives")
        self.RANKINGS_DIR = os.path.join(self.ARCHIVES_DIR, "rankings")
        self.CSV_DIR = os.path.join(self.ARCHIVES_DIR, "csv")
        self.BACKUPS_DIR = os.path.join(self.ARCHIVES_DIR, "backups")

        # 配置文件目录
        self.CONFIG_DIR = os.path.join(self.DATA_DIR, "config")
        self.CONFIG_FILE = os.path.join(self.CONFIG_DIR, "speech_config.json")

        # 日志目录
        self.LOGS_DIR = os.path.join(self.BASE_DIR, "logs")

        # 功能模式（需在加载配置前初始化，加载时会被 JSON 中的值覆盖）
        self.USE_WHITELIST_MODE = False

        # 允许的群聊列表
        self.ALLOWED_GROUPS = self._load_allowed_groups()

        # 管理员列表
        self.ADMIN_USERS = self._load_admin_users()
        # 操作员列表
        self.OPERATOR_USERS = self._load_operator_users()

        # 文件扩展名
        self.USER_FILE_EXTENSION = ".json"
        self.RANKING_FILE_EXTENSION = ".json"
        self.CSV_FILE_EXTENSION = ".csv"
        self.LOG_FILE_EXTENSION = ".log"

        # 排行榜配置
        self.RANKING_TOP_N = 20
        self.RANKING_DAILY_TOP_N = 15
        self.RANKING_WEEKLY_TOP_N = 10
        self.RANKING_MONTHLY_TOP_N = 10
        self.RANKING_SEASONAL_TOP_N = 10
        self.RANKING_YEARLY_TOP_N = 10
        self.MIN_MESSAGES_FOR_RANKING = 1

        # 日期时间格式
        self.DATE_FORMAT = "%Y-%m-%d"
        self.DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
        self.DISPLAY_DATE_FORMAT = "%Y年%m月%d日"

        # 功能开关
        self.ARCHIVE_DAILY = True
        self.BACKUP_BEFORE_ARCHIVE = False
        self.ENABLE_LOGGING = True

        # 初始化所有目录
        self._init_directories()

    def _load_config_from_json(self):
        """从 JSON 文件加载配置"""
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                groups = set(str(g) for g in config.get("allowed_groups", []))
                admins = set(str(u) for u in config.get("admin_users", []))
                operators = set(str(u) for u in config.get("operator_users", []))
                self.USE_WHITELIST_MODE = config.get("use_whitelist_mode", False)
                return groups, admins, operators
            except Exception as e:
                logger.warning(f"从 JSON 加载配置失败: {e}")

        return set(), set(), set()

    def _save_config_to_json(self):
        """保存配置到 JSON 文件"""
        try:
            config = {
                "allowed_groups": sorted(self.ALLOWED_GROUPS),
                "admin_users": sorted(self.ADMIN_USERS),
                "operator_users": sorted(self.OPERATOR_USERS),
                "use_whitelist_mode": self.USE_WHITELIST_MODE,
            }
            os.makedirs(self.CONFIG_DIR, exist_ok=True)
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存配置到 JSON 失败: {e}")

    def _load_allowed_groups(self):
        groups, admins, operators = self._load_config_from_json()
        return groups

    def _load_admin_users(self):
        groups, admins, operators = self._load_config_from_json()
        return admins

    def _load_operator_users(self):
        groups, admins, operators = self._load_config_from_json()
        return operators

    def add_allowed_group(self, group_id):
        """添加允许的群聊"""
        self.ALLOWED_GROUPS.add(str(group_id))
        self._save_config_to_json()

    def remove_allowed_group(self, group_id):
        """移除允许的群聊"""
        self.ALLOWED_GROUPS.discard(str(group_id))
        self._save_config_to_json()

    def add_admin_user(self, user_id):
        """添加管理员"""
        self.ADMIN_USERS.add(str(user_id))
        self._save_config_to_json()

    def remove_admin_user(self, user_id):
        """移除管理员"""
        self.ADMIN_USERS.discard(str(user_id))
        self._save_config_to_json()

    def add_operator_user(self, user_id):
        """添加操作员"""
        self.OPERATOR_USERS.add(str(user_id))
        self._save_config_to_json()

    def remove_operator_user(self, user_id):
        """移除操作员"""
        self.OPERATOR_USERS.discard(str(user_id))
        self._save_config_to_json()

    def _save_allowed_groups(self):
        """保存配置（兼容旧接口）"""
        self._save_config_to_json()

    def get_allowed_groups_list(self):
        """获取允许的群聊列表（返回列表格式）"""
        return list(self.ALLOWED_GROUPS)

    def _init_directories(self):
        """初始化所有需要的顶层目录"""
        directories = [
            self.DATA_DIR,
            self.USERS_DIR,
            self.ARCHIVES_DIR,
            self.RANKINGS_DIR,
            self.CSV_DIR,
            self.BACKUPS_DIR,
            self.CONFIG_DIR,
            self.LOGS_DIR
        ]
        for directory in directories:
            os.makedirs(directory, exist_ok=True)

    def _migrate_old_data(self):
        """
        迁移旧版本数据到新目录结构
        当前核心数据已统一到 user 文件，不再迁移 daily/weekly 统计文件
        """
        import shutil
        global logger

        old_base_data = os.path.join(self.BASE_DIR, "base_data")
        old_config_file = os.path.join(self.BASE_DIR, "speech_config.json")
        old_logs_dir = os.path.join(self.BASE_DIR, "logs")

        new_data_dir = os.path.join(self.BASE_DIR, "data")
        new_users_dir = os.path.join(new_data_dir, "users")
        new_config_dir = os.path.join(new_data_dir, "config")
        new_config_file = os.path.join(new_config_dir, "speech_config.json")

        migrated = False

        # 迁移 base_data/ 下的用户数据
        if os.path.exists(old_base_data):
            old_users_dir = os.path.join(old_base_data, "users")
            if os.path.exists(old_users_dir):
                os.makedirs(new_users_dir, exist_ok=True)
                for fname in os.listdir(old_users_dir):
                    if fname.endswith(".json"):
                        src = os.path.join(old_users_dir, fname)
                        dst = os.path.join(new_users_dir, fname)
                        if not os.path.exists(dst):
                            shutil.move(src, dst)
                logger.info(f"已迁移用户数据: {old_users_dir} -> {new_users_dir}")
                migrated = True

            # 清理旧的 base_data 目录
            try:
                shutil.rmtree(old_base_data)
                logger.info(f"已清理旧目录: {old_base_data}")
            except Exception as e:
                logger.warning(f"无法清理旧目录 {old_base_data}: {e}")

        # 迁移根目录下的配置文件
        if os.path.exists(old_config_file):
            os.makedirs(new_config_dir, exist_ok=True)
            if not os.path.exists(new_config_file):
                shutil.move(old_config_file, new_config_file)
                logger.info(f"已迁移配置文件: {old_config_file} -> {new_config_file}")
                migrated = True

        # 迁移日志文件（按年分层）
        if os.path.exists(old_logs_dir):
            for fname in os.listdir(old_logs_dir):
                if fname.startswith("speech_") and fname.endswith(".log"):
                    try:
                        date_str = fname[7:-4]
                        year = date_str.split("-")[0]
                        target_dir = os.path.join(old_logs_dir, year)
                        os.makedirs(target_dir, exist_ok=True)
                        src = os.path.join(old_logs_dir, fname)
                        dst = os.path.join(target_dir, fname)
                        if not os.path.exists(dst):
                            shutil.move(src, dst)
                    except (ValueError, IndexError):
                        continue
            logger.info("已按年分层日志文件")
            migrated = True

        if migrated:
            logger.info("rqhspeech 数据目录结构迁移完成！")

    def get_current_date(self):
        """获取当前日期字符串"""
        return datetime.now().strftime(self.DATE_FORMAT)

    def get_current_datetime(self):
        """获取当前日期时间字符串"""
        return datetime.now().strftime(self.DATETIME_FORMAT)

    def get_daily_archive_dir(self, date=None):
        """获取指定日期的归档目录"""
        if date is None:
            date = self.get_current_date()
        return os.path.join(self.ARCHIVES_DIR, date)

    def get_ranking_filename(self, date=None):
        """获取排行榜文件名"""
        if date is None:
            date = self.get_current_date()
        return f"ranking_{date}{self.RANKING_FILE_EXTENSION}"

    def get_weekly_ranking_filename(self, week_key: str) -> str:
        """获取周榜JSON文件名"""
        return f"ranking_{week_key}{self.RANKING_FILE_EXTENSION}"

    def get_csv_filename(self, date=None):
        """获取CSV文件名"""
        if date is None:
            date = self.get_current_date()
        return f"ranking_{date}{self.CSV_FILE_EXTENSION}"

    def get_weekly_csv_filename(self, week_key: str) -> str:
        """获取周榜CSV文件名"""
        return f"ranking_{week_key}{self.CSV_FILE_EXTENSION}"

    def get_log_filename(self):
        """获取日志文件名"""
        return f"speech_{self.get_current_date()}{self.LOG_FILE_EXTENSION}"

    def is_allowed_group(self, group_id):
        """检查群聊是否在允许列表中"""
        if not self.USE_WHITELIST_MODE:
            return True
        return str(group_id) in self.ALLOWED_GROUPS

    def is_admin(self, user_id):
        """检查用户是否为管理员"""
        return str(user_id) in self.ADMIN_USERS

    def is_operator(self, user_id):
        """检查用户是否为操作员"""
        return str(user_id) in self.OPERATOR_USERS

    def is_any_admin(self, user_id):
        """检查用户是否为管理员或操作员"""
        return self.is_admin(user_id) or self.is_operator(user_id)


# 全局配置实例
SpeechConfig = SpeechConfig()

# 为了兼容旧代码，导出所有配置项
BASE_DIR = SpeechConfig.BASE_DIR
DATA_DIR = SpeechConfig.DATA_DIR
USERS_DIR = SpeechConfig.USERS_DIR
ARCHIVES_DIR = SpeechConfig.ARCHIVES_DIR
RANKINGS_DIR = SpeechConfig.RANKINGS_DIR
CSV_DIR = SpeechConfig.CSV_DIR
BACKUPS_DIR = SpeechConfig.BACKUPS_DIR
CONFIG_DIR = SpeechConfig.CONFIG_DIR
LOGS_DIR = SpeechConfig.LOGS_DIR
ALLOWED_GROUPS = SpeechConfig.ALLOWED_GROUPS
ADMIN_USERS = SpeechConfig.ADMIN_USERS
USER_FILE_EXTENSION = SpeechConfig.USER_FILE_EXTENSION
RANKING_FILE_EXTENSION = SpeechConfig.RANKING_FILE_EXTENSION
CSV_FILE_EXTENSION = SpeechConfig.CSV_FILE_EXTENSION
LOG_FILE_EXTENSION = SpeechConfig.LOG_FILE_EXTENSION
RANKING_TOP_N = SpeechConfig.RANKING_TOP_N
RANKING_DAILY_TOP_N = SpeechConfig.RANKING_DAILY_TOP_N
RANKING_WEEKLY_TOP_N = SpeechConfig.RANKING_WEEKLY_TOP_N
MIN_MESSAGES_FOR_RANKING = SpeechConfig.MIN_MESSAGES_FOR_RANKING
DATE_FORMAT = SpeechConfig.DATE_FORMAT
DATETIME_FORMAT = SpeechConfig.DATETIME_FORMAT
DISPLAY_DATE_FORMAT = SpeechConfig.DISPLAY_DATE_FORMAT
ARCHIVE_DAILY = SpeechConfig.ARCHIVE_DAILY
BACKUP_BEFORE_ARCHIVE = SpeechConfig.BACKUP_BEFORE_ARCHIVE
ENABLE_LOGGING = SpeechConfig.ENABLE_LOGGING
get_current_date = SpeechConfig.get_current_date
get_current_datetime = SpeechConfig.get_current_datetime
get_ranking_filename = SpeechConfig.get_ranking_filename
get_csv_filename = SpeechConfig.get_csv_filename
get_log_filename = SpeechConfig.get_log_filename
is_allowed_group = SpeechConfig.is_allowed_group
is_admin = SpeechConfig.is_admin