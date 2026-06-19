import time
import uuid
from urllib.parse import urlparse

import cloudinary
import cloudinary.uploader
import cloudinary.utils

from api.v1.utils.config import config

# Allowlist of MIME types the browser MediaRecorder may produce for the
# student's recorded answer. Chrome records audio/webm, Safari typically
# records audio/mp4 — the others are included defensively for other
# browsers/devices. Narrow this list if the real frontend turns out to use
# a smaller set.
AUDIO_CONTENT_TYPE_ALLOWLIST: dict[str, str] = {
    "audio/webm": "webm",
    "audio/mp4": "mp4",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/mpeg": "mp3",
}

# Cloudinary routes audio through its "video" resource pipeline — there is
# no separate "audio" resource_type.
_AUDIO_RESOURCE_TYPE = "video"
# "authenticated" delivery type means the asset is not publicly listable or
# guessable; access requires a signature. See get_playable_audio_url() for
# the caveat on expiry.
_AUDIO_DELIVERY_TYPE = "authenticated"


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


def is_allowed_audio_content_type(content_type: str) -> bool:
    return content_type in AUDIO_CONTENT_TYPE_ALLOWLIST


def build_audio_storage_key(session_id: uuid.UUID, turn_sequence: int) -> str:
    """
    Cloudinary public_id doubles as our storage key — predictable and scoped,
    so ownership is inferable from the path alone. No file extension: Cloudinary
    tracks the resource's actual format internally.
    """
    return f"sessions/{session_id}/turns/{turn_sequence}/user-{uuid.uuid4()}"


def generate_audio_upload_params(storage_key: str) -> dict[str, str]:
    """
    Cloudinary has no S3-style presigned PUT URL. Direct browser uploads
    instead use a *signed upload*: the backend signs a fixed set of params
    with the API secret, and the client POSTs the file plus those params to
    Cloudinary's (fixed, non-expiring) upload endpoint. The signature itself
    is what's short-lived (tied to `timestamp`) and single-use in intent.
    """
    timestamp = int(time.time())
    params_to_sign = {
        "public_id": storage_key,
        "timestamp": timestamp,
        "type": _AUDIO_DELIVERY_TYPE,
    }
    signature = cloudinary.utils.api_sign_request(params_to_sign, cloudinary.config().api_secret)
    return {
        "public_id": storage_key,
        "timestamp": str(timestamp),
        "type": _AUDIO_DELIVERY_TYPE,
        "api_key": cloudinary.config().api_key,
        "signature": signature,
    }


def get_audio_upload_url() -> str:
    return f"https://api.cloudinary.com/v1_1/{cloudinary.config().cloud_name}/{_AUDIO_RESOURCE_TYPE}/upload"


def get_playable_audio_url(storage_key: str) -> str:
    """
    Generates a signed GET URL for the given key, resolved fresh at read time
    — never persist or reuse the result.

    Caveat: Cloudinary's `sign_url=True` on "authenticated" delivery produces
    a URL that requires a valid signature to resolve (not publicly listable
    or guessable), but it does not carry a real time-based expiry the way an
    S3 presigned URL does — that requires Cloudinary's token-based
    authentication add-on (a separate signing key, not configured here). This
    is the closest equivalent available without that add-on.
    """
    url, _ = cloudinary.utils.cloudinary_url(
        storage_key,
        resource_type=_AUDIO_RESOURCE_TYPE,
        type=_AUDIO_DELIVERY_TYPE,
        sign_url=True,
    )
    return url
