"""Every tool, declared once. Imported by app.registry.

Each entry drives its page (generic template unless `template` is set), its
picker and extra controls, and how the result is rendered. The handler is
`@runner('<slug>')` in app/blueprints/tools/<category>.py.
"""
from app.registry import (
    ToolSpec, checkbox_field, file_field, range_field, select_field,
    text_field, textarea_field,
)

TOOL_CATEGORIES = [
    ('pdf', 'PDF', 'Merge, split, compress, protect and convert PDFs'),
    ('image', 'Images', 'Convert, resize, clean and generate images'),
    ('video', 'Video & audio', 'Compress, cut, convert and transcribe media'),
    ('privacy', 'Privacy', 'Remove what a file secretly says about you'),
    ('documents', 'Documents & text', 'Codes, conversions and text utilities'),
    ('data', 'Data & files', 'Spreadsheets, archives and bulk file jobs'),
]

IMAGES = 'image/*'
PDF = 'application/pdf'
VIDEO = 'video/*'
MEDIA = 'video/*,audio/*'

IMAGE_FORMATS = [('jpg', 'JPEG'), ('png', 'PNG'), ('webp', 'WebP'), ('bmp', 'BMP'), ('tiff', 'TIFF')]


TOOLS: list[ToolSpec] = [
    # ======================================================================
    # PDF
    # ======================================================================
    ToolSpec(
        slug='pdf-combiner', category='pdf', title='Merge PDFs',
        subtitle='Several PDFs into one', view='pdf_combiner',
        blurb='Upload PDFs in the order you want them and get a single merged file.',
        input='files', accept=PDF, hint='Two or more PDFs, merged in the order you pick them',
        button='Merge PDFs', legacy=('/tools/tool1',),
    ),
    ToolSpec(
        slug='pdf-split', category='pdf', title='Split PDF',
        subtitle='Extract pages or ranges', view='pdf_split',
        blurb='Pull selected pages out of a PDF into a new one, or burst it into one file per page.',
        accept=PDF, hint='One PDF', button='Split',
        fields=(text_field('pages', 'Pages to extract', '1-3, 5, 8-10',
                           'Leave empty to split every page into its own file (zipped).',
                           required=False),),
    ),
    ToolSpec(
        slug='pdf-pages', category='pdf', title='Rotate, reorder, delete pages',
        subtitle='Rearrange a PDF', view='pdf_pages',
        blurb='Give the new page order; anything you leave out is deleted. Add r90, r180 or r270 to rotate a page.',
        accept=PDF, hint='One PDF', button='Rebuild PDF',
        fields=(text_field('order', 'New page order', '3, 1r90, 2, 5-8',
                           'Page numbers in the order you want them. "1r90" rotates page 1 by 90°. Ranges like 5-8 work.'),),
    ),
    ToolSpec(
        slug='pdf-compress', category='pdf', title='Compress PDF',
        subtitle='Shrink the file size', view='pdf_compress',
        blurb='Re-encodes the images inside a PDF at a lower quality and compresses the page streams. Text stays sharp.',
        accept=PDF, hint='One PDF', button='Compress',
        fields=(range_field('quality', 'Image quality', 20, 95, 5, 60,
                            'Lower is smaller. 60 is usually indistinguishable on screen.'),
                range_field('max_dim', 'Largest image side (px)', 600, 3000, 100, 1600,
                            'Images larger than this are scaled down.')),
    ),
    ToolSpec(
        slug='pdf-to-images', category='pdf', title='PDF to images',
        subtitle='One image per page', view='pdf_to_images',
        blurb='Renders every page of a PDF to PNG or JPEG and zips them.',
        accept=PDF, hint='One PDF', button='Render pages', needs=('pdftoppm',),
        fields=(select_field('format', 'Image format', [('png', 'PNG'), ('jpg', 'JPEG')]),
                range_field('dpi', 'Resolution (dpi)', 72, 300, 6, 150)),
    ),
    ToolSpec(
        slug='images-to-pdf', category='pdf', title='Images to PDF',
        subtitle='Photos or scans into one PDF', view='images_to_pdf',
        blurb='Combines images into a single PDF, one per page, in the order you pick them.',
        input='files', accept=IMAGES, hint='One or more images', button='Make PDF',
        fields=(select_field('page', 'Page size', [('fit', 'Fit each image'), ('a4', 'A4'), ('letter', 'US Letter')]),),
    ),
    ToolSpec(
        slug='pdf-password', category='pdf', title='PDF password',
        subtitle='Add or remove protection', view='pdf_password',
        blurb='Encrypt a PDF with a password, or remove the password from one you own.',
        accept=PDF, hint='One PDF', button='Apply',
        fields=(select_field('mode', 'Action', [('add', 'Add a password'), ('remove', 'Remove the password')]),
                text_field('password', 'Password', help='The password to set, or the current one to remove.')),
    ),
    ToolSpec(
        slug='pdf-watermark', category='pdf', title='Watermark PDF',
        subtitle='Stamp text on every page', view='pdf_watermark',
        blurb='Adds diagonal, semi-transparent text across every page — "DRAFT", "CONFIDENTIAL", your name.',
        accept=PDF, hint='One PDF', button='Add watermark',
        fields=(text_field('text', 'Watermark text', 'CONFIDENTIAL'),
                range_field('opacity', 'Opacity', 0.05, 0.6, 0.05, 0.2),
                range_field('size', 'Font size', 24, 120, 4, 60)),
    ),

    # ======================================================================
    # Images
    # ======================================================================
    ToolSpec(
        slug='bg-remover', category='image', title='Background remover',
        subtitle='Cut the subject out of a photo', view='bg_remover',
        blurb='Removes the background with rembg and returns a transparent PNG.',
        accept=IMAGES, hint='PNG, JPG, WebP or BMP', render='image',
        button='Remove the background', legacy=('/tools/tool2',),
    ),
    ToolSpec(
        slug='reduce-quality', category='image', title='Image compressor',
        subtitle='Shrink an image for sharing', view='reduce_quality',
        blurb='Scales an image down and re-encodes it as JPEG at the quality you pick.',
        accept=IMAGES, hint='PNG, JPG, WebP or BMP', render='image', button='Compress',
        fields=(range_field('percentage', 'Scale and JPEG quality', 5, 100, 5, 60,
                            'One control does both: 60 = 60% of the size at JPEG quality 60.'),),
        legacy=('/tools/tool3',),
    ),
    ToolSpec(
        slug='bulk-convert', category='image', title='Bulk resize & convert',
        subtitle='Many images, one format, zipped', view='bulk_convert',
        blurb='Drop a pile of images, choose a format and a maximum size, get a zip. No three-file limit.',
        input='files', accept=IMAGES, hint='Any number of images', button='Convert all',
        fields=(select_field('format', 'Output format', IMAGE_FORMATS, 'webp'),
                range_field('max_dim', 'Longest side (px)', 200, 4000, 100, 1920,
                            'Images are scaled down to fit; smaller ones are left alone.'),
                range_field('quality', 'Quality (JPEG / WebP)', 40, 100, 5, 85)),
    ),
    ToolSpec(
        slug='heic-to-jpg', category='image', title='HEIC to JPG',
        subtitle='iPhone photos to a format everything opens', view='heic_to_jpg',
        blurb='Converts HEIC/HEIF photos to JPEG (or PNG). Several at once, zipped.',
        input='files', accept='.heic,.heif,image/heic,image/heif', hint='One or more HEIC files',
        button='Convert',
        fields=(select_field('format', 'Output format', [('jpg', 'JPEG'), ('png', 'PNG')]),
                range_field('quality', 'JPEG quality', 60, 100, 5, 92)),
    ),
    ToolSpec(
        slug='passport-photo', category='image', title='Passport / ID photo',
        subtitle='Regulation-size headshot', view='passport_photo',
        blurb='Finds the face, crops to the official proportions for the chosen standard, and puts it on a plain white background.',
        accept=IMAGES, hint='A front-facing photo with some room around the head',
        render='image', button='Make ID photo',
        fields=(select_field('standard', 'Standard', [
            ('35x45', '35 × 45 mm (EU, UK, PH, most countries)'),
            ('2x2', '2 × 2 in (US passport)'),
            ('33x48', '33 × 48 mm (China)'),
            ('50x70', '50 × 70 mm (Canada)'),
        ]),
        checkbox_field('white_bg', 'Replace the background with white', True)),
    ),
    ToolSpec(
        slug='face-blur', category='privacy', title='Blur faces',
        subtitle='Anonymise people in a photo', view='face_blur',
        blurb='Detects every face and pixelates or blurs it before you post the picture.',
        accept=IMAGES, hint='A photo with people in it', render='image', button='Blur faces',
        fields=(select_field('style', 'Style', [('pixelate', 'Pixelate'), ('blur', 'Gaussian blur'), ('box', 'Black box')]),
                range_field('strength', 'Strength', 1, 10, 1, 6)),
    ),
    ToolSpec(
        slug='palette', category='image', title='Colour palette',
        subtitle='Dominant colours of an image', view='palette',
        blurb='Extracts the main colours with k-means and gives you hex codes to copy.',
        accept=IMAGES, hint='Any image', render='custom', button='Extract palette',
        fields=(range_field('count', 'Number of colours', 3, 12, 1, 6),),
    ),
    ToolSpec(
        slug='favicon', category='image', title='Favicon & app icons',
        subtitle='Every size from one image', view='favicon',
        blurb='One square PNG in; favicon.ico plus 16 to 512 px PNGs and a site.webmanifest out, zipped.',
        accept=IMAGES, hint='A square image, ideally 512 px or larger', button='Generate icons',
    ),
    ToolSpec(
        slug='ascii-art', category='image', title='ASCII art',
        subtitle='Turn a picture into text', view='ascii_art',
        blurb='Converts an image into a block of characters you can paste anywhere.',
        accept=IMAGES, hint='Any image; high contrast works best', render='text', button='Convert',
        fields=(range_field('width', 'Characters wide', 40, 200, 10, 100),
                checkbox_field('invert', 'Invert (for light-on-dark terminals)', False)),
    ),
    ToolSpec(
        slug='image-watermark', category='image', title='Watermark image',
        subtitle='Text stamp, single or tiled', view='image_watermark',
        blurb='Adds semi-transparent text to a photo — once in a corner, or tiled across the whole thing.',
        accept=IMAGES, hint='Any image', render='image', button='Add watermark',
        fields=(text_field('text', 'Watermark text', '© your name'),
                select_field('placement', 'Placement', [('corner', 'Bottom-right corner'), ('center', 'Centre'), ('tile', 'Tiled')]),
                range_field('opacity', 'Opacity', 0.1, 1.0, 0.05, 0.4),
                range_field('size', 'Text size (% of width)', 2, 20, 1, 5)),
    ),

    # ======================================================================
    # Video & audio
    # ======================================================================
    ToolSpec(
        slug='video-compress', category='video', title='Compress video',
        subtitle='Smaller file, same length', view='video_compress',
        blurb='Re-encodes with H.264 at a quality you choose and optionally scales the picture down. The most-paywalled video tool on the internet.',
        accept=VIDEO, hint='MP4, MOV, MKV, WebM or AVI', render='video', button='Compress', needs=('ffmpeg',),
        fields=(range_field('crf', 'Quality (CRF)', 18, 40, 1, 28,
                            'Lower = better quality and bigger. 23 is near-lossless, 28 is a good balance, 32+ is small.'),
                select_field('height', 'Resolution', [('0', 'Keep'), ('1080', '1080p'), ('720', '720p'), ('480', '480p'), ('360', '360p')]),
                select_field('preset', 'Speed', [('veryfast', 'Fast'), ('medium', 'Balanced'), ('slow', 'Smallest file (slow)')])),
    ),
    ToolSpec(
        slug='video-to-gif', category='video', title='Video to GIF',
        subtitle='With an optimised palette', view='video_to_gif',
        blurb='Cuts a clip out of a video and turns it into a GIF with a per-clip colour palette, which looks far better than the default.',
        accept=VIDEO, hint='Any video', render='image', button='Make GIF', needs=('ffmpeg',),
        fields=(text_field('start', 'Start at', '0:00', help='mm:ss or seconds', required=False),
                range_field('duration', 'Length (seconds)', 1, 15, 1, 4),
                range_field('fps', 'Frames per second', 5, 25, 1, 12),
                range_field('width', 'Width (px)', 160, 800, 40, 480)),
    ),
    ToolSpec(
        slug='video-trim', category='video', title='Trim video',
        subtitle='Cut without re-encoding', view='video_trim',
        blurb='Keeps only the part between two timestamps. Streams are copied, so it finishes in seconds with no quality loss.',
        accept=MEDIA, hint='Any video or audio file', render='video', button='Trim', needs=('ffmpeg',),
        fields=(text_field('start', 'Start', '0:30', help='mm:ss or h:mm:ss'),
                text_field('end', 'End', '1:45', help='mm:ss or h:mm:ss')),
    ),
    ToolSpec(
        slug='audio-extract', category='video', title='Extract audio',
        subtitle='Video to MP3, AAC, WAV or FLAC', view='audio_extract',
        blurb='Pulls the sound track out of a video.',
        accept=VIDEO, hint='Any video', button='Extract audio', needs=('ffmpeg',),
        fields=(select_field('format', 'Format', [('mp3', 'MP3'), ('m4a', 'AAC (m4a)'), ('wav', 'WAV'), ('flac', 'FLAC')]),
                select_field('bitrate', 'Bitrate (lossy formats)', [('128k', '128 kbps'), ('192k', '192 kbps'), ('320k', '320 kbps')], '192k')),
    ),
    ToolSpec(
        slug='video-convert', category='video', title='Convert video',
        subtitle='MKV, MOV, AVI, WebM → MP4 and back', view='video_convert',
        blurb='Changes the container and, when the codecs allow it, copies the streams straight across so nothing is re-encoded.',
        accept=VIDEO, hint='Any video', render='video', button='Convert', needs=('ffmpeg',),
        fields=(select_field('format', 'Output format', [('mp4', 'MP4'), ('mkv', 'MKV'), ('webm', 'WebM'), ('mov', 'MOV'), ('avi', 'AVI')]),),
    ),
    ToolSpec(
        slug='video-merge', category='video', title='Merge videos',
        subtitle='Several clips into one', view='video_merge',
        blurb='Joins clips end to end. Clips with matching codecs are concatenated without re-encoding; mixed ones are normalised to 720p H.264 first.',
        input='files', accept=VIDEO, hint='Two or more clips, in order', render='video', button='Merge', needs=('ffmpeg',),
    ),
    ToolSpec(
        slug='subtitle-burn', category='video', title='Burn in subtitles',
        subtitle='Hardcode an SRT into the picture', view='subtitle_burn',
        blurb='Renders a subtitle file permanently into the video so it shows everywhere, including players with no subtitle support.',
        accept=VIDEO, hint='The video', render='video', button='Burn subtitles', needs=('ffmpeg',),
        fields=(file_field('subtitles', 'Subtitle file', '.srt,.vtt,.ass', 'SRT, VTT or ASS'),
                range_field('size', 'Font size', 16, 48, 2, 24)),
    ),
    ToolSpec(
        slug='frame-extract', category='video', title='Frames & contact sheet',
        subtitle='Thumbnails from a video', view='frame_extract',
        blurb='Grabs evenly spaced frames and tiles them into one contact-sheet image, plus the individual frames zipped.',
        accept=VIDEO, hint='Any video', render='image', button='Extract frames', needs=('ffmpeg',),
        fields=(range_field('count', 'Number of frames', 4, 36, 2, 12),
                range_field('columns', 'Columns in the sheet', 2, 6, 1, 4)),
    ),
    ToolSpec(
        slug='transcribe', category='video', title='Speech to text',
        subtitle='Transcribe audio or video', view='transcribe',
        blurb='Runs Whisper locally and returns the transcript with timestamps, plus an SRT you can download. Nothing leaves this machine.',
        accept=MEDIA, hint='Audio or video, any language', render='text', button='Transcribe', needs=('ffmpeg',),
        fields=(select_field('model', 'Model', [('tiny', 'Tiny (fastest, rough)'), ('base', 'Base (good balance)'), ('small', 'Small (better, slower)')], 'base'),
                text_field('language', 'Language code', 'en', 'Leave empty to auto-detect.', required=False)),
    ),

    # ======================================================================
    # Privacy (the metadata tools keep their own templates)
    # ======================================================================
    ToolSpec(
        slug='metadata-remover', category='privacy', title='Photo metadata remover',
        subtitle='Strip EXIF, GPS and hidden tags', view='metadata_remover',
        blurb='Shows every piece of metadata embedded in a photo — including the GPS coordinates it was taken at — then gives you back a clean copy with all of it removed.',
        template='tools/metadata-remover.html',
    ),
    ToolSpec(
        slug='video-metadata-remover', category='privacy', title='Video metadata remover',
        subtitle='Strip tags, location and device info', view='video_metadata_remover',
        blurb='Lists every tag ffprobe can find in a video — where and when it was recorded, on which device — then rewrites it with all of them removed, without re-encoding.',
        template='tools/video-metadata-remover.html', needs=('ffmpeg', 'ffprobe'),
    ),
    ToolSpec(
        slug='pdf-metadata-remover', category='privacy', title='PDF metadata remover',
        subtitle='Author, creator, dates', view='pdf_metadata',
        blurb='Shows the document info a PDF carries — author, the software that made it, creation dates — and writes a copy without it.',
        accept=PDF, hint='One PDF', render='table', button='Inspect and strip',
    ),

    # ======================================================================
    # Documents & text
    # ======================================================================
    ToolSpec(
        slug='qr-generator', category='documents', title='QR code generator',
        subtitle='Any text or link', view='qr_generate',
        blurb='Makes a QR code as a PNG. Optionally drops a small logo in the centre — the thing generators charge for.',
        input='none', render='image', button='Generate',
        fields=(textarea_field('text', 'Content', 'https://example.com', rows=3),
                select_field('size', 'Size', [('256', '256 px'), ('512', '512 px'), ('1024', '1024 px')], '512'),
                text_field('fg', 'Colour', '#000000', required=False),
                file_field('logo', 'Logo (optional)', IMAGES, 'A small square image placed in the centre', required=False)),
    ),
    ToolSpec(
        slug='qr-reader', category='documents', title='QR code reader',
        subtitle='Decode a QR from a photo', view='qr_read',
        blurb='Finds and decodes every QR code in an image.',
        accept=IMAGES, hint='A photo or screenshot containing a QR code', render='text', button='Decode',
    ),
    ToolSpec(
        slug='barcode', category='documents', title='Barcode generator',
        subtitle='EAN, UPC, Code 128 and more', view='barcode_generate',
        blurb='Generates a printable barcode image from a number or text.',
        input='none', render='image', button='Generate',
        fields=(text_field('data', 'Data', '4006381333931'),
                select_field('kind', 'Type', [('code128', 'Code 128 (any text)'), ('ean13', 'EAN-13 (12–13 digits)'),
                                              ('ean8', 'EAN-8 (7–8 digits)'), ('upca', 'UPC-A (11–12 digits)'),
                                              ('code39', 'Code 39'), ('isbn13', 'ISBN-13')])),
    ),
    ToolSpec(
        slug='docx-to-pdf', category='documents', title='Word to PDF',
        subtitle='DOCX, ODT, PPTX, XLSX → PDF', view='office_to_pdf',
        blurb='Converts office documents to PDF with LibreOffice, headless, on this machine.',
        accept='.docx,.doc,.odt,.rtf,.pptx,.ppt,.odp,.xlsx,.xls,.ods', hint='A Word, PowerPoint, Excel or OpenDocument file',
        button='Convert to PDF', needs=('soffice',),
    ),
    ToolSpec(
        slug='text-diff', category='documents', title='Text diff',
        subtitle='Compare two blocks of text', view='text_diff',
        blurb='Shows exactly what changed between two versions, line by line.',
        input='none', render='custom', button='Compare',
        fields=(textarea_field('left', 'Original', rows=8), textarea_field('right', 'Changed', rows=8)),
    ),
    ToolSpec(
        slug='formatter', category='documents', title='JSON / YAML formatter',
        subtitle='Pretty-print, minify, convert', view='formatter',
        blurb='Validates and reformats JSON or YAML, and converts between the two.',
        input='none', render='text', button='Format',
        fields=(textarea_field('text', 'Input', '{"a": 1}', rows=10),
                select_field('output', 'Output as', [('json', 'JSON, indented'), ('json-min', 'JSON, minified'), ('yaml', 'YAML')])),
    ),
    ToolSpec(
        slug='hash', category='documents', title='Checksums',
        subtitle='MD5, SHA-1, SHA-256, SHA-512', view='hash_file',
        blurb='Computes the checksums of a file so you can verify a download or compare two copies.',
        accept='*/*', hint='Any file', render='table', button='Compute',
    ),
    ToolSpec(
        slug='regex', category='documents', title='Regex tester',
        subtitle='Try a pattern against text', view='regex_test',
        blurb='Lists every match and its groups, using Python regular expressions.',
        input='none', render='custom', button='Test',
        fields=(text_field('pattern', 'Pattern', r'(\w+)@(\w+)\.com'),
                textarea_field('text', 'Test text', 'mail me at ana@example.com or bo@test.com', rows=6),
                checkbox_field('ignorecase', 'Ignore case', False),
                checkbox_field('multiline', 'Multiline (^ and $ per line)', True)),
    ),

    # ======================================================================
    # Data & files
    # ======================================================================
    ToolSpec(
        slug='table-convert', category='data', title='CSV ↔ Excel ↔ JSON',
        subtitle='Convert tabular data', view='table_convert',
        blurb='Reads a CSV, Excel sheet or JSON array and writes it back out in another of those formats.',
        accept='.csv,.tsv,.xlsx,.xls,.json', hint='CSV, TSV, XLSX or a JSON array of objects', button='Convert',
        fields=(select_field('format', 'Output format', [('xlsx', 'Excel (.xlsx)'), ('csv', 'CSV'), ('json', 'JSON')]),),
    ),
    ToolSpec(
        slug='bulk-rename', category='data', title='Bulk rename',
        subtitle='Rename many files with a pattern', view='bulk_rename',
        blurb='Drop files, give a pattern like "holiday_{n:03}{ext}", and get them back renamed in a zip.',
        input='files', accept='*/*', hint='Any files', button='Rename all',
        fields=(text_field('pattern', 'New name pattern', 'photo_{n:03}{ext}',
                           '{n} counter · {name} original name · {ext} extension · {date} today'),
                range_field('start', 'Counter starts at', 0, 100, 1, 1)),
    ),
    ToolSpec(
        slug='zip', category='data', title='Zip files',
        subtitle='Bundle files into an archive', view='zip_files',
        blurb='Drop any files and get one zip back.',
        input='files', accept='*/*', hint='Any files', button='Zip',
    ),
    ToolSpec(
        slug='unzip', category='data', title='Unzip',
        subtitle='List and extract an archive', view='unzip',
        blurb='Lists the contents of a zip and lets you download each file, or everything re-zipped flat.',
        accept='.zip', hint='A zip archive', render='table', button='Open archive',
    ),
    ToolSpec(
        slug='photo-sort', category='data', title='Sort photos by date',
        subtitle='Folders from EXIF dates', view='photo_sort',
        blurb='Takes a dump of photos and returns them zipped into year/month folders based on when they were taken.',
        input='files', accept=IMAGES, hint='Any number of photos', button='Sort',
        fields=(select_field('scheme', 'Folder scheme', [('ym', 'YYYY/MM'), ('ymd', 'YYYY/MM/DD'), ('y', 'YYYY')]),),
    ),
]
