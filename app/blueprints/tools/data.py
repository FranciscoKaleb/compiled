"""Data and files: tabular conversion, bulk rename, archives, photo sorting."""
import io
import re
import zipfile
from datetime import datetime

from PIL import Image

from app.blueprints.tools._base import runner
from app.core.errors import AppError
from app.core.toolkit import (
    Job, form_choice, form_int, form_str, human_bytes, result, safe_name,
    stem_of, today, uploads,
)
from app.core.uploads import IMAGE_EXTENSIONS, extension_of, get_file


@runner('table-convert')
def table_convert(spec):
    import pandas as pd

    upload = get_file('file', allowed={'csv', 'tsv', 'xlsx', 'xls', 'json'})
    fmt = form_choice('format', ['xlsx', 'csv', 'json'], 'xlsx')
    ext = extension_of(upload.filename)
    try:
        if ext == 'csv':
            frame = pd.read_csv(upload.stream)
        elif ext == 'tsv':
            frame = pd.read_csv(upload.stream, sep='\t')
        elif ext in ('xlsx', 'xls'):
            frame = pd.read_excel(upload.stream)
        else:
            frame = pd.read_json(upload.stream)
    except Exception as exc:
        raise AppError(f'Could not read that file: {type(exc).__name__}: {str(exc)[:120]}')
    if frame.empty:
        raise AppError('That file has no rows.')

    job = Job(spec.slug)
    out = f'{stem_of(upload.filename)}.{fmt}'
    path = job.path(out)
    if fmt == 'xlsx':
        frame.to_excel(path, index=False)
    elif fmt == 'csv':
        frame.to_csv(path, index=False)
    else:
        frame.to_json(path, orient='records', indent=2, force_ascii=False)
    return result(job, filename=out, message=f'{len(frame):,} rows × {len(frame.columns)} columns → {fmt.upper()}.',
                  facts=[['Rows', f'{len(frame):,}'], ['Columns', ', '.join(map(str, frame.columns[:8])) + (' …' if len(frame.columns) > 8 else '')]])


_FIELD = re.compile(r'\{(n|name|ext|date)(?::(\d*)(0?\d+))?\}')


@runner('bulk-rename')
def bulk_rename(spec):
    files = uploads('files')
    pattern = form_str('pattern') or 'file_{n:03}{ext}'
    start = form_int('start', 1, 0, 100)
    if not _FIELD.search(pattern) and len(files) > 1:
        raise AppError('The pattern needs {n} so the names stay unique.')

    job = Job(spec.slug)
    renamed, seen = [], set()
    for index, upload in enumerate(files):
        original = safe_name(upload.filename)
        stem, ext = stem_of(upload.filename), ('.' + extension_of(upload.filename) if extension_of(upload.filename) else '')

        def sub(match):
            field, _, width = match.groups()
            if field == 'n':
                return f'{start + index:0{width}d}' if width else str(start + index)
            return {'name': stem, 'ext': ext, 'date': today()}[field]

        new_name = safe_name(_FIELD.sub(sub, pattern)) or original
        if '{' in pattern and '{ext}' not in pattern and ext and not new_name.endswith(ext):
            new_name += ext
        if new_name in seen:
            new_name = f'{stem_of(new_name)}_{index}{ext}'
        seen.add(new_name)
        path = job.path(new_name)
        upload.save(path)
        renamed.append((path, original))

    out = 'renamed.zip'
    job.zip([p for p, _ in renamed], out)
    job.cleanup(*(p for p, _ in renamed))
    return result(job, filename=out, message=f'Renamed {len(renamed)} files.',
                  rows=[[orig, p.name] for p, orig in renamed[:50]])


@runner('zip')
def zip_files(spec):
    files = uploads('files')
    job = Job(spec.slug)
    saved, seen = [], set()
    for upload in files:
        name = safe_name(upload.filename)
        if name in seen:
            name = f'{stem_of(name)}_{len(seen)}.{extension_of(name)}'
        seen.add(name)
        saved.append(job.save_upload(upload, name))
    out = 'archive.zip'
    job.zip(saved, out)
    total = sum(p.stat().st_size for p in saved)
    job.cleanup(*saved)
    return result(job, filename=out, message=f'{len(saved)} files zipped.',
                  facts=[['Uncompressed', human_bytes(total)], ['Zip', human_bytes(job.path(out).stat().st_size)]])


@runner('unzip')
def unzip(spec):
    upload = get_file('file', allowed={'zip'})
    job = Job(spec.slug)
    try:
        archive = zipfile.ZipFile(upload.stream)
        bad = archive.testzip()
    except zipfile.BadZipFile:
        raise AppError('That is not a valid zip archive.')
    if bad:
        raise AppError(f'The archive is corrupt at "{bad}".')

    entries = [e for e in archive.infolist() if not e.is_dir()]
    total = sum(e.file_size for e in entries)
    if total > 2 * 1024 ** 3:
        raise AppError('That archive expands to more than 2 GB; refusing to extract it here.')

    rows, extracted = [], []
    for entry in entries:
        # Flatten and sanitise: no directories, no traversal.
        flat = safe_name(entry.filename.rsplit('/', 1)[-1])
        if flat in {p.name for p in extracted}:
            flat = f'{stem_of(flat)}_{len(extracted)}.{extension_of(flat)}'.rstrip('.')
        path = job.path(flat)
        with archive.open(entry) as src, open(path, 'wb') as dst:
            dst.write(src.read())
        extracted.append(path)
        rows.append([entry.filename, human_bytes(entry.file_size)])

    out = 'extracted_flat.zip'
    job.zip(extracted, out)
    return result(job, filename=out, rows=rows, extra_files=[p.name for p in extracted[:40]],
                  message=f'{len(entries)} files, {human_bytes(total)} uncompressed.')


@runner('photo-sort')
def photo_sort(spec):
    files = uploads('files', allowed=IMAGE_EXTENSIONS | {'heic', 'heif'})
    scheme = form_choice('scheme', ['ym', 'ymd', 'y'], 'ym')
    fmt = {'ym': '%Y/%m', 'ymd': '%Y/%m/%d', 'y': '%Y'}[scheme]

    job = Job(spec.slug)
    saved, arcnames, undated = [], [], 0
    for upload in files:
        taken = None
        data = upload.read()
        try:
            exif = Image.open(io.BytesIO(data)).getexif()
            raw = exif.get(36867) or exif.get(306)          # DateTimeOriginal, else DateTime
            if raw:
                taken = datetime.strptime(str(raw)[:19], '%Y:%m:%d %H:%M:%S')
        except Exception:
            taken = None
        folder = taken.strftime(fmt) if taken else 'undated'
        if not taken:
            undated += 1
        name = safe_name(upload.filename)
        path = job.path(f'{len(saved):04d}_{name}')
        path.write_bytes(data)
        saved.append(path)
        arcnames.append(f'{folder}/{name}')

    out = 'photos_sorted.zip'
    job.zip(saved, out, arcnames=arcnames)
    job.cleanup(*saved)
    folders = sorted({a.rsplit('/', 1)[0] for a in arcnames})
    return result(job, filename=out, message=f'{len(saved)} photos into {len(folders)} folder(s).',
                  facts=[['Folders', ', '.join(folders[:10]) + (' …' if len(folders) > 10 else '')],
                         ['Without a date', undated]])
