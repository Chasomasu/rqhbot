from __future__ import annotations

import json
import os
import re
from threading import Lock
from typing import Any, Dict, Optional

hmd = [""]
gly = ["2654278608"]


class AnswerManager:
    """问答数据管理器：内存缓存 + 脏标记保存。"""

    def __init__(self, precise_file_path: str, fuzzy_file_path: str) -> None:
        self.precise_file_path = precise_file_path
        self.fuzzy_file_path = fuzzy_file_path
        self.lock = Lock()
        self.write_lock = Lock()
        self.precise_data: Dict[str, str] = {}
        self.fuzzy_data: Dict[str, str] = {}
        self.dirty = False
        self.load_all_to_memory()

    def load_all_to_memory(self) -> None:
        with self.lock:
            self.precise_data = self._safe_load(self.precise_file_path, {})
            self.fuzzy_data = self._safe_load(self.fuzzy_file_path, {})

    def _safe_load(self, path: str, default: Dict[str, str]) -> Dict[str, str]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data: Any = json.load(f)
            return data if isinstance(data, dict) else default
        except (FileNotFoundError, json.JSONDecodeError):
            self._save_file(path, {})
            return default
        except Exception:
            return default

    def _save_file(self, path: str, data: Dict[str, str]) -> bool:
        temp_file = path + ".tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            os.replace(temp_file, path)
            return True
        except Exception:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            return False

    def save_if_dirty(self) -> bool:
        if not self.dirty:
            return True
        with self.write_lock:
            # 分别保存两个文件，确保都成功才清除脏标记
            precise_success = self._save_file(self.precise_file_path, self.precise_data)
            fuzzy_success = self._save_file(self.fuzzy_file_path, self.fuzzy_data)
            # 只有两个文件都保存成功才清除脏标记
            if precise_success and fuzzy_success:
                self.dirty = False
            return precise_success and fuzzy_success

    def load_all_data(self) -> Dict[str, str]:
        with self.lock:
            all_data = self.precise_data.copy()
            all_data.update(self.fuzzy_data)
            return all_data

    def save_precise_data(self, data: Dict[str, str]) -> bool:
        with self.lock:
            self.precise_data = data
            self.dirty = True
        return self.save_if_dirty()

    def save_fuzzy_data(self, data: Dict[str, str]) -> bool:
        with self.lock:
            self.fuzzy_data = data
            self.dirty = True
        return self.save_if_dirty()

    def add_precise_answer(self, question: str, answer: str) -> bool:
        """添加精确问答；返回 True 表示已写入且成功落盘"""
        with self.lock:
            self.precise_data[question.strip()] = answer.strip()
            self.dirty = True
        return self.save_if_dirty()

    def add_fuzzy_answer(self, question: str, answer: str) -> bool:
        """添加模糊问答；返回 True 表示已写入且成功落盘"""
        with self.lock:
            self.fuzzy_data[question.strip()] = answer.strip()
            self.dirty = True
        return self.save_if_dirty()

    def add_normal_answer(self, question: str, answer: str) -> bool:
        return self.add_fuzzy_answer(question, answer)

    def has_answer(self, question: str) -> bool:
        with self.lock:
            return question in self.precise_data or question in self.fuzzy_data

    def update_answer(self, question: str, new_answer: str) -> bool:
        """修改问答；返回 True 表示已修改且成功落盘"""
        with self.lock:
            if question in self.precise_data:
                self.precise_data[question] = new_answer.strip()
            elif question in self.fuzzy_data:
                self.fuzzy_data[question] = new_answer.strip()
            else:
                return False
            self.dirty = True
        return self.save_if_dirty()

    def delete_answer(self, question: str) -> bool:
        """删除问答；返回 True 表示已删除且成功落盘"""
        with self.lock:
            deleted = False
            if question in self.precise_data:
                del self.precise_data[question]
                deleted = True
            if question in self.fuzzy_data:
                del self.fuzzy_data[question]
                deleted = True
            if not deleted:
                return False
            self.dirty = True
        return self.save_if_dirty()

    def clear_all_answers(self) -> bool:
        """清空问答；返回 True 表示已清空且成功落盘"""
        with self.lock:
            self.precise_data.clear()
            self.fuzzy_data.clear()
            self.dirty = True
        return self.save_if_dirty()

    def search_precise(self, question: str) -> Optional[str]:
        if not question:
            return None
        question_processed = self._preprocess_text(question.lower())
        with self.lock:
            items = list(self.precise_data.items())
        for stored_question, answer in items:
            if question_processed == self._preprocess_text(stored_question.lower()):
                return answer
        return None

    def search_fuzzy(self, text: str) -> Optional[str]:
        if not text:
            return None
        text_lower = text.lower()
        text_processed = self._preprocess_text(text_lower)
        best_match = None
        best_score = 0
        with self.lock:
            items = list(self.fuzzy_data.items())
        for question, answer in items:
            question_lower = question.lower()
            question_processed = self._preprocess_text(question_lower)
            score = 0
            if question_processed == text_processed or question_lower == text_lower:
                score += 100
            elif question_lower in text_lower or question_processed in text_processed:
                score += 80 + len(question)
            if score > best_score:
                best_score = score
                best_match = answer
        return best_match

    @staticmethod
    def _preprocess_text(text: str) -> str:
        text = re.sub(r"\n+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()


PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

answer_manager = AnswerManager(
    os.path.join(PLUGIN_DIR, "precise_ans.json"),
    os.path.join(PLUGIN_DIR, "fuzzy_ans.json"),
)
