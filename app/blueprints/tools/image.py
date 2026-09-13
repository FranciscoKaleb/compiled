"""Image tools: convert, resize, cut out, ID photos, palettes, icons, watermarks."""
import io
import json

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from app.blueprints.tools._base import runner
from app.core.errors import AppError
from app.core.toolkit import (
    Job, form_bool, form_choice, form_float, form_int, form_str, human_bytes,
    result, stem_of, uploads,
)
from app.core.uploads import IMAGE_EXTENSIONS, get_file

SAVE_FORMAT = {'jpg': 'JPEG', 'jpeg': 'JPEG', 'png': 'PNG', 'webp': 'WEBP', 'bmp': 'BMP', 'tiff': 'TIFF'}


def _open(upload) -> Image.Image:
    try:
        image = Image.open(upload.stream)
        image.load()
    except Exception:
        raise AppError(f'"{upload.filename}" could not be read as an image.')
    return ImageOps.exif_transpose(image)


def _save(image: Image.Image, path, fmt: str, quality: int = 85) -> None:
    fmt = SAVE_FORMAT[fmt]
    if fmt == 'JPEG' and image.mode not in ('RGB', 'L'):
        image = image.convert('RGB')
    if fmt == 'BMP' and image.mode == 'RGBA':
        image = image.convert('RGB')
    kwargs = {'quality': quality} if fmt in ('JPEG', 'WEBP') else {}
    if fmt == 'JPEG':
        kwargs['optimize'] = True
    image.save(path, fmt, **kwargs)


def _font(size: int):
    for name in ('DejaVuSans-Bold.ttf', 'DejaVuSans.ttf', 'LiberationSans-Bold.ttf'):
        try:
            return ImageFont.truetype(name, max(8, size))
        except OSError:
            continue
    return ImageFont.load_default()


def _register_heif():
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        raise AppError('HEIC support (pillow-heif) is not installed on the server.', 503)


# ---------------------------------------------------------------------------

@runner('bg-remover')
def bg_remover(spec):
    upload = get_file('file', allowed=IMAGE_EXTENSIONS)
    data = upload.read()
    if not data:
        raise AppError('That file was empty.')
    from rembg import remove
    try:
        cutout = remove(data)
    except Exception as exc:
        raise AppError(f'Background removal failed. ({type(exc).__name__})')
    job = Job(spec.slug)
    out = f'{stem_of(upload.filename)}_cutout.png'
    job.path(out).write_bytes(cutout)
    return result(job, filename=out, message='Background removed.',
                  facts=[['Before', human_bytes(len(data))], ['After', human_bytes(len(cutout))]])


@runner('reduce-quality')
def reduce_quality(spec):
    upload = get_file('file', allowed=IMAGE_EXTENSIONS)
    percentage = form_int('percentage', 60, 5, 100)
    image = _open(upload)
    before = image.size
    width = max(1, int(image.width * percentage / 100))
    height = max(1, int(image.height * percentage / 100))
    resized = image.resize((width, height), Image.Resampling.LANCZOS).convert('RGB')

    job = Job(spec.slug)
    out = f'{stem_of(upload.filename)}_reduced.jpg'
    resized.save(job.path(out), 'JPEG', quality=percentage, optimize=True)
    return result(job, filename=out, message=f'Scaled to {percentage}% at JPEG quality {percentage}.',
                  facts=[['Before', f'{before[0]} × {before[1]}'], ['After', f'{width} × {height}']])


@runner('bulk-convert')
def bulk_convert(spec):
    files = uploads('files', allowed=IMAGE_EXTENSIONS | {'heic', 'heif'})
    fmt = form_choice('format', list(SAVE_FORMAT), 'webp')
    max_dim = form_int('max_dim', 1920, 200, 4000)
    quality = form_int('quality', 85, 40, 100)
    if any(f.filename.lower().endswith(('.heic', '.heif')) for f in files):
        _register_heif()

    job = Job(spec.slug)
    outputs, before, after = [], 0, 0
    for upload in files:
        upload.stream.seek(0, io.SEEK_END)
        before += upload.stream.tell()
        upload.stream.seek(0)
        image = _open(upload)
        if max(image.size) > max_dim:
            image = ImageOps.contain(image, (max_dim, max_dim), Image.Resampling.LANCZOS)
        path = job.path(f'{stem_of(upload.filename)}.{fmt}')
        _save(image, path, fmt, quality)
        after += path.stat().st_size
        outputs.append(path)

    if len(outputs) == 1:
        return result(job, filename=outputs[0].name, message='Converted 1 image.',
                      facts=[['Before', human_bytes(before)], ['After', human_bytes(after)]])
    out = f'converted_{fmt}.zip'
    job.zip(outputs, out)
    job.cleanup(*outputs)
    return result(job, filename=out, message=f'Converted {len(outputs)} images to {fmt.upper()}.',
                  facts=[['Images', len(outputs)], ['Before', human_bytes(before)], ['After', human_bytes(after)]])


