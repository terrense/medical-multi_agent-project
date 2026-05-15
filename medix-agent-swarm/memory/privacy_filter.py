"""
隐私过滤与置信度评估（PostgreSQL-first 写入前处理）。
"""
import re
from typing import Any, Dict, Optional, Tuple

# 常见 PII 模式（医疗场景简化版）
_PII_PATTERNS = [
    (re.compile(r"\b1[3-9]\d{9}\b"), "[PHONE]"),
    (re.compile(r"\b\d{17}[\dXx]\b"), "[ID_CARD]"),
    (re.compile(r"\b\d{6}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b"), "[ID_CARD]"),
    (re.compile(r"[\w.-]+@[\w.-]+\.\w+"), "[EMAIL]"),
]


def filter_pii(text: str) -> str:
    """脱敏文本中的手机号、身份证、邮箱等。"""
    if not text:
        return text
    out = text
    for pattern, repl in _PII_PATTERNS:
        out = pattern.sub(repl, out)
    return out


def assess_confidence(
    question: str,
    answer: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> float:
    """
    启发式置信度 0~1：用于决定是否同步 Mem0。
    """
    meta = metadata or {}
    score = 0.5
    if answer and len(answer.strip()) > 80:
        score += 0.15
    if question and len(question.strip()) > 10:
        score += 0.1
    if meta.get("timeout_occurred"):
        score -= 0.25
    if meta.get("mode") == "swarm" and meta.get("agents_count", 0) >= 2:
        score += 0.1
    return max(0.0, min(1.0, score))


def prepare_memory_record(
    question: str,
    answer: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str, float, Dict[str, Any]]:
    """
    返回 (filtered_question, filtered_answer, confidence, enriched_metadata)。
    """
    meta = dict(metadata or {})
    fq = filter_pii(question)
    fa = filter_pii(answer)
    confidence = assess_confidence(fq, fa, meta)
    meta["confidence"] = confidence
    meta["pii_filtered"] = True
    return fq, fa, confidence, meta
