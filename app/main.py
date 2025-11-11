import os, json, asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import redis.asyncio as redis

# Railway/Nixpacks da ci PORT w env:
PORT = int(os.getenv("PORT", "8080"))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

app = FastAPI(title="BetMind API")
r = redis.from_url(REDIS_URL, decode_responses=True)

@app.get("/")
async def root():
    return {"ok": True, "service": "BetMind-API"}

@app.get("/live")
async def live(min_ghi: float = 70.0, min_ngi: float = 0.0, limit: int = 50):
    # Demo/placeholder – czytamy snapy z Redisa jeśli są, inaczej zwracamy pustą listę:
    items = []
    if await r.exists("live:index"):
        ids = await r.zrevrange("live:index", 0, limit-1)
        for mid in ids:
            raw = await r.hget("live:match", mid)
            if raw:
                items.append(json.loads(raw))
    return JSONResponse(items)

@app.websocket("/stream")
async def stream(ws: WebSocket):
    await ws.accept()
    pubsub = r.pubsub()
    await pubsub.subscribe("stream:ghi")
    try:
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                await ws.send_text(msg["data"])
    except WebSocketDisconnect:
        await pubsub.unsubscribe("stream:ghi")
    finally:
        await pubsub.close()
