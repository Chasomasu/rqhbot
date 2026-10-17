# 项目概述

## 🤖 什么是 RqhBot？

RqhBot 是一个基于 NapCat OneBot11 协议的 Python QQ 机器人 SDK，提供简洁的 API、强大的插件系统和事件驱动架构。采用模块化设计，支持热插拔插件。

## ✨ 核心特性

### 事件总线架构
- **EventBus**：模块间通过事件总线通信，彻底解耦
- 插件只依赖 `IClient` 接口，不持有 `BotClient` 引用
- 支持任意模块订阅/发布事件

### 强类型事件
- `GroupMessageEvent`、`PrivateMessageEvent` 等均为强类型 dataclass
- `Message` 对象自动解析 20+ 种消息段类型（text/image/video/record/file/forward/music/json/xml/markdown 等）
- `NoticeEvent` 细分：`GroupIncreaseNotice`、`GroupBanNotice`、`GroupAdminNotice`、`GroupCardNotice`、`EssenceMsgNotice` 等
- `RequestEvent` 细分：`FriendRequestEvent`、`GroupRequestEvent`
- 自动按类型分发，无需手动解析原始 dict

### 简洁的 API 设计
- 直观的接口，完整类型提示
- 异步编程模型
- `NapCatClient.call()` 支持调用任意 OneBot API

### 插件系统
- 热插拔架构，支持 `filter_registry.group_server` / `filter_registry.private_server` 消息过滤器
- 标准化接口（只依赖 `IClient` + `EventBus`）
- 内置配置加载与数据持久化

### 灵活配置
- YAML 配置文件 + 环境变量
- 动态配置更新
- 完善的日志系统（按日期分隔）

## 📁 项目结构

```
rqhbot/
├── sdk/                    # SDK 核心
│   ├── core/              # 客户端、事件模型、事件总线
│   ├── config/            # 配置管理
│   └── pluginsystem/      # 插件基类与热加载管理器
├── plugins/               # 插件目录
│   ├── group_summary/     # 群总结
│   ├── pintu/             # 九宫格拼图
│   ├── rqhmain/           # 综合（天气/新闻/运势）
│   ├── rqhshen/           # 修仙游戏
│   ├── rqhspeech/         # 发言统计
│   └── rqhwenda/          # 关键字问答
├── docs/                  # 文档
├── config.yaml.example    # 配置示例
├── requirements.txt       # 依赖
└── run.py                 # 入口
```

## 🎯 适用场景

- QQ 群自动回复与群管理
- AI 聊天接入、消息推送
- 数据统计与自动化工作流

## 🔧 技术栈

- Python 3.10+ · websockets · aiohttp · PyYAML · python-dotenv · requests · packaging

## 📊 架构设计

```
┌─────────────────┐
│     NapCat      │ ← WebSocket
└────────┬────────┘
         ▼
┌─────────────────┐
│  NapCatClient   │ ← 连接 + API（实现 IClient Protocol）
└────────┬────────┘
         ▼
┌─────────────────┐
│    EventBus     │ ← 发布强类型事件，模块解耦
└──┬──────────┬───┘
   ▼          ▼
┌─────────┐  ┌──────────────┐
│BotClient│  │PluginManager │ ← 管理所有插件
└─────────┘  └──────┬───────┘
                    ▼
              ┌──────────┐
              │ Plugins  │ ← 只依赖 IClient + EventBus
              └──────────┘
```

**关键原则：** `NapCatClient` 负责连接和 API，`EventBus` 是模块通信唯一中介，插件只依赖 `IClient` 接口（由 `NapCatClient` 实现）。

---

**版本**: 3.8.0 | **更新**: 2026-06
