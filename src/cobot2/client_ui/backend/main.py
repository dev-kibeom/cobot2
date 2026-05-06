"""
Client UI backend (Computer A)
- ROS2 /status, /wakeup_status, /voice_command 구독
- WebSocket으로 Client UI frontend에 브로드캐스트
- FastAPI + rclpy 통합
"""
import json
import asyncio
import threading

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

# ── WebSocket 연결 관리 ────────────────────────────
class WsManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self._connections = [c for c in self._connections if c != ws]

    async def broadcast(self, data: dict):
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(json.dumps(data, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


ws_manager = WsManager()
loop: asyncio.AbstractEventLoop = None


# ── ROS2 구독 노드 ─────────────────────────────────
class ClientBridgeNode(Node):
    def __init__(self):
        super().__init__('client_bridge_node')

        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)

        self.create_subscription(String, '/wakeup_status', self._on_wakeup,  qos)
        self.create_subscription(String, '/status',        self._on_status,  qos)
        self.create_subscription(String, '/stt_result',    self._on_stt,     qos)

        self.get_logger().info('ClientBridgeNode 시작')

    def _on_wakeup(self, msg: String):
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            return
        data['type'] = 'wakeup'
        self._emit(data)

    def _on_status(self, msg: String):
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            return
        data['type'] = 'robot_status'
        self._emit(data)

    def _on_stt(self, msg: String):
        self._emit({'type': 'stt_result', 'text': msg.data})

    def _emit(self, data: dict):
        if loop and not loop.is_closed():
            asyncio.run_coroutine_threadsafe(ws_manager.broadcast(data), loop)


# ── FastAPI 앱 ─────────────────────────────────────
app = FastAPI(title='Client UI Bridge', version='1.0.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

import os
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'frontend')


@app.websocket('/ws/client')
async def ws_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# 정적 파일은 WebSocket 라우트 뒤에 마운트 (라우트 우선순위)
if os.path.isdir(FRONTEND_DIR):
    app.mount('/', StaticFiles(directory=FRONTEND_DIR, html=True), name='static')


# ── 실행 진입점 ────────────────────────────────────
def ros_spin(node: Node):
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


def main():
    global loop

    rclpy.init()
    node = ClientBridgeNode()

    ros_thread = threading.Thread(target=ros_spin, args=(node,), daemon=True)
    ros_thread.start()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    config = uvicorn.Config(app, host='0.0.0.0', port=8001, loop='asyncio', log_level='warning')
    server = uvicorn.Server(config)
    loop.run_until_complete(server.serve())


if __name__ == '__main__':
    main()
