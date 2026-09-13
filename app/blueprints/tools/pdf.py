"""PDF tools: merge, split, rearrange, compress, convert, protect, watermark."""
import io
import math
import re

from PIL import Image, ImageDraw, ImageFont
from PyPDF2 import PdfReader, PdfWriter, errors

from app.blueprints.tools._base import runner
from app.core.errors import AppError
from app.core.toolkit import (
    Job, form_choice, form_float, form_int, form_str, human_bytes, parse_pages,
    require, result, run, stem_of, uploads,
)
from app.core.uploads import IMAGE_EXTENSIONS, get_file


def _reader(upload, password: str | None = None) -> PdfReader:
    try:
        reader = PdfReader(upload.stream)
    except (errors.PdfReadError, ValueError, OSError):
        raise AppError(f'"{upload.filename}" could not be read as a PDF.')
    if reader.is_encrypted:
        if not password or not reader.decrypt(password):
            raise AppError(f'"{upload.filename}" is password protected. Remove the password first.')
    if len(reader.pages) == 0:
        raise AppError(f'"{upload.filename}" has no pages.')
    return reader


def _write(writer: PdfWriter, path):
    with open(path, 'wb') as fh:
        writer.write(fh)


# ---------------------------------------------------------------------------

@runner('pdf-combiner')
def pdf_combiner(spec):
    files = uploads('files', allowed={'pdf'}, minimum=2)
    job = Job(spec.slug)
    writer = PdfWriter()
    pages = 0
    for upload in files:
        for page in _reader(upload).pages:
            writer.add_page(page)
            pages += 1
    out = f'{stem_of(files[0].filename)}_merged.pdf'
    _write(writer, job.path(out))
    return result(job, filename=out, message=f'Merged {len(files)} PDFs into {pages} pages.',
                  facts=[['Files', len(files)], ['Pages', pages]])


@runner('pdf-split')
def pdf_split(spec):
    upload = get_file('file', allowed={'pdf'})
    reader = _reader(upload)
    total = len(reader.pages)
    stem = stem_of(upload.filename)
    job = Job(spec.slug)
    selection = form_str('pages')

    if selection:
        indexes = parse_pages(selection, total)
        writer = PdfWriter()
        for index in indexes:
            writer.add_page(reader.pages[index])
        out = f'{stem}_pages.pdf'
        _write(writer, job.path(out))
        return result(job, filename=out, message=f'Extracted {len(indexes)} of {total} pages.',
                      facts=[['Pages kept', len(indexes)], ['Pages in source', total]])

    parts = []
    for index, page in enumerate(reader.pages, start=1):
        writer = PdfWriter()
        writer.add_page(page)
        part = job.path(f'{stem}_page_{index:03d}.pdf')
        _write(writer, part)
        parts.append(part)
    out = f'{stem}_pages.zip'
    job.zip(parts, out)
    job.cleanup(*parts)
    return result(job, filename=out, message=f'Split into {total} single-page PDFs.',
                  facts=[['Pages', total]])


_ORDER_TOKEN = re.compile(r'^(\d+)(?:-(\d+))?(?:r(90|180|270))?$', re.I)


@runner('pdf-pages')
def pdf_pages(spec):
    upload = get_file('file', allowed={'pdf'})
    reader = _reader(upload)
    total = len(reader.pages)
    spec_text = form_str('order')
    if not spec_text:
        raise AppError('Give the new page order, e.g. "3, 1r90, 2".')

    writer = PdfWriter()
    kept = 0
    rotated = 0
    for token in re.split(r'[,\s]+', spec_text):
        if not token:
            continue
        match = _ORDER_TOKEN.match(token)
        if not match:
            raise AppError(f'"{token}" is not understood. Use numbers like 3, ranges like 5-8, rotations like 1r90.')
        start, end, angle = int(match.group(1)), match.group(2), match.group(3)
        end = int(end) if end else start
        if start < 1 or end > total or start > end:
            raise AppError(f'"{token}" is outside this document\'s {total} page(s).')
        for index in range(start - 1, end):
            page = reader.pages[index]
            if angle:
                page.rotate(int(angle))
                rotated += 1
            writer.add_page(page)
            kept += 1

    job = Job(spec.slug)
    out = f'{stem_of(upload.filename)}_rearranged.pdf'
    _write(writer, job.path(out))
    return result(job, filename=out,
                  message=f'Rebuilt with {kept} pages ({total - kept} removed, {rotated} rotated).',
                  facts=[['Pages kept', kept], ['Pages removed', max(total - kept, 0)], ['Rotated', rotated]])


