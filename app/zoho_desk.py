from typing import Annotated, Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.services.ticket_webhook import process_zoho_webhook_events
from app.settings import Settings, get_settings

router = APIRouter(prefix="/webhooks", tags=["zoho_desk"])


@router.post("/zoho")
async def zoho_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    if settings.webhook_secret_token:
        q = request.query_params.get("token")
        if q != settings.webhook_secret_token:
            raise HTTPException(status_code=401, detail="Unauthorized")
    raw: Any = await request.json()
    http: httpx.AsyncClient = request.app.state.http_client
    background_tasks.add_task(process_zoho_webhook_events, raw, http, settings)
    return {"status": "accepted"}
