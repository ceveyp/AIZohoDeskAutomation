from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app import zoho_desk
from app.logger import setup_logging
from app.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging()
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            app.state.http_client = client
            yield

    application = FastAPI(title=settings.app_name, lifespan=lifespan)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    application.include_router(zoho_desk.router)
    return application


app = create_app()

if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run("main:app", host=s.host, port=s.port, reload=True)
