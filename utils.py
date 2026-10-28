"""
utils.py - small helper functions: image checking and request throttling.

Keeping these out of app.py makes them easy to test without starting Streamlit.
"""

import hashlib
import io
import math

from PIL import Image, ImageOps, UnidentifiedImageError

import config


class ImageValidationError(Exception):
    """Raised when an uploaded file is not a usable image. The message is safe to show."""


def prepare_image(raw_bytes: bytes) -> tuple[bytes, str]:
    """
    Check an uploaded image and return (jpeg_bytes, "image/jpeg").

    Steps:
      1. Reject empty or oversized files.
      2. Confirm the file REALLY is a JPEG/PNG/WEBP (we do not trust the file name).
      3. Fix rotation, shrink big photos, and re-save as JPEG.

    Re-saving also removes hidden metadata such as GPS location, so we never
    send that to the AI provider.
    """
    if not raw_bytes:
        raise ImageValidationError("The file is empty. Please choose another photo.")
    if len(raw_bytes) > config.MAX_UPLOAD_BYTES:
        raise ImageValidationError(
            f"This photo is larger than {config.MAX_UPLOAD_MB} MB. "
            "Please choose a smaller one."
        )

    try:
        # verify() checks that the file is not corrupted, but it "uses up" the
        # image object, so we open the data a second time afterwards.
        with Image.open(io.BytesIO(raw_bytes)) as probe:
            probe.verify()
        image = Image.open(io.BytesIO(raw_bytes))

        if image.format not in config.ALLOWED_IMAGE_FORMATS:
            raise ImageValidationError(
                "That image format is not supported. Please use a JPG, PNG or WEBP photo."
            )
        if image.width * image.height > config.MAX_IMAGE_PIXELS:
            raise ImageValidationError(
                "This image has too many pixels. Please use a smaller photo."
            )

        image = ImageOps.exif_transpose(image)  # respect the phone's rotation
        image.thumbnail((config.MAX_IMAGE_SIDE, config.MAX_IMAGE_SIDE))

        # JPEG has no transparency, so place transparent images on white.
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1])
            image = background
        else:
            image = image.convert("RGB")

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90)
        return buffer.getvalue(), "image/jpeg"

    except ImageValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise ImageValidationError(
            "I could not read that file as an image. It may be damaged or not a photo."
        ) from None


def fingerprint(image_bytes: bytes) -> str:
    """A short unique 'fingerprint' of the image, used to detect the same photo twice."""
    return hashlib.sha256(image_bytes).hexdigest()


def seconds_until_next_request(last_request_time, now: float, cooldown: float) -> int:
    """How many whole seconds the user must still wait (0 means 'go ahead')."""
    if last_request_time is None:
        return 0
    remaining = cooldown - (now - last_request_time)
    return max(0, math.ceil(remaining))
