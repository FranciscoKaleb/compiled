"""OCR: Nougat for document pages, TrOCR for single printed lines."""
import torch

from app.blueprints.models._base import predictor
from app.core import loader
from app.core.errors import AppError
from app.core.imaging import to_b64_png
from app.core.responses import ok
from app.core.uploads import read_image


@predictor('ocr', 'nougat')
def nougat(spec):
    image = read_image()
    bundle = loader.get(spec.slug)

    try:
        inputs = bundle.processor.image_processor(
            image,
            return_tensors='pt',
            do_crop_margin=True,
            do_align_long_axis=False,
            do_pad=True,
        )
        with torch.inference_mode():
            generated = bundle.model.generate(
                inputs.pixel_values, max_new_tokens=1024, do_sample=False
            )
        text = bundle.processor.batch_decode(generated, skip_special_tokens=True)[0]
    except Exception as exc:
        # Nougat is brittle on non-document images; say so rather than
        # returning the exception text as if it were the recognised content,
        # which is what the old page did.
        raise AppError(
            'Nougat could not read that image. It expects a page from an '
            f'academic document. ({type(exc).__name__})'
        ) from exc

    return ok(text=text, image_data=to_b64_png(image))


@predictor('ocr', 'trocr')
def trocr(spec):
    image = read_image()
    bundle = loader.get(spec.slug)

    pixel_values = bundle.processor(images=image, return_tensors='pt').pixel_values
    with torch.no_grad():
        generated = bundle.model.generate(pixel_values, max_new_tokens=128)

    text = bundle.processor.batch_decode(generated, skip_special_tokens=True)[0]
    return ok(text=text, image_data=to_b64_png(image))
