"""
PostgreSQL 权威存储：长期记忆账本、会话摘要、审计日志、用户授权。
"""
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from .settings import get_memory_config, get_postgres_config

_store_singleton: Optional["AuthoritativeStore"] = None

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS user_consents (
    user_id VARCHAR(128) PRIMARY KEY,
    allowed_categories JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL,
    session_id VARCHAR(128),
    memory_type VARCHAR(64) NOT NULL DEFAULT 'session_summary',
    content TEXT NOT NULL,
    structured_data JSONB,
    confidence REAL NOT NULL DEFAULT 0.0,
    mem0_id VARCHAR(256),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id);

CREATE TABLE IF NOT EXISTS session_summaries (
    id UUID PRIMARY KEY,
    session_id VARCHAR(128) NOT NULL UNIQUE,
    user_id VARCHAR(128) NOT NULL,
    question TEXT,
    summary_json JSONB,
    markdown_export_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    memory_id UUID,
    user_id VARCHAR(128),
    action VARCHAR(64) NOT NULL,
    actor VARCHAR(128) NOT NULL DEFAULT 'system',
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_memory ON audit_logs(memory_id);
"""


class AuthoritativeStore:
    """PostgreSQL 账本；不可用时 enabled=False，长期记忆降级为仅 Mem0。"""

    def __init__(self, pg_config: Optional[Dict[str, Any]] = None):
        self._config = pg_config or get_postgres_config()
        self._default_user = get_memory_config().get("default_user_id", "medix_user")
        self.conn = None
        self.enabled = False
        try:
            import psycopg2
            import psycopg2.extras

            self.conn = psycopg2.connect(
                host=self._config["host"],
                port=self._config["port"],
                dbname=self._config["database"],
                user=self._config["user"],
                password=self._config["password"],
            )
            self.conn.autocommit = True
            self._psycopg2_extras = psycopg2.extras
            self._init_schema()
            self.enabled = True
            logger.info("AuthoritativeStore (PostgreSQL) connected")
        except Exception as e:
            logger.warning(f"AuthoritativeStore unavailable: {e}")

    def _init_schema(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute(_SCHEMA_SQL)

    def _audit(
        self,
        cur,
        action: str,
        memory_id: Optional[str] = None,
        user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        actor: str = "system",
    ) -> None:
        cur.execute(
            """
            INSERT INTO audit_logs (memory_id, user_id, action, actor, details)
            VALUES (%s::uuid, %s, %s, %s, %s::jsonb)
            """,
            (memory_id, user_id or self._default_user, action, actor, json.dumps(details or {})),
        )

    def ensure_user_consent(self, user_id: str, allowed_categories: Optional[List[str]] = None) -> None:
        if not self.enabled:
            return
        cats = allowed_categories or ["session_summary", "structured_case", "qa_summary"]
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_consents (user_id, allowed_categories)
                VALUES (%s, %s::jsonb)
                ON CONFLICT (user_id) DO NOTHING
                """,
                (user_id, json.dumps(cats)),
            )

    def insert_memory(
        self,
        session_id: str,
        content: str,
        user_id: Optional[str] = None,
        memory_type: str = "session_summary",
        structured_data: Optional[Dict[str, Any]] = None,
        confidence: float = 0.0,
        question: Optional[str] = None,
        answer_preview: Optional[str] = None,
    ) -> Optional[str]:
        """
        PostgreSQL-first：写入权威记忆行，返回 pg memory UUID。
        """
        if not self.enabled:
            return None

        uid = user_id or self._default_user
        self.ensure_user_consent(uid)
        memory_id = str(uuid.uuid4())
        payload = dict(structured_data or {})
        if question:
            payload["question"] = question[:500]
        if answer_preview:
            payload["answer_preview"] = answer_preview[:500]

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO memories (
                        id, user_id, session_id, memory_type, content,
                        structured_data, confidence
                    ) VALUES (%s::uuid, %s, %s, %s, %s, %s::jsonb, %s)
                    """,
                    (
                        memory_id,
                        uid,
                        session_id,
                        memory_type,
                        content,
                        json.dumps(payload, ensure_ascii=False),
                        confidence,
                    ),
                )
                self._audit(
                    cur,
                    action="memory_created",
                    memory_id=memory_id,
                    user_id=uid,
                    details={"session_id": session_id, "memory_type": memory_type},
                )
            logger.info(f"PG memory created: {memory_id}")
            return memory_id
        except Exception as e:
            logger.error(f"insert_memory failed: {e}")
            return None

    def attach_mem0_id(self, pg_memory_id: str, mem0_id: str) -> bool:
        if not self.enabled:
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE memories SET mem0_id = %s, updated_at = NOW()
                    WHERE id = %s::uuid AND is_deleted = FALSE
                    """,
                    (mem0_id, pg_memory_id),
                )
                self._audit(
                    cur,
                    action="mem0_synced",
                    memory_id=pg_memory_id,
                    details={"mem0_id": mem0_id},
                )
            return True
        except Exception as e:
            logger.error(f"attach_mem0_id failed: {e}")
            return False

    def get_memory(self, pg_memory_id: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        try:
            with self.conn.cursor(cursor_factory=self._psycopg2_extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id::text, user_id, session_id, memory_type, content,
                           structured_data, confidence, mem0_id, created_at, updated_at
                    FROM memories
                    WHERE id = %s::uuid AND is_deleted = FALSE
                    """,
                    (pg_memory_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"get_memory failed: {e}")
            return None

    def get_memory_by_mem0_id(self, mem0_id: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        try:
            with self.conn.cursor(cursor_factory=self._psycopg2_extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id::text, user_id, session_id, memory_type, content,
                           structured_data, confidence, mem0_id, created_at
                    FROM memories
                    WHERE mem0_id = %s AND is_deleted = FALSE
                    """,
                    (mem0_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"get_memory_by_mem0_id failed: {e}")
            return None

    def soft_delete_memory(self, pg_memory_id: str, actor: str = "system") -> bool:
        if not self.enabled:
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE memories SET is_deleted = TRUE, updated_at = NOW()
                    WHERE id = %s::uuid
                    """,
                    (pg_memory_id,),
                )
                self._audit(
                    cur,
                    action="memory_soft_deleted",
                    memory_id=pg_memory_id,
                    actor=actor,
                )
            return True
        except Exception as e:
            logger.error(f"soft_delete_memory failed: {e}")
            return False

    def save_session_summary_row(
        self,
        session_id: str,
        question: str,
        summary_json: Dict[str, Any],
        markdown_path: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Optional[str]:
        if not self.enabled:
            return None
        uid = user_id or self._default_user
        row_id = str(uuid.uuid4())
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO session_summaries (
                        id, session_id, user_id, question, summary_json, markdown_export_path
                    ) VALUES (%s::uuid, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (session_id) DO UPDATE SET
                        question = EXCLUDED.question,
                        summary_json = EXCLUDED.summary_json,
                        markdown_export_path = EXCLUDED.markdown_export_path
                    """,
                    (
                        row_id,
                        session_id,
                        uid,
                        question,
                        json.dumps(summary_json, ensure_ascii=False, default=str),
                        markdown_path,
                    ),
                )
                self._audit(
                    cur,
                    action="session_summary_saved",
                    user_id=uid,
                    details={"session_id": session_id},
                )
            return row_id
        except Exception as e:
            logger.error(f"save_session_summary_row failed: {e}")
            return None


def get_authoritative_store() -> AuthoritativeStore:
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = AuthoritativeStore()
    return _store_singleton
