from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import (
    Any, Awaitable, Callable, Dict, Final, List, Optional, Union, TypeAlias,
)
import websockets
from websockets.exceptions import ConnectionClosed

from sdk.config import BackendSpec, Config, get_backend, setup_logging
from sdk.core.interfaces import IClient, IConnectionEventListener, MessageSegmentType

# 设置日志系统
setup_logging()

logger = logging.getLogger(__name__)

# ---- 类型别名 ----
EventHandler = Callable[[Dict[str, Any]], Awaitable[None]]
Decorator = Callable[[EventHandler], EventHandler]


# ==================== 消息段构建工具 ====================


class MessageSegment:
    """消息段构建器 —— 用于构建 OneBot 11 数组格式的消息

    OneBot 11（NapCat / SnowLuma 等）的 message 支持数组格式：
    ```python
    [
        {"type": "text", "data": {"text": "你好，"}},
        {"type": "image", "data": {"file": "https://example.com/pic.png"}},
        {"type": "text", "data": {"text": "这是图片！"}},
    ]
    ```
    """

    @staticmethod
    def text(content: str) -> MessageSegmentType:
        """文字消息段"""
        return {"type": "text", "data": {"text": content}}

    @staticmethod
    def image(file: str, summary: str = "") -> MessageSegmentType:
        """图片消息段
        Args:
            file: 图片路径（本地路径或 URL）
            summary: 图片简介（可选，用于加载失败时显示）
        """
        data: Dict[str, Any] = {"file": file}
        if summary:
            data["summary"] = summary
        return {"type": "image", "data": data}

    @staticmethod
    def at(qq: Union[int, str]) -> MessageSegmentType:
        """@某人消息段"""
        return {"type": "at", "data": {"qq": str(qq)}}

    @staticmethod
    def reply(message_id: int) -> MessageSegmentType:
        """回复消息段"""
        return {"type": "reply", "data": {"id": message_id}}

    @staticmethod
    def face(face_id: int) -> MessageSegmentType:
        """QQ 表情消息段 (face id)"""
        return {"type": "face", "data": {"id": face_id}}

    @staticmethod
    def dice() -> MessageSegmentType:
        """骰子消息段"""
        return {"type": "dice", "data": {}}

    @staticmethod
    def rps() -> MessageSegmentType:
        """猜拳消息段"""
        return {"type": "rps", "data": {}}

    @staticmethod
    def json_data(data: Union[Dict[str, Any], str]) -> MessageSegmentType:
        """JSON 卡片消息段"""
        if isinstance(data, dict):
            data = json.dumps(data, ensure_ascii=False)
        return {"type": "json", "data": {"data": data}}

    @staticmethod
    def video(file: str) -> MessageSegmentType:
        """视频消息段"""
        return {"type": "video", "data": {"file": file}}

    @staticmethod
    def record(file: str, magic: bool = False) -> MessageSegmentType:
        """语音消息段"""
        data: Dict[str, Any] = {"file": file}
        if magic:
            data["magic"] = True
        return {"type": "record", "data": data}

    @staticmethod
    def file(file: str, file_name: str = "") -> MessageSegmentType:
        """文件消息段"""
        data: Dict[str, Any] = {"file": file}
        if file_name:
            data["file_name"] = file_name
        return {"type": "file", "data": data}

    @staticmethod
    def forward(res_id: str = "", news: Optional[List[Dict[str, Any]]] = None) -> MessageSegmentType:
        """合并转发消息段"""
        data: Dict[str, Any] = {}
        if res_id:
            data["id"] = res_id
        if news:
            data["news"] = news
        return {"type": "forward", "data": data}

    @staticmethod
    def node(name: str, uin: int, content: List[MessageSegmentType]) -> MessageSegmentType:
        """合并转发节点"""
        return {
            "type": "node",
            "data": {
                "name": name,
                "uin": str(uin),
                "content": content,
            },
        }

    @staticmethod
    def music(
        type_: str,
        id_: str = "",
        url: str = "",
        title: str = "",
        content: str = "",
        image: str = "",
    ) -> MessageSegmentType:
        """音乐卡片消息段

        Args:
            type_: 平台类型（qq / 163 / kugou / mfeel / bilibili）
            id_: 音乐平台的歌曲 ID
            url: 点击后跳转的链接
            title: 标题
            content: 简介
            image: 封面图
        """
        data: Dict[str, Any] = {"type": type_}
        if id_:
            data["id"] = id_
        if url:
            data["url"] = url
        if title:
            data["title"] = title
        if content:
            data["content"] = content
        if image:
            data["image"] = image
        return {"type": "music", "data": data}

    @staticmethod
    def markdown(content: str) -> MessageSegmentType:
        """Markdown 消息段"""
        return {"type": "markdown", "data": {"content": content}}

    @staticmethod
    def mface(emoji_id: str, emoji_type: int = 0) -> MessageSegmentType:
        """表情商店表情消息段"""
        data: Dict[str, Any] = {"emoji_id": emoji_id}
        if emoji_type:
            data["emoji_type"] = emoji_type
        return {"type": "mface", "data": data}

    @staticmethod
    def xml(data: str) -> MessageSegmentType:
        """XML 消息段"""
        return {"type": "xml", "data": {"data": data}}


