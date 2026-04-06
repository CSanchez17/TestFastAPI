from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["web"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def booking_frontend(request: Request):
    """Serve the modular booking UI."""
    return templates.TemplateResponse(
        request=request,
        name="web/index.html",
        context={"request": request},
    )


@router.get("/my-bookings", response_class=HTMLResponse, include_in_schema=False)
async def my_bookings_frontend(request: Request):
    """Serve the bookings page UI."""
    return templates.TemplateResponse(
        request=request,
        name="web/my_bookings.html",
        context={"request": request},
    )
