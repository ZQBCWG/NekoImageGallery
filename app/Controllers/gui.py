from fastapi import APIRouter
from fastapi.responses import FileResponse
from pathlib import Path

gui_router = APIRouter(tags=["GUI"])

@gui_router.get("/", include_in_schema=False)
async def serve_gui():
    """Serve the web interface"""
    return FileResponse(Path(__file__).parent.parent.parent / "web" / "index.html")