@runner('heic-to-jpg')
def heic_to_jpg(spec):
    _register_heif()
    files = uploads('files', allowed={'heic', 'heif'})
    fmt = form_choice('format', ['jpg', 'png'], 'jpg')
    quality = form_int('quality', 92, 60, 100)

    job = Job(spec.slug)
    outputs = []
    image = None
    for upload in files:
        image = _open(upload)
        path = job.path(f'{stem_of(upload.filename)}.{fmt}')
        _save(image, path, fmt, quality)
        outputs.append(path)

    if len(outputs) == 1:
        return result(job, filename=outputs[0].name, message='Converted.',
                      facts=[['Size', f'{image.width} × {image.height}']])
    out = f'converted_{fmt}.zip'
    job.zip(outputs, out)
    job.cleanup(*outputs)
    return result(job, filename=out, message=f'Converted {len(outputs)} HEIC files.',
                  facts=[['Files', len(outputs)]])


# --- passport photo ----------------------------------------------------------

# width mm, height mm, head height as a fraction of photo height, eye line from top
STANDARDS = {
    '35x45': (35, 45, 0.72, 0.42),
    '2x2': (51, 51, 0.60, 0.44),
    '33x48': (33, 48, 0.70, 0.42),
    '50x70': (50, 70, 0.55, 0.42),
}
DPI = 300


def _detect_faces(image: Image.Image):
    from app.core import loader
    return loader.get('face/detect').model.get(np.array(image.convert('RGB')))


@runner('passport-photo')
def passport_photo(spec):
    upload = get_file('file', allowed=IMAGE_EXTENSIONS)
    standard = form_choice('standard', list(STANDARDS), '35x45')
    white_bg = form_bool('white_bg')
    image = _open(upload).convert('RGB')

    if white_bg:
        from rembg import remove
        buffer = io.BytesIO()
        image.save(buffer, 'PNG')
        cutout = Image.open(io.BytesIO(remove(buffer.getvalue()))).convert('RGBA')
        white = Image.new('RGBA', cutout.size, (255, 255, 255, 255))
        image = Image.alpha_composite(white, cutout).convert('RGB')

    faces = _detect_faces(image)
    if not faces:
        raise AppError('No face was found. Use a front-facing photo with the whole head visible.')
    face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    x1, y1, x2, y2 = face.bbox
    face_h = y2 - y1
    # Detectors box brow to chin; the full head (hair to chin) is roughly 1.5x.
    head_h = face_h * 1.5
    eye_y = y1 + face_h * 0.35

    w_mm, h_mm, head_frac, eye_frac = STANDARDS[standard]
    crop_h = head_h / head_frac
    crop_w = crop_h * (w_mm / h_mm)
    top = eye_y - crop_h * eye_frac
    left = (x1 + x2) / 2 - crop_w / 2

    # Pad with white when the crop runs off the photo.
    pad = int(max(0, -left, -top, left + crop_w - image.width, top + crop_h - image.height)) + 2
    padded = ImageOps.expand(image, border=pad, fill='white')
    box = (int(left + pad), int(top + pad), int(left + crop_w + pad), int(top + crop_h + pad))
    out_size = (round(w_mm / 25.4 * DPI), round(h_mm / 25.4 * DPI))
    final = padded.crop(box).resize(out_size, Image.Resampling.LANCZOS)

    job = Job(spec.slug)
    stem = stem_of(upload.filename)
    out = f'{stem}_id_{standard}.jpg'
    final.save(job.path(out), 'JPEG', quality=95, dpi=(DPI, DPI))

    # A 4x6 in print sheet with as many copies as fit — what photo shops charge for.
    sheet = Image.new('RGB', (6 * DPI, 4 * DPI), 'white')
    gap = int(0.1 * DPI)
    cols = (sheet.width - gap) // (out_size[0] + gap)
    rows = (sheet.height - gap) // (out_size[1] + gap)
    for r in range(rows):
        for c in range(cols):
            sheet.paste(final, (gap + c * (out_size[0] + gap), gap + r * (out_size[1] + gap)))
    sheet_name = f'{stem}_print_sheet_4x6.jpg'
    sheet.save(job.path(sheet_name), 'JPEG', quality=95, dpi=(DPI, DPI))

    return result(job, filename=out, extra_files=[sheet_name],
                  message=f'{w_mm} × {h_mm} mm at {DPI} dpi, plus a 4×6 in print sheet with {cols * rows} copies.',
                  facts=[['Standard', standard], ['Pixels', f'{out_size[0]} × {out_size[1]}'],
                         ['Copies on sheet', cols * rows]])


