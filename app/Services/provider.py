import asyncio
import os
from pathlib import Path
from loguru import logger

from .index_service import IndexService
from .lifespan_service import LifespanService
from .storage import StorageService
from .transformers_service import TransformersService
from .wd14_tagger_service import WD14TaggerService
from .upload_service import UploadService
from .vector_db_context import VectorDbContext
from .local_search_service import LocalSearchService
from ..config import config, environment


class ServiceProvider:
    def __init__(self):
        self.transformers_service = TransformersService()
        self.tagger_service = WD14TaggerService()
        
        # Initialize appropriate search service based on configuration
        if config.local_search.enabled:
            self.db_context = VectorDbContext()
            self.search_service = LocalSearchService(
                self.transformers_service, 
                self.tagger_service,
                self.db_context
            )
            logger.info("Using LocalSearchService for image search")
        else:
            self.search_service = VectorDbContext()
            self.db_context = self.search_service  # Backward compatibility
            logger.info("Using VectorDbContext for image search")

        self.ocr_service = None

        if config.ocr_search.enable and (environment.local_indexing or config.admin_api_enable):
            match config.ocr_search.ocr_module:
                case "easyocr":
                    from .ocr_services import EasyOCRService
                    self.ocr_service = EasyOCRService()
                case "easypaddleocr":
                    from .ocr_services import EasyPaddleOCRService
                    self.ocr_service = EasyPaddleOCRService()
                case "paddleocr":
                    from .ocr_services import PaddleOCRService
                    self.ocr_service = PaddleOCRService()
                case _:
                    raise NotImplementedError(f"OCR module {config.ocr_search.ocr_module} not implemented.")
        else:
            from .ocr_services import DisabledOCRService
            self.ocr_service = DisabledOCRService()
        logger.info(f"OCR service '{type(self.ocr_service).__name__}' initialized.")

        self.index_service = IndexService(
            self.ocr_service, 
            self.transformers_service, 
            self.db_context,
            self.tagger_service
        )
        self.storage_service = StorageService()
        logger.info(f"Storage service '{type(self.storage_service.active_storage).__name__}' initialized.")

        self.upload_service = UploadService(self.storage_service, self.search_service, self.index_service)
        logger.info(f"Upload service '{type(self.upload_service).__name__}' initialized")

    async def _check_initialized(self):
        """Check if index has been initialized"""
        init_flag = Path(config.qdrant.local_path) / ".initialized"
        return init_flag.exists()

    async def _mark_initialized(self):
        """Mark index as initialized"""
        init_flag = Path(config.qdrant.local_path) / ".initialized"
        init_flag.parent.mkdir(parents=True, exist_ok=True)
        init_flag.touch()

    async def onload(self):
        # First load all services
        tasks = [service.on_load() for service_name in dir(self)
                 if isinstance((service := getattr(self, service_name)), LifespanService)]
        await asyncio.gather(*tasks)

        # Initialize index if needed
        if config.local_search.enabled and not await self._check_initialized():
            try:
                logger.info("Initializing image index for first time use...")
                await self.index_service.initialize_index()
                await self._mark_initialized()
                logger.success("Image index initialization completed")
            except Exception as e:
                logger.error(f"Failed to initialize image index: {e}")
                raise

    async def onexit(self):
        tasks = [service.on_exit() for service_name in dir(self)
                 if isinstance((service := getattr(self, service_name)), LifespanService)]
        await asyncio.gather(*tasks)
