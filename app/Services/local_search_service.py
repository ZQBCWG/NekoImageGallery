import os
from datetime import datetime
from typing import Optional, List
from uuid import uuid4

import numpy
from PIL import Image
from loguru import logger

from app.Models.mapped_image import MappedImage
from app.Models.query_params import FilterParams
from app.Models.search_result import SearchResult
from app.Services.lifespan_service import LifespanService
from app.Services.transformers_service import TransformersService
from app.Services.wd14_tagger_service import WD14TaggerService
from app.Services.vector_db_context import VectorDbContext
from app.config import config
from app.util.calculate_vectors_cosine import calculate_vectors_cosine
from app.Models.api_models.search_api_model import SearchBasisEnum


class LocalSearchService(LifespanService):
    IMG_VECTOR = "image_vector"
    TEXT_VECTOR = "text_contain_vector"

    def __init__(self, transformers_service: TransformersService, tagger_service: WD14TaggerService, 
                 db_context: VectorDbContext):
        self.transformers_service = transformers_service
        self.tagger_service = tagger_service
        self.db_context = db_context
        self.image_files = []
        self._scan_directory()

    async def on_load(self):
        """Called when service is loaded"""
        pass

    def _scan_directory(self):
        """Scan the configured directory for image files"""
        if not config.local_search.enabled:
            return

        if not os.path.exists(config.local_search.directory):
            logger.error(f"Local search directory does not exist: {config.local_search.directory}")
            return

        self.image_files = []
        for root, _, files in os.walk(config.local_search.directory):
            for file in files:
                if any(file.lower().endswith(ext) for ext in config.local_search.extensions):
                    self.image_files.append(os.path.join(root, file))

        logger.info(f"Found {len(self.image_files)} image files in local directory")

    async def query_search(self, query_vector, query_vector_name: str = "image_vector",
                          top_k=10, skip=0, filter_param: FilterParams | None = None) -> List[SearchResult]:
        """Search for images similar to the query vector using pre-built index"""
        if not config.local_search.enabled:
            return []

        # Search in vector database
        search_results = await self.db_context.query_search(
            query_vector=query_vector,
            query_vector_name=query_vector_name,
            top_k=top_k,
            skip=skip,
            filter_param=filter_param
        )

        return search_results

    async def query_similar(self,
                          query_vector_name: str = "image_vector",
                          search_id: Optional[str] = None,
                          positive_vectors: Optional[List[numpy.ndarray]] = None,
                          negative_vectors: Optional[List[numpy.ndarray]] = None,
                          mode: Optional[str] = None,
                          with_vectors: bool = False,
                          filter_param: FilterParams | None = None,
                          top_k: int = 10,
                          skip: int = 0) -> List[SearchResult]:
        """Search for similar images using pre-built index"""
        if positive_vectors:
            return await self.query_search(positive_vectors[0], query_vector_name, top_k, skip, filter_param)
        return []

    def _passes_filters(self, mapped_img: MappedImage, filter_param: FilterParams) -> bool:
        """Check if image passes all filters"""
        payload = mapped_img.payload
        
        # Check tag filter
        if filter_param.query_text and mapped_img.tags:
            query_text = filter_param.query_text.lower()
            if not any(query_text in tag.lower() for tag in mapped_img.tags):
                return False
                
        # Check width filter
        if filter_param.min_width and payload.get('width', 0) < filter_param.min_width:
            return False
            
        # Check height filter
        if filter_param.min_height and payload.get('height', 0) < filter_param.min_height:
            return False
            
        # Check aspect ratio filter
        if filter_param.min_ratio:
            aspect_ratio = payload.get('aspect_ratio', 1.0)
            if aspect_ratio < filter_param.min_ratio or aspect_ratio > filter_param.max_ratio:
                return False
                
        return True

    @classmethod
    def vector_name_for_basis(cls, basis: SearchBasisEnum) -> str:
        """Get vector name based on search basis"""
        match basis:
            case SearchBasisEnum.vision:
                return cls.IMG_VECTOR
            case SearchBasisEnum.ocr:
                return cls.TEXT_VECTOR
            case _:
                raise ValueError("Invalid basis")