"""Lazy, cached model loading driven by the registry.

Replaces the 230-line if/elif chain in the old model_cache.py. Each family of
models needs one loader function; the registry says which one to use and where
the weights are. Heavy imports (transformers, insightface, onnxruntime) happen
inside the loader functions so importing this module stays cheap.
"""
import csv
import gc
import os
import threading
from dataclasses import dataclass
from typing import Any, Callable

from app.registry import BY_SLUG, ModelSpec


@dataclass
class Bundle:
    """Everything a handler needs for one model."""

    model: Any
    processor: Any = None
    tokenizer: Any = None
    extra: Any = None


_cache: dict[str, Bundle] = {}
_lock = threading.RLock()
_models_dir: str | None = None


def configure(models_dir) -> None:
    """Point the loader at the weights directory. Called once by create_app."""
    global _models_dir
    _models_dir = str(models_dir)


def _path(weights: str) -> str:
    if _models_dir is None:
        raise RuntimeError('loader.configure() was never called')
    return os.path.join(_models_dir, weights)


# ---------------------------------------------------------------------------
# Loaders. One per family; `weights` is an absolute directory.
# ---------------------------------------------------------------------------

def _seq_classification(path: str, spec: ModelSpec) -> Bundle:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    return Bundle(
        model=AutoModelForSequenceClassification.from_pretrained(path, local_files_only=True),
        tokenizer=AutoTokenizer.from_pretrained(path, local_files_only=True),
    )


def _image_classification(path: str, spec: ModelSpec) -> Bundle:
    from transformers import AutoImageProcessor, AutoModelForImageClassification
    return Bundle(
        model=AutoModelForImageClassification.from_pretrained(path, local_files_only=True),
        processor=AutoImageProcessor.from_pretrained(path, local_files_only=True),
    )


def _object_detection(path: str, spec: ModelSpec) -> Bundle:
    from transformers import AutoImageProcessor, AutoModelForObjectDetection
    return Bundle(
        model=AutoModelForObjectDetection.from_pretrained(path, local_files_only=True),
        processor=AutoImageProcessor.from_pretrained(path, local_files_only=True),
    )


def _detr(path: str, spec: ModelSpec) -> Bundle:
    from transformers import DetrForObjectDetection, DetrImageProcessor
    return Bundle(
        model=DetrForObjectDetection.from_pretrained(path, local_files_only=True),
        processor=DetrImageProcessor.from_pretrained(path, local_files_only=True),
    )


def _zero_shot_detection(path: str, spec: ModelSpec) -> Bundle:
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
    return Bundle(
        model=AutoModelForZeroShotObjectDetection.from_pretrained(path, local_files_only=True),
        processor=AutoProcessor.from_pretrained(path, local_files_only=True),
    )


def _semantic_seg(path: str, spec: ModelSpec) -> Bundle:
    from transformers import AutoImageProcessor, AutoModelForSemanticSegmentation
    return Bundle(
        model=AutoModelForSemanticSegmentation.from_pretrained(path, local_files_only=True),
        processor=AutoImageProcessor.from_pretrained(path, local_files_only=True),
    )


def _universal_seg(path: str, spec: ModelSpec) -> Bundle:
    from transformers import AutoImageProcessor, Mask2FormerForUniversalSegmentation
    return Bundle(
        model=Mask2FormerForUniversalSegmentation.from_pretrained(path, local_files_only=True),
        processor=AutoImageProcessor.from_pretrained(path, local_files_only=True),
    )


def _nougat(path: str, spec: ModelSpec) -> Bundle:
    from transformers import NougatProcessor, VisionEncoderDecoderModel
    return Bundle(
        model=VisionEncoderDecoderModel.from_pretrained(path, local_files_only=True),
        processor=NougatProcessor.from_pretrained(path, local_files_only=True),
    )


def _trocr(path: str, spec: ModelSpec) -> Bundle:
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    return Bundle(
        model=VisionEncoderDecoderModel.from_pretrained(path, local_files_only=True),
        processor=TrOCRProcessor.from_pretrained(path, local_files_only=True),
    )


def _clip(path: str, spec: ModelSpec) -> Bundle:
    from transformers import CLIPModel, CLIPProcessor
    return Bundle(
        model=CLIPModel.from_pretrained(path, local_files_only=True),
        processor=CLIPProcessor.from_pretrained(path, local_files_only=True),
    )


def _onnx_tagger(path: str, spec: ModelSpec) -> Bundle:
    import onnxruntime as ort

    session = ort.InferenceSession(
        os.path.join(path, 'model.onnx'), providers=['CPUExecutionProvider']
    )
    with open(os.path.join(path, 'selected_tags.csv'), encoding='utf-8') as fh:
        tags = [
            {'name': row['name'], 'category': int(row['category'])}
            for row in csv.DictReader(fh)
        ]
    return Bundle(model=session, extra=tags)


def _insightface(path: str, spec: ModelSpec) -> Bundle:
    from insightface.app import FaceAnalysis

    # root= keeps the weights inside app_files instead of downloading a second
    # copy into ~/.insightface, which is what the old page12/page13 did.
    analyzer = FaceAnalysis(providers=['CPUExecutionProvider'], root=path)
    analyzer.prepare(ctx_id=-1, det_size=(640, 640))  # -1 = CPU
    return Bundle(model=analyzer)


LOADERS: dict[str, Callable[[str, ModelSpec], Bundle]] = {
    'seq_classification': _seq_classification,
    'image_classification': _image_classification,
    'object_detection': _object_detection,
    'detr': _detr,
    'zero_shot_detection': _zero_shot_detection,
    'semantic_seg': _semantic_seg,
    'universal_seg': _universal_seg,
    'nougat': _nougat,
    'trocr': _trocr,
    'clip': _clip,
    'onnx_tagger': _onnx_tagger,
    'insightface': _insightface,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get(slug: str) -> Bundle:
    """Return the loaded Bundle for a registry slug, loading it on first use.

    The lock means two simultaneous first-requests load the weights once
    rather than twice.
    """
    spec = BY_SLUG[slug]
    key = spec.cache_key

    cached = _cache.get(key)
    if cached is not None:
        return cached

    with _lock:
        cached = _cache.get(key)          # re-check: another thread may have won
        if cached is not None:
            return cached

        owner = BY_SLUG[key]
        if not owner.loader:
            raise RuntimeError(f'{key} has no loader — it needs no weights')

        bundle = LOADERS[owner.loader](_path(owner.weights), owner)
        _cache[key] = bundle
        return bundle


def loaded_keys() -> list[str]:
    with _lock:
        return sorted(_cache)


def unload(slug: str) -> bool:
    """Drop one model from memory. Returns whether anything was removed."""
    spec = BY_SLUG.get(slug)
    key = spec.cache_key if spec else slug
    with _lock:
        removed = _cache.pop(key, None) is not None
    if removed:
        gc.collect()
    return removed


def clear() -> list[str]:
    """Drop every loaded model. Returns the keys that were freed."""
    with _lock:
        keys = sorted(_cache)
        _cache.clear()
    gc.collect()
    return keys
