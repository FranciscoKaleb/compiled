"""Video and audio tools, all built on ffmpeg."""
import math
import shlex

from PIL import Image

from app.blueprints.tools._base import runner
from app.core.errors import AppError
from app.core.toolkit import (
    Job, ffmpeg, ffprobe_json, form_choice, form_int, form_str, human_bytes,
    human_time, media_duration, parse_timestamp, result, stem_of, uploads,
)
from app.core.uploads import VIDEO_EXTENSIONS, extension_of, get_file

AUDIO_EXTENSIONS = {'mp3', 'wav', 'm4a', 'aac', 'flac', 'ogg', 'opus', 'wma'}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS | {'m4v', '3gp', 'mpg', 'mpeg', 'ts'}


def _source(job: Job, upload, name='source'):
    return job.save_upload(upload, f'{name}.{extension_of(upload.filename)}')


def _facts_for(source, target, duration=None):
    facts = [['Before', human_bytes(source.stat().st_size)], ['After', human_bytes(target.stat().st_size)]]
    if duration:
        facts.insert(0, ['Length', human_time(duration)])
    return facts


# ---------------------------------------------------------------------------

@runner('video-compress')
def video_compress(spec):
    upload = get_file('file', allowed=VIDEO_EXTENSIONS | {'m4v', '3gp', 'mpg', 'mpeg', 'ts'})
    crf = form_int('crf', 28, 18, 40)
    height = form_int('height', 0, 0, 2160)
    preset = form_choice('preset', ['veryfast', 'medium', 'slow'], 'veryfast')

    job = Job(spec.slug)
    source = _source(job, upload)
    target = job.path(f'{stem_of(upload.filename)}_compressed.mp4')
    duration = media_duration(source)

    args = ['-i', source, '-c:v', 'libx264', '-crf', crf, '-preset', preset,
            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart']
    if height:
        args += ['-vf', f'scale=-2:{height}']
    ffmpeg(*args, target, timeout=1800)
    job.cleanup(source)

    before, after = upload.content_length or 0, target.stat().st_size
    return result(job, filename=target.name,
                  message=f'Compressed to {human_bytes(after)} (CRF {crf}{", " + str(height) + "p" if height else ""}).',
                  facts=[['Length', human_time(duration)], ['After', human_bytes(after)], ['Preset', preset]])


@runner('video-to-gif')
def video_to_gif(spec):
    upload = get_file('file', allowed=MEDIA_EXTENSIONS)
    start = parse_timestamp(form_str('start'), 0.0)
    duration = form_int('duration', 4, 1, 15)
    fps = form_int('fps', 12, 5, 25)
    width = form_int('width', 480, 160, 800)

    job = Job(spec.slug)
    source = _source(job, upload)
    target = job.path(f'{stem_of(upload.filename)}.gif')
    # Two-pass palette: a colour table built from these frames looks far
    # better than the fixed 256-colour default.
    filters = (f'fps={fps},scale={width}:-2:flags=lanczos,'
               f'split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5')
    ffmpeg('-ss', start, '-t', duration, '-i', source, '-vf', filters, '-loop', '0', target, timeout=600)
    job.cleanup(source)
    return result(job, filename=target.name, message=f'{duration}s GIF at {fps} fps, {width}px wide.',
                  facts=[['Size', human_bytes(target.stat().st_size)], ['Frames', fps * duration]])


@runner('video-trim')
def video_trim(spec):
    upload = get_file('file', allowed=MEDIA_EXTENSIONS)
    start = parse_timestamp(form_str('start'), 0.0)
    end = parse_timestamp(form_str('end'))
    if end is None or end <= start:
        raise AppError('The end time must come after the start time.')

    job = Job(spec.slug)
    source = _source(job, upload)
    total = media_duration(source)
    if total and start >= total:
        raise AppError(f'The file is only {human_time(total)} long.')
    ext = extension_of(upload.filename)
    target = job.path(f'{stem_of(upload.filename)}_trimmed.{ext}')
    # -ss before -i seeks on keyframes; copying streams means no re-encode.
    ffmpeg('-ss', start, '-to', end, '-i', source, '-map', '0', '-c', 'copy',
           '-avoid_negative_ts', 'make_zero', target, timeout=300)
    job.cleanup(source)
    return result(job, filename=target.name,
                  message=f'Kept {human_time(start)} – {human_time(min(end, total or end))} without re-encoding.',
                  facts=[['New length', human_time(min(end, total or end) - start)],
                         ['Size', human_bytes(target.stat().st_size)]])


@runner('audio-extract')
def audio_extract(spec):
    upload = get_file('file', allowed=MEDIA_EXTENSIONS)
    fmt = form_choice('format', ['mp3', 'm4a', 'wav', 'flac'], 'mp3')
    bitrate = form_choice('bitrate', ['128k', '192k', '320k'], '192k')

    job = Job(spec.slug)
    source = _source(job, upload)
    info = ffprobe_json(source)
    if not any(s.get('codec_type') == 'audio' for s in info.get('streams', [])):
        raise AppError('That file has no audio track.')
    target = job.path(f'{stem_of(upload.filename)}.{fmt}')
    codec = {'mp3': ['-c:a', 'libmp3lame', '-b:a', bitrate],
             'm4a': ['-c:a', 'aac', '-b:a', bitrate],
             'wav': ['-c:a', 'pcm_s16le'],
             'flac': ['-c:a', 'flac']}[fmt]
    ffmpeg('-i', source, '-vn', *codec, target, timeout=600)
    duration = media_duration(target)
    job.cleanup(source)
    return result(job, filename=target.name, message=f'{fmt.upper()} extracted.',
                  facts=[['Length', human_time(duration)], ['Size', human_bytes(target.stat().st_size)]])


COPY_SAFE = {
    'mp4': {'h264', 'hevc', 'av1', 'aac', 'mp3', 'ac3'},
    'mov': {'h264', 'hevc', 'prores', 'aac', 'mp3', 'pcm_s16le'},
    'mkv': None,                 # Matroska takes anything
    'webm': {'vp8', 'vp9', 'av1', 'opus', 'vorbis'},
    'avi': {'mpeg4', 'h264', 'mp3', 'ac3', 'pcm_s16le'},
}
ENCODE = {
    'mp4': ['-c:v', 'libx264', '-crf', '23', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k'],
    'mov': ['-c:v', 'libx264', '-crf', '23', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k'],
    'mkv': ['-c:v', 'libx264', '-crf', '23', '-preset', 'veryfast', '-c:a', 'aac', '-b:a', '160k'],
    'webm': ['-c:v', 'libvpx-vp9', '-crf', '33', '-b:v', '0', '-row-mt', '1', '-c:a', 'libopus', '-b:a', '128k'],
    'avi': ['-c:v', 'libx264', '-crf', '23', '-preset', 'veryfast', '-c:a', 'mp3', '-b:a', '160k'],
}


@runner('video-convert')
def video_convert(spec):
    upload = get_file('file', allowed=MEDIA_EXTENSIONS)
    fmt = form_choice('format', list(ENCODE), 'mp4')

    job = Job(spec.slug)
    source = _source(job, upload)
    codecs = {s.get('codec_name') for s in ffprobe_json(source).get('streams', [])}
    allowed = COPY_SAFE[fmt]
    copy = allowed is None or codecs <= allowed
    target = job.path(f'{stem_of(upload.filename)}.{fmt}')

    args = ['-i', source, '-map', '0:v?', '-map', '0:a?']
    args += ['-c', 'copy'] if copy else ENCODE[fmt]
    if fmt in ('mp4', 'mov'):
        args += ['-movflags', '+faststart']
    ffmpeg(*args, target, timeout=1800)
    job.cleanup(source)
    return result(job, filename=target.name,
                  message=f'Converted to {fmt.upper()} ' + ('by copying the streams — no quality loss.' if copy else 'with re-encoding.'),
                  facts=[['Codecs', ', '.join(sorted(c for c in codecs if c))], ['Re-encoded', 'no' if copy else 'yes'],
                         ['Size', human_bytes(target.stat().st_size)]])


@runner('video-merge')
def video_merge(spec):
    files = uploads('files', allowed=MEDIA_EXTENSIONS, minimum=2)
    job = Job(spec.slug)
    sources = [job.save_upload(f, f'part_{i:03d}.{extension_of(f.filename)}') for i, f in enumerate(files)]

    signatures = set()
    for path in sources:
        streams = ffprobe_json(path).get('streams', [])
        video = next((s for s in streams if s.get('codec_type') == 'video'), {})
        audio = next((s for s in streams if s.get('codec_type') == 'audio'), {})
        signatures.add((video.get('codec_name'), video.get('width'), video.get('height'),
                        audio.get('codec_name'), audio.get('sample_rate')))
    uniform = len(signatures) == 1 and extension_of(files[0].filename) in ('mp4', 'mov', 'm4v')
    target = job.path(f'{stem_of(files[0].filename)}_merged.mp4')

    if uniform:
        # Same codecs and geometry: the concat demuxer joins without re-encoding.
        listing = job.path('list.txt')
        listing.write_text(''.join(f"file {shlex.quote(str(p))}\n" for p in sources))
        ffmpeg('-f', 'concat', '-safe', '0', '-i', listing, '-c', 'copy', '-movflags', '+faststart', target, timeout=600)
        job.cleanup(listing)
    else:
        # Mixed inputs: normalise every clip to 720p H.264 / AAC, then concatenate.
        inputs, chain = [], ''
        for i, path in enumerate(sources):
            inputs += ['-i', path]
            chain += (f'[{i}:v]scale=1280:720:force_original_aspect_ratio=decrease,'
                      f'pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}];'
                      f'[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}];')
        chain += ''.join(f'[v{i}][a{i}]' for i in range(len(sources))) + f'concat=n={len(sources)}:v=1:a=1[v][a]'
        ffmpeg(*inputs, '-filter_complex', chain, '-map', '[v]', '-map', '[a]',
               '-c:v', 'libx264', '-crf', '23', '-preset', 'veryfast', '-c:a', 'aac', '-b:a', '160k',
               '-movflags', '+faststart', target, timeout=1800)

    job.cleanup(*sources)
    return result(job, filename=target.name,
                  message=f'Joined {len(files)} clips ' + ('without re-encoding.' if uniform else '(normalised to 720p first).'),
                  facts=[['Clips', len(files)], ['Length', human_time(media_duration(target))],
                         ['Size', human_bytes(target.stat().st_size)]])


@runner('subtitle-burn')
def subtitle_burn(spec):
    upload = get_file('file', allowed=VIDEO_EXTENSIONS | {'m4v'})
    subtitles = get_file('subtitles', allowed={'srt', 'vtt', 'ass', 'ssa'})
    size = form_int('size', 24, 16, 48)

    job = Job(spec.slug)
    source = _source(job, upload)
    subs = job.save_upload(subtitles, f'subs.{extension_of(subtitles.filename)}')
    target = job.path(f'{stem_of(upload.filename)}_subtitled.mp4')

    # The subtitles filter takes its own escaping; the file has a plain name we control.
    style = f"FontSize={size},Outline=1,Shadow=0,MarginV=24"
    _burn(job, source, subs, style, target)
    job.cleanup(source, subs)
    return result(job, filename=target.name, message='Subtitles burned in.',
                  facts=[['Font size', size], ['Size', human_bytes(target.stat().st_size)]])


def _burn(job, source, subs, style, target):
    """Run ffmpeg from inside the job directory so the subtitle path needs no escaping."""
    import subprocess
    from app.core.toolkit import require
    require('ffmpeg')
    command = ['ffmpeg', '-v', 'error', '-y', '-i', source.name,
               '-vf', f"subtitles={subs.name}:force_style='{style}'",
               '-c:v', 'libx264', '-crf', '23', '-preset', 'veryfast', '-c:a', 'copy',
               '-movflags', '+faststart', target.name]
    try:
        completed = subprocess.run(command, cwd=job.dir, capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired:
        raise AppError('Burning subtitles took too long. Try a shorter clip.')
    if completed.returncode != 0:
        lines = [l for l in completed.stderr.splitlines() if l.strip()]
        raise AppError('ffmpeg failed: ' + (lines[-1][:200] if lines else 'unknown error'))


@runner('frame-extract')
def frame_extract(spec):
    upload = get_file('file', allowed=VIDEO_EXTENSIONS | {'m4v', 'mpg', 'mpeg', 'ts'})
    count = form_int('count', 12, 4, 36)
    columns = form_int('columns', 4, 2, 6)

    job = Job(spec.slug)
    source = _source(job, upload)
    duration = media_duration(source)
    if duration <= 0:
        raise AppError('Could not determine how long that video is.')

    frames = []
    for i in range(count):
        at = duration * (i + 0.5) / count
        path = job.path(f'frame_{i + 1:03d}_{human_time(at).replace(":", "-")}.jpg')
        ffmpeg('-ss', f'{at:.3f}', '-i', source, '-frames:v', '1', '-q:v', '3',
               '-vf', 'scale=640:-2', path, timeout=120)
        frames.append((path, at))

    thumbs = [Image.open(p).convert('RGB') for p, _ in frames]
    w, h = thumbs[0].size
    rows = math.ceil(len(thumbs) / columns)
    gap, label_h = 8, 22
    sheet = Image.new('RGB', (columns * (w + gap) + gap, rows * (h + label_h + gap) + gap), (24, 28, 36))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(sheet)
    for i, (thumb, (_, at)) in enumerate(zip(thumbs, frames)):
        x = gap + (i % columns) * (w + gap)
        y = gap + (i // columns) * (h + label_h + gap)
        sheet.paste(thumb, (x, y))
        draw.text((x + 4, y + h + 4), human_time(at), fill=(230, 230, 230))
    stem = stem_of(upload.filename)
    sheet_name = f'{stem}_contact_sheet.jpg'
    sheet.save(job.path(sheet_name), 'JPEG', quality=88)
    zip_name = f'{stem}_frames.zip'
    job.zip([p for p, _ in frames], zip_name)
    job.cleanup(source, *(p for p, _ in frames))
    return result(job, filename=sheet_name, extra_files=[zip_name],
                  message=f'{count} frames across {human_time(duration)}.',
                  facts=[['Frames', count], ['Grid', f'{columns} × {rows}']])


@runner('transcribe')
def transcribe(spec):
    upload = get_file('file', allowed=MEDIA_EXTENSIONS)
    model_name = form_choice('model', ['tiny', 'base', 'small'], 'base')
    language = form_str('language') or None

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise AppError('faster-whisper is not installed on the server.', 503)

    job = Job(spec.slug)
    source = _source(job, upload)
    audio = job.path('audio.wav')
    ffmpeg('-i', source, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', audio, timeout=600)

    from flask import current_app
    cache_dir = current_app.config['MODELS_DIR'] / 'whisper'
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        model = WhisperModel(model_name, device='cpu', compute_type='int8', download_root=str(cache_dir))
        segments, info = model.transcribe(str(audio), language=language, vad_filter=True)
        segments = list(segments)
    except Exception as exc:
        raise AppError(f'Transcription failed: {type(exc).__name__}: {str(exc)[:160]}')
    finally:
        job.cleanup(source, audio)

    def srt_time(seconds: float) -> str:
        ms = int(round(seconds * 1000))
        h, ms = divmod(ms, 3_600_000)
        m, ms = divmod(ms, 60_000)
        s, ms = divmod(ms, 1000)
        return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'

    lines, srt = [], []
    for i, seg in enumerate(segments, start=1):
        text = seg.text.strip()
        lines.append(f'[{human_time(seg.start)}] {text}')
        srt.append(f'{i}\n{srt_time(seg.start)} --> {srt_time(seg.end)}\n{text}\n')

    transcript = '\n'.join(lines) or '(no speech detected)'
    stem = stem_of(upload.filename)
    txt_name, srt_name = f'{stem}.txt', f'{stem}.srt'
    job.path(txt_name).write_text('\n'.join(s.text.strip() for s in segments))
    job.path(srt_name).write_text('\n'.join(srt))
    return result(job, filename=srt_name, extra_files=[txt_name], text=transcript,
                  message=f'{len(segments)} segments, language "{info.language}" ({info.language_probability:.0%} sure).',
                  facts=[['Model', model_name], ['Length', human_time(info.duration)]])
