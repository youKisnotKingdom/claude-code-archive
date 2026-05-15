from pathlib import Path
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from cc_history.api.projects import router as projects_api
from cc_history.api.search import router as search_api
from cc_history.api.sessions import router as sessions_api
from cc_history.api.users import router as users_api
from cc_history.config import settings
from cc_history.services.watcher import WatchManager
from cc_history.web import auth
from cc_history.web.routes import router as web_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    watch_manager = WatchManager()
    watch_manager.start()
    try:
        yield
    finally:
        watch_manager.stop()


app = FastAPI(title="CC History Viewer", lifespan=lifespan)


@app.middleware("http")
async def require_authentication(request: Request, call_next) -> Response:
    if auth.path_is_exempt(request.url.path) or auth.request_is_authenticated(request):
        return await call_next(request)
    return auth.unauthenticated_response(request.url.path)


static_dir = Path(__file__).parent / "web" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.include_router(web_router)
app.include_router(users_api, prefix="/api")
app.include_router(projects_api, prefix="/api")
app.include_router(sessions_api, prefix="/api")
app.include_router(search_api, prefix="/api")


def main() -> None:
    uvicorn.run(
        "cc_history.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )


if __name__ == "__main__":
    main()
