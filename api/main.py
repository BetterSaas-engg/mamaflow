from fastapi import FastAPI

from api.auth.oauth import router as auth_router
from api.routers.sync import router as sync_router

app = FastAPI(title="Mamaflow API", version="0.1.0")

app.include_router(auth_router)
app.include_router(sync_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
