"""
配置模块
YAML 配置管理、环境变量加载与日志系统，全部采用强类型声明
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Final, Optional, TypeAlias

import yaml
from dotenv import load_dotenv

from .backends import DEFAULT_BACKEND, get_backend

# 日志器
logger = logging.getLogger(__name__)

# 加载环境变量
_env_path: Path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

# ---- 类型别名 ----
YamlConfig: TypeAlias = Dict[str, Any]


class ConfigError(RuntimeError):
    """配置读写错误

    在「配置无法安全序列化」或「加载失败后拒绝写入」时抛出，
    避免把配置文件静默清空成 ``{}``。
    """


class ConfigManager:
    """YAML 配置管理器"""

    def __init__(self, config_path: str = "config.yaml") -> None:
        """初始化配置管理器

        Args:
            config_path: 配置文件路径
        """
        _raw: Path = Path(config_path)
        if not _raw.is_absolute():
            # 相对路径解析到项目根目录
            _raw = Path(__file__).parent.parent.parent / _raw
        self.config_path: Path = _raw
        self.config: YamlConfig = {}
        self._load_failed: bool = False
        self._load_config()

    def _load_config(self) -> None:
        """加载配置文件

        读取失败（YAML 语法错误、``safe_load`` 不认识的 ``!!python/...`` 标签等）
        时不会静默当成空配置：记录错误并置位 ``_load_failed``，让后续
        ``save()`` 拒绝写入，避免用 ``{}`` 覆盖磁盘上仍然有效的文件。
        """
        self._load_failed = False

        if not self.config_path.exists():
            self.config = {}
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                loaded: Any = yaml.safe_load(f)
        except Exception as e:
            self.config = {}
            self._load_failed = True
            logger.error(
                "[配置] 加载失败: %s：%s；已拒绝后续写入以避免覆盖该文件",
                self.config_path,
                e,
            )
            return

        if loaded is None:
            # 空文件视为空配置（可安全写入）
            self.config = {}
        elif isinstance(loaded, dict):
            self.config = loaded
        else:
            self.config = {}
            self._load_failed = True
            logger.error(
                "[配置] 加载失败: %s 顶层不是映射（实际为 %s）；已拒绝后续写入以避免覆盖该文件",
                self.config_path,
                type(loaded).__name__,
            )

    def _save_config(self) -> None:
        """保存配置文件（原子写入）

        用与 ``_load_config`` 对称的 ``yaml.safe_dump`` 序列化：无法安全表示的值
        会立即报错，而不是写成 ``safe_load`` 读不回来的 ``!!python/...`` 标签。
        先写同目录临时文件再 ``os.replace``，因此任何一步失败都不会截断现有配置。

        Raises:
            ConfigError: 加载曾失败（拒绝用空配置覆盖磁盘文件）或序列化失败。
        """
        if self._load_failed:
            raise ConfigError(
                f"[配置] {self.config_path} 加载失败，已拒绝写入以避免覆盖原文件；"
                "请修复该文件的 YAML 内容后调用 reload()"
            )

        try:
            text: str = yaml.safe_dump(
                self.config,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
        except yaml.YAMLError as e:
            message = f"[配置] 无法安全序列化为 YAML（存在不可表示的值）: {e}"
            logger.error(message)
            raise ConfigError(message) from e

        tmp_path: Path = self.config_path.with_name(self.config_path.name + ".tmp")
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.config_path)
        except Exception as e:
            logger.error("[配置] 保存失败: %s", e)
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
            raise

    # ---- 通用读写 ----

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值（支持点号分隔路径）

        Args:
            key: 配置键，如 'napcat.ws_url'
            default: 默认值

        Returns:
            配置值
        """
        keys: list[str] = key.split(".")
        value: Any = self.config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default

        return value if value is not None else default

    def set(self, key: str, value: Any) -> None:
        """设置配置值（支持点号分隔路径）

        路径中间若已存在的值不是映射（手写配置里常见的 ``napcat:``，即 null，
        或 ``napcat: "ws://x"`` 这类标量），会用新的空映射替换它并记录警告，
        保证写入行为可预测，而不是抛出裸 ``TypeError``。

        Args:
            key: 配置键
            value: 配置值
        """
        keys: list[str] = key.split(".")
        current: Dict[str, Any] = self.config

        for index, k in enumerate(keys[:-1]):
            child: Any = current.get(k)
            if not isinstance(child, dict):
                if child is not None:
                    logger.warning(
                        "[配置] %s 不是映射（实际为 %s），已替换为空映射以写入 %s",
                        ".".join(keys[: index + 1]),
                        type(child).__name__,
                        key,
                    )
                child = {}
                current[k] = child
            current = child

        current[keys[-1]] = value

    def save(self) -> None:
        """保存配置到文件"""
        self._save_config()

    def reload(self) -> None:
        """重新加载配置"""
        self._load_config()

    def show(self) -> None:
        """显示当前配置"""
        config_str = yaml.dump(
            self.config,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        logger.info("当前配置:\n%s", config_str)

    # ==================== 适配器后端配置 ====================

    def get_backend_name(self) -> str:
        """获取当前适配器后端名称（顶层 ``adapter`` 字段，缺省为默认后端）"""
        return get_backend(self.get("adapter") or DEFAULT_BACKEND).name

    def set_backend(self, name: str) -> None:
        """设置适配器后端（写入顶层 ``adapter`` 字段并保存）

        Args:
            name: 后端名称，如 "napcat" / "snowluma"

        Raises:
            ValueError: 名称不在已注册后端中。
        """
        self.set("adapter", get_backend(name).name)
        self._save_config()

    def get_ws_uri(self) -> str:
        """按当前后端读取 WebSocket 地址，缺省回落到该后端默认值"""
        backend = get_backend(self.get_backend_name())
        return self.get(f"{backend.config_section}.ws_url") or backend.default_ws_uri

    def get_ws_token(self) -> str:
        """按当前后端读取访问令牌，缺省为空串"""
        backend = get_backend(self.get_backend_name())
        return self.get(f"{backend.config_section}.access_token", "") or ""

    # ==================== NapCat 配置 ====================

    def set_bot_uin(self, bot_uin: str) -> None:
        """设置机器人 QQ 号"""
        self.set("napcat.bot_uin", bot_uin)
        self._save_config()

    def set_root(self, root: str) -> None:
        """设置根账号"""
        self.set("napcat.root", root)
        self._save_config()

    def set_ws_uri(self, ws_uri: str) -> None:
        """设置 WebSocket URI"""
        self.set("napcat.ws_url", ws_uri)
        self._save_config()

    def set_ws_token(self, ws_token: str) -> None:
        """设置 WebSocket Token"""
        self.set("napcat.access_token", ws_token)
        self._save_config()

    def set_webui_uri(self, webui_uri: str) -> None:
        """设置 WebUI URI"""
        self.set("napcat.webui_uri", webui_uri)
        self._save_config()

    def set_webui_token(self, webui_token: str) -> None:
        """设置 WebUI Token"""
        self.set("napcat.webui_token", webui_token)
        self._save_config()

    # ==================== Bot 配置 ====================

    def set_load_plugins(self, load_plugins: bool) -> None:
        """设置是否加载插件"""
        self.set("bot.load_plugins", load_plugins)
        self._save_config()

    def set_plugin_dir(self, plugin_dir: str) -> None:
        """设置插件目录"""
        self.set("bot.plugin_dir", plugin_dir)
        self._save_config()

    # ==================== 日志配置 ====================

    def set_log_level(self, level: str) -> None:
        """设置日志级别"""
        self.set("logging.level", level)
        self._save_config()

    def set_log_dir(self, log_dir: str) -> None:
        """设置日志目录"""
        self.set("logging.log_dir", log_dir)
        self._save_config()

    # ==================== 其他 ====================

    def set_debug(self, debug: bool) -> None:
        """设置调试模式"""
        self.set("settings.debug", debug)
        self._save_config()


# 全局配置实例
config_manager: ConfigManager = ConfigManager()


# ==================== 环境变量配置类 ====================

class Config:
    """环境变量配置类（兼容旧版）

    环境变量只在类定义时读取一次，提升性能。
    支持通过 reload_env() 热更新配置。
    """

    # 适配器连接配置（未设置时回落到所选后端的默认地址）
    NAPCAT_WS_URL: str = os.getenv("NAPCAT_WS_URL", "")
    NAPCAT_ACCESS_TOKEN: str = os.getenv("NAPCAT_ACCESS_TOKEN", "")

    # 日志配置
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = (
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    LOG_DIR: str = os.getenv("LOG_DIR", "logs")

    # 机器人配置
    BOT_DEBUG: bool = os.getenv("BOT_DEBUG", "false").lower() == "true"

    @classmethod
    def reload_env(cls, env_file: Optional[str] = None) -> None:
        """重新加载环境变量（热更新用）

        Args:
            env_file: 环境变量文件路径，默认项目根目录 .env
        """
        if env_file:
            load_dotenv(env_file, override=True)
        else:
            load_dotenv(Path(__file__).parent.parent / ".env", override=True)
        # 更新类属性
        cls.NAPCAT_WS_URL = os.getenv("NAPCAT_WS_URL", cls.NAPCAT_WS_URL)
        cls.NAPCAT_ACCESS_TOKEN = os.getenv("NAPCAT_ACCESS_TOKEN", cls.NAPCAT_ACCESS_TOKEN)
        cls.LOG_LEVEL = os.getenv("LOG_LEVEL", cls.LOG_LEVEL)
        cls.LOG_DIR = os.getenv("LOG_DIR", cls.LOG_DIR)
        cls.BOT_DEBUG = os.getenv("BOT_DEBUG", str(cls.BOT_DEBUG)).lower() == "true"

    @classmethod
    def get(cls, key: str, default: str = "") -> str:
        """获取配置值

        Args:
            key: 配置键名
            default: 默认值

        Returns:
            配置值
        """
        return os.getenv(key, default)

    @classmethod
    def get_bool(cls, key: str, default: bool = False) -> bool:
        """获取布尔配置值

        Args:
            key: 配置键名
            default: 默认值

        Returns:
            布尔配置值
        """
        raw: str = os.getenv(key, str(default)).lower()
        return raw in ("true", "1", "yes", "y")


# ==================== 日志系统 ====================

_logging_setup_done: bool = False


def setup_logging(
    log_level: Optional[str] = None,
    log_dir: Optional[str] = None,
    backup_count: int = 30,
) -> None:
    """设置日志系统（按日期轮转，保留最近30天，幂等调用）

    Args:
        log_level: 日志级别，默认从 Config 读取
        log_dir: 日志目录，默认从 Config 读取
        backup_count: 保留的日志文件数量，默认30
    """
    global _logging_setup_done
    if _logging_setup_done:
        return
    _logging_setup_done = True

    level: str = log_level if log_level is not None else Config.LOG_LEVEL
    directory: str = log_dir if log_dir is not None else Config.LOG_DIR

    # 创建日志目录
    log_path: Path = Path(directory)
    log_path.mkdir(parents=True, exist_ok=True)

    log_file: Path = log_path / "bot.log"

    # 根日志器
    root: logging.Logger = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    # 文件处理器（按日期轮转）
    fh: logging.handlers.TimedRotatingFileHandler = (
        logging.handlers.TimedRotatingFileHandler(
            str(log_file),
            when="midnight",
            interval=1,
            backupCount=backup_count,
            encoding="utf-8",
        )
    )
    fh.suffix = "%Y-%m-%d"
    fh.setLevel(getattr(logging, level.upper(), logging.INFO))
    fh.setFormatter(logging.Formatter(Config.LOG_FORMAT))
    root.addHandler(fh)

    # 控制台处理器
    ch: logging.StreamHandler = logging.StreamHandler()
    ch.setLevel(getattr(logging, level.upper(), logging.INFO))
    ch.setFormatter(logging.Formatter(Config.LOG_FORMAT))
    root.addHandler(ch)

    # 抑制第三方库日志
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """获取日志器

    Args:
        name: 日志器名称

    Returns:
        logging.Logger 实例
    """
    return logging.getLogger(name)
