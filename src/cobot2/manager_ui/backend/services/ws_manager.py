import json
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self._client_connections: list[WebSocket] = []
        self._admin_connections:  list[WebSocket] = []

    async def connect_client(self, ws: WebSocket):
        await ws.accept()
        self._client_connections.append(ws)

    async def connect_admin(self, ws: WebSocket):
        await ws.accept()
        self._admin_connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self._client_connections = [c for c in self._client_connections if c != ws]
        self._admin_connections  = [c for c in self._admin_connections  if c != ws]

    async def broadcast_client(self, data: dict):
        dead = []
        for ws in self._client_connections:
            try:
                await ws.send_text(json.dumps(data, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_admin(self, data: dict):
        dead = []
        for ws in self._admin_connections:
            try:
                await ws.send_text(json.dumps(data, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


ws_manager = ConnectionManager()
