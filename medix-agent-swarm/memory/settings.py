"""Load memory-related configuration from project config or environment."""
import os
import sys
from typing import Any, Dict

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from config import MEM0_CONFIG, REDIS_CONFIG, POSTGRES_CONFIG, MEMORY_CONFIG
except ImportError:
    MEM0_CONFIG = {}
    REDIS_CONFIG = {}
    POSTGRES_CONFIG = {}
    MEMORY_CONFIG = {}


def _env(key: str, default: Any = None) -> Any:
    val = os.getenv(key)
    return val if val is not None else default


def get_redis_config() -> Dict[str, Any]:
    return {
        "host": _env("REDIS_HOST", REDIS_CONFIG.get("host", "localhost")),
        "port": int(_env("REDIS_PORT", REDIS_CONFIG.get("port", 6379))),
        "db": int(_env("REDIS_DB", REDIS_CONFIG.get("db", 0))),
        "password": _env("REDIS_PASSWORD", REDIS_CONFIG.get("password")),
    }


def get_postgres_config() -> Dict[str, Any]:
    return {
        "host": _env("POSTGRES_HOST", POSTGRES_CONFIG.get("host", "localhost")),
        "port": int(_env("POSTGRES_PORT", POSTGRES_CONFIG.get("port", 5432))),
        "database": _env("POSTGRES_DB", POSTGRES_CONFIG.get("database", "medix_memory")),
        "user": _env("POSTGRES_USER", POSTGRES_CONFIG.get("user", "medix")),
        "password": _env("POSTGRES_PASSWORD", POSTGRES_CONFIG.get("password", "medix")),
    }


def get_memory_config() -> Dict[str, Any]:
    return {
        "default_user_id": _env("MEMORY_DEFAULT_USER_ID", MEMORY_CONFIG.get("default_user_id", "medix_user")),
        "short_term_storage": _env("SHORT_TERM_STORAGE", MEMORY_CONFIG.get("short_term_storage", "redis")),
        "session_ttl_seconds": int(_env("SESSION_TTL", MEMORY_CONFIG.get("session_ttl_seconds", 3600))),
        "blackboard_ttl_seconds": int(_env("BLACKBOARD_TTL", MEMORY_CONFIG.get("blackboard_ttl_seconds", 7200))),
        "tool_cache_ttl_seconds": int(_env("TOOL_CACHE_TTL", MEMORY_CONFIG.get("tool_cache_ttl_seconds", 1800))),
        "min_confidence_for_sync": float(_env("MIN_CONFIDENCE", MEMORY_CONFIG.get("min_confidence_for_sync", 0.3))),
        "fallback_to_memory_if_redis_down": MEMORY_CONFIG.get("fallback_to_memory_if_redis_down", True),
    }


def get_mem0_config() -> Dict[str, Any]:
    return dict(MEM0_CONFIG or {})
