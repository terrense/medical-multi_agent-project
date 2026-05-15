"""
工具调用结果缓存（Redis）。
"""
from typing import Any, Dict, Optional

from loguru import logger

from .redis_store import get_redis_store


class ToolCallCache:
    def __init__(self, redis_store=None):
        self.redis = redis_store or get_redis_store()

    @property
    def enabled(self) -> bool:
        return self.redis.enabled

    def get(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        hit = self.redis.get_tool_cache(tool_name, arguments)
        if hit:
            logger.debug(f"Tool cache HIT: {tool_name}")
        return hit

    def set(self, tool_name: str, arguments: Dict[str, Any], result: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        if result.get("success") is False:
            return
        self.redis.set_tool_cache(tool_name, arguments, result)