class OneBotClient(IClient):
    """OneBot 11 客户端 —— 支持 NapCat / SnowLuma 后端，实现 IClient Protocol"""

    # ---- 重连配置 ----
    MAX_RECONNECT_ATTEMPTS: Final[int] = 5
    RECONNECT_DELAY: Final[float] = 3.0       # 秒
    RECONNECT_MAX_ROUNDS: Final[int] = 3      # 断线后自动重连的最大轮数
    PING_INTERVAL: Final[float] = 25.0
    PING_TIMEOUT: Final[float] = 10.0
    CLOSE_TIMEOUT: Final[float] = 5.0

    def __init__(
        self,
        ws_url: Optional[str] = None,
        access_token: Optional[str] = None,
        backend: Optional[str] = None,
    ) -> None:
        self.backend: BackendSpec = get_backend(backend)
        raw_url: str = ws_url or Config.NAPCAT_WS_URL or self.backend.default_ws_uri
        self.ws_url: str = raw_url
        self.access_token: str = access_token or Config.NAPCAT_ACCESS_TOKEN
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.message_handlers: Dict[str, List[EventHandler]] = {}
        self._connected: bool = False
        self.echo_map: Dict[str, asyncio.Future[Any]] = {}

        # ---- 消息处理队列 ----
        self.msg_queue: Optional[asyncio.Queue[str]] = None
        self._processing_task: Optional[asyncio.Task[None]] = None
        self._listen_task: Optional[asyncio.Task[None]] = None

        # ---- 性能监控 ----
        self._perf_stats: Dict[str, Union[int, float]] = {
            "total_messages": 0,
            "total_processing_time": 0.0,
            "avg_latency": 0.0,
        }

        # ---- 重连控制 ----
        self._reconnect_attempts: int = 0
        self._reconnect_task: Optional[asyncio.Task[None]] = None
        self._closing: bool = False  # 主动关闭后不再自动重连

        # ---- 连接事件监听器 ----
        self._connection_listeners: List[IConnectionEventListener] = []

        # ---- echo_map 保护（最多 1000 条，防止内存泄漏）----
        self._echo_maxsize: int = 1000

    @property
    def connected(self) -> bool:
        """是否已连接"""
        return self._connected

    @property
    def reconnecting(self) -> bool:
        """是否正在进行自动重连"""
        return self._reconnect_task is not None and not self._reconnect_task.done()

    async def _cancel_connection_tasks(self) -> None:
        """回收上一轮遗留的监听/处理任务

        重连时必须先取消旧任务，否则旧的监听/处理协程可能与新任务并存，
        造成同一条消息被重复处理。
        """
        for attr in ("_processing_task", "_listen_task"):
            task: Optional[asyncio.Task[None]] = getattr(self, attr)
            if task is None or task is asyncio.current_task():
                continue
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"回收旧连接任务时出错: {e}")
            finally:
                setattr(self, attr, None)

    async def _cancel_reconnect_task(self) -> None:
        """取消进行中的自动重连任务"""
        task = self._reconnect_task
        self._reconnect_task = None
        if task is None or task.done() or task is asyncio.current_task():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"取消重连任务时出错: {e}")

    def _schedule_reconnect(self) -> None:
        """监听循环结束后安排自动重连（保证同一时间只有一个重连任务）"""
        if self._closing:
            return
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("事件循环已关闭，跳过自动重连")
            return
        self._reconnect_task = loop.create_task(self._reconnect_loop())
        self._reconnect_task.add_done_callback(self._on_reconnect_task_done)

    @staticmethod
    def _on_reconnect_task_done(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(f"自动重连任务异常: {exc}", exc_info=exc)

    async def _reconnect_loop(self) -> None:
        """断线后的自动重连：带退避地重试，直到成功或放弃

        每一轮调用 connect()，由 connect() 负责通知连接监听器；
        达到最大轮数仍失败则结束，使 run_frontend 得以正常退出。
        """
        for round_index in range(1, self.RECONNECT_MAX_ROUNDS + 1):
            delay = min(self.RECONNECT_DELAY * round_index, 30.0)
            logger.info(
                f"连接已断开，{delay:.0f} 秒后进行第 {round_index}/{self.RECONNECT_MAX_ROUNDS} 轮重连..."
            )
            await asyncio.sleep(delay)
            if self._closing:
                return
            # 标记为重连，connect() 会走 on_reconnect_success 通知分支
            self._reconnect_attempts = round_index
            if await self.connect():
                logger.info(f"第 {round_index} 轮重连成功")
                return
        self._reconnect_attempts = 0
        logger.error(f"自动重连失败，已尝试 {self.RECONNECT_MAX_ROUNDS} 轮")

    async def connect(self, max_retries: Optional[int] = None) -> bool:
        """
        建立连接（支持重连）
        
        Args:
            max_retries: 最大重试次数，None使用默认配置
            
        Returns:
            是否连接成功
        """
        self._closing = False
        # 重连前先回收上一轮的监听/处理任务，避免新旧任务同时消费消息
        await self._cancel_connection_tasks()

        retries = 0
        max_retries = max_retries or self.MAX_RECONNECT_ATTEMPTS
        
        while retries < max_retries:
            try:
                if retries > 0:
                    self._reconnect_attempts = retries
                    logger.info(f"尝试重连 ({retries}/{max_retries})...")
                    for listener in self._connection_listeners:
                        try:
                            await listener.on_reconnecting(retries)
                        except Exception as e:
                            logger.error(f"重连监听器执行失败: {e}")
                
                headers = {}
                if self.access_token:
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    headers["access_token"] = self.access_token

                connect_kwargs = {
                    "ping_interval": self.PING_INTERVAL,
                    "ping_timeout": self.PING_TIMEOUT,
                    "close_timeout": self.CLOSE_TIMEOUT,
                    "additional_headers": headers if headers else {},
                }

                self.ws = await websockets.connect(
                    self.ws_url,
                    **connect_kwargs
                )
                
                # 初始化消息队列
                self.msg_queue = asyncio.Queue(maxsize=1000)
                
                self._connected = True

                # 启动接收任务
                self._listen_task = asyncio.create_task(self._listen_messages())
                
                # 启动处理任务
                self._processing_task = asyncio.create_task(self._process_messages())
                
                was_reconnect = self._reconnect_attempts > 0
                self._reconnect_attempts = 0

                logger.info(f"成功连接到{self.backend.display_name}服务器: {self.ws_url}")

                # 通知连接成功
                for listener in self._connection_listeners:
                    try:
                        if was_reconnect and hasattr(listener, 'on_reconnect_success'):
                            await listener.on_reconnect_success()
                        else:
                            await listener.on_connected()
                    except Exception as e:
                        logger.error(f"连接监听器执行失败: {e}")
                
                return True
                
            except Exception as e:
                retries += 1
                logger.error(f"连接失败 ({retries}/{max_retries}): {e}")
                
                if retries < max_retries:
                    wait_time = self.RECONNECT_DELAY * retries
                    logger.info(f"{wait_time}秒后重试...")
                    await asyncio.sleep(wait_time)
        
        logger.error(f"连接失败，已达到最大重试次数 ({max_retries})")
        
        # 通知重连失败
        for listener in self._connection_listeners:
            try:
                await listener.on_reconnect_failed(
                    Exception(f"连接失败，已达到最大重试次数 ({max_retries})")
                )
            except Exception as e:
                logger.error(f"重连失败监听器执行失败: {e}")
        
        return False
    
    async def disconnect(self, force: bool = False) -> None:
        """断开连接

        异常断线时 _connected 已被置为 False，但监听/处理任务、WebSocket 引用、
        消息队列和未完成的 API 请求可能仍然存在，此时也必须清理，
        不能仅凭连接标志提前返回。

        Args:
            force: 是否强制断开
        """
        self._closing = True
        await self._cancel_reconnect_task()

        has_resources = (
            self._processing_task is not None
            or self._listen_task is not None
            or self.ws is not None
            or self.msg_queue is not None
            or bool(self.echo_map)
        )
        if not self._connected and not force and not has_resources:
            return

        self._connected = False
        
        # 关闭消息队列处理
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"关闭处理任务时出错: {e}")
            finally:
                self._processing_task = None
        
        # 关闭监听任务
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"关闭监听任务时出错: {e}")
            finally:
                self._listen_task = None
        
        # 关闭 WebSocket 连接
        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                logger.error(f"关闭WebSocket连接时出错: {e}")
            finally:
                self.ws = None

        # 清空消息队列引用（防止重连时旧 Queue 泄漏）
        self.msg_queue = None

        # 清空未完成的 echo Future
        cancelled = 0
        for key, future in self.echo_map.items():
            if not future.done():
                future.cancel()
                cancelled += 1
        self.echo_map.clear()
        if cancelled:
            logger.warning(f"断开连接时取消了 {cancelled} 个未完成的 API 请求")

        logger.info("WebSocket 连接已关闭")
        
        # 通知断开连接
        for listener in self._connection_listeners:
            try:
                await listener.on_disconnected()
            except Exception as e:
                logger.error(f"断开连接监听器执行失败: {e}")
    
    def add_connection_listener(self, listener: IConnectionEventListener) -> None:
        """添加连接事件监听器

        Args:
            listener: IConnectionEventListener 实例
        """
        if listener not in self._connection_listeners:
            self._connection_listeners.append(listener)

    def remove_connection_listener(self, listener: IConnectionEventListener) -> None:
        """移除连接事件监听器

        Args:
            listener: IConnectionEventListener 实例
        """
        if listener in self._connection_listeners:
            self._connection_listeners.remove(listener)

    async def _listen_messages(self) -> None:
        """监听消息 —— 接收循环（入队时带超时，避免静默丢消息）"""
        try:
            async for message in self.ws:
                try:
                    if self.msg_queue:
                        # 先尝试快速入队；队列满时最多等 2 秒，仍失败才丢弃
                        try:
                            self.msg_queue.put_nowait(message)
                        except asyncio.QueueFull:
                            try:
                                await asyncio.wait_for(
                                    self.msg_queue.put(message), timeout=2.0
                                )
                            except asyncio.TimeoutError:
                                logger.warning(
                                    "消息队列持续拥堵，丢弃消息（队列大小=%d）",
                                    self.msg_queue.maxsize,
                                )
                except Exception as e:
                    logger.error(f"消息入队失败: {e}")
        except asyncio.CancelledError:
            raise
        except ConnectionClosed:
            logger.warning("WebSocket连接已关闭")
        except Exception as e:
            logger.error(f"监听消息时发生错误: {e}")
        else:
            # websockets 在正常关闭（1000/1001）时会把 ConnectionClosedOK
            # 转成 StopAsyncIteration 让 async for 正常结束，
            # 不会进入上面的 ConnectionClosed 分支，必须在此更新状态
            logger.warning("WebSocket连接已正常关闭")
        finally:
            # 无论正常关闭、异常还是被取消，都要标记断开，
            # 否则 run_frontend 会一直等待一个已经死掉的连接
            self._connected = False
            # 非主动关闭时安排自动重连
            if not self._closing:
                self._schedule_reconnect()

    async def _process_messages(self) -> None:
        """消息处理循环 —— 与接收分离"""
        while self._connected:
            try:
                if not self.msg_queue:
                    await asyncio.sleep(0.1)
                    continue

                # 带超时获取，保证断开后处理循环能在一个周期内自行退出
                try:
                    message = await asyncio.wait_for(self.msg_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                
                # 性能监控 - 开始
                start_time = time.perf_counter()
                
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    logger.error(f"消息解析失败: {e}")
                except Exception as e:
                    logger.error(f"处理消息时发生错误: {e}")
                finally:
                    # 性能监控 - 结束
                    processing_time = time.perf_counter() - start_time
                    self._perf_stats["total_messages"] += 1
                    self._perf_stats["total_processing_time"] += processing_time
                    self._perf_stats["avg_latency"] = (
                        self._perf_stats["total_processing_time"] / 
                        self._perf_stats["total_messages"]
                    )
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"处理循环错误: {e}")

    async def _handle_message(self, data: Dict[str, Any]) -> None:
        """处理消息"""
        if "echo" in data:
            echo_id = data["echo"]
            if echo_id in self.echo_map:
                future = self.echo_map.pop(echo_id)
                if not future.done():
                    future.set_result(data)
                return
        
        post_type = data.get("post_type")
        message_type = data.get("message_type")
        
        event_types = []
        if post_type:
            event_types.append(post_type)
        if message_type and message_type != post_type:
            event_types.append(message_type)
        
        seen: set[int] = set()
        for event_type in event_types:
            for handler in self.message_handlers.get(event_type, []):
                handler_id = id(handler)
                if handler_id in seen:
                    continue
                seen.add(handler_id)
                try:
                    task = asyncio.create_task(handler(data))
                    task.add_done_callback(self._on_handler_task_done)
                except Exception as e:
                    logger.error(f"创建处理器任务失败: {e}", exc_info=True)

    @staticmethod
    def _on_handler_task_done(task: asyncio.Task[Any]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(f"消息处理器异常: {exc}", exc_info=exc)

    def _evict_oldest_echo(self) -> None:
        """淘汰 echo_map 中最旧的 pending Future，防止内存泄漏"""
        oldest_key = next(iter(self.echo_map), None)
        if oldest_key is not None:
            old_future = self.echo_map.pop(oldest_key, None)
            if old_future is not None and not old_future.done():
                old_future.set_exception(
                    TimeoutError(f"echo_map 超限，旧请求 {oldest_key!r} 被自动淘汰")
                )
            logger.warning(
                f"echo_map 已达上限 {self._echo_maxsize}，已淘汰最旧条目: {oldest_key!r}"
            )

    def on_message(self, message_type: str) -> Decorator:
        """装饰器：注册消息事件处理器

        Args:
            message_type: 消息类型（'group' / 'private' / 'notice' / 'request'）

        Returns:
            装饰器函数
        """
        def decorator(func: EventHandler) -> EventHandler:
            handlers = self.message_handlers.setdefault(message_type, [])
            if func not in handlers:
                handlers.append(func)
            else:
                logger.debug("处理器 %s 已注册到 %s，跳过重复注册", func.__name__, message_type)
            return func
        return decorator

    async def call(self, action: str, params: Optional[Dict[str, Any]] = None,
                   max_retries: int = 3, retry_delay: float = 1.0) -> Dict[str, Any]:
        """
        调用API（支持重试）

        Args:
            action: API动作名称
            params: 参数字典
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）

        Returns:
            API响应数据

        Raises:
            ConnectionError: 未连接
            TimeoutError: API调用超时
            Exception: 其他错误
        """
        if not self.connected or not self.ws:
            raise ConnectionError(f"未连接到{self.backend.display_name}服务器")

        last_error = None
        pending_futures: List[asyncio.Future[Any]] = []

        try:
            for attempt in range(max_retries):
                echo_id = f"rqhbot-{uuid.uuid4().hex}"
                message = {
                    "action": action,
                    "params": params or {},
                    "echo": echo_id
                }

                future = asyncio.Future()
                pending_futures.append(future)

                # 插入前淘汰最旧的，防止 echo_map 无限增长
                if len(self.echo_map) >= self._echo_maxsize:
                    self._evict_oldest_echo()

                self.echo_map[echo_id] = future

                try:
                    await self.ws.send(json.dumps(message))
                    result = await asyncio.wait_for(future, timeout=30)

                    if result.get("status") == "ok":
                        return result.get("data", {})
                    else:
                        last_error = Exception(f"API调用失败: {result.get('msg', '未知错误')}")

                except asyncio.TimeoutError:
                    last_error = TimeoutError(f"API调用超时 (尝试 {attempt + 1}/{max_retries})")
                except Exception as e:
                    last_error = e
                finally:
                    self.echo_map.pop(echo_id, None)

                # 如果不是最后一次尝试，等待后重试
                if attempt < max_retries - 1:
                    logger.warning(f"API调用失败，{retry_delay}秒后重试 ({attempt + 1}/{max_retries}): {last_error}")
                    await asyncio.sleep(retry_delay)

            # 所有重试都失败
            if last_error:
                raise last_error
            raise Exception(f"API调用失败: 未知错误 (action={action})")
        finally:
            # 清理所有未完成的 futures，防止内存泄漏
            for future in pending_futures:
                if not future.done():
                    future.cancel()
    


    async def send_private_message(
        self, 
        user_id: int, 
        message: str = "", 
        image_path: Optional[str] = None,
        reply_message_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """发送私聊消息（数组格式，更安全可靠）
        
        Args:
            user_id: 用户ID
            message: 消息内容
            image_path: 图片文件路径（可选）
            reply_message_id: 回复的消息ID（可选）
            
        Returns:
            API响应数据
        """
        segments: List[MessageSegmentType] = []
        
        if reply_message_id is not None:
            segments.append(MessageSegment.reply(reply_message_id))
        
        if message:
            segments.append(MessageSegment.text(message))
        
        if image_path:
            segments.append(MessageSegment.image(image_path))
        
        return await self.call("send_private_msg", {
            "user_id": user_id,
            "message": segments
        })
    
    async def send_group_message(
        self, 
        group_id: int, 
        message: str = "", 
        image_path: Optional[str] = None,
        at_user_id: Optional[int] = None,
        reply_message_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """发送群聊消息（数组格式，更安全可靠）
        
        Args:
            group_id: 群ID
            message: 消息内容
            image_path: 图片文件路径（可选）
            at_user_id: @的用户ID（可选）
            reply_message_id: 回复的消息ID（可选）
            
        Returns:
            API响应数据
        """
        segments: List[MessageSegmentType] = []
        
        if reply_message_id is not None:
            segments.append(MessageSegment.reply(reply_message_id))
        
        if at_user_id is not None:
            segments.append(MessageSegment.at(at_user_id))
        
        if message:
            segments.append(MessageSegment.text(message))
        
        if image_path:
            segments.append(MessageSegment.image(image_path))
        
        return await self.call("send_group_msg", {
            "group_id": group_id,
            "message": segments
        })

    async def send_group_message_segments(
        self,
        group_id: int,
        segments: List[MessageSegmentType],
        reply_message_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """发送图文混排群消息（数组格式，推荐）

        Args:
            group_id: 群号
            segments: 消息段列表，使用 MessageSegment 构建
            reply_message_id: 回复的消息 ID（可选）

        Example:
            ```python
            await client.send_group_message_segments(
                group_id=123,
                segments=[
                    MessageSegment.text("你好，"),
                    MessageSegment.image("https://example.com/pic.png"),
                    MessageSegment.text("这是图片！"),
                ]
            )
            ```
        """
        msg_segments = list(segments)
        if reply_message_id is not None:
            msg_segments.insert(0, MessageSegment.reply(reply_message_id))

        return await self.call("send_group_msg", {
            "group_id": group_id,
            "message": msg_segments,
        })

    async def send_private_message_segments(
        self,
        user_id: int,
        segments: List[MessageSegmentType],
        reply_message_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """发送图文混排私聊消息（数组格式，推荐）

        Args:
            user_id: 用户ID
            segments: 消息段列表，使用 MessageSegment 构建
            reply_message_id: 回复的消息 ID（可选）

        Example:
            ```python
            await client.send_private_message_segments(
                user_id=123,
                segments=[
                    MessageSegment.text("你好，"),
                    MessageSegment.image("https://example.com/pic.png"),
                    MessageSegment.text("这是图片！"),
                ]
            )
            ```
        """
        msg_segments = list(segments)
        if reply_message_id is not None:
            msg_segments.insert(0, MessageSegment.reply(reply_message_id))

        return await self.call("send_private_msg", {
            "user_id": user_id,
            "message": msg_segments,
        })

    async def send_event_message(
        self,
        event: Any,
        message: str = "",
        message_segments: Optional[List[MessageSegmentType]] = None,
        image_path: Optional[str] = None,
        reply_message_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """按事件来源统一回复（自动识别群聊/私聊）

        Args:
            event: 事件对象（需有 group_id 或 user_id 属性）
            message: 文本消息（与 message_segments 二选一）
            message_segments: 消息段列表（与 message 二选一）
            image_path: 图片路径（可选）
            reply_message_id: 回复消息 ID（可选）

        Returns:
            API 调用结果
        """
        group_id = getattr(event, "group_id", None)
        user_id = getattr(event, "user_id", None)

        if group_id:
            if message_segments is not None:
                return await self.send_group_message_segments(
                    group_id, message_segments, reply_message_id=reply_message_id,
                )
            return await self.send_group_message(
                group_id, message, image_path=image_path, reply_message_id=reply_message_id,
            )

        if user_id:
            if message_segments is not None:
                return await self.send_private_message_segments(
                    user_id, message_segments, reply_message_id=reply_message_id,
                )
            return await self.send_private_message(
                user_id, message, image_path=image_path, reply_message_id=reply_message_id,
            )

        logger.warning("send_event_message: 事件无 group_id 或 user_id，无法回复")
        return {}

    async def delete_message(self, message_id: int) -> Dict[str, Any]:
        """撤回/删除消息
        
        Args:
            message_id: 消息ID
            
        Returns:
            API响应数据
        """
        return await self.call("delete_msg", {
            "message_id": message_id
        })
    
    async def group_poke(self, group_id: int, user_id: int) -> Dict[str, Any]:
        """群内戳一戳
        
        Args:
            group_id: 群号
            user_id: 要戳的用户ID
            
        Returns:
            API响应数据
        """
        return await self.call("group_poke", {
            "group_id": group_id,
            "user_id": user_id
        })
    
    async def friend_poke(self, user_id: int) -> Dict[str, Any]:
        """好友戳一戳
        
        Args:
            user_id: 要戳的用户ID
            
        Returns:
            API响应数据
        """
        return await self.call("friend_poke", {
            "user_id": user_id
        })
    
    async def send_group_dice(self, group_id: int) -> Dict[str, Any]:
        """发送群骰子消息

        Args:
            group_id: 群号

        Returns:
            API响应数据
        """
        return await self.call("send_group_msg", {
            "group_id": group_id,
            "message": [MessageSegment.dice()]
        })

    async def send_group_rps(self, group_id: int) -> Dict[str, Any]:
        """发送群猜拳消息

        Args:
            group_id: 群号

        Returns:
            API响应数据
        """
        return await self.call("send_group_msg", {
            "group_id": group_id,
            "message": [MessageSegment.rps()]
        })

    async def send_private_dice(self, user_id: int) -> Dict[str, Any]:
        """发送私聊骰子消息

        Args:
            user_id: 用户ID

        Returns:
            API响应数据
        """
        return await self.call("send_private_msg", {
            "user_id": user_id,
            "message": [MessageSegment.dice()]
        })

    async def send_private_rps(self, user_id: int) -> Dict[str, Any]:
        """发送私聊猜拳消息

        Args:
            user_id: 用户ID

        Returns:
            API响应数据
        """
        return await self.call("send_private_msg", {
            "user_id": user_id,
            "message": [MessageSegment.rps()]
        })
    
    async def get_group_message_history(
        self, 
        group_id: int, 
        message_seq: Optional[int] = None, 
        count: int = 20,
        reverse_order: bool = False
    ) -> Dict[str, Any]:
        """获取群消息历史记录
        
        Args:
            group_id: 群号
            message_seq: 消息序号，提供则从该消息开始获取
            count: 获取数量，默认20
            reverse_order: 是否倒序，默认False
            
        Returns:
            API响应数据
        """
        params = {
            "group_id": group_id,
            "count": count,
            "reverseOrder": reverse_order
        }
        if message_seq is not None:
            params["message_seq"] = message_seq
        
        return await self.call("get_group_msg_history", params)
    
    async def get_private_message_history(
        self,
        user_id: int,
        message_seq: int,
        count: int = 20,
        reverse_order: bool = False
    ) -> Dict[str, Any]:
        """获取私聊消息历史记录
        
        Args:
            user_id: 用户ID
            message_seq: 消息序号
            count: 获取数量，默认20
            reverse_order: 是否倒序，默认False
            
        Returns:
            API响应数据
        """
        return await self.call("get_friend_msg_history", {
            "user_id": user_id,
            "message_seq": message_seq,
            "count": count,
            "reverseOrder": reverse_order
        })
    
    async def get_message(self, message_id: int) -> Dict[str, Any]:
        """获取指定消息
        
        Args:
            message_id: 消息ID
            
        Returns:
            API响应数据
        """
        return await self.call("get_msg", {
            "message_id": message_id
        })

    # ======================== 群组管理 ========================

    async def get_group_list(self) -> Dict[str, Any]:
        """获取群列表

        Returns:
            API响应数据
        """
        return await self.call("get_group_list")

    async def get_group_member_list(self, group_id: int) -> Dict[str, Any]:
        """获取群成员列表

        Args:
            group_id: 群号

        Returns:
            API响应数据
        """
        return await self.call("get_group_member_list", {
            "group_id": group_id
        })

    async def get_group_member_info(self, group_id: int, user_id: int) -> Dict[str, Any]:
        """获取群成员信息

        Args:
            group_id: 群号
            user_id: 用户ID

        Returns:
            API响应数据
        """
        return await self.call("get_group_member_info", {
            "group_id": group_id,
            "user_id": user_id
        })

    async def set_group_ban(self, group_id: int, user_id: int, duration: int = 1800) -> Dict[str, Any]:
        """设置群禁言

        Args:
            group_id: 群号
            user_id: 用户ID
            duration: 禁言时长（秒），默认1800秒

        Returns:
            API响应数据
        """
        return await self.call("set_group_ban", {
            "group_id": group_id,
            "user_id": user_id,
            "duration": duration
        })

    async def set_group_kick(self, group_id: int, user_id: int, reject_add_request: bool = False) -> Dict[str, Any]:
        """踢出群成员

        Args:
            group_id: 群号
            user_id: 用户ID
            reject_add_request: 是否拒绝后续加群请求

        Returns:
            API响应数据
        """
        return await self.call("set_group_kick", {
            "group_id": group_id,
            "user_id": user_id,
            "reject_add_request": reject_add_request
        })

    async def set_group_card(self, group_id: int, user_id: int, card: str = "") -> Dict[str, Any]:
        """设置群成员名片

        Args:
            group_id: 群号
            user_id: 用户ID
            card: 名片内容，空字符串表示取消

        Returns:
            API响应数据
        """
        return await self.call("set_group_card", {
            "group_id": group_id,
            "user_id": user_id,
            "card": card
        })

    # ======================== 好友管理 ========================

    async def get_friend_list(self) -> Dict[str, Any]:
        """获取好友列表

        Returns:
            API响应数据
        """
        return await self.call("get_friend_list")

    async def get_login_info(self) -> Dict[str, Any]:
        """获取登录信息

        Returns:
            API响应数据
        """
        return await self.call("get_login_info")

    async def get_stranger_info(self, user_id: int) -> Dict[str, Any]:
        """获取陌生人信息

        Args:
            user_id: 用户ID

        Returns:
            API响应数据
        """
        return await self.call("get_stranger_info", {
            "user_id": user_id
        })

    # ======================== 请求处理 ========================

    async def set_friend_add_request(self, flag: str, approve: bool = True, remark: str = "") -> Dict[str, Any]:
        """处理好友请求

        Args:
            flag: 请求标识
            approve: 是否同意
            remark: 备注名

        Returns:
            API响应数据
        """
        return await self.call("set_friend_add_request", {
            "flag": flag,
            "approve": approve,
            "remark": remark
        })

    async def set_group_add_request(self, flag: str, sub_type: str, approve: bool = True, reason: str = "") -> Dict[str, Any]:
        """处理群请求

        Args:
            flag: 请求标识
            sub_type: 请求子类型（add/invite）
            approve: 是否同意
            reason: 拒绝理由

        Returns:
            API响应数据
        """
        return await self.call("set_group_add_request", {
            "flag": flag,
            "sub_type": sub_type,
            "approve": approve,
            "reason": reason
        })

    async def send_like(self, user_id: int, times: int = 1) -> Dict[str, Any]:
        """发送赞

        Args:
            user_id: 用户ID
            times: 点赞次数

        Returns:
            API响应数据
        """
        return await self.call("send_like", {
            "user_id": user_id,
            "times": times
        })

    async def get_version_info(self) -> Dict[str, Any]:
        """获取版本信息

        Returns:
            API响应数据
        """
        return await self.call("get_version_info")
    
    def get_performance_stats(self) -> Dict[str, Union[int, float, bool]]:
        """获取性能统计信息

        Returns:
            性能统计字典
        """
        stats: Dict[str, Union[int, float, bool]] = dict(self._perf_stats.copy())
        stats["reconnect_attempts"] = self._reconnect_attempts
        stats["is_connected"] = self._connected
        return stats


# 向后兼容别名：早期版本仅支持 NapCat，客户端名为 NapCatClient
NapCatClient = OneBotClient
