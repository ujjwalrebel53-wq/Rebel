"""Rebel API — Cursor-style coding agent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agent import run_agent
from app.config import settings
from app.tools import WORKSPACE, _safe_path, execute_tool

app = FastAPI(title="Rebel Agent", version="0.1.0")

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class FileWriteRequest(BaseModel):
    path: str
    content: str


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "workspace": str(WORKSPACE),
        "model": settings.copilot_model,
        "api_base": settings.copilot_api_base,
    }


@app.get("/api/config")
def get_config():
    return {
        "workspace": str(WORKSPACE),
        "model": settings.copilot_model,
        "github_configured": bool(settings.github_token and settings.github_repo),
        "repo": settings.github_repo or None,
    }


def _tree(path: Path, prefix: str = "") -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    try:
        children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return items
    for child in children:
        if child.name in (".git", "node_modules", "__pycache__", ".venv", "dist"):
            continue
        if child.name.startswith(".") and child.name not in (".env.example",):
            continue
        rel = str(child.relative_to(WORKSPACE))
        if child.is_dir():
            items.append({"name": child.name, "path": rel, "type": "dir", "children": _tree(child)})
        else:
            items.append({"name": child.name, "path": rel, "type": "file"})
    return items


@app.get("/api/files/tree")
def file_tree():
    return {"root": str(WORKSPACE), "tree": _tree(WORKSPACE)}


@app.get("/api/files/read")
def read_file(path: str):
    try:
        p = _safe_path(path)
        if not p.is_file():
            raise HTTPException(404, "File not found")
        return {"path": path, "content": p.read_text(encoding="utf-8", errors="replace")}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/files/write")
def write_file(req: FileWriteRequest):
    try:
        result = execute_tool("write_file", {"path": req.path, "content": req.content})
        return {"ok": True, "message": result}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/terminal")
def terminal(command: str):
    result = execute_tool("run_terminal", {"command": command})
    return {"output": result}


@app.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            action = data.get("action", "chat")

            if action == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            user_messages = data.get("messages", [])
            if not user_messages:
                await websocket.send_json({"type": "error", "content": "No messages"})
                continue

            async for event in run_agent(user_messages):
                await websocket.send_json(event)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "content": str(e)})
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