@runner('pdf-compress')
def pdf_compress(spec):
    upload = get_file('file', allowed={'pdf'})
    quality = form_int('quality', 60, 20, 95)
    max_dim = form_int('max_dim', 1600, 600, 3000)
    original_size = _size_of(upload)

    reader = _reader(upload)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    images = 0
    for page in writer.pages:
        images += _recompress_images(page, quality, max_dim)
        try:
            page.compress_content_streams()
        except Exception:
            pass

    writer.add_metadata(reader.metadata or {})
    job = Job(spec.slug)
    out = f'{stem_of(upload.filename)}_compressed.pdf'
    _write(writer, job.path(out))
    new_size = job.path(out).stat().st_size
    saved = max(0, 100 - round(new_size / original_size * 100)) if original_size else 0
    return result(job, filename=out,
                  message=f'{human_bytes(original_size)} → {human_bytes(new_size)} ({saved}% smaller).',
                  facts=[['Images re-encoded', images], ['Before', human_bytes(original_size)],
                         ['After', human_bytes(new_size)]])


def _recompress_images(page, quality: int, max_dim: int) -> int:
    """Re-encode the image XObjects on a page as JPEG. Returns how many changed.

    PyPDF2 3.0.1 has no image-replace API, so this edits the stream objects
    directly: decode with the same helper `page.images` uses, re-encode with
    Pillow, and swap the stream data plus the filter/colour-space entries.
    Images with transparency masks are left alone to avoid breaking them.
    """
    from PyPDF2.filters import _xobj_to_image
    from PyPDF2.generic import NameObject, NumberObject

    resources = page.get('/Resources')
    xobjects = resources.get('/XObject') if resources else None
    if not xobjects:
        return 0
    xobjects = xobjects.get_object()

    changed = 0
    for key in list(xobjects.keys()):
        obj = xobjects[key].get_object()
        if obj.get('/Subtype') != '/Image' or '/SMask' in obj or '/Mask' in obj:
            continue
        try:
            _, raw = _xobj_to_image(obj)
            pil = Image.open(io.BytesIO(raw))
            pil.load()
        except Exception:
            continue

        original_len = len(obj._data)
        if max(pil.size) > max_dim:
            scale = max_dim / max(pil.size)
            pil = pil.resize((max(1, int(pil.width * scale)), max(1, int(pil.height * scale))),
                             Image.Resampling.LANCZOS)
        if pil.mode not in ('RGB', 'L'):
            pil = pil.convert('RGB')

        buffer = io.BytesIO()
        pil.save(buffer, 'JPEG', quality=quality, optimize=True)
        data = buffer.getvalue()
        if len(data) >= original_len:
            continue                          # already smaller than we can make it

        # PyPDF2 3.0.1 refuses set_data() on encoded streams, but the writer only
        # ever reads _data, so replace it directly and drop the decode cache.
        obj._data = data
        obj.decoded_self = None
        obj[NameObject('/Filter')] = NameObject('/DCTDecode')
        obj[NameObject('/ColorSpace')] = NameObject('/DeviceGray' if pil.mode == 'L' else '/DeviceRGB')
        obj[NameObject('/BitsPerComponent')] = NumberObject(8)
        obj[NameObject('/Width')] = NumberObject(pil.width)
        obj[NameObject('/Height')] = NumberObject(pil.height)
        for stale in ('/DecodeParms', '/Decode', '/Interpolate'):
            if stale in obj:
                del obj[NameObject(stale)]
        changed += 1
    return changed


