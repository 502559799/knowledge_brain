"""多轮对话管理"""
import logging
import threading
import time
import uuid
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ConversationManager:
    """多轮对话会话管理（线程安全）"""

    def __init__(self, max_turns: int = 20, timeout_minutes: int = 30, history_turns: int = 5):
        self.max_turns = max_turns
        self.timeout_minutes = timeout_minutes
        self.history_turns = history_turns
        self._sessions: Dict[str, Dict] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.time()

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        now = time.time()
        with self._lock:
            self._sessions[session_id] = {"created_at": now, "last_activity": now, "turns": []}
        self._maybe_cleanup()
        return session_id

    def add_turn(self, session_id: str, role: str, content: str) -> None:
        now = time.time()
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = {"created_at": now, "last_activity": now, "turns": []}
            self._sessions[session_id]["last_activity"] = now
            self._sessions[session_id]["turns"].append({
                "role": role, "content": content, "timestamp": now,
            })
            if len(self._sessions[session_id]["turns"]) > self.max_turns:
                self._sessions[session_id]["turns"] = self._sessions[session_id]["turns"][-self.max_turns:]

    def get_history(self, session_id: str, n: Optional[int] = None) -> List[Dict]:
        with self._lock:
            if session_id not in self._sessions:
                return []
            turns = self._sessions[session_id]["turns"]
        n = n or self.history_turns
        return turns[-n:]

    def get_or_create_session(self, session_id: Optional[str] = None) -> str:
        if session_id:
            with self._lock:
                if session_id in self._sessions and not self._is_expired_locked(session_id):
                    self._sessions[session_id]["last_activity"] = time.time()
                    return session_id
        return self.create_session()

    def is_expired(self, session_id: str) -> bool:
        with self._lock:
            return self._is_expired_locked(session_id)

    def _is_expired_locked(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return True
        sess = self._sessions[session_id]
        last = sess.get("last_activity", sess["created_at"])
        return time.time() - last > self.timeout_minutes * 60

    def _maybe_cleanup(self) -> None:
        now = time.time()
        if now - self._last_cleanup < 300:
            return
        self._last_cleanup = now
        with self._lock:
            expired = [sid for sid in list(self._sessions.keys()) if self._is_expired_locked(sid)]
            for sid in expired:
                del self._sessions[sid]
        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired sessions")
