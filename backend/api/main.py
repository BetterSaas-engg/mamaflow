from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.auth.oauth import router as auth_router
from api.config.settings import settings
from api.db.session import engine
from api.routers.account import router as account_router
from api.routers.devices import router as devices_router
from api.routers.items import router as items_router
from api.routers.sync import router as sync_router
from api.services.reminder_scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()
    await engine.dispose()


def configure_cors(app: FastAPI) -> None:
    """Allow browser calls from the configured web-app origin(s) only.

    No origins configured (the default) adds no middleware — non-web deploys
    keep today's behavior of emitting no CORS headers at all."""
    origins = settings.web_origins_list
    if not origins:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )


app = FastAPI(title="Mamaflow API", version="0.1.0", lifespan=lifespan)
configure_cors(app)

app.include_router(auth_router)
app.include_router(sync_router)
app.include_router(items_router)
app.include_router(devices_router)
app.include_router(account_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
