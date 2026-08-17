import json
import base64
import collections
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import os

app = FastAPI()

# The dashboard is served by this same server, so same-origin is the only
# caller that ever legitimately needs these endpoints.
ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

clients = set()

# Binary bodies are stored here (not broadcast over the websocket) and only
# served when explicitly requested via /api/body. Capped to match the
# frontend's MAX_ROWS so this can't grow unbounded over a long session.
MAX_STORED_BODIES = 500
body_store = {}
body_order = collections.deque()

def _store_blob(flow_id, direction, content_type, b64data):
    try:
        raw = base64.b64decode(b64data)
    except Exception:
        return
    key = (flow_id, direction)
    body_store[key] = (content_type, raw)
    body_order.append(key)
    while len(body_order) > MAX_STORED_BODIES:
        old_key = body_order.popleft()
        body_store.pop(old_key, None)

@app.post("/api/log")
async def log_traffic(data: dict = Body(...)):
    blobs = data.pop("blobs", None)
    if blobs:
        flow_id = data.get("id")
        for direction, blob in blobs.items():
            _store_blob(flow_id, direction, blob.get("content_type", "application/octet-stream"), blob.get("data", ""))

    dead_clients = set()
    for client in clients:
        try:
            await client.send_json(data)
        except Exception:
            dead_clients.add(client)

    clients.difference_update(dead_clients)
    return {"status": "ok"}

@app.get("/api/body/{flow_id}/{direction}")
async def get_body(flow_id: str, direction: str):
    if direction not in ("req", "res"):
        raise HTTPException(status_code=400, detail="Invalid direction")

    stored = body_store.get((flow_id, direction))
    if not stored:
        raise HTTPException(status_code=404, detail="Body not available (never captured or evicted)")

    content_type, raw = stored
    safe_type = content_type if content_type and "\n" not in content_type else "application/octet-stream"
    return Response(
        content=raw,
        media_type=safe_type,
        headers={"Content-Disposition": f'attachment; filename="{flow_id}_{direction}"'},
    )

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # CORS middleware does not cover WebSocket handshakes, so the same-origin
    # rule has to be applied explicitly here.
    #
    # A missing Origin means a non-browser client (curl, a test script).
    # Browsers always send one, so accepting it keeps local tooling usable.
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in ALLOWED_ORIGINS:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        clients.remove(websocket)

# Mount frontend directory
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
