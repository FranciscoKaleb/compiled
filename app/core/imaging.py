"""Image helpers shared by every model handler.

The base64 encode block below was copy-pasted into eleven route files; the box
drawing into five; the palette blending into three.
"""
import base64
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw

BOX_COLOR = (220, 38, 38)      # red, matches --color-danger in the CSS
BOX_WIDTH = 4


def to_b64_png(image: Image.Image) -> str:
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()


def to_b64_jpeg(frame, quality: int = 85) -> str:
    """Encode an OpenCV BGR frame. Imported lazily so PIL-only pages skip cv2."""
    import cv2

    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(buffer).decode()


def from_b64_frame(b64: str):
    """Decode a base64 JPEG (from a browser canvas) into an OpenCV frame."""
    import cv2

    raw = base64.b64decode(b64)
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)


def draw_boxes(image: Image.Image, boxes, labels=None, color=BOX_COLOR,
               width: int = BOX_WIDTH) -> Image.Image:
    """Draw labelled rectangles onto a copy of `image`."""
    canvas = image.copy()
    draw = ImageDraw.Draw(canvas)
    labels = labels or [None] * len(boxes)

    for box, label in zip(boxes, labels):
        box = [round(float(v), 2) for v in box]
        draw.rectangle(box, outline=color, width=width)
        if label:
            # Keep the caption on-canvas when the box starts at the top edge.
            y = box[1] - 14 if box[1] > 16 else box[1] + 2
            draw.text((box[0] + 2, y), str(label), fill=color)
    return canvas


def palette(size: int, seed: int) -> np.ndarray:
    """A stable, readable colour table — same seeds as the original pages."""
    rng = np.random.default_rng(seed)
    return rng.integers(60, 230, size=(size, 3), dtype=np.uint8)


def blend_mask(image: Image.Image, colored: np.ndarray, alpha: float = 0.55) -> Image.Image:
    """Blend an (H, W, 3) colour array over the original image."""
    overlay = Image.fromarray(colored)
    return Image.blend(image.resize(overlay.size), overlay, alpha)
