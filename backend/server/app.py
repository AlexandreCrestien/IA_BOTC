from fastapi import FastAPI
from backend.server.websockets import router as ws_router

app = FastAPI(title="Blood on the Clocktower - API")

app.include_router(ws_router)

@app.get("/health")
def health_check():
    return {"status": "running"}