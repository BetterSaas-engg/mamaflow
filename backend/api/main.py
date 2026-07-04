from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.auth.oauth import router as auth_router
from api.db.session import engine
from api.routers.account import router as account_router
from api.routers.devices import router as devices_router
from api.routers.items import router as items_router
from api.routers.sync import router as sync_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title="Mamaflow API", version="0.1.0", lifespan=lifespan)

app.include_router(auth_router)
app.include_router(sync_router)
app.include_router(items_router)
app.include_router(devices_router)
app.include_router(account_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
