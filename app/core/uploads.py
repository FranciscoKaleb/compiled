"""Validated upload handling.

Every model page used to do `request.files['image']` directly, which raises a
BadRequestKeyError (an HTML 400) when the field is missing, and decoded
arbitrary bytes straight into PIL with no size guard.
"""
import base64
import binascii
import re
from io import BytesIO

from flask import request
from PIL import Image, UnidentifiedImageError

from app.core.errors import BadUpload

# A 100-megapixel ceiling: comfortably above any real photograph, far below
# what a decompression bomb needs. PIL warns above half this and errors above it.
Image.MAX_IMAGE_PIXELS = 100_000_000

IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'bmp', 'tif', 'tiff'}
VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm'}

_DATA_URL = re.compile(r'^data:(?P<mime>[\w./+-]+)?;base64,(?P<payload>.+)$', re.DOTALL)


def extension_of(filename: str | None) -> str:
    if not filename or '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[1].lower()


def get_file(field: str = 'image', *, allowed: set[str] | None = None):
    """Fetch an uploaded file, or raise BadUpload with a readable message."""
    file = request.files.get(field)
    if file is None or not file.filename:
        raise BadUpload(f'No file was uploaded in the "{field}" field.')

    if allowed is not None:
        ext = extension_of(file.filename)
        if ext not in allowed:
            pretty = ', '.join(sorted(allowed)).upper()
            raise BadUpload(f'Unsupported file type ".{ext}". Accepted: {pretty}.')
    return file


def read_image(field: str = 'image') -> Image.Image:
    """An uploaded image as RGB, with orientation applied."""
    file = get_file(field, allowed=IMAGE_EXTENSIONS)
    return _open(file.stream, source=file.filename)


def read_images(*fields: str) -> list[Image.Image]:
    return [read_image(field) for field in fields]


def decode_data_url(value: str | None, *, field: str = 'image') -> Image.Image:
    """Decode a browser canvas `data:image/png;base64,...` string.

    The old code did `value.split(',')[1]`, which raises IndexError on anything
    malformed and 500s the request.
    """
    if not value or not isinstance(value, str):
        raise BadUpload(f'No image data was sent in "{field}".')

    match = _DATA_URL.match(value.strip())
    payload = match.group('payload') if match else value

    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise BadUpload('The captured image was not valid base64 data.')

    return _open(BytesIO(raw), source='camera capture')


def _open(stream, *, source: str) -> Image.Image:
    from PIL import ImageOps

    try:
        image = Image.open(stream)
        image.load()
    except UnidentifiedImageError:
        raise BadUpload(f'Could not read "{source}" as an image.')
    except Image.DecompressionBombError:
        raise BadUpload('That image is too large to process safely.')
    except OSError:
        raise BadUpload(f'"{source}" appears to be corrupt or truncated.')

    # Respect the EXIF orientation tag so a phone photo is not processed sideways.
    image = ImageOps.exif_transpose(image)
    return image.convert('RGB')


def form_float(name: str, default: float, *, low: float = 0.0, high: float = 1.0) -> float:
    """A numeric form field, clamped. Bad input falls back to the default."""
    try:
        value = float(request.form.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


def form_text(name: str, default: str = '') -> str:
    return (request.form.get(name) or default).strip()
