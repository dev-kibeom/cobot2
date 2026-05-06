from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from manager_ui.backend.api import admin, client, recommendations
from manager_ui.backend.db.connection import check_connection
from manager_ui.backend.services.ws_manager import ws_manager

app = FastAPI(title='Robot Admin API', version='1.0.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(admin.router)
app.include_router(client.router)
app.include_router(recommendations.router)

# Manager UI 정적 파일
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'frontend')
if os.path.isdir(FRONTEND_DIR):
    app.mount('/manager', StaticFiles(directory=FRONTEND_DIR, html=True), name='manager')


@app.websocket('/ws/client')
async def ws_client(websocket: WebSocket):
    await ws_manager.connect_client(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.websocket('/ws/admin/logs')
async def ws_admin(websocket: WebSocket):
    await ws_manager.connect_admin(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.on_event('startup')
def startup():
    if check_connection():
        print('✅ DB 연결 성공')
    else:
        print('❌ DB 연결 실패 — .env 확인 필요')
