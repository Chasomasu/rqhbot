"""
BotClient 类
支持装饰器模式的机器人客户端，所有对外接口均为强类型声明
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, TypeAlias

from sdk.config import setup_logging
from sdk.core import OneBotClient
from sdk.core.event_bus import EventBus
from sdk.core.events import (
    BaseEvent,
    EssenceMsgNotice,
    FriendAddNotice,
    GroupAdminNotice,
    GroupCardNotice,
    GroupMessageEvent,
    GroupUploadNotice,
    NoticeEvent,
    PrivateMessageEvent,
    RequestEvent,
)
from sdk.pluginsystem import HotReloadPluginManager, PluginBase, PluginManager

# 设置日志系统
setup_logging()

logger: logging.Logger = logging.getLogger(__name__)

# ---- 类型别名 ----
GroupMsgHandler: TypeAlias = Callable[[GroupMessageEvent], Awaitable[None]]
PrivateMsgHandler: TypeAlias = Callable[[PrivateMessageEvent], Awaitable[None]]
NoticeHandler: TypeAlias = Callable[[NoticeEvent], Awaitable[None]]
RequestHandler: TypeAlias = Callable[[RequestEvent], Awaitable[None]]


class BotClient:
    """机器人客户端 —— 装饰器模式入口"""

    def __init__(
        self,
        ws_url: Optional[str] = None,
        access_token: Optional[str] = None,
        plugins_dir: str = "plugins",
        backend: Optional[str] = None,
    ) -> None:
        self.client: OneBotClient = OneBotClient(
            ws_url=ws_url, access_token=access_token, backend=backend
        )
        self.api = self.client
        self.event_bus: EventBus = EventBus()
        self._plugins_dir: str = plugins_dir

        self._group_message_handlers: List[GroupMsgHandler] = []
        self._private_message_handlers: List[PrivateMsgHandler] = []
        self._notice_handlers: List[NoticeHandler] = []
        self._request_handlers: List[RequestHandler] = []
        self._tracked_tasks: Set[asyncio.Task[Any]] = set()

        self.plugin_manager: PluginManager = PluginManager(self.api, self.event_bus)
        self.hot_reload_manager: HotReloadPluginManager = HotReloadPluginManager(self._plugins_dir)

        self._setup_handlers()

    @property
    def plugins_dir(self) -> str:
        """插件目录路径"""
        return self._plugins_dir

    @plugins_dir.setter
    def plugins_dir(self, value: str) -> None:
        """设置插件目录路径（同步更新 hot_reload_manager）"""
        self._plugins_dir = value
        self.hot_reload_manager.plugin_dir = Path(value)

    def _setup_handlers(self) -> None:
        """向底层客户端注册事件路由，并通过 EventBus 发布强类型事件"""

        @self.client.on_message("group")
        async def _handle_group(data: Dict[str, Any]) -> None:
            try:
                event: GroupMessageEvent = GroupMessageEvent.from_dict(data)
                self._fire_task(self._print_group_message(event))
                await self.event_bus.publish(event)
                self._dispatch_to_handlers(event, self._group_message_handlers)
            except Exception as e:
                logger.error(f"处理群消息时出错: {e}", exc_info=True)

        @self.client.on_message("private")
        async def _handle_private(data: Dict[str, Any]) -> None:
            try:
                event: PrivateMessageEvent = PrivateMessageEvent.from_dict(data)
                self._fire_task(self._print_private_message(event))
                await self.event_bus.publish(event)
                self._dispatch_to_handlers(event, self._private_message_handlers)
            except Exception as e:
                logger.error(f"处理私聊消息时出错: {e}", exc_info=True)

        @self.client.on_message("notice")
        async def _handle_notice(data: Dict[str, Any]) -> None:
            try:
                event: NoticeEvent = NoticeEvent.from_dict(data)
                await self.event_bus.publish(event)
                self._dispatch_to_handlers(event, self._notice_handlers)
            except Exception as e:
                logger.error(f"处理通知事件时出错: {e}", exc_info=True)

        @self.client.on_message("request")
        async def _handle_request(data: Dict[str, Any]) -> None:
            try:
                event: RequestEvent = RequestEvent.from_dict(data)
                await self.event_bus.publish(event)
                self._dispatch_to_handlers(event, self._request_handlers)
            except Exception as e:
                logger.error(f"处理请求事件时出错: {e}", exc_info=True)

    def _fire_task(self, coro: Awaitable[Any]) -> None:
        """创建后台任务并追踪，异常会被记录而非静默丢失"""
        # 使用 create_task（仅在 running loop 中调用，语义更明确）
        task = asyncio.create_task(coro)
        self._tracked_tasks.add(task)
        task.add_done_callback(self._tracked_tasks.discard)
        task.add_done_callback(self._on_task_error)

    @staticmethod
    def _on_task_error(task: asyncio.Task[Any]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(f"后台任务异常: {exc}", exc_info=exc)

    def _dispatch_to_handlers(
        self, event: Any, handlers: List[Callable[..., Any]]
    ) -> None:
        """将事件分发给处理器列表，追踪任务并捕获异常"""
        for handler in handlers:
            try:
                self._fire_task(handler(event))
            except Exception as e:
                logger.error(f"注册处理器任务时出错: {e}", exc_info=True)

    def _cancel_tracked_tasks(self) -> None:
        """取消所有正在追踪的后台任务"""
        for task in self._tracked_tasks:
            if not task.done():
                task.cancel()
        self._tracked_tasks.clear()

    async def _print_group_message(self, event: GroupMessageEvent) -> None:
        """异步打印群消息"""
        logger.info(
            "[群消息] 群:%s 用户:%s(%s): %s",
            event.group_id,
            event.user_name,
            event.user_id,
            event.message.plain_text,
        )

    async def _print_private_message(self, event: PrivateMessageEvent) -> None:
        """异步打印私聊消息"""
        logger.info(
            "[私聊] 用户:%s(%s): %s",
            event.user_name,
            event.user_id,
            event.message.plain_text,
        )

    # ======================== 装饰器式事件注册 ========================

    def on_group_message(self) -> Callable[[GroupMsgHandler], GroupMsgHandler]:
        """装饰器：注册群消息事件处理器

        Returns:
            装饰器函数
        """
        def decorator(func: GroupMsgHandler) -> GroupMsgHandler:
            if func not in self._group_message_handlers:
                self._group_message_handlers.append(func)
            return func
        return decorator

    def on_private_message(self) -> Callable[[PrivateMsgHandler], PrivateMsgHandler]:
        """装饰器：注册私聊消息事件处理器

        Returns:
            装饰器函数
        """
        def decorator(func: PrivateMsgHandler) -> PrivateMsgHandler:
            if func not in self._private_message_handlers:
                self._private_message_handlers.append(func)
            return func
        return decorator

    def on_notice(self) -> Callable[[NoticeHandler], NoticeHandler]:
        """装饰器：注册通知事件处理器

        Returns:
            装饰器函数
        """
        def decorator(func: NoticeHandler) -> NoticeHandler:
            if func not in self._notice_handlers:
                self._notice_handlers.append(func)
            return func
        return decorator

    def on_request(self) -> Callable[[RequestHandler], RequestHandler]:
        """装饰器：注册请求事件处理器

        Returns:
            装饰器函数
        """
        def decorator(func: RequestHandler) -> RequestHandler:
            if func not in self._request_handlers:
                self._request_handlers.append(func)
            return func
        return decorator

    # ======================== 插件管理 ========================

    def register_plugin(self, plugin: PluginBase) -> bool:
        """注册插件

        Args:
            plugin: 插件实例

        Returns:
            是否成功
        """
        return self.plugin_manager.register_plugin(plugin)

    async def load_plugins(self) -> List[str]:
        """使用热重载管理器从插件目录加载所有插件

        Returns:
            成功加载的插件名称列表
        """
        return await self.hot_reload_manager.load_all_plugins(
            self.api, self.event_bus
        )

    async def reload_plugin(self, plugin_name: str) -> bool:
        """热重载指定插件

        Args:
            plugin_name: 插件名称

        Returns:
            是否成功
        """
        return await self.hot_reload_manager.reload_plugin(
            plugin_name, self.api, self.event_bus
        )

    def start_file_watcher(self) -> bool:
        """启动文件监控，实现自动热重载

        Returns:
            是否成功启动
        """
        return self.hot_reload_manager.start_file_watcher()

    def stop_file_watcher(self) -> None:
        """停止文件监控"""
        self.hot_reload_manager.stop_file_watcher()

    # ======================== 生命周期 ========================

    async def run_frontend(
        self, debug: bool = False, load_plugins: bool = True
    ) -> None:
        """运行机器人前端（事件循环入口）

        Args:
            debug: 是否开启调试模式
            load_plugins: 是否自动加载插件
        """
        try:
            await self.client.connect()

            if debug:
                logger.setLevel(logging.DEBUG)
                logger.info("调试模式已开启")

            # 加载插件（使用热重载管理器）
            if load_plugins:
                loaded: List[str] = await self.hot_reload_manager.load_all_plugins(
                    self.api, self.event_bus
                )
                logger.info(f"成功加载 {len(loaded)} 个插件: {', '.join(loaded) if loaded else '无'}")

            logger.info("=" * 50)
            logger.info("机器人已启动（装饰器模式）")
            logger.info("=" * 50)
            logger.info(
                f"注册的群消息处理器数量: {len(self._group_message_handlers)}"
            )
            logger.info(
                f"注册的私聊消息处理器数量: {len(self._private_message_handlers)}"
            )
            logger.info(f"注册的通知处理器数量: {len(self._notice_handlers)}")
            logger.info(f"注册的请求处理器数量: {len(self._request_handlers)}")
            logger.info(
                f"已加载插件数量: {len(self.hot_reload_manager.get_all_plugins())}"
            )
            logger.info("=" * 50)
            logger.info("等待消息中...")
            logger.info("=" * 50)

            # 断线后若仍在自动重连，保持进程存活等待重连结果
            while self.client.connected or self.client.reconnecting:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("收到中断信号，正在关闭...")
        except Exception as e:
            logger.error(f"发生错误: {e}", exc_info=True)
        finally:
            # 先停文件监控，再逆序卸载插件（退订事件、取消任务、落盘），
            # 最后取消剩余后台任务并断开连接
            try:
                self.stop_file_watcher()
            except Exception as e:
                logger.error(f"停止文件监控失败: {e}", exc_info=True)
            try:
                await self.hot_reload_manager.unload_all_plugins()
            except Exception as e:
                logger.error(f"卸载插件失败: {e}", exc_info=True)
            self._cancel_tracked_tasks()
            await self.client.disconnect()
            logger.info("机器人已关闭")

    @classmethod
    def run(cls) -> None:
        """一键启动：从 config.yaml 读取配置并运行机器人"""
        from sdk.config import config_manager

        bot = cls(
            ws_url=config_manager.get_ws_uri(),
            access_token=config_manager.get_ws_token(),
            plugins_dir=config_manager.get("bot.plugin_dir", "plugins"),
            backend=config_manager.get_backend_name(),
        )
        bot.start(
            debug=config_manager.get("settings.debug", False),
            load_plugins=config_manager.get("bot.load_plugins", True),
        )

    def __call__(self, debug: bool = False, load_plugins: bool = True) -> None:
        """直接调用实例启动机器人"""
        self.start(debug=debug, load_plugins=load_plugins)

    def start(self, debug: bool = False, load_plugins: bool = True) -> None:
        """启动机器人（便捷方法，兼容已有事件循环）"""
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                # 如果在 Jupyter 等已有事件循环的环境中，创建后台任务
                asyncio.create_task(self.run_frontend(debug=debug, load_plugins=load_plugins))
                return
        except RuntimeError:
            pass
        asyncio.run(self.run_frontend(debug=debug, load_plugins=load_plugins))
