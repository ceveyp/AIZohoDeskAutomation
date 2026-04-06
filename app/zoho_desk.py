from typing import Annotated, Any

from fastapi import APIRouter, Request, Depends

from app.settings import Settings, get_settings

router = APIRouter(tags=["zoho_desk"])


@router.api_route("/ticket", methods=["GET", "POST"])
async def ticket(
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)]
) -> dict[str, Any]:
    if request.method == "GET":
        return {
            "method": "GET",
            "query": dict(request.query_params),
        }

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body: Any = await request.json()
        except Exception:
            body = None
    else:
        body = (await request.body()).decode("utf-8", errors="replace") or None

    return {
        "method": "POST",
        "content_type": content_type or None,
        "body": body,
    }
