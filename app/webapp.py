from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import config
from app.Controllers import admin, images, search, gui
from app.Services.provider import ServiceProvider

async def lifespan(app: FastAPI):
    # Initialize service provider with running event loop
    app.state.services = ServiceProvider()
    await app.state.services.onload()
    yield
    await app.state.services.onexit()

def create_app():
    app = FastAPI(lifespan=lifespan)
    
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
    app.mount("/images", StaticFiles(directory="./images"), name="images")

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
