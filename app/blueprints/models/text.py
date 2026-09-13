"""Sequence classification: the two sentiment models."""
import torch
from flask import request

from app.blueprints.models._base import predictor
from app.core import loader
from app.core.errors import AppError
from app.core.responses import ok


@predictor('text', 'sentiment')
def sentiment(spec):
    text = (request.form.get('text') or '').strip()
    if not text:
        raise AppError('Enter some text to analyse.')

    bundle = loader.get(spec.slug)
    inputs = bundle.tokenizer(text, return_tensors='pt', truncation=True, max_length=512)

    with torch.no_grad():
        outputs = bundle.model(**inputs)

    probabilities = torch.softmax(outputs.logits, dim=-1)[0]
    index = int(torch.argmax(probabilities).item())

    labels = spec.extra['labels']
    # Fall back to the model's own labels if the checkpoint disagrees with ours.
    if len(labels) != probabilities.numel():
        id2label = bundle.model.config.id2label
        labels = [id2label[i] for i in range(probabilities.numel())]

    return ok(
        sentiment=labels[index],
        confidence=float(probabilities[index]) * 100,
        scores=[[label, float(p) * 100] for label, p in zip(labels, probabilities)],
    )
