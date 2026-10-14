"""
RqhBot SDK —— 核心模块
提供客户端连接、API 调用、事件模型等基础能力
"""

from __future__ import annotations

from .client import MessageSegment, NapCatClient, OneBotClient
from .event_bus import EventBus
from .events import (
    BaseEvent,
    EssenceMsgNotice,
    FriendAddNotice,
    FriendRecallNotice,
    FriendRequestEvent,
    GroupAdminNotice,
    GroupBanNotice,
    GroupCardNotice,
    GroupDecreaseNotice,
    GroupIncreaseNotice,
    GroupMessageEvent,
    GroupRecallNotice,
    GroupRequestEvent,
    GroupUploadNotice,
    Message,
    NoticeEvent,
    PokeNotice,
    PrivateMessageEvent,
    RequestEvent,
)

__all__: list[str] = [
    "MessageSegment",
    "OneBotClient",
    "NapCatClient",
    "EventBus",
    "BaseEvent",
    "Message",
    "GroupMessageEvent",
    "PrivateMessageEvent",
    "NoticeEvent",
    "GroupIncreaseNotice",
    "GroupDecreaseNotice",
    "GroupBanNotice",
    "GroupRecallNotice",
    "FriendRecallNotice",
    "GroupAdminNotice",
    "GroupUploadNotice",
    "GroupCardNotice",
    "FriendAddNotice",
    "EssenceMsgNotice",
    "PokeNotice",
    "RequestEvent",
    "FriendRequestEvent",
    "GroupRequestEvent",
]
