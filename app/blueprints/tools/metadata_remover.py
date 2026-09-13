"""Photo metadata remover.

Shows everything hidden in a photograph's headers — camera, timestamps,
software, and the GPS coordinates it was taken at — then hands back a copy with
all of it removed. Pillow only; no extra dependency.
"""
from io import BytesIO


from PIL import ExifTags, Image, ImageOps
from PIL.PngImagePlugin import PngInfo

from app.blueprints.tools._base import bp
from app.core import storage
from app.core.errors import AppError
from app.core.responses import ok
from app.core.uploads import IMAGE_EXTENSIONS, extension_of, get_file

TOOL = 'metadata-remover'

# Tags worth calling out explicitly: they identify a person, a device or a place.
SENSITIVE = {
    'GPSInfo', 'GPSLatitude', 'GPSLongitude', 'GPSAltitude', 'GPSDateStamp',
    'Make', 'Model', 'BodySerialNumber', 'CameraOwnerName', 'Artist',
    'Copyright', 'Software', 'HostComputer', 'SerialNumber',
    'DateTime', 'DateTimeOriginal', 'DateTimeDigitized',
}

# JPEG cannot carry transparency, and only a few formats round-trip cleanly.
SAVE_FORMAT = {
    'jpg': 'JPEG', 'jpeg': 'JPEG', 'png': 'PNG',
    'webp': 'WEBP', 'tif': 'TIFF', 'tiff': 'TIFF', 'bmp': 'BMP',
}


def _readable(value):
    """EXIF values include bytes, rationals and long tuples — make them printable."""
    if isinstance(value, bytes):
        try:
            return value.decode('utf-8', 'replace').strip('\x00') or '(binary)'
        except Exception:
            return '(binary)'
    if isinstance(value, tuple):
        if len(value) > 8:
            return f'({len(value)} values)'
        return ', '.join(str(_readable(item)) for item in value)
    text = str(value).strip()
    return text[:180] + '…' if len(text) > 180 else text


def _to_degrees(values) -> float:
    degrees, minutes, seconds = (float(v) for v in values)
    return degrees + minutes / 60 + seconds / 3600


def _gps_summary(gps: dict) -> str | None:
    """Turn raw GPS IFD entries into something a person can paste into a map."""
    named = {ExifTags.GPSTAGS.get(key, key): value for key, value in gps.items()}
    if 'GPSLatitude' not in named or 'GPSLongitude' not in named:
        return None
    try:
        latitude = _to_degrees(named['GPSLatitude'])
        longitude = _to_degrees(named['GPSLongitude'])
    except (TypeError, ValueError, ZeroDivisionError):
        return None

    if str(named.get('GPSLatitudeRef', 'N')).upper().startswith('S'):
        latitude = -latitude
    if str(named.get('GPSLongitudeRef', 'E')).upper().startswith('W'):
        longitude = -longitude
    return f'{latitude:.6f}, {longitude:.6f}'


