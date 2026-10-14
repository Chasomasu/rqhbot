"""
RqhBot SDK —— 配置模块
提供配置管理、OneBot 后端注册表与日志设置
"""

from __future__ import annotations

from .backends import BACKENDS, DEFAULT_BACKEND, BackendSpec, get_backend
from .config import (
    Config,
    ConfigManager,
    config_manager,
    get_logger,
    setup_logging,
)

__all__: list[str] = [
    "Config",
    "ConfigManager",
    "config_manager",
    "setup_logging",
    "get_logger",
    "BackendSpec",
    "BACKENDS",
    "DEFAULT_BACKEND",
    "get_backend",
]
