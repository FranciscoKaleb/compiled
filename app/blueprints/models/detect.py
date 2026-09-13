"""Object detection: DETR, YOLOS, RT-DETR and Grounding DINO."""
import torch

from app.blueprints.models._base import predictor
from app.core import loader
from app.core.errors import AppError
from app.core.imaging import draw_boxes, to_b64_png
from app.core.responses import ok
from app.core.uploads import form_float, form_text, read_image


def _run_detector(spec, image, threshold):
    """Shared inference + post-processing for the three DETR-family models."""
    bundle = loader.get(spec.slug)

    inputs = bundle.processor(images=image, return_tensors='pt')
    with torch.no_grad():
        outputs = bundle.model(**inputs)

    target_sizes = torch.tensor([image.size[::-1]])
    results = bundle.processor.post_process_object_detection(
        outputs, target_sizes=target_sizes, threshold=threshold
    )[0]
    return bundle, results


@predictor('detect', 'detect')
def detect(spec):
    image = read_image()
    threshold = form_float('threshold', 0.5, low=0.05, high=0.95)
    bundle, results = _run_detector(spec, image, threshold)

    id2label = bundle.model.config.id2label
    boxes, captions, detections = [], [], []
    for score, label, box in zip(results['scores'], results['labels'], results['boxes']):
        name = id2label[int(label)]
        confidence = float(score)
        boxes.append(box.tolist())
        captions.append(f'{name} {confidence:.2f}')
        detections.append({'label': name, 'score': confidence})

    annotated = draw_boxes(image, boxes, captions)
    return ok(
        image_data=to_b64_png(annotated),
        detections=detections,
        summary=f'{len(detections)} object(s) above {threshold:.2f}',
    )


@predictor('detect', 'detect_people')
def detect_people(spec):
    """DETR ResNet-50, filtered to people only — what the old page did."""
    image = read_image()
    bundle, results = _run_detector(spec, image, 0.5)

    id2label = bundle.model.config.id2label
    boxes, detections = [], []
    for score, label, box in zip(results['scores'], results['labels'], results['boxes']):
        if id2label[int(label)] != 'person':
            continue
        boxes.append(box.tolist())
        detections.append({'label': 'person', 'score': float(score)})

    annotated = draw_boxes(image, boxes, [f'person {d["score"]:.2f}' for d in detections])
    count = len(detections)
    return ok(
        image_data=to_b64_png(annotated),
        detections=detections,
        summary=f'Found {count} person(s)' if count else 'No people found',
    )


@predictor('detect', 'grounded_detect')
def grounded_detect(spec):
    image = read_image()
    raw = form_text('text').lower()

    # Grounding DINO wants lowercase phrases separated by periods, ending in
    # one. Accept "cat, dog" or "cat. dog" and normalise either way.
    phrases = [p.strip() for p in raw.replace(',', '.').split('.') if p.strip()]
    if not phrases:
        raise AppError('Describe what to look for, e.g. "cat. dog. person."')
    prompt = '. '.join(phrases) + '.'

    bundle = loader.get(spec.slug)
    inputs = bundle.processor(images=image, text=prompt, return_tensors='pt')
    with torch.no_grad():
        outputs = bundle.model(**inputs)

    results = bundle.processor.post_process_grounded_object_detection(
        outputs,
        input_ids=inputs.input_ids,
        target_sizes=torch.tensor([image.size[::-1]]),
        threshold=0.4,
        text_threshold=0.4,
    )[0]

    labels = results.get('text_labels', results['labels'])
    boxes, captions, detections = [], [], []
    for score, label, box in zip(results['scores'], labels, results['boxes']):
        confidence = float(score)
        boxes.append(box.tolist())
        captions.append(f'{label} {confidence:.2f}')
        detections.append({'label': str(label), 'score': confidence})

    annotated = draw_boxes(image, boxes, captions)
    return ok(
        image_data=to_b64_png(annotated),
        detections=detections,
        summary=f'{len(detections)} match(es) for “{prompt}”',
    )
