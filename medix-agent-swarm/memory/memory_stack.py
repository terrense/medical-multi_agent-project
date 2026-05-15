"""
记忆栈单例：统一初始化 Redis / PostgreSQL / Mem0 三层组件。
"""
from typing import Optional

from .authoritative_store import AuthoritativeStore, get_authoritative_store
from .long_term import LongTermMemory
from .redis_store import RedisStore, get_redis_store
from .settings import get_memory_config, get_mem0_config
from .short_term import ShortTermMemory
from .tool_cache import ToolCallCache

_stack: Optional["MemoryStack"] = None


class MemoryStack:
    def __init__(self):
        cfg = get_memory_config()
        self.redis_store = get_redis_store()
        self.authoritative_store = get_authoritative_store()
        self.tool_cache = ToolCallCache(self.redis_store)

        preferred = cfg.get("short_term_storage", "redis")
        if preferred == "redis" and self.redis_store.enabled:
            storage_type = "redis"
        elif preferred == "redis" and cfg.get("fallback_to_memory_if_redis_down", True):
            storage_type = "memory"
        else:
            storage_type = preferred if preferred in ("memory", "redis") else "memory"

        self.short_term_memory = ShortTermMemory(
            storage_type=storage_type,
            redis_store=self.redis_store,
        )
        self.long_term_memory = LongTermMemory(
            mem0_config=get_mem0_config(),
            authoritative_store=self.authoritative_store,
        )
        self.default_user_id = cfg.get("default_user_id", "medix_user")


def get_memory_stack() -> MemoryStack:
    global _stack
    if _stack is None:
        _stack = MemoryStack()
    return _stack