@runner('face-blur')
def face_blur(spec):
    upload = get_file('file', allowed=IMAGE_EXTENSIONS)
    style = form_choice('style', ['pixelate', 'blur', 'box'], 'pixelate')
    strength = form_int('strength', 6, 1, 10)
    image = _open(upload).convert('RGB')

    faces = _detect_faces(image)
    if not faces:
        raise AppError('No faces were found in that photo.')

    for face in faces:
        x1, y1, x2, y2 = (int(v) for v in face.bbox)
        margin = int((x2 - x1) * 0.15)
        box = (max(0, x1 - margin), max(0, y1 - margin),
               min(image.width, x2 + margin), min(image.height, y2 + margin))
        region = image.crop(box)
        if style == 'box':
            region = Image.new('RGB', region.size, 'black')
        elif style == 'blur':
            region = region.filter(ImageFilter.GaussianBlur(radius=strength * 4))
        else:
            small = max(2, 24 - strength * 2)
            region = (region.resize((small, small), Image.Resampling.BILINEAR)
                            .resize(region.size, Image.Resampling.NEAREST))
        image.paste(region, box)

    job = Job(spec.slug)
    out = f'{stem_of(upload.filename)}_faces_hidden.jpg'
    image.save(job.path(out), 'JPEG', quality=92)
    return result(job, filename=out, message=f'{len(faces)} face(s) hidden.',
                  facts=[['Faces', len(faces)], ['Style', style]])


