from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import config
from app.Controllers import admin, images, search, gui
from app.Services.provider import ServiceProvider

def create_app():
    app = FastAPI()
    
    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(search.search_router)
    app.include_router(images.images_router)
    app.include_router(gui.gui_router)
    
    if config.admin_api_enable:
        app.include_router(admin.admin_router)

    # Mount static files with correct path
    app.mount("/static", StaticFiles(directory="./images"), name="static")

    # Initialize service provider
    app.state.services = ServiceProvider()

    return app

app = create_app()

async def lifespan(app: FastAPI):
    await app.state.services.onload()
    yield
    await app.state.services.onexit()
