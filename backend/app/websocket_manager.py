"""WebSocket connection manager — tracks active connections per session."""

from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """Manages one WebSocket connection per chat session."""

    def __init__(self) -> None:
        self._active: dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._active[session_id] = websocket

    def disconnect(self, session_id: str) -> None:
        self._active.pop(session_id, None)

    async def send_json(self, session_id: str, data: dict[str, Any]) -> None:
        ws = self._active.get(session_id)
        if ws:
            await ws.send_text(json.dumps(data))


manager = ConnectionManager()
