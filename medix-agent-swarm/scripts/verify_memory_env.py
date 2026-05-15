#!/usr/bin/env python3
"""检查记忆系统依赖：Redis / PostgreSQL / Mem0 配置与连通性。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SWARM = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SWARM))


def main():
    print("=" * 60)
    print("Medix 记忆环境自检")
    print("=" * 60)

    try:
        from config import LLM_CONFIG, MEM0_CONFIG, REDIS_CONFIG, POSTGRES_CONFIG
        print("\n[config.py]")
        print(f"  LLM api_key: {'已配置' if LLM_CONFIG.get('api_key') else '未配置 (必填)'}")
        print(f"  Mem0 api_key: {'已配置' if MEM0_CONFIG.get('api_key') else '未配置 (长期记忆可选)'}")
        print(f"  Redis: {REDIS_CONFIG.get('host')}:{REDIS_CONFIG.get('port')}")
        print(f"  PostgreSQL: {POSTGRES_CONFIG.get('host')}:{POSTGRES_CONFIG.get('port')}/{POSTGRES_CONFIG.get('database')}")
    except Exception as e:
        print(f"\n[config.py] 读取失败: {e}")
        print("  请确认文件位于: 医疗助手/config.py")
        return 1

    from memory import get_memory_stack

    stack = get_memory_stack()
    print("\n[运行时]")
    print(f"  Redis:      {'OK' if stack.redis_store.enabled else '不可用 (短期记忆将降级内存)'}")
    print(f"  PostgreSQL: {'OK' if stack.authoritative_store.enabled else '不可用 (长期记忆仅 Mem0)'}")
    print(f"  Mem0:       {'OK' if stack.long_term_memory.mem0_enabled else '不可用 (无语义召回)'}")
    print(f"  短期存储:   {stack.short_term_memory.storage_type}")

    if not LLM_CONFIG.get("api_key"):
        print("\n请先填写 config.py 中的 LLM_CONFIG['api_key'] 再运行 main.py")
        return 1

    print("\n自检完成。可运行: python main.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
