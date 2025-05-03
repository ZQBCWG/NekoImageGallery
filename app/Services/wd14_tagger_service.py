from pathlib import Path
from typing import Optional
import numpy as np
from PIL import Image
from loguru import logger
from tagger.interrogator import WaifuDiffusionInterrogator
from app.config import config

class WD14TaggerService:
    def __init__(self):
        self.tagger: Optional[WaifuDiffusionInterrogator] = None
        self._model_loaded = False
        self.load_model()

    def load_model(self):
        if not config.model.tagger_enabled:
            logger.info("WD14 tagger is disabled in config")
            return

        try:
            self.tagger = WaifuDiffusionInterrogator(
                name='WD14 Tagger',
                repo_id=config.model.wd14_tagger,
                model_path='model.onnx',
                tags_path='selected_tags.csv'
            )
            self._model_loaded = True
            logger.success(f"Loaded WD14 tagger model: {config.model.wd14_tagger}")
        except Exception as e:
            logger.error(f"Failed to load WD14 tagger: {str(e)}")
            self._model_loaded = False

    def generate_tags(self, image: Image.Image) -> list[str]:
        if not self._model_loaded or not self.tagger:
            return []

        try:
            # Convert image to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Generate predictions using interrogate method
            _, tag_confidents = self.tagger.interrogate(image)
            
            # Filter tags by threshold
            tags = [
                tag
                for tag, prob in tag_confidents.items()
                if prob > config.model.tagger_threshold
            ]
            
            return tags
        except Exception as e:
            logger.error(f"Error generating tags: {str(e)}")
            return []