def _size_of(upload) -> int:
    upload.stream.seek(0, io.SEEK_END)
    size = upload.stream.tell()
    upload.stream.seek(0)
    return size


@runner('pdf-to-images')
def pdf_to_images(spec):
    require('pdftoppm')
    from pdf2image import convert_from_path

    upload = get_file('file', allowed={'pdf'})
    fmt = form_choice('format', ['png', 'jpg'], 'png')
    dpi = form_int('dpi', 150, 72, 300)

    job = Job(spec.slug)
    source = job.save_upload(upload, 'source.pdf')
    try:
        pages = convert_from_path(str(source), dpi=dpi, fmt='jpeg' if fmt == 'jpg' else 'png')
    except Exception as exc:
        raise AppError(f'Could not render that PDF. ({type(exc).__name__})')
    finally:
        job.cleanup(source)

    stem = stem_of(upload.filename)
    files = []
    for index, page in enumerate(pages, start=1):
        path = job.path(f'{stem}_page_{index:03d}.{fmt}')
        page.save(path, quality=90) if fmt == 'jpg' else page.save(path)
        files.append(path)
    out = f'{stem}_pages.zip'
    job.zip(files, out)
    job.cleanup(*files)
    return result(job, filename=out, message=f'Rendered {len(files)} pages at {dpi} dpi.',
                  facts=[['Pages', len(files)], ['Format', fmt.upper()], ['Resolution', f'{dpi} dpi']])


_PAGE_SIZES = {'a4': (595, 842), 'letter': (612, 792)}


