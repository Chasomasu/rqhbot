# RqhBot

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)
![Version](https://img.shields.io/badge/Version-3.8.0-orange.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![OneBot](https://img.shields.io/badge/OneBot-11-00b894.svg)
![NapCat](https://img.shields.io/badge/NapCat-supported-6c5ce7.svg)

基于 **NapCat OneBot11** 协议的 Python QQ 机器人框架。

[English](#english) | 中文

</div>

---

## 三层结构

```
run.py
 └── sdk  3.8.0 (协议 / 插件 / 配置)
      └── plugins/  6 个插件
```

## 6 个插件

| 插件 | 功能 | 数据存储 |
|------|------|----------|
| rqhspeech | 发言统计 / 排行榜 | JSON 文件 |
| rqhmain | 综合（运势/天气/新闻/发图） | 无持久化（静态 JSON 资源） |
| pintu | 拼图游戏 | 内存 |
| rqhshen | 修仙游戏 | JSON |
| rqhwenda | 问答匹配 | JSON |
| group_summary | 群聊总结 | JSONL |

## 数据流

```
用户消息 → NapCat WS → SDK EventBus → 插件 filter → 插件 handler → SDK API → NapCat → QQ
```

当前 SDK 特性：事件总线快照分发、filter 命中并发执行、任务异常统一记录、插件卸载顺序优化、`send_event_message` 统一回复。

## 核心模块

| 模块 | 说明 |
|------|------|
| `NapCatClient` | WebSocket 客户端 + OneBot API 封装 |
| `EventBus` | 事件总线（快照分发，并发 handler） |
| `PluginBase` | 插件基类（配置/数据/任务管理） |
| `PluginManager` | 插件加载与生命周期管理 |
| `BotClient` | 装饰器模式机器人入口 |

## 快速开始

```bash
pip install -r requirements.txt
cp config.yaml.example config.yaml   # 编辑配置
python run.py
```

## 项目结构

```text
rqhbot/
├── sdk/              # 框架核心
├── plugins/          # 6 个插件
├── docs/             # 文档
├── tests/            # 测试
├── config.yaml.example
├── requirements.txt
├── pyproject.toml
├── setup.py
└── run.py
```

## 一键安装

```bash
pip install .
```

---

## English

<div align="center">

[中文](#三层结构) | English

</div>

### Three-Layer Structure

```
run.py
 └── sdk  3.8.0 (protocol / plugins / config)
      └── plugins/  6 plugins
```

### 6 Plugins

| Plugin | Description | Storage |
|--------|-------------|---------|
| rqhspeech | Message stats / leaderboard | JSON files |
| rqhmain | Misc (horoscope/weather/news/image) | None (static JSON resources) |
| pintu | Jigsaw puzzle game | In-memory |
| rqhshen | Cultivation game | JSON |
| rqhwenda | Q&A matching | JSON |
| group_summary | Group chat summary | JSONL |

### Data Flow

```
User message → NapCat WS → SDK EventBus → Plugin filter → Plugin handler → SDK API → NapCat → QQ
```

SDK features: EventBus snapshot dispatch, concurrent filter+handler execution, unified task exception logging, plugin unloading order optimization, `send_event_message` unified reply.

### Core Modules

| Module | Description |
|--------|-------------|
| `NapCatClient` | WebSocket client + OneBot API wrapper |
| `EventBus` | Event bus (snapshot dispatch, concurrent handlers) |
| `PluginBase` | Plugin base class (config / data / task management) |
| `PluginManager` | Plugin loading & lifecycle management |
| `BotClient` | Decorator-based bot entry point |

### Quick Start

```bash
pip install -r requirements.txt
cp config.yaml.example config.yaml   # edit config
python run.py
```

### One-Line Install

```bash
pip install .
```

---

<div align="center">

**RqhBot v3.8.0**

</div>
