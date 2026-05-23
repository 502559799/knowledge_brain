"""多轮对话管理"""
import uuid, time
from typing import Any, Dict, List, Optional

class ConversationManager:
    """多轮对话会话管理"""
    def __init__(self, max_turns: int = 20, timeout_minutes: int = 30, history_turns: int = 5):
        self.max_turns = max_turns
        self.timeout_minutes = timeout_minutes
        self.history_turns = history_turns
        self._sessions: Dict[str, Dict] = {}

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = {"created_at": time.time(), "turns": []}
        return session_id

    def add_turn(self, session_id: str, role: str, content: str) -> None:
        if session_id not in self._sessions:
            self._sessions[session_id] = {"created_at": time.time(), "turns": []}
        self._sessions[session_id]["turns"].append({"role": role, "content": content, "timestamp": time.time()})
        if len(self._sessions[session_id]["turns"]) > self.max_turns:
            self._sessions[session_id]["turns"] = self._sessions[session_id]["turns"][-self.max_turns:]

    def get_history(self, session_id: str, n: Optional[int] = None) -> List[Dict]:
        if session_id not in self._sessions: return []
        turns = self._sessions[session_id]["turns"]
        n = n or self.history_turns
        return turns[-n:]

    def is_expired(self, session_id: str) -> bool:
        if session_id not in self._sessions: return True
        return time.time() - self._sessions[session_id]["created_at"] > self.timeout_minutes * 60
