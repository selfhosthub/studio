# api/app/application/services/org_file/thumbnail.py

"""Thumbnail generation for image resources."""

import logging
from pathlib import Path
from typing import Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)


def generate_thumbnail(
    source_path: Path, output_dir: Path, filename: str
) -> Optional[str]:
    """Generate a JPEG thumbnail and return its filename, or None on failure.

    Thumbnail is named {stem}-thumbnail.jpg and written to output_dir.
    """
    try:
        from PIL import Image

        # Generate thumbnail filename
        name_part = filename.rsplit(".", 1)[0]
        thumbnail_filename = f"{name_part}-thumbnail.jpg"
        thumbnail_path = output_dir / thumbnail_filename

        # Open and create thumbnail
        with Image.open(source_path) as img:
            # Convert to RGB if necessary (for PNG with transparency)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Create thumbnail preserving aspect ratio
            img.thumbnail(
                (settings.THUMBNAIL_MAX_SIZE, settings.THUMBNAIL_MAX_SIZE), Image.Resampling.LANCZOS
            )
            img.save(thumbnail_path, "JPEG", quality=settings.THUMBNAIL_QUALITY)

        return thumbnail_filename
    except Exception as e:
        logger.warning(f"Failed to generate thumbnail for {source_path}: {e}")
        return None