def inspect(image: Image.Image) -> dict:
    """Every piece of metadata we can find, grouped for display."""
    groups, location = [], None

    basics = [
        {'tag': 'Format', 'value': image.format or 'unknown', 'sensitive': False},
        {'tag': 'Mode', 'value': image.mode, 'sensitive': False},
        {'tag': 'Dimensions', 'value': f'{image.width} x {image.height}', 'sensitive': False},
    ]
    groups.append({'title': 'Image', 'rows': basics})

    exif = image.getexif()
    if exif:
        rows = []
        for tag_id, value in exif.items():
            name = ExifTags.TAGS.get(tag_id, f'Tag {tag_id}')
            if name == 'GPSInfo':
                continue                      # handled as its own group below
            rows.append({
                'tag': name,
                'value': _readable(value),
                'sensitive': name in SENSITIVE,
            })

        # The Exif sub-IFD holds the interesting camera settings.
        try:
            for tag_id, value in exif.get_ifd(ExifTags.IFD.Exif).items():
                name = ExifTags.TAGS.get(tag_id, f'Tag {tag_id}')
                rows.append({
                    'tag': name,
                    'value': _readable(value),
                    'sensitive': name in SENSITIVE,
                })
        except (AttributeError, KeyError, ValueError):
            pass

        if rows:
            rows.sort(key=lambda row: (not row['sensitive'], row['tag']))
            groups.append({'title': 'EXIF', 'rows': rows})

        try:
            gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
        except (AttributeError, KeyError, ValueError):
            gps = None

        if gps:
            location = _gps_summary(gps)
            rows = [
                {
                    'tag': ExifTags.GPSTAGS.get(key, f'GPS {key}'),
                    'value': _readable(value),
                    'sensitive': True,
                }
                for key, value in gps.items()
            ]
            groups.append({'title': 'GPS location', 'rows': rows})

    # PNG text chunks and other format-specific extras.
    skip = {'exif', 'icc_profile', 'photoshop', 'dpi', 'jfif', 'jfif_version',
            'jfif_unit', 'jfif_density', 'adobe', 'adobe_transform'}
    rows = [
        {'tag': key, 'value': _readable(value), 'sensitive': False}
        for key, value in (image.info or {}).items()
        if key.lower() not in skip and not isinstance(value, (bytes, bytearray))
    ]
    if image.info.get('icc_profile'):
        rows.append({'tag': 'icc_profile', 'value': 'embedded colour profile', 'sensitive': False})
    if rows:
        groups.append({'title': 'Embedded text and profiles', 'rows': rows})

    tag_count = sum(len(g['rows']) for g in groups) - len(basics)
    return {'groups': groups, 'count': tag_count, 'location': location}


def strip(image: Image.Image) -> Image.Image:
    """A pixel-identical copy carrying no metadata at all.

    Orientation is applied *first*: a phone photo is usually stored sideways
    with an EXIF tag saying "rotate me". Dropping that tag without baking the
    rotation in is how these tools end up silently rotating people's photos.
    """
    upright = ImageOps.exif_transpose(image)

    clean = Image.new(upright.mode, upright.size)
    clean.putdata(list(upright.getdata()))
    return clean


@bp.post('/metadata-remover/run', endpoint='metadata_remover_run')
def run():
    upload = get_file('file', allowed=IMAGE_EXTENSIONS)
    extension = extension_of(upload.filename)
    fmt = SAVE_FORMAT.get(extension, 'PNG')

    try:
        image = Image.open(upload.stream)
        image.load()
    except Exception:
        raise AppError('Could not read that file as an image.')

    before = inspect(image)
    cleaned = strip(image)

    if fmt == 'JPEG' and cleaned.mode not in ('RGB', 'L'):
        cleaned = cleaned.convert('RGB')

    job_id = storage.new_job(TOOL)
    out_name = f'clean.{ "jpg" if fmt == "JPEG" else extension }'
    out_path = storage.job_dir(TOOL, job_id) / out_name

    save_args = {'format': fmt}
    if fmt == 'JPEG':
        save_args.update(quality=95, subsampling=0)
    if fmt == 'PNG':
        save_args['pnginfo'] = PngInfo()      # an empty chunk table
    cleaned.save(out_path, **save_args)

    # Prove it: re-read what we just wrote rather than assuming.
    with Image.open(out_path) as written:
        written.load()
        after = inspect(written)

    return ok(
        job_id=job_id,
        filename=out_name,
        before=before,
        after=after,
        removed=max(before['count'] - after['count'], 0),
        had_location=bool(before['location']),
        location=before['location'],
        size_before=upload.tell() if upload.seekable() else None,
        size_after=out_path.stat().st_size,
        preview=_preview_data(out_path, fmt),
    )


def _preview_data(path, fmt: str) -> str:
    """A small base64 thumbnail so the page can show the cleaned result."""
    import base64

    with Image.open(path) as image:
        image.load()
        thumbnail = image.copy()
        thumbnail.thumbnail((640, 640))
        if thumbnail.mode not in ('RGB', 'RGBA'):
            thumbnail = thumbnail.convert('RGB')
        buffer = BytesIO()
        thumbnail.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()
