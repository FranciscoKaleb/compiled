"""Image classification: top-k, single-label, multi-label and zero-shot."""
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

from app.blueprints.models._base import predictor
from app.core import loader
from app.core.errors import AppError
from app.core.responses import ok
from app.core.uploads import form_float, form_text, read_image


@predictor('classify', 'topk')
def topk(spec):
    """The pattern behind ViT base/large, BEiT and the dog-breed model."""
    image = read_image()
    bundle = loader.get(spec.slug)

    inputs = bundle.processor(images=image, return_tensors='pt')
    with torch.no_grad():
        outputs = bundle.model(**inputs)

    probabilities = F.softmax(outputs.logits, dim=-1)[0]
    k = min(spec.extra.get('k', 5), probabilities.numel())
    scores, indices = torch.topk(probabilities, k=k)

    id2label = bundle.model.config.id2label
    predictions = [
        [id2label[int(i)], float(p) * 100] for i, p in zip(indices, scores)
    ]
    return ok(predictions=predictions)


@predictor('classify', 'single_label')
def single_label(spec):
    image = read_image()
    bundle = loader.get(spec.slug)

    inputs = bundle.processor(images=image, return_tensors='pt')
    with torch.no_grad():
        outputs = bundle.model(**inputs)

    probabilities = F.softmax(outputs.logits, dim=-1)[0]
    index = int(probabilities.argmax())
    return ok(
        label=bundle.model.config.id2label[index],
        confidence=float(probabilities[index]) * 100,
    )


def _pad_square(image: Image.Image, size: int = 448) -> np.ndarray:
    """wd-tagger wants a square, white-padded, BGR float32 array in [0, 255]."""
    largest = max(image.size)
    padded = Image.new('RGB', (largest, largest), (255, 255, 255))
    padded.paste(image, ((largest - image.size[0]) // 2, (largest - image.size[1]) // 2))
    padded = padded.resize((size, size), Image.BICUBIC)

    array = np.asarray(padded, dtype=np.float32)[:, :, ::-1]  # RGB -> BGR
    return np.expand_dims(array, axis=0)


@predictor('classify', 'tagger')
def tagger(spec):
    image = read_image()
    threshold = form_float('threshold', 0.35, low=0.05, high=0.95)

    bundle = loader.get(spec.slug)
    session, tags = bundle.model, bundle.extra

    input_name = session.get_inputs()[0].name
    probabilities = session.run(None, {input_name: _pad_square(image)})[0][0]

    ratings, characters, general = [], [], []
    for tag, probability in zip(tags, probabilities):
        score = float(probability)
        # Category 9 is the rating group, always reported regardless of score.
        if score < threshold and tag['category'] != 9:
            continue
        entry = {'name': tag['name'], 'score': score}
        if tag['category'] == 9:
            ratings.append(entry)
        elif tag['category'] == 4:
            characters.append(entry)
        else:
            general.append(entry)

    for group in (ratings, characters, general):
        group.sort(key=lambda item: -item['score'])

    return ok(groups=[
        {'title': 'Rating', 'items': ratings},
        {'title': 'Characters', 'items': characters[:20]},
        {'title': 'Tags', 'items': general[:30]},
    ])


@predictor('classify', 'zero_shot')
def zero_shot(spec):
    image = read_image()
    labels = [part.strip() for part in form_text('labels').split(',') if part.strip()]
    if len(labels) < 2:
        raise AppError('Give at least two comma-separated labels to choose between.')

    bundle = loader.get(spec.slug)
    prompts = [f'a photo of {label}' for label in labels]

    inputs = bundle.processor(text=prompts, images=image, return_tensors='pt', padding=True)
    with torch.no_grad():
        outputs = bundle.model(**inputs)

    probabilities = outputs.logits_per_image.softmax(dim=-1)[0]
    ranked = sorted(zip(labels, probabilities.tolist()), key=lambda pair: -pair[1])
    return ok(predictions=[[label, score * 100] for label, score in ranked])
