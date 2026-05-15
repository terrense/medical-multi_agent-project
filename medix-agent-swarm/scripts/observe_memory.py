#!/usr/bin/env python3
"""
记忆系统观察工具：一次性查看 Redis（短期）/ PostgreSQL（权威账本）/ Mem0（语义层）快照。

用法：
  # 列出最近会话（从 Redis + PG 推断）
  python scripts/observe_memory.py --list

  # 查看指定 session（从 main.py 日志里复制 session_id）
  python scripts/observe_memory.py 20260516-001100-a40a5cfa

  # 附带一条查询，看 Mem0 语义召回
  python scripts/observe_memory.py 20260516-001100-a40a5cfa --query "高血压"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
SWARM = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SWARM))


def _banner(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _print_json(data: Any, max_len: int = 2000) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) > max_len:
        print(text[:max_len] + f"\n... (truncated, total {len(text)} chars)")
    else:
        print(text)


def observe_redis(session_id: Optional[str]) -> None:
    _banner("1. Redis — 短期会话 / Blackboard / 工具缓存")
    from memory import get_redis_store

    store = get_redis_store()
    if not store.enabled:
        print("  [x] Redis 未连接（短期记忆可能降级为内存）")
        return

    print("  [ok] Redis 已连接\n")

    if session_id:
        session_key = f"{store.PREFIX_SESSION}{session_id}"
        blackboard_key = f"{store.PREFIX_BLACKBOARD}{session_id}"
        session_data = store.load_session(session_id)
        blackboard_data = store.load_blackboard(session_id)

        print(f"  Key: {session_key}")
        if session_data:
            msgs = session_data.get("messages", [])
            print(f"  短期消息数: {len(msgs)}")
            for i, m in enumerate(msgs[-6:], 1):
                role = m.get("role", "?")
                content = (m.get("content") or "")[:120]
                print(f"    [{i}] {role}: {content}{'...' if len(m.get('content',''))>120 else ''}")
        else:
            print("  (无数据 — 可能已过期 TTL~1h，或 session_id 不对)")

        print(f"\n  Key: {blackboard_key}")
        if blackboard_data:
            print(f"  子任务数: {len(blackboard_data.get('task_decomposition', {}))}")
            print(f"  事件数: {len(blackboard_data.get('events', []))}")
        else:
            print("  (无 blackboard — 未走 Swarm 或已过期)")
    else:
        keys = store.client.keys(f"{store.PREFIX_SESSION}*")
        print(f"  当前 session keys ({len(keys)}):")
        for k in sorted(keys)[:20]:
            print(f"    - {k}")
        if len(keys) > 20:
            print(f"    ... 还有 {len(keys) - 20} 个")

        bb_keys = store.client.keys(f"{store.PREFIX_BLACKBOARD}*")
        print(f"\n  blackboard keys: {len(bb_keys)}")
        tool_keys = store.client.keys(f"{store.PREFIX_TOOL}*")
        print(f"  tool cache keys: {len(tool_keys)}")


def observe_postgres(session_id: Optional[str]) -> None:
    _banner("2. PostgreSQL — 权威长期记忆账本")
    from memory import get_authoritative_store

    pg = get_authoritative_store()
    if not pg.enabled:
        print("  [x] PostgreSQL 未连接")
        return

    print("  [ok] PostgreSQL 已连接\n")

    try:
        with pg.conn.cursor() as cur:
            if session_id:
                cur.execute(
                    """
                    SELECT id::text, session_id, left(content, 100) AS content_preview,
                           confidence, mem0_id, created_at
                    FROM memories
                    WHERE session_id = %s AND is_deleted = FALSE
                    ORDER BY created_at DESC
                    """,
                    (session_id,),
                )
                rows = cur.fetchall()
                print(f"  memories 表（session={session_id}）: {len(rows)} 条")
                for r in rows:
                    print(f"    pg_id={r[0]}  mem0_id={r[4] or '(未同步)'}  conf={r[3]}")
                    print(f"      preview: {r[2]}...")
                    print(f"      at: {r[5]}")

                cur.execute(
                    """
                    SELECT session_id, left(question, 80), created_at
                    FROM session_summaries
                    WHERE session_id = %s
                    """,
                    (session_id,),
                )
                summ = cur.fetchall()
                print(f"\n  session_summaries: {len(summ)} 条")
                for s in summ:
                    print(f"    Q: {s[1]}...  at={s[2]}")
            else:
                cur.execute(
                    """
                    SELECT session_id, count(*) AS cnt, max(created_at) AS last_at
                    FROM memories
                    WHERE is_deleted = FALSE
                    GROUP BY session_id
                    ORDER BY last_at DESC
                    LIMIT 10
                    """
                )
                print("  最近有记忆的 session（Top 10）:")
                for row in cur.fetchall():
                    print(f"    {row[0]}  ({row[1]} 条, 最后 {row[2]})")
    except Exception as e:
        print(f"  查询失败: {e}")


def observe_mem0(session_id: Optional[str], query: Optional[str]) -> None:
    _banner("3. Mem0 — 语义检索层（跨会话）")
    from memory import get_memory_stack

    ltm = get_memory_stack().long_term_memory
    if not ltm.mem0_enabled:
        print("  [x] Mem0 未启用")
        return

    print("  [ok] Mem0 已启用")
    print("  说明: Mem0 按「语义相似」召回，不是按 session_id 精确查库\n")

    q = query or "高血压 生活方式"
    print(f"  试探查询: {q}")
    hits = ltm.search_similar_sessions(query=q, limit=3)
    print(f"  命中: {len(hits)} 条\n")
    for i, h in enumerate(hits, 1):
        print(f"  [{i}] score={h.get('score', 0):.3f}  source={h.get('source')}")
        print(f"      session_id={h.get('session_id')}  pg_memory_id={h.get('pg_memory_id')}")
        content = (h.get("content") or "")[:200]
        print(f"      content: {content}...")
        if session_id and h.get("session_id") == session_id:
            print("      ^^^ 属于当前观察的 session")


def main() -> int:
    parser = argparse.ArgumentParser(description="观察 Redis + PG + Mem0 记忆快照")
    parser.add_argument(
        "session_id",
        nargs="?",
        help="main.py 日志里的 session_id，例如 20260516-001100-a40a5cfa",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="只列出最近 session，不指定 id",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Mem0 语义检索试探语句",
    )
    args = parser.parse_args()

    session_id = None if args.list else args.session_id

    print("\nMedix 记忆系统观察工具")
    print("-" * 60)
    if session_id:
        print(f"目标 session_id: {session_id}")
    else:
        print("模式: 列出最近 session（加 session_id 参数可看详情）")

    observe_redis(session_id)
    observe_postgres(session_id)
    observe_mem0(session_id, args.query)

    _banner("对照记忆")
    print("""
  Redis     → 本次对话多轮消息（热数据，~1小时 TTL）
  PostgreSQL→ 每次问答的权威存档（pg_memory_id，可审计）
  Mem0      → 按意思找历史（带 pg_memory_id 时回 PG 取正文）

  main.py 日志里找 session_id，例如:
    Interactive session started with session_id: 20260516-001100-a40a5cfa
    Processing question (session=20260516-001100-a40a5cfa)
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
