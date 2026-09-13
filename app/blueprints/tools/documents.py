"""Documents and text: codes, office conversion, diff, formatting, checksums, regex."""
import difflib
import hashlib
import json
import re

from PIL import Image, ImageOps

from app.blueprints.tools._base import runner
from app.core.errors import AppError
from app.core.toolkit import (
    Job, form_bool, form_choice, form_str, human_bytes, require, result, run,
    stem_of,
)
from app.core.uploads import IMAGE_EXTENSIONS, get_file
from flask import request


@runner('qr-generator')
def qr_generate(spec):
    import qrcode
    from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_M

    text = form_str('text')
    if not text:
        raise AppError('Enter the text or link to encode.')
    if len(text) > 2000:
        raise AppError('That is too much text for one QR code (2000 characters max).')
    size = int(form_choice('size', ['256', '512', '1024'], '512'))
    color = form_str('fg', '#000000') or '#000000'
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        raise AppError('Colour must be a hex code like #1a73e8.')
    logo = request.files.get('logo')

    code = qrcode.QRCode(error_correction=ERROR_CORRECT_H if logo and logo.filename else ERROR_CORRECT_M,
                         box_size=10, border=2)
    code.add_data(text)
    code.make(fit=True)
    image = code.make_image(fill_color=color, back_color='white').convert('RGB')
    image = image.resize((size, size), Image.Resampling.NEAREST)

    if logo and logo.filename:
        try:
            badge = ImageOps.exif_transpose(Image.open(logo.stream)).convert('RGBA')
        except Exception:
            raise AppError('The logo could not be read as an image.')
        side = size // 5                       # high error correction tolerates ~30% loss
        badge = ImageOps.contain(badge, (side, side))
        pad = side // 10
        plate = Image.new('RGBA', (badge.width + 2 * pad, badge.height + 2 * pad), 'white')
        plate.alpha_composite(badge, (pad, pad))
        image.paste(plate, ((size - plate.width) // 2, (size - plate.height) // 2), plate)

    job = Job(spec.slug)
    out = 'qr.png'
    image.save(job.path(out), 'PNG')
    return result(job, filename=out, message=f'{size} × {size} px QR code.',
                  facts=[['Encoded', text[:80] + ('…' if len(text) > 80 else '')], ['Modules', f'{code.modules_count} × {code.modules_count}']])


@runner('qr-reader')
def qr_read(spec):
    import cv2
    import numpy as np

    upload = get_file('file', allowed=IMAGE_EXTENSIONS)
    try:
        image = ImageOps.exif_transpose(Image.open(upload.stream)).convert('RGB')
    except Exception:
        raise AppError('That file could not be read as an image.')
    frame = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

    detector = cv2.QRCodeDetector()
    found, texts, _, _ = detector.detectAndDecodeMulti(frame)
    texts = [t for t in (texts if found else []) if t]
    if not texts:
        # Retry on an upscaled, sharpened copy — small codes in photos often need it.
        bigger = cv2.resize(frame, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        text, _, _ = detector.detectAndDecode(bigger)
        texts = [text] if text else []
    if not texts:
        raise AppError('No QR code could be decoded in that image.')

    job = Job(spec.slug)
    out = 'decoded.txt'
    job.path(out).write_text('\n'.join(texts))
    return result(job, filename=out, text='\n\n'.join(texts),
                  message=f'Decoded {len(texts)} code(s).')


@runner('barcode')
def barcode_generate(spec):
    import barcode
    from barcode.writer import ImageWriter

    data = form_str('data')
    kind = form_choice('kind', ['code128', 'ean13', 'ean8', 'upca', 'code39', 'isbn13'], 'code128')
    if not data:
        raise AppError('Enter the data to encode.')
    try:
        cls = barcode.get_barcode_class(kind)
        code = cls(data, writer=ImageWriter())
    except Exception as exc:
        raise AppError(f'{kind.upper()} cannot encode "{data}": {exc}')

    job = Job(spec.slug)
    base = job.path('barcode')
    saved = code.save(str(base), options={'module_height': 18, 'font_size': 12, 'text_distance': 4, 'quiet_zone': 4})
    out = saved.split('/')[-1] if saved else 'barcode.png'
    return result(job, filename=out, message=f'{kind.upper()} barcode.',
                  facts=[['Encoded', code.get_fullcode()]])


@runner('docx-to-pdf')
def office_to_pdf(spec):
    require('soffice')
    upload = get_file('file', allowed={'docx', 'doc', 'odt', 'rtf', 'pptx', 'ppt', 'odp', 'xlsx', 'xls', 'ods'})
    job = Job(spec.slug)
    source = job.save_upload(upload)
    profile = job.path('lo-profile')
    run(['soffice', f'-env:UserInstallation=file://{profile}', '--headless', '--norestore',
         '--convert-to', 'pdf', '--outdir', job.dir, source],
        timeout=300, what='LibreOffice')
    out = f'{source.stem}.pdf'
    if not job.path(out).is_file():
        raise AppError('LibreOffice did not produce a PDF for that file.')
    job.cleanup(source, profile)
    return result(job, filename=out, message='Converted to PDF.',
                  facts=[['Size', human_bytes(job.path(out).stat().st_size)]])


@runner('text-diff')
def text_diff(spec):
    left = request.form.get('left', '')
    right = request.form.get('right', '')
    if not left and not right:
        raise AppError('Paste text into both boxes.')
    a, b = left.splitlines(), right.splitlines()
    ops = []
    matcher = difflib.SequenceMatcher(None, a, b)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            ops.extend({'kind': 'same', 'text': line} for line in a[i1:i2])
        else:
            ops.extend({'kind': 'removed', 'text': line} for line in a[i1:i2])
            ops.extend({'kind': 'added', 'text': line} for line in b[j1:j2])
    removed = sum(1 for o in ops if o['kind'] == 'removed')
    added = sum(1 for o in ops if o['kind'] == 'added')
    unified = '\n'.join(difflib.unified_diff(a, b, 'original', 'changed', lineterm=''))

    job = Job(spec.slug)
    out = 'diff.patch'
    job.path(out).write_text(unified + '\n')
    return result(job, filename=out, lines=ops,
                  message=f'{added} line(s) added, {removed} removed, {round(matcher.ratio() * 100)}% similar.')


@runner('formatter')
def formatter(spec):
    import yaml

    text = request.form.get('text', '').strip()
    output = form_choice('output', ['json', 'json-min', 'yaml'], 'json')
    if not text:
        raise AppError('Paste some JSON or YAML.')
    data, kind = None, None
    try:
        data, kind = json.loads(text), 'JSON'
    except ValueError as json_error:
        try:
            data, kind = yaml.safe_load(text), 'YAML'
        except yaml.YAMLError as yaml_error:
            mark = getattr(yaml_error, 'problem_mark', None)
            where = f' (line {mark.line + 1}, column {mark.column + 1})' if mark else ''
            raise AppError(f'Not valid JSON ({json_error}) nor valid YAML{where}.')

    if output == 'json':
        formatted, ext = json.dumps(data, indent=2, ensure_ascii=False), 'json'
    elif output == 'json-min':
        formatted, ext = json.dumps(data, separators=(',', ':'), ensure_ascii=False), 'json'
    else:
        formatted, ext = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False), 'yaml'

    job = Job(spec.slug)
    out = f'formatted.{ext}'
    job.path(out).write_text(formatted)
    return result(job, filename=out, text=formatted,
                  message=f'Valid {kind}, written as {output.upper().replace("-MIN", " (minified)")}.')


@runner('hash')
def hash_file(spec):
    upload = get_file('file')
    digests = {name: hashlib.new(name) for name in ('md5', 'sha1', 'sha256', 'sha512')}
    size = 0
    while chunk := upload.stream.read(1 << 20):
        size += len(chunk)
        for digest in digests.values():
            digest.update(chunk)
    rows = [[name.upper().replace('SHA', 'SHA-'), digest.hexdigest()] for name, digest in digests.items()]

    job = Job(spec.slug)
    out = f'{stem_of(upload.filename)}.checksums.txt'
    job.path(out).write_text(''.join(f'{v}  {upload.filename}  ({k})\n' for k, v in rows))
    return result(job, filename=out, rows=rows, message=f'{human_bytes(size)} hashed.',
                  facts=[['File', upload.filename], ['Size', human_bytes(size)]])


@runner('regex')
def regex_test(spec):
    pattern = request.form.get('pattern', '')
    text = request.form.get('text', '')
    if not pattern:
        raise AppError('Enter a pattern.')
    flags = 0
    if form_bool('ignorecase'):
        flags |= re.IGNORECASE
    if form_bool('multiline'):
        flags |= re.MULTILINE
    try:
        compiled = re.compile(pattern, flags)
    except re.error as exc:
        raise AppError(f'Invalid pattern: {exc}')

    matches = []
    for m in compiled.finditer(text):
        if len(matches) >= 500:
            break
        matches.append({
            'match': m.group(0), 'start': m.start(), 'end': m.end(),
            'groups': [g if g is not None else '' for g in m.groups()],
            'named': {k: (v if v is not None else '') for k, v in m.groupdict().items()},
        })

    job = Job(spec.slug)
    out = 'matches.json'
    job.path(out).write_text(json.dumps(matches, indent=2, ensure_ascii=False))
    return result(job, filename=out, matches=matches, group_count=compiled.groups,
                  message=f'{len(matches)} match(es).' + (' Showing the first 500.' if len(matches) == 500 else ''))
