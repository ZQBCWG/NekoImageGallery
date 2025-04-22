import os
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
from app.config import config
from app.util.calculate_vectors_cosine import calculate_vectors_cosine


class LocalSearchService(LifespanService):
    def __init__(self, transformers_service: TransformersService):
        self.transformers_service = transformers_service
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
        """Search for images similar to the query vector"""
        if not config.local_search.enabled:
            return []

        # Process all images and calculate similarity scores
        results = []
        for file_path in self.image_files[skip:skip+top_k]:
            try:
                with Image.open(file_path) as img:
                    # Get image vector
                    img_vector = self.transformers_service.get_image_vector(img)
                    
                    # Calculate similarity score
                    score = calculate_vectors_cosine(query_vector, img_vector)
                    
                    # Create mapped image
                    mapped_img = MappedImage(
                        id=str(uuid4()),
                        payload={
                            "path": file_path,
                            "width": img.width,
                            "height": img.height,
                            "aspect_ratio": img.width / img.height,
                            "format": img.format.lower() if img.format else "unknown"
                        },
                        image_vector=img_vector
                    )
                    
                    # Apply filters if provided
                    if filter_param and not self._passes_filters(mapped_img, filter_param):
                        continue
                        
                    results.append(SearchResult(img=mapped_img, score=score))
            except Exception as e:
                logger.warning(f"Error processing image {file_path}: {e}")

        # Sort by score descending
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

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
        """Search for similar images (simplified implementation)"""
        if positive_vectors:
            # For simplicity, just use the first positive vector
            return await self.query_search(positive_vectors[0], query_vector_name, top_k, skip, filter_param)
        return []

    def _passes_filters(self, mapped_img: MappedImage, filter_param: FilterParams) -> bool:
        """Check if image passes all filters"""
        payload = mapped_img.payload
        
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