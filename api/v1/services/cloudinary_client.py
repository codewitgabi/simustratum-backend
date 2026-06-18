from urllib.parse import urlparse

import cloudinary
import cloudinary.uploader

from api.v1.utils.config import config


def _configure_cloudinary() -> None:
    if not config.CLOUDINARY_URL:
        return
    parsed = urlparse(config.CLOUDINARY_URL)
    cloudinary.config(
        cloud_name=parsed.hostname,
        api_key=parsed.username,
        api_secret=parsed.password,
        secure=True,
    )


_configure_cloudinary()


def upload_document(file_bytes: bytes, filename: str) -> str:
    """Uploads raw document bytes to Cloudinary and returns the secure URL."""
    result = cloudinary.uploader.upload(
        file_bytes,
        resource_type="raw",
        folder="documents",
        public_id=filename,
        use_filename=True,
        unique_filename=True,
    )
    return result["secure_url"]
