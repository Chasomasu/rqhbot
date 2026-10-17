# 配置指南

## 📋 概述

RqhBot 使用 YAML 配置文件 `config.yaml`，项目提供 `config.yaml.example` 作为模板。

## 📁 配置文件结构

```yaml
# 适配器后端：napcat 或 snowluma
# 决定读取下面哪一段连接配置
adapter: "napcat"

# NapCat 连接（adapter: napcat 时生效）
napcat:
  ws_url: "ws://127.0.0.1:3002"         # WebSocket 地址
  access_token: ""                      # 访问令牌
  bot_uin: ""                           # 机器人 QQ 号
  root: ""                              # 管理员 QQ 号
  webui_uri: "http://localhost:6098"    # WebUI 地址
  webui_token: ""                       # WebUI 令牌

# SnowLuma 连接（adapter: snowluma 时生效）
snowluma:
  ws_url: "ws://127.0.0.1:3001"         # WebSocket 地址
  access_token: ""                      # 访问令牌

# 机器人
bot:
  load_plugins: true                    # 是否加载插件
  plugin_dir: "plugins"                 # 插件目录

# 日志（logging.* 为预留键：当前仅被 ConfigManager.set_log_level()/set_log_dir()
#       写入，运行时未读取；setup_logging() 使用环境变量 LOG_LEVEL / LOG_DIR）
logging:
  level: "INFO"                         # DEBUG/INFO/WARNING/ERROR/CRITICAL（当前未应用）
  log_dir: "logs"                       # 当前未应用；运行时默认 logs（LOG_DIR）
  log_file: "bot.log"                   # 当前未应用；运行时固定 logs/bot.log

# 设置
settings:
  debug: false                          # 会应用（BotClient.run 读取）
  auto_reconnect: true                  # 预留：当前运行时未读取
  reconnect_interval: 5                 # 重连间隔（秒，预留：当前运行时未读取）
```

## 🔧 ConfigManager API

```python
from sdk.config import config_manager

# 获取配置（点号分隔路径）
ws_url = config_manager.get("napcat.ws_url", "ws://localhost:3002")
debug = config_manager.get("settings.debug", False)

# 适配器后端（自动按当前 adapter 读取对应配置段，缺省回落到该后端默认地址）
adapter = config_manager.get_backend_name()          # "napcat" / "snowluma"
ws_url = config_manager.get_ws_uri()                  # 当前后端的 WebSocket 地址
ws_token = config_manager.get_ws_token()              # 当前后端的访问令牌
config_manager.set_backend("snowluma")                # 切换后端并保存

# 设置配置（仅写入内存，不落盘；需随后调用 config_manager.save()）
config_manager.set("settings.debug", True)

# 便捷方法（均自动保存）
config_manager.set_bot_uin("123456789")
config_manager.set_root("2654278608")
config_manager.set_ws_uri("ws://localhost:3002")
config_manager.set_ws_token("your_token")
config_manager.set_webui_uri("http://localhost:6098")
config_manager.set_webui_token("your_token")
config_manager.set_load_plugins(True)
config_manager.set_plugin_dir("plugins")
config_manager.set_log_level("DEBUG")
config_manager.set_log_dir("logs")
config_manager.set_debug(False)

# 重新加载 / 查看
config_manager.reload()
config_manager.show()
```

## 💡 常用示例

### 初始化首次配置

```python
from sdk.config import config_manager
import os

if not os.path.exists("config.yaml"):
    config_manager.set_ws_uri("ws://127.0.0.1:3001")
    config_manager.set_load_plugins(True)
    print("默认配置已创建")
```

### 在启动脚本中使用

```python
from sdk.config import config_manager

ws_url = config_manager.get_ws_uri()          # 按 adapter 自动解析后端地址
load_plugins = config_manager.get("bot.load_plugins", True)
plugin_dir = config_manager.get("bot.plugin_dir", "plugins")

bot.api.ws_url = ws_url
bot.start(load_plugins=load_plugins)
```

### 区分环境

```python
env = "production"
if env == "production":
    config_manager.set_debug(False)
    config_manager.set_log_level("WARNING")
else:
    config_manager.set_debug(True)
    config_manager.set_log_level("DEBUG")
```

## ⚠️ 注意事项

1. `set_*()` 便捷方法调用后会自动保存到 `config.yaml`；裸 `set()` 只改内存，需手动 `save()`
2. 项目没有命令行参数解析。YAML（`ConfigManager`，读取 `config.yaml`）与环境变量（`Config`，读取 `.env`/系统环境变量）是两套互不合并的来源：
   - 顶层 `adapter` 字段选择后端（`napcat` / `snowluma`），`BotClient.run()` 据此通过 `config_manager.get_ws_uri()` / `get_ws_token()` 读取对应配置段；对应段缺省时回落到该后端默认地址（NapCat `ws://localhost:3002`、SnowLuma `ws://localhost:3001`）
   - `BotClient.run()` 从 YAML 读取 `bot.plugin_dir` / `bot.load_plugins` / `settings.debug`
   - 日志级别与目录由环境变量 `LOG_LEVEL` / `LOG_DIR`（`Config`）决定，不读取 YAML 的 `logging.*`
3. `logging.level` / `logging.log_dir` / `logging.log_file` / `settings.auto_reconnect` / `settings.reconnect_interval` 为预留键：当前运行时未读取，保留仅为兼容已有配置文件
4. `config.yaml.example` 为模板，实际使用 `config.yaml`

---

**版本**: 3.8.0
