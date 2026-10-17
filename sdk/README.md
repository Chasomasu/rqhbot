# RqhBot SDK 模块化结构说明

## 📖 简介

RqhBot SDK 是一个基于 OneBot 11 协议的 Python QQ 机器人开发框架，支持 NapCat / SnowLuma 等后端，采用模块化设计，提供简洁易用的 API、强大的插件系统和事件驱动的架构。

## 📁 目录结构

```
sdk/
├── __init__.py              # 主模块入口，导出核心类
├── bot_client.py            # BotClient 核心类，整合所有功能
├── core/                    # 核心模块
│   ├── __init__.py          # 核心模块导出
│   ├── client.py           # OneBotClient - WebSocket 客户端 / MessageSegment
│   ├── emoji_map.py        # QQ 表情 ID → 名称映射
│   ├── events.py           # 强类型事件与 Message 定义
│   ├── event_bus.py        # 事件总线（EventBus）
│   └── interfaces.py       # 接口定义（IClient 等）
├── pluginsystem/            # 插件系统模块
│   ├── __init__.py          # 插件系统导出
│   ├── plugin_base.py      # PluginBase / PluginManager / filter_registry
│   └── plugin_manager.py   # HotReloadPluginManager 热重载管理器
└── config/                  # 配置模块
    ├── __init__.py          # 配置模块导出
    ├── backends.py          # OneBot 后端注册表（NapCat / SnowLuma）
    └── config.py           # 配置管理和日志设置
```

## 🧩 模块说明

### 核心模块 (sdk.core)

提供机器人核心功能：

- **OneBotClient**: WebSocket 客户端（别名 `NapCatClient`），负责与选定的 OneBot 后端（NapCat / SnowLuma）建立连接、收发消息并封装常用 OneBot API 调用
- **MessageSegment**: 消息段构建器，用于构造数组格式的图文混排消息
- **Event classes**: 强类型事件，包括 GroupMessageEvent、PrivateMessageEvent 等（含 Message 对象）
- **EventBus**: 事件总线，实现模块间的解耦通信
- **Interfaces**: 接口定义，包括 `IClient`、`IConnectionEventListener`

### 插件系统模块 (sdk.pluginsystem)

提供插件开发功能：

- **PluginBase**: 插件基类，所有插件必须继承此类
- **PluginManager**: 插件管理器，负责插件的加载、卸载和管理
- **filter_registry**: 过滤器注册表实例，用于消息过滤和路由（`group_server` / `private_server` / `message_filter`）

### 配置模块 (sdk.config)

提供配置和日志功能：

- **Config**: 配置管理类，支持 YAML 配置文件和环境变量
- **get_backend**: OneBot 后端注册表查询（`BackendSpec` / `BACKENDS` / `DEFAULT_BACKEND`）
- **setup_logging**: 日志设置函数，支持按日期分隔的日志文件

## 🚀 使用方法

### 导入核心模块

```python
# 方式一：从子模块导入
from sdk.bot_client import BotClient
from sdk.core import OneBotClient, MessageSegment, GroupMessageEvent

# 方式二：从主模块导入（推荐）
from sdk import BotClient, GroupMessageEvent
```

### 导入插件系统

```python
# 方式一：从子模块导入
from sdk.pluginsystem import PluginBase, PluginManager

# 方式二：从主模块导入（推荐）
from sdk import PluginBase, PluginManager
```

### 导入配置

```python
# 方式一：从子模块导入
from sdk.config import Config, setup_logging

# 方式二：从主模块导入（推荐）
from sdk import Config, setup_logging
```

### 统一导入（推荐）

```python
from sdk import (
    BotClient,           # 机器人客户端
    PluginBase,          # 插件基类
    PluginManager,       # 插件管理器
    EventBus,            # 事件总线
    GroupMessageEvent,   # 群消息事件
    PrivateMessageEvent, # 私聊消息事件
    Config,              # 配置管理
    setup_logging,       # 日志设置
    filter_registry,     # 过滤器注册表
)

# MessageSegment 由 sdk.core 导出
from sdk.core import MessageSegment
```

## 💡 快速示例

### 创建简单机器人

```python
from sdk import BotClient, GroupMessageEvent
from sdk.config import config_manager

# 创建机器人实例
bot = BotClient()

# 定义群消息处理函数
@bot.on_group_message()
async def handle_message(msg: GroupMessageEvent):
    text = msg.message.plain_text.strip()
    
    if text == "ping":
        await bot.api.send_group_message(
            group_id=msg.group_id,
            message="pong!"
        )
    elif text == "hello":
        await bot.api.send_group_message(
            group_id=msg.group_id,
            message=f"你好 {msg.user_name}！"
        )

if __name__ == "__main__":
    # 从配置读取 WebSocket 地址
    ws_url = config_manager.get("napcat.ws_url", "ws://localhost:3001")
    bot.client.ws_url = ws_url
    
    # 启动机器人
    bot.start(load_plugins=False)
```

### 创建插件

```python
import logging
from sdk import PluginBase, filter_registry
from sdk.core.events import GroupMessageEvent, PrivateMessageEvent

logger = logging.getLogger(__name__)

class HelloPlugin(PluginBase):
    def __init__(self):
        super().__init__()
        self.name = "hello"
        self.version = "1.0.0"
        self.description = "Hello World 插件"
        self.author = "Your Name"

    @filter_registry.group_server(equals="你好")
    async def hello_group(self, event: GroupMessageEvent):
        await self.reply_with_event(event, "你好！我是群聊机器人")

    @filter_registry.private_server(equals="你好")
    async def hello_private(self, event: PrivateMessageEvent):
        await self.reply_with_event(event, "你好！我是私聊机器人")
```

## 🔗 相关文档

- [项目概述](../docs/02_OVERVIEW.md) - 了解 RqhBot 整体架构
- [快速开始](../docs/03_QUICK_START.md) - 5分钟上手指南
- [配置指南](../docs/04_CONFIG_GUIDE.md) - 配置系统详解
- [API 参考](../docs/05_API.md) - 完整 API 文档
- [插件开发](../docs/06_PLUGIN_DEVELOPMENT.md) - 插件开发指南

## 📋 版本信息

- **当前版本**: 3.8.0
- **最后更新**: 2026-05-16
- **Python 要求**: >= 3.10
- **依赖库**: websockets, aiohttp, PyYAML, python-dotenv, requests, packaging
