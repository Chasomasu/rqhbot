"""
OneBot 后端注册表

NapCat 与 SnowLuma 均通过 OneBot 11 正向 WebSocket 暴露接口，
差异仅在默认端口与是否支持由框架自动启动。此处登记各后端的元信息，
供配置解析与启动流程按顶层 ``adapter`` 字段自选后端。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BackendSpec:
    """OneBot 后端描述"""

    name: str
    display_name: str
    config_section: str
    default_ws_uri: str
    auto_start_capable: bool


BACKENDS: dict[str, BackendSpec] = {
    "napcat": BackendSpec(
        name="napcat",
        display_name="NapCat",
        config_section="napcat",
        default_ws_uri="ws://localhost:3002",
        auto_start_capable=True,
    ),
    "snowluma": BackendSpec(
        name="snowluma",
        display_name="SnowLuma",
        config_section="snowluma",
        default_ws_uri="ws://localhost:3001",
        auto_start_capable=False,
    ),
}

DEFAULT_BACKEND: str = "napcat"


def get_backend(name: str | None = None) -> BackendSpec:
    """按名称获取后端描述，缺省返回默认后端。

    Args:
        name: 后端名称（不区分大小写），None/空串时返回默认后端。

    Returns:
        对应的 ``BackendSpec``。

    Raises:
        ValueError: 名称不在 ``BACKENDS`` 中。
    """
    key: str = (name or DEFAULT_BACKEND).strip().lower()
    spec: BackendSpec | None = BACKENDS.get(key)
    if spec is None:
        raise ValueError(
            f"未知的适配器后端: {name!r}，可选值: {', '.join(BACKENDS)}"
        )
    return spec
