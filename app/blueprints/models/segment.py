"""Segmentation: semantic, instance and panoptic."""
import numpy as np
import torch
import torch.nn.functional as F

from app.blueprints.models._base import predictor
from app.core import loader
from app.core.imaging import blend_mask, palette, to_b64_png
from app.core.responses import ok
from app.core.uploads import form_float, read_image

# Stable palettes — the same seeds the original pages used, so colours do not
# shift for anyone used to them.
_SEMANTIC = palette(150, seed=42)
_INSTANCE = palette(300, seed=7)
_PANOPTIC = palette(300, seed=13)


@predictor('segment', 'semantic')
def semantic(spec):
    image = read_image()
    bundle = loader.get(spec.slug)

    inputs = bundle.processor(images=image, return_tensors='pt')
    with torch.no_grad():
        outputs = bundle.model(**inputs)

    # Logits come back at a reduced resolution; upsample before taking argmax.
    logits = F.interpolate(
        outputs.logits, size=image.size[::-1], mode='bilinear', align_corners=False
    )
    label_map = logits.argmax(dim=1)[0].cpu().numpy().astype(np.uint8)

    id2label = bundle.model.config.id2label
    segments = [
        {'label': id2label.get(int(i), str(i)), 'detail': f'class {int(i)}'}
        for i in np.unique(label_map)
    ]

    result = blend_mask(image, _SEMANTIC[label_map], alpha=0.55)
    return ok(
        image_data=to_b64_png(result),
        segments=segments,
        summary=f'{len(segments)} class(es) present',
    )


def _overlay(image, segmentation, segments_info, id2label, colors, describe):
    """Colour each segment and blend it over the original."""
    seg = segmentation.cpu().numpy()
    canvas = np.zeros((*seg.shape, 3), dtype=np.uint8)
    segments = []

    for index, info in enumerate(segments_info):
        canvas[seg == info['id']] = colors[index % len(colors)]
        label = id2label.get(info['label_id'], str(info['label_id']))
        segments.append(describe(index, label, info))

    return blend_mask(image, canvas, alpha=0.6), segments


@predictor('segment', 'instance')
def instance(spec):
    image = read_image()
    threshold = form_float('threshold', 0.5, low=0.05, high=0.95)
    bundle = loader.get(spec.slug)

    inputs = bundle.processor(images=image, return_tensors='pt')
    with torch.no_grad():
        outputs = bundle.model(**inputs)

    results = bundle.processor.post_process_instance_segmentation(
        outputs, target_sizes=[image.size[::-1]], threshold=threshold
    )[0]

    result, segments = _overlay(
        image, results['segmentation'], results['segments_info'],
        bundle.model.config.id2label, _INSTANCE,
        lambda i, label, info: {
            'label': label,
            'detail': f'instance {i + 1} · {round(info.get("score", 1.0), 2)}',
        },
    )
    return ok(
        image_data=to_b64_png(result),
        segments=segments,
        summary=f'{len(segments)} instance(s) above {threshold:.2f}',
    )


@predictor('segment', 'panoptic')
def panoptic(spec):
    image = read_image()
    bundle = loader.get(spec.slug)

    inputs = bundle.processor(images=image, return_tensors='pt')
    with torch.no_grad():
        outputs = bundle.model(**inputs)

    results = bundle.processor.post_process_panoptic_segmentation(
        outputs, target_sizes=[image.size[::-1]]
    )[0]

    result, segments = _overlay(
        image, results['segmentation'], results['segments_info'],
        bundle.model.config.id2label, _PANOPTIC,
        lambda i, label, info: {
            'label': label,
            # Fused segments are uncountable "stuff"; the rest are "things".
            'detail': ('stuff' if info.get('was_fused', False) else 'thing')
                      + f' · {round(info.get("score", 1.0), 2)}',
        },
    )
    return ok(
        image_data=to_b64_png(result),
        segments=segments,
        summary=f'{len(segments)} segment(s)',
    )
