"""
长期记忆：PostgreSQL-first + Mem0 语义层。

写入：隐私过滤 → PG 权威账本 →（置信度达标）同步 Mem0 并回写 mem0_id
读取：Mem0 语义召回 → 按 pg_memory_id 回查 PG 权威内容
"""
import json
from typing import Any, Dict, List, Optional
from datetime import datetime
from loguru import logger
import os

# Mem0 Cloud API：metadata JSON 序列化后不得超过 2000 字符
MEM0_METADATA_MAX_CHARS = 1900

try:
    from .entropy_manager import MemoryEntropyManager
    ENTROPY_ENABLED = True
except ImportError:
    ENTROPY_ENABLED = False

from .authoritative_store import AuthoritativeStore, get_authoritative_store
from .privacy_filter import prepare_memory_record
from .settings import get_mem0_config, get_memory_config

try:
    from mem0 import MemoryClient
    MEM0_AVAILABLE = True
except ImportError:
    MEM0_AVAILABLE = False
    logger.warning("mem0ai not installed. Mem0 semantic layer disabled.")


class LongTermMemory:
    """
    长期记忆管理器：PG 账本 + Mem0 语义索引。
    """

    def __init__(
        self,
        mem0_config: Optional[Dict[str, Any]] = None,
        authoritative_store: Optional[AuthoritativeStore] = None,
        user_id: Optional[str] = None,
    ):
        self.pg = authoritative_store or get_authoritative_store()
        self.mem_cfg = get_memory_config()
        self.user_id = user_id or self.mem_cfg.get("default_user_id", "medix_user")
        self.min_confidence = float(self.mem_cfg.get("min_confidence_for_sync", 0.3))

        self.entropy_manager = MemoryEntropyManager() if ENTROPY_ENABLED else None
        self.mem0 = None
        self.mem0_enabled = False

        if MEM0_AVAILABLE:
            try:
                cfg = mem0_config or get_mem0_config()
                api_key = (
                    (cfg or {}).get("api_key")
                    or os.getenv("MEM0_API_KEY")
                )
                if api_key:
                    self.mem0 = MemoryClient(api_key=api_key)
                    self.mem0_enabled = True
                    logger.info("LongTermMemory: Mem0 semantic layer enabled")
                else:
                    logger.warning("MEM0_API_KEY not set; semantic search disabled")
            except Exception as e:
                logger.warning(f"Mem0 init failed: {e}")

        self.enabled = self.pg.enabled or self.mem0_enabled
        if not self.enabled:
            logger.warning("Long-term memory fully disabled (no PG and no Mem0)")

    @staticmethod
    def _build_mem0_metadata(
        session_id: str,
        pg_memory_id: Optional[str],
        source_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        仅向 Mem0 传递轻量标量元数据（禁止塞入长文本 / 嵌套对象）。
        完整内容在 PG；Mem0 只做语义索引 + pg_memory_id 回链。
        """
        src = source_meta or {}
        compact: Dict[str, Any] = {
            "type": "session_summary",
            "session_id": str(session_id)[:128],
            "pg_memory_id": str(pg_memory_id) if pg_memory_id else None,
            "timestamp": datetime.now().isoformat(),
        }
        for key in (
            "confidence",
            "mode",
            "pii_filtered",
            "agents_count",
            "subtasks_count",
            "timeout_occurred",
        ):
            if key not in src:
                continue
            val = src[key]
            if isinstance(val, (bool, int, float)) or val is None:
                compact[key] = val
            elif isinstance(val, str):
                compact[key] = val[:200]

        if "total_time" in src:
            try:
                compact["total_time"] = round(float(src["total_time"]), 2)
            except (TypeError, ValueError):
                pass

        serialized = json.dumps(compact, ensure_ascii=False)
        if len(serialized) > MEM0_METADATA_MAX_CHARS:
            compact.pop("total_time", None)
            compact.pop("timeout_occurred", None)
        return compact

    def add_session_summary(
        self,
        session_id: str,
        question: str,
        answer: str,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        PostgreSQL-first 写入长期记忆。

        Returns:
            pg_memory_id（权威 ID）；失败返回 None
        """
        uid = user_id or self.user_id
        fq, fa, confidence, meta = prepare_memory_record(question, answer, metadata)
        memory_text = f"问题：{fq}\n回答：{fa[:500]}{'...' if len(fa) > 500 else ''}"
        # Mem0 消息体单独截断（语义检索用，权威全文在 PG）
        mem0_message = (
            f"问题：{fq[:200]}\n"
            f"回答摘要：{fa[:400]}{'...' if len(fa) > 400 else ''}"
        )

        pg_structured = {**meta}
        pg_id = self.pg.insert_memory(
            session_id=session_id,
            content=memory_text,
            user_id=uid,
            memory_type="session_summary",
            structured_data=pg_structured,
            confidence=confidence,
            question=fq,
            answer_preview=fa,
        )

        if not pg_id and not self.mem0_enabled:
            return None

        mem0_id = None
        if self.mem0_enabled and confidence >= self.min_confidence:
            mem0_id = self._sync_to_mem0(
                memory_text=mem0_message,
                session_id=session_id,
                pg_memory_id=pg_id,
                user_id=uid,
                source_meta=meta,
            )
            if pg_id and mem0_id:
                self.pg.attach_mem0_id(pg_id, mem0_id)
        elif self.mem0_enabled and confidence < self.min_confidence:
            logger.info(
                f"Skip Mem0 sync: confidence {confidence:.2f} < {self.min_confidence}"
            )

        return pg_id or mem0_id

    def _sync_to_mem0(
        self,
        memory_text: str,
        session_id: str,
        pg_memory_id: Optional[str],
        user_id: str,
        source_meta: Dict[str, Any],
    ) -> Optional[str]:
        mem0_metadata = self._build_mem0_metadata(session_id, pg_memory_id, source_meta)
        try:
            result = self.mem0.add(
                messages=[{"role": "user", "content": memory_text}],
                user_id=user_id,
                metadata=mem0_metadata,
                infer=False,
            )
            if isinstance(result, dict):
                return result.get("id") or (
                    result.get("results", [{}])[0].get("id") if result.get("results") else None
                )
            return str(result) if result else None
        except Exception as e:
            logger.error(f"Mem0 sync failed: {e}")
            return None

    def search_similar_sessions(
        self,
        query: str,
        limit: int = 5,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Mem0 语义召回 + PG 权威内容回查。
        """
        uid = user_id or self.user_id
        if not self.mem0_enabled:
            return []

        try:
            results = self.mem0.search(query=query, user_id=uid, limit=limit * 2)
            if isinstance(results, dict):
                results_list = results.get("results", [])
            elif isinstance(results, list):
                results_list = results
            else:
                results_list = []

            formatted: List[Dict[str, Any]] = []
            for result in results_list:
                meta = result.get("metadata", {}) or {}
                pg_id = meta.get("pg_memory_id")
                mem0_id = result.get("id", "unknown")

                content = result.get("memory", result.get("text", ""))
                confidence = meta.get("confidence")
                session_id = meta.get("session_id")

                if pg_id and self.pg.enabled:
                    row = self.pg.get_memory(str(pg_id))
                    if row:
                        content = row["content"]
                        confidence = row.get("confidence", confidence)
                        session_id = row.get("session_id", session_id)

                formatted.append({
                    "memory_id": mem0_id,
                    "pg_memory_id": pg_id,
                    "content": content,
                    "score": result.get("score", 0.0),
                    "metadata": meta,
                    "confidence": confidence,
                    "session_id": session_id,
                    "timestamp": meta.get("timestamp"),
                    "source": "pg+mem0" if pg_id and self.pg.enabled else "mem0",
                })

            if self.entropy_manager and formatted:
                formatted = self.entropy_manager.deduplicate_sessions(formatted)

            formatted = formatted[:limit]
            logger.info(f"Long-term search: {len(formatted)} results for query={query[:50]}...")
            return formatted

        except Exception as e:
            logger.error(f"search_similar_sessions failed: {e}")
            return []

    def delete_memory(self, pg_memory_id: str, actor: str = "system") -> bool:
        """软删 PG 账本记录（Mem0 侧需另行调用 API 时可扩展）。"""
        return self.pg.soft_delete_memory(pg_memory_id, actor=actor)
