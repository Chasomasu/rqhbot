"""
pintu — 九宫格拼图游戏核心逻辑
"""

from __future__ import annotations

import random
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from .config_manager import add_admin, get_admins, is_puzzle_admin, remove_admin

PLUGIN_DIR = Path(__file__).resolve().parent
IMAGE_DIR = PLUGIN_DIR / "tupina"
TEMP_DIR = PLUGIN_DIR / "temp"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
CORRECT_ORDER = list(range(1, 10))

HELP_TEXT = (
    "九宫格拼图游戏指令：\n"
    "开拼图：拼图管理员开始新对局\n"
    "结算：拼图管理员结束当前对局并结算\n"
    "重开：拼图管理员重新打乱当前拼图\n"
    "拼图加管 QQ号/@用户：添加拼图管理员\n"
    "拼图删管 QQ号/@用户：移除拼图管理员\n"
    "拼图管理：查看拼图管理员\n"
    "9换1 或 交换 4 7：交换两个位置的碎片\n"
    "状态 或 /puzzle：查看当前拼图\n"
    "得分 或 /score：查看本局得分排行\n"
    "帮助 或 /help：查看本帮助\n"
    "兼容旧命令：/startgame、/endgame、/resetpuzzle"
)


@dataclass
class GameSession:
    group_id: int
    active: bool = False
    original_image_path: str = ""
    tiles: List[Image.Image] = field(default_factory=list)
    arrangement: List[int] = field(default_factory=lambda: CORRECT_ORDER.copy())
    scores: Dict[str, int] = field(default_factory=dict)
    scored_positions: Dict[str, set] = field(default_factory=dict)
    piece_size: Tuple[int, int] = (0, 0)


class GameService:
    """拼图游戏服务 —— 纯逻辑，不持有 api 引用"""

    def __init__(self) -> None:
        self.games: Dict[int, GameSession] = {}
        TEMP_DIR.mkdir(parents=True, exist_ok=True)

    def get_session(self, group_id: int) -> GameSession:
        if group_id not in self.games:
            self.games[group_id] = GameSession(group_id=group_id)
        return self.games[group_id]

    def choose_image(self) -> Optional[Path]:
        if not IMAGE_DIR.exists():
            return None
        images = [
            path for path in IMAGE_DIR.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        if not images:
            return None
        return random.choice(images)

    def load_tiles(self, image_path: Path) -> Tuple[List[Image.Image], Tuple[int, int]]:
        with Image.open(image_path) as image:
            image = image.convert("RGB")
            width, height = image.size
            piece = min(width, height) // 3
            left = (width - piece * 3) // 2
            top = (height - piece * 3) // 2
            image = image.crop((left, top, left + piece * 3, top + piece * 3))
            tiles = []
            for row in range(3):
                for col in range(3):
                    box = (col * piece, row * piece, (col + 1) * piece, (row + 1) * piece)
                    tiles.append(image.crop(box).copy())
        return tiles, (piece, piece)

    def shuffle(self, session: GameSession) -> None:
        arrangement = CORRECT_ORDER.copy()
        while arrangement == CORRECT_ORDER:
            random.shuffle(arrangement)
        session.arrangement = arrangement

    @staticmethod
    def count_correct_tiles(arrangement: List[int]) -> int:
        return sum(1 for index, tile in enumerate(arrangement, 1) if index == tile)

    def save_puzzle_image(self, session: GameSession) -> Path:
        piece_w, piece_h = session.piece_size
        image = Image.new("RGB", (piece_w * 3, piece_h * 3), "white")
        for index, tile_index in enumerate(session.arrangement):
            row, col = divmod(index, 3)
            image.paste(session.tiles[tile_index - 1], (col * piece_w, row * piece_h))

        draw = ImageDraw.Draw(image)
        font = self._get_font(max(18, piece_w // 6))
        for index in range(9):
            row, col = divmod(index, 3)
            x = col * piece_w
            y = row * piece_h
            draw.rectangle(
                (x, y, x + piece_w - 1, y + piece_h - 1),
                outline=(255, 255, 255),
                width=max(2, piece_w // 80),
            )
            label = str(index + 1)
            bbox = draw.textbbox((0, 0), label, font=font)
            label_w = bbox[2] - bbox[0]
            label_h = bbox[3] - bbox[1]
            padding = max(6, piece_w // 35)
            draw.rectangle(
                (x + padding, y + padding, x + padding * 2 + label_w, y + padding * 2 + label_h),
                fill=(0, 0, 0),
            )
            draw.text(
                (x + padding * 1.5, y + padding * 1.2),
                label,
                fill=(255, 255, 255),
                font=font,
            )

        # 每次渲染都用唯一文件名：并发交换时不会覆盖彼此的棋盘图
        output = TEMP_DIR / f"puzzle_{session.group_id}_{uuid.uuid4().hex}.jpg"
        image.save(output, "JPEG", quality=90)
        return output

    @staticmethod
    def remove_temp_image(image_path) -> None:
        """删除本次渲染的临时图片（仅限 TEMP_DIR 内），失败时静默忽略"""
        try:
            path = Path(image_path)
            if path.parent == TEMP_DIR:
                path.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _get_font(size: int) -> ImageFont.FreeTypeFont:
        for font_name in ("msyh.ttc", "simhei.ttf", "arial.ttf"):
            try:
                return ImageFont.truetype(font_name, size)
            except Exception:
                pass
        return ImageFont.load_default()

    @staticmethod
    def parse_swap(text: str) -> Optional[Tuple[int, int]]:
        match = re.fullmatch(r"(\d)\s*换\s*(\d)", text)
        if not match:
            match = re.fullmatch(r"交换\s+(\d)\s+(\d)", text)
        if not match:
            return None
        return int(match.group(1)), int(match.group(2))

    @staticmethod
    def extract_target_user_id(text: str, prefix: str, event_segments: list) -> Optional[str]:
        """从 @ 消息段或前缀后文本中提取目标用户 ID"""
        for seg in event_segments:
            if seg.get("type") == "at":
                qq = seg.get("data", {}).get("qq", "")
                if qq:
                    return str(qq)
        target = text.removeprefix(prefix).strip()
        return target if target.isdigit() else None

    # ---------- 管理员包装 ----------

    @staticmethod
    def is_admin(user_id: int, group_id: Optional[int] = None) -> bool:
        return is_puzzle_admin(user_id, group_id)

    @staticmethod
    def get_admins(group_id: Optional[int] = None) -> List[str]:
        return get_admins(group_id)

    @staticmethod
    def add_admin(user_id: str, group_id: Optional[int] = None) -> bool:
        return add_admin(user_id, group_id)

    @staticmethod
    def remove_admin(user_id: str, group_id: Optional[int] = None) -> bool:
        return remove_admin(user_id, group_id)
