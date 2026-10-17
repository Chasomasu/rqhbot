# 快速开始指南

## 🎯 5 分钟上手 RqhBot

## 📋 前置要求

- Python 3.10+
- NapCat 已安装并登录 QQ
- 基本的 Python 知识

## 🚀 安装步骤

### 1. 克隆项目

```bash
git clone https://github.com/your-repo/rqhbot.git
cd rqhbot
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

> 依赖中的 `watchdog` 用于插件热重载的文件监控；若未安装，热重载会自动降级为手动重载。

### 3. 配置连接

```bash
cp config.yaml.example config.yaml
```

编辑 `config.yaml`，设置 NapCat 连接信息：

```yaml
napcat:
  ws_url: "ws://127.0.0.1:3001"
  access_token: ""                  # NapCat 访问令牌
```

### 4. 启动

```bash
python run.py
```

## ✅ 验证

启动后可以看到（日志格式为 `时间 - 模块 - 级别 - 消息`，内容随实际配置/插件而异）：

```
2026-06-01 12:00:00 - sdk.core.client - INFO - 成功连接到NapCat服务器: ws://127.0.0.1:3001
2026-06-01 12:00:00 - sdk.bot_client - INFO - 成功加载 6 个插件: group_summary, pintu, rqhmain, rqhshen, rqhspeech, rqhwenda
2026-06-01 12:00:00 - sdk.bot_client - INFO - ==================================================
2026-06-01 12:00:00 - sdk.bot_client - INFO - 机器人已启动（装饰器模式）
2026-06-01 12:00:00 - sdk.bot_client - INFO - ==================================================
2026-06-01 12:00:00 - sdk.bot_client - INFO - 注册的群消息处理器数量: 0
2026-06-01 12:00:00 - sdk.bot_client - INFO - 注册的私聊消息处理器数量: 0
2026-06-01 12:00:00 - sdk.bot_client - INFO - 注册的通知处理器数量: 0
2026-06-01 12:00:00 - sdk.bot_client - INFO - 注册的请求处理器数量: 0
2026-06-01 12:00:00 - sdk.bot_client - INFO - 已加载插件数量: 6
2026-06-01 12:00:00 - sdk.bot_client - INFO - ==================================================
2026-06-01 12:00:00 - sdk.bot_client - INFO - 等待消息中...
2026-06-01 12:00:00 - sdk.bot_client - INFO - ==================================================
```

连接失败时会看到 `尝试重连 (n/max)...`、`连接失败 (n/max): ...` 等日志。

在 QQ 中发送消息，机器人加载的插件将按规则响应。

## 📝 自定义机器人

创建 `my_bot.py`：

```python
from sdk import BotClient, GroupMessageEvent

bot = BotClient()

@bot.on_group_message()
async def handle_message(msg: GroupMessageEvent):
    if msg.message.plain_text == "ping":
        await bot.api.send_group_message(msg.group_id, "pong!")

if __name__ == "__main__":
    bot.start(load_plugins=False)
```

```bash
python my_bot.py
```

## 🔧 基础配置

```yaml
bot:
  load_plugins: true    # 是否加载插件
  plugin_dir: "plugins"

logging:
  level: "INFO"         # DEBUG / INFO / WARNING / ERROR

settings:
  debug: false
```

## 🎓 下一步

- [配置指南](./04_CONFIG_GUIDE.md) — 详细配置说明
- [插件开发](./06_PLUGIN_DEVELOPMENT.md) — 开发自己的插件
- [API 参考](./05_API.md) — 完整 API 文档

## ❓ 常见问题

| 问题 | 解决 |
|------|------|
| 连接失败 | 检查 NapCat 是否运行、ws_url 是否正确 |
| 插件不加载 | 确认 `config.yaml` 中 `load_plugins: true` |
| 查看日志 | 日志文件在 `logs/` 目录，文件名为 `bot.log`（按日期轮转） |

---

**版本**: 3.8.0
