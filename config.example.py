# Copy this file to config.py and fill in your API keys.

LLM_CONFIG = {
    "api_key": "your-deepseek-or-openai-api-key",
    "model_name": "deepseek-chat",
    "base_url": "https://api.deepseek.com/v1",
    "temperature": 0.7,
    "max_tokens": 8192,
}

MEM0_CONFIG = {
    "api_key": "your-mem0-api-key",
}

REDIS_CONFIG = {
    "host": "localhost",
    "port": 6379,
    "db": 0,
    "password": None,
}

POSTGRES_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "medix_memory",
    "user": "medix",
    "password": "medix",
}

MEMORY_CONFIG = {
    "default_user_id": "medix_user",
    "short_term_storage": "redis",
    "session_ttl_seconds": 3600,
    "blackboard_ttl_seconds": 7200,
    "tool_cache_ttl_seconds": 1800,
    "min_confidence_for_sync": 0.3,
    "fallback_to_memory_if_redis_down": True,
}