@runner('images-to-pdf')
def images_to_pdf(spec):
    files = uploads('files', allowed=IMAGE_EXTENSIONS | {'heic', 'heif'})
    page_mode = form_choice('page', ['fit', 'a4', 'letter'], 'fit')

    pages = []
    for upload in files:
        try:
            image = Image.open(upload.stream)
            image.load()
        except Exception:
            raise AppError(f'"{upload.filename}" could not be read as an image.')
        from PIL import ImageOps
        image = ImageOps.exif_transpose(image).convert('RGB')
        if page_mode in _PAGE_SIZES:
            width, height = _PAGE_SIZES[page_mode]
            if image.width > image.height:
                width, height = height, width
            canvas = Image.new('RGB', (width * 2, height * 2), 'white')
            fitted = ImageOps.contain(image, (int(width * 1.8), int(height * 1.8)))
            canvas.paste(fitted, ((canvas.width - fitted.width) // 2, (canvas.height - fitted.height) // 2))
            image = canvas
        pages.append(image)

    job = Job(spec.slug)
    out = f'{stem_of(files[0].filename)}.pdf' if len(files) == 1 else 'images.pdf'
    pages[0].save(job.path(out), 'PDF', save_all=True, append_images=pages[1:], resolution=144)
    return result(job, filename=out, message=f'{len(pages)} image(s) placed on {len(pages)} page(s).',
                  facts=[['Pages', len(pages)], ['Page size', page_mode.upper() if page_mode != 'fit' else 'Fit to image']])


@runner('pdf-password')
def pdf_password(spec):
    upload = get_file('file', allowed={'pdf'})
    mode = form_choice('mode', ['add', 'remove'], 'add')
    password = form_str('password')
    if not password:
        raise AppError('Enter a password.')

    writer = PdfWriter()
    stem = stem_of(upload.filename)
    if mode == 'add':
        reader = _reader(upload)
        for page in reader.pages:
            writer.add_page(page)
        writer.encrypt(password, use_128bit=True)
        out = f'{stem}_protected.pdf'
        message = 'Encrypted (128-bit). Keep the password somewhere safe.'
    else:
        try:
            reader = PdfReader(upload.stream)
        except Exception:
            raise AppError('That file could not be read as a PDF.')
        if not reader.is_encrypted:
            raise AppError('That PDF is not password protected.')
        if not reader.decrypt(password):
            raise AppError('That password does not open this PDF.')
        for page in reader.pages:
            writer.add_page(page)
        out = f'{stem}_unlocked.pdf'
        message = 'Password removed.'

    job = Job(spec.slug)
    _write(writer, job.path(out))
    return result(job, filename=out, message=message, facts=[['Pages', len(writer.pages)]])


def _stamp_pdf(text: str, width: float, height: float, opacity: float, size: int) -> PdfReader:
    """A one-page PDF with diagonal text, built with Pillow (no reportlab needed)."""
    scale = 2
    canvas = Image.new('RGBA', (int(width * scale), int(height * scale)), (0, 0, 0, 0))
    font = _font(size * scale)
    layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    text_img = Image.new('RGBA', (text_w + 20, text_h + 20), (0, 0, 0, 0))
    ImageDraw.Draw(text_img).text((10 - bbox[0], 10 - bbox[1]), text, font=font,
                                  fill=(90, 90, 90, int(255 * opacity)))
    angle = math.degrees(math.atan2(height, width))
    rotated = text_img.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    layer.paste(rotated, ((canvas.width - rotated.width) // 2, (canvas.height - rotated.height) // 2), rotated)
    canvas.alpha_composite(layer)

    buffer = io.BytesIO()
    canvas.save(buffer, 'PDF', resolution=72 * scale)
    buffer.seek(0)
    return PdfReader(buffer)


def _font(size: int):
    for name in ('DejaVuSans-Bold.ttf', 'DejaVuSans.ttf', 'LiberationSans-Bold.ttf', 'Arial.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


@runner('pdf-watermark')
def pdf_watermark(spec):
    upload = get_file('file', allowed={'pdf'})
    text = form_str('text')
    if not text:
        raise AppError('Enter the watermark text.')
    opacity = form_float('opacity', 0.2, 0.05, 0.6)
    size = form_int('size', 60, 24, 120)

    reader = _reader(upload)
    writer = PdfWriter()
    stamps = {}
    for page in reader.pages:
        box = page.mediabox
        key = (round(float(box.width)), round(float(box.height)))
        if key not in stamps:
            stamps[key] = _stamp_pdf(text, key[0], key[1], opacity, size).pages[0]
        page.merge_page(stamps[key])
        writer.add_page(page)

    job = Job(spec.slug)
    out = f'{stem_of(upload.filename)}_watermarked.pdf'
    _write(writer, job.path(out))
    return result(job, filename=out, message=f'"{text}" stamped on {len(writer.pages)} pages.',
                  facts=[['Pages', len(writer.pages)], ['Opacity', f'{int(opacity * 100)}%']])


@runner('pdf-metadata-remover')
def pdf_metadata(spec):
    upload = get_file('file', allowed={'pdf'})
    reader = _reader(upload)

    rows = []
    for key, value in (reader.metadata or {}).items():
        name = str(key).lstrip('/')
        rows.append([name, str(value)[:200]])
    xmp = None
    try:
        xmp = reader.xmp_metadata
    except Exception:
        pass

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_metadata({'/Producer': ''})
    # Drop the XMP packet too; PyPDF2 copies it with the catalog otherwise.
    try:
        from PyPDF2.generic import NameObject
        if '/Metadata' in writer._root_object:
            del writer._root_object[NameObject('/Metadata')]
    except Exception:
        pass

    job = Job(spec.slug)
    out = f'{stem_of(upload.filename)}_clean.pdf'
    _write(writer, job.path(out))
    with open(job.path(out), 'rb') as fh:
        remaining = {k: v for k, v in (PdfReader(fh).metadata or {}).items() if v}

    return result(
        job, filename=out,
        message=f'Removed {len(rows)} document-info entr{"y" if len(rows) == 1 else "ies"}'
                + (' and an XMP metadata packet.' if xmp is not None else '.'),
        rows=rows or [['(none)', 'This PDF carried no document info.']],
        facts=[['Pages', len(writer.pages)], ['Entries remaining', len(remaining)]],
    )
