from fastapi import FastAPI

import app.zoho_desk
from app.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    fastapi_app = FastAPI(title=settings.app_name)

    @fastapi_app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return fastapi_app


fastapi_app = create_app()
fastapi_app.include_router(app.zoho_desk.router)

if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run("main:fastapi_app", host=s.host, port=s.port, reload=True)
