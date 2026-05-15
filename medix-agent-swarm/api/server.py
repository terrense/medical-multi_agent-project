#!/usr/bin/env python3
"""
MediX Web UI — FastAPI 服务
启动: python api/server.py
浏览器: http://127.0.0.1:8765
"""
from __future__ import annotations

import asyncio
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = PROJECT_ROOT / "web"
sys.path.insert(0, str(PROJECT_ROOT))

from swarm import process_with_swarm  # noqa: E402

app = FastAPI(title="MediX Medical Assistant", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    session_id: Optional[str] = None
    enable_swarm: bool = True


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    swarm_enabled: bool = False
    agents_involved: list = Field(default_factory=list)
    suggestions: list = Field(default_factory=list)
    disclaimer: str = ""
    execution_time_sec: float = 0.0
    timeout_occurred: bool = False


def _new_session_id() -> str:
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


@app.get("/api/health")
async def health() -> Dict[str, str]:
    return {"status": "ok", "service": "medix-ui"}


@app.post("/api/session")
async def create_session() -> Dict[str, str]:
    sid = _new_session_id()
    logger.info(f"Web session created: {sid}")
    return {"session_id": sid}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    session_id = req.session_id or _new_session_id()
    text = req.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="消息不能为空")

    logger.info(f"Web chat (session={session_id}): {text[:80]}...")
    start = time.time()
    try:
        result: Dict[str, Any] = await process_with_swarm(
            text,
            enable_swarm=req.enable_swarm,
            session_id=session_id,
        )
    except Exception as exc:
        logger.exception("Chat processing failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    elapsed = time.time() - start
    return ChatResponse(
        session_id=session_id,
        answer=result.get("answer", ""),
        swarm_enabled=bool(result.get("swarm_enabled")),
        agents_involved=result.get("agents_involved") or [],
        suggestions=result.get("suggestions") or [],
        disclaimer=result.get("disclaimer", ""),
        execution_time_sec=round(elapsed, 2),
        timeout_occurred=bool(result.get("timeout_occurred")),
    )


@app.get("/")
async def index() -> FileResponse:
    index_path = WEB_ROOT / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=404, detail="web/index.html not found")
    return FileResponse(index_path)


if WEB_ROOT.is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_ROOT), name="web_assets")


def main() -> None:
    import uvicorn

    logger.remove()
    logger.add(sys.stderr, level="INFO")
    print("\n  MediX Web UI")
    print("  Open http://127.0.0.1:8765 in your browser\n")
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8765,
        log_level="info",
    )


if __name__ == "__main__":
    main()
