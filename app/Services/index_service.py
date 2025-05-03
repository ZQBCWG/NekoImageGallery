from PIL import Image
from fastapi.concurrency import run_in_threadpool
from pathlib import Path
from typing import List
import os
from datetime import datetime
import uuid
import hashlib

from app.Models.errors import PointDuplicateError
from app.Models.mapped_image import MappedImage
from app.Services.lifespan_service import LifespanService
from app.Services.ocr_services import OCRService
from app.Services.transformers_service import TransformersService
from app.Services.vector_db_context import VectorDbContext
from app.Services.wd14_tagger_service import WD14TaggerService
from app.config import config
from loguru import logger


class IndexService(LifespanService):
    def __init__(self, ocr_service: OCRService, transformers_service: TransformersService, 
                 db_context: VectorDbContext, tagger_service: WD14TaggerService):
        self._ocr_service = ocr_service
        self._transformers_service = transformers_service
        self._db_context = db_context
        self._tagger_service = tagger_service

    def _generate_image_id(self, file_path: str) -> str:
        """Generate UUID from file content hash"""
        with open(file_path, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        return str(uuid.uuid5(uuid.NAMESPACE_URL, file_hash))

    def _prepare_image(self, image: Image.Image, image_data: MappedImage, skip_ocr=False):
        image_data.width = image.width
        image_data.height = image.height
        image_data.aspect_ratio = float(image.width) / image.height

        if image.mode != 'RGB':
            image = image.convert('RGB')
        else:
            image = image.copy()
        image_data.image_vector = self._transformers_service.get_image_vector(image)
        
        # Always generate tags if enabled
        if config.model.tagger_enabled:
            image_data.tags = self._tagger_service.generate_tags(image)
            
        # Skip OCR if disabled in config or explicitly requested
        if not skip_ocr and config.ocr_search.enable:
            try:
                image_data.ocr_text = self._ocr_service.ocr_interface(image)
                if image_data.ocr_text != "":
                    image_data.text_contain_vector = self._transformers_service.get_bert_vector(image_data.ocr_text)
                else:
                    image_data.ocr_text = None
            except Exception as e:
                logger.warning(f"OCR processing failed: {e}")
                image_data.ocr_text = None

    async def initialize_index(self):
        """Initialize the index by scanning all images in the local directory"""
        if not config.local_search.enabled:
            logger.warning("Local search is disabled, skipping index initialization")
            return

        image_dir = Path(config.local_search.directory)
        if not image_dir.exists():
            logger.error(f"Image directory does not exist: {image_dir}")
            return

        image_files = []
        for ext in config.local_search.extensions:
            image_files.extend(image_dir.glob(f"**/*{ext}"))

        logger.info(f"Found {len(image_files)} images to index")

        batch_size = 10
        for i in range(0, len(image_files), batch_size):
            batch = image_files[i:i + batch_size]
            try:
                images = []
                image_data_list = []
                
                for img_path in batch:
                    try:
                        with Image.open(img_path) as img:
                            img_data = MappedImage(
                                id=self._generate_image_id(str(img_path)),
                                index_date=datetime.now(),
                                url=f"file://{img_path.absolute()}",
                                local=True,
                                format=img.format.lower() if img.format else "unknown",
                                comments=f"Original path: {img_path}"
                            )
                            img_data.add_payload_data("filename", img_path.name)
                            img_data.add_payload_data("width", img.width)
                            img_data.add_payload_data("height", img.height)
                            img_data.add_payload_data("aspect_ratio", float(img.width)/img.height)
                            # Skip OCR if disabled in config
                            self._prepare_image(img, img_data, skip_ocr=not config.ocr_search.enable)
                            images.append(img)
                            image_data_list.append(img_data)
                    except Exception as e:
                        logger.error(f"Error processing image {img_path}: {e}")
                        continue

                if image_data_list:
                    await self._db_context.insert_items(image_data_list)
                    logger.info(f"Indexed batch {i//batch_size + 1}/{(len(image_files)//batch_size + 1)}")

            except Exception as e:
                logger.error(f"Error indexing batch: {e}")

        logger.success("Index initialization completed")

    async def _is_point_duplicate(self, image_data: list[MappedImage]) -> bool:
        image_id_list = [str(item.id) for item in image_data]
        result = await self._db_context.validate_ids(image_id_list)
        return len(result) != 0

    async def index_image(self, image: Image.Image, image_data: MappedImage, skip_ocr=False, skip_duplicate_check=False,
                          background=False):
        if not skip_duplicate_check and (await self._is_point_duplicate([image_data])):
            raise PointDuplicateError("The uploaded points are contained in the database!", image_data.id)

        if background:
            await run_in_threadpool(self._prepare_image, image, image_data, skip_ocr)
        else:
            self._prepare_image(image, image_data, skip_ocr)

        await self._db_context.insert_items([image_data])

    async def index_image_batch(self, image: list[Image.Image], image_data: list[MappedImage],
                                skip_ocr=False, allow_overwrite=False):
        if not allow_overwrite and (await self._is_point_duplicate(image_data)):
            raise PointDuplicateError("The uploaded points are contained in the database!")
        for img, img_data in zip(image, image_data):
            self._prepare_image(img, img_data, skip_ocr)
        await self._db_context.insert_items(image_data)
