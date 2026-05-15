"""
Redis 统一访问层：短期会话、Swarm blackboard、工具调用缓存。
"""
import hashlib
import json
from typing import Any, Dict, Optional

from loguru import logger

from .settings import get_memory_config, get_redis_config

_redis_singleton: Optional["RedisStore"] = None


class RedisStore:
    """Redis 封装：连接管理 + 三类 key 空间。"""

    PREFIX_SESSION = "medix:session:"
    PREFIX_BLACKBOARD = "medix:blackboard:"
    PREFIX_TOOL = "medix:tool:"

    def __init__(self, redis_config: Optional[Dict[str, Any]] = None):
        self._config = redis_config or get_redis_config()
        self._mem_cfg = get_memory_config()
        self.client = None
        self.enabled = False
        try:
            import redis

            self.client = redis.Redis(
                host=self._config.get("host", "localhost"),
                port=self._config.get("port", 6379),
                db=self._config.get("db", 0),
                password=self._config.get("password"),
                decode_responses=True,
            )
            self.client.ping()
            self.enabled = True
            logger.info("RedisStore connected")
        except Exception as e:
            logger.warning(f"RedisStore unavailable: {e}")

    @property
    def session_ttl(self) -> int:
        return int(self._mem_cfg.get("session_ttl_seconds", 3600))

    @property
    def blackboard_ttl(self) -> int:
        return int(self._mem_cfg.get("blackboard_ttl_seconds", 7200))

    @property
    def tool_cache_ttl(self) -> int:
        return int(self._mem_cfg.get("tool_cache_ttl_seconds", 1800))

    # --- session (short-term) ---
    def save_session(self, session_id: str, payload: Dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        key = f"{self.PREFIX_SESSION}{session_id}"
        try:
            self.client.setex(key, self.session_ttl, json.dumps(payload, ensure_ascii=False))
            return True
        except Exception as e:
            logger.error(f"Redis save_session failed: {e}")
            return False

    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        key = f"{self.PREFIX_SESSION}{session_id}"
        try:
            raw = self.client.get(key)
            return json.loads(raw) if raw else None
        except Exception as e:
            logger.error(f"Redis load_session failed: {e}")
            return None

    def delete_session(self, session_id: str) -> None:
        if self.enabled:
            self.client.delete(f"{self.PREFIX_SESSION}{session_id}")

    # --- blackboard (swarm) ---
    def save_blackboard(self, session_id: str, snapshot: Dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        key = f"{self.PREFIX_BLACKBOARD}{session_id}"
        try:
            self.client.setex(key, self.blackboard_ttl, json.dumps(snapshot, ensure_ascii=False))
            return True
        except Exception as e:
            logger.error(f"Redis save_blackboard failed: {e}")
            return False

    def load_blackboard(self, session_id: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        key = f"{self.PREFIX_BLACKBOARD}{session_id}"
        try:
            raw = self.client.get(key)
            return json.loads(raw) if raw else None
        except Exception as e:
            logger.error(f"Redis load_blackboard failed: {e}")
            return None

    # --- tool cache ---
    @staticmethod
    def tool_cache_key(tool_name: str, arguments: Dict[str, Any]) -> str:
        raw = json.dumps({"tool": tool_name, "args": arguments}, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
        return f"{RedisStore.PREFIX_TOOL}{tool_name}:{digest}"

    def get_tool_cache(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        key = self.tool_cache_key(tool_name, arguments)
        try:
            raw = self.client.get(key)
            return json.loads(raw) if raw else None
        except Exception as e:
            logger.error(f"Redis get_tool_cache failed: {e}")
            return None

    def set_tool_cache(self, tool_name: str, arguments: Dict[str, Any], result: Dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        key = self.tool_cache_key(tool_name, arguments)
        try:
            self.client.setex(
                key,
                self.tool_cache_ttl,
                json.dumps(result, ensure_ascii=False),
            )
            return True
        except Exception as e:
            logger.error(f"Redis set_tool_cache failed: {e}")
            return False


def get_redis_store() -> RedisStore:
    global _redis_singleton
    if _redis_singleton is None:
        _redis_singleton = RedisStore()
    return _redis_singleton