@runner('palette')
def palette(spec):
    upload = get_file('file', allowed=IMAGE_EXTENSIONS)
    count = form_int('count', 6, 3, 12)
    image = _open(upload).convert('RGB')
    image.thumbnail((200, 200))
    pixels = np.array(image).reshape(-1, 3).astype(np.float32)
    count = min(count, len(pixels))

    # Plain k-means with a fixed seed: the same image always gives the same palette.
    rng = np.random.default_rng(0)
    centers = pixels[rng.choice(len(pixels), count, replace=False)]
    labels = np.zeros(len(pixels), dtype=int)
    for _ in range(20):
        distances = ((pixels[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        labels = distances.argmin(axis=1)
        new_centers = np.array([
            pixels[labels == k].mean(axis=0) if (labels == k).any() else centers[k]
            for k in range(count)
        ])
        if np.allclose(new_centers, centers, atol=0.5):
            break
        centers = new_centers

    counts = np.bincount(labels, minlength=count)
    colors = []
    for k in np.argsort(-counts):
        r, g, b = (int(round(v)) for v in centers[k])
        colors.append({'hex': f'#{r:02x}{g:02x}{b:02x}', 'rgb': f'rgb({r}, {g}, {b})',
                       'share': round(float(counts[k]) / len(pixels) * 100, 1)})

    strip = Image.new('RGB', (100 * count, 100))
    draw = ImageDraw.Draw(strip)
    for i, color in enumerate(colors):
        draw.rectangle([i * 100, 0, (i + 1) * 100, 100], fill=color['hex'])
    job = Job(spec.slug)
    out = f'{stem_of(upload.filename)}_palette.png'
    strip.save(job.path(out))
    return result(job, filename=out, message=f'{count} dominant colours.', colors=colors)


ICON_SIZES = (16, 32, 48, 64, 128, 180, 192, 256, 512)


@runner('favicon')
def favicon(spec):
    upload = get_file('file', allowed=IMAGE_EXTENSIONS)
    image = _open(upload).convert('RGBA')
    side = min(image.size)
    image = image.crop(((image.width - side) // 2, (image.height - side) // 2,
                        (image.width + side) // 2, (image.height + side) // 2))

    job = Job(spec.slug)
    files = []
    for size in ICON_SIZES:
        name = 'apple-touch-icon.png' if size == 180 else f'icon-{size}x{size}.png'
        path = job.path(name)
        image.resize((size, size), Image.Resampling.LANCZOS).save(path, 'PNG', optimize=True)
        files.append(path)
    ico = job.path('favicon.ico')
    image.resize((256, 256), Image.Resampling.LANCZOS).save(
        ico, 'ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    files.append(ico)

    stem = stem_of(upload.filename)
    manifest = job.path('site.webmanifest')
    manifest.write_text(json.dumps({
        'name': stem, 'short_name': stem,
        'icons': [{'src': f'/icon-{s}x{s}.png', 'sizes': f'{s}x{s}', 'type': 'image/png'} for s in (192, 512)],
        'theme_color': '#ffffff', 'background_color': '#ffffff', 'display': 'standalone',
    }, indent=2))
    files.append(manifest)
    snippet = job.path('head-snippet.html')
    snippet.write_text(
        '<link rel="icon" href="/favicon.ico" sizes="any">\n'
        '<link rel="icon" type="image/png" sizes="32x32" href="/icon-32x32.png">\n'
        '<link rel="apple-touch-icon" href="/apple-touch-icon.png">\n'
        '<link rel="manifest" href="/site.webmanifest">\n')
    files.append(snippet)

    out = f'{stem}_icons.zip'
    job.zip(files, out)
    job.cleanup(*files)
    return result(job, filename=out,
                  message=f'{len(ICON_SIZES)} PNG sizes, favicon.ico, a manifest and the HTML snippet.',
                  facts=[['Sizes', ', '.join(str(s) for s in ICON_SIZES)], ['Source', f'{side} × {side} (centre crop)']])


ASCII_RAMP = '@%#*+=-:. '


@runner('ascii-art')
def ascii_art(spec):
    upload = get_file('file', allowed=IMAGE_EXTENSIONS)
    width = form_int('width', 100, 40, 200)
    invert = form_bool('invert')
    image = _open(upload).convert('L')
    height = max(1, int(image.height / image.width * width * 0.5))     # glyphs are ~2:1
    image = image.resize((width, height))
    ramp = ASCII_RAMP[::-1] if invert else ASCII_RAMP
    text = '\n'.join(
        ''.join(ramp[min(len(ramp) - 1, int(v) * len(ramp) // 256)] for v in row)
        for row in np.array(image)
    )
    job = Job(spec.slug)
    out = f'{stem_of(upload.filename)}_ascii.txt'
    job.path(out).write_text(text)
    return result(job, filename=out, text=text, message=f'{width} × {height} characters.')


@runner('image-watermark')
def image_watermark(spec):
    upload = get_file('file', allowed=IMAGE_EXTENSIONS)
    text = form_str('text')
    if not text:
        raise AppError('Enter the watermark text.')
    placement = form_choice('placement', ['corner', 'center', 'tile'], 'corner')
    opacity = form_float('opacity', 0.4, 0.1, 1.0)
    size_pct = form_int('size', 5, 2, 20)

    image = _open(upload).convert('RGBA')
    font = _font(int(image.width * size_pct / 100))
    layer = Image.new('RGBA', image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    fill = (255, 255, 255, int(255 * opacity))
    shadow = (0, 0, 0, int(160 * opacity))

    def stamp(x, y):
        draw.text((x + 2, y + 2), text, font=font, fill=shadow)
        draw.text((x, y), text, font=font, fill=fill)

    margin = int(image.width * 0.02)
    if placement == 'corner':
        stamp(image.width - tw - margin, image.height - th - margin)
    elif placement == 'center':
        stamp((image.width - tw) // 2, (image.height - th) // 2)
    else:
        tile = Image.new('RGBA', (tw + 40, th + 40), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((20 - bbox[0], 20 - bbox[1]), text, font=font, fill=fill)
        tile = tile.rotate(30, expand=True, resample=Image.Resampling.BICUBIC)
        step_x, step_y = int(tile.width * 1.15), int(tile.height * 1.15)
        for y in range(-tile.height, image.height, step_y):
            for x in range(-tile.width, image.width, step_x):
                layer.alpha_composite(tile, (max(0, x), max(0, y)),
                                      (max(0, -x), max(0, -y)))
    composed = Image.alpha_composite(image, layer)

    job = Job(spec.slug)
    has_alpha = composed.getchannel('A').getextrema()[0] < 255
    ext = 'png' if has_alpha else 'jpg'
    out = f'{stem_of(upload.filename)}_watermarked.{ext}'
    _save(composed, job.path(out), ext, 92)
    return result(job, filename=out, message=f'Watermark added ({placement}).',
                  facts=[['Opacity', f'{int(opacity * 100)}%']])
