from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from loguru import logger
from typing import Optional

from app.Models.api_response.images_api_response import QueryImagesApiResponse
from app.Models.query_params import FilterParams
from app.Services.provider import ServiceProvider
from app.config import config

images_router = APIRouter(tags=["Images"])

@images_router.get("/scroll", response_model=QueryImagesApiResponse)
async def scroll_images(
    prev_offset_id: Optional[str] = Query(None, description="The last image ID from previous request"),
    count: int = Query(10, description="Number of images to return", ge=1, le=100),
    filter_param: FilterParams = Depends(),
    services: ServiceProvider = Depends(ServiceProvider)
):
    """Scroll through images with pagination"""
    if config.local_search.enabled:
        return JSONResponse(
            status_code=501,
            content={"message": "Scrolling not supported in local search mode"}
        )
    
    if not services.db_context:
        return JSONResponse(
            status_code=500,
            content={"message": "Database context not available"}
        )

    try:
        images, offset = await services.db_context.scroll_points(
            str(prev_offset_id), 
            count, 
            filter_param=filter_param
        )
        return {
            "images": images,
            "next_page_offset": offset
        }
    except Exception as e:
        logger.error(f"Error scrolling images: {e}")
        return JSONResponse(
            status_code=500,
            content={"message": "Error scrolling images"}
        )
