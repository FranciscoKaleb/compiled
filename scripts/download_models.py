#!/usr/bin/env python3
"""Fetch model weights into app_files/models.

Replaces dl.py, which was 700 lines of commented-out snippets with three live
multi-gigabyte downloads at module scope. Nothing here runs on import.

    python scripts/download_models.py --list
    python scripts/download_models.py classify/vit-base ocr/trocr
    python scripts/download_models.py --all
    python scripts/download_models.py --missing        # only what is not on disk

Model directories are the ones the registry expects, so the app picks them up
with no further configuration.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.registry import BY_SLUG, MODELS  # noqa: E402

# slug -> (hugging face repo, how to fetch)
#   'auto'      -> AutoModel* + AutoProcessor/AutoTokenizer save_pretrained
#   'snapshot'  -> huggingface_hub.snapshot_download (raw files: ONNX, csv, ...)
#   'insightface' -> the insightface package downloads its own pack
SOURCES = {
    'text/sentiment-distilbert': ('distilbert-base-uncased-finetuned-sst-2-english', 'auto'),
    'text/sentiment-roberta': ('cardiffnlp/twitter-xlm-roberta-base-sentiment', 'auto'),
    'classify/vit-base': ('google/vit-base-patch16-224', 'auto'),
    'classify/vit-large': ('google/vit-large-patch16-224', 'auto'),
    'classify/human-nonhuman': ('prithivMLmods/Human-vs-NonHuman-Detection', 'auto'),
    'classify/multi-label': ('SmilingWolf/wd-vit-tagger-v3', 'snapshot'),
    'classify/hierarchical': ('microsoft/beit-base-patch16-224-pt22k-ft22k', 'auto'),
    'classify/fine-grained': ('wesleyacheng/dog-breeds-multiclass-image-classification-with-vit', 'auto'),
    'classify/zero-shot': ('openai/clip-vit-large-patch14', 'auto'),
    'detect/detr-resnet50': ('facebook/detr-resnet-50', 'auto'),
    'detect/detr-resnet101': ('facebook/detr-resnet-101', 'auto'),
    'detect/yolos-small': ('hustvl/yolos-small', 'auto'),
    'detect/rt-detr': ('PekingU/rtdetr_r50vd', 'auto'),
    'detect/grounding-dino': ('IDEA-Research/grounding-dino-base', 'auto'),
    'segment/semantic': ('nvidia/segformer-b2-finetuned-ade-512-512', 'auto'),
    'segment/instance': ('facebook/mask2former-swin-small-coco-instance', 'auto'),
    'segment/panoptic': ('facebook/mask2former-swin-base-coco-panoptic', 'auto'),
    'ocr/nougat': ('facebook/nougat-base', 'auto'),
    'ocr/trocr': ('microsoft/trocr-base-printed', 'auto'),
    'face/detect': ('buffalo_l', 'insightface'),
}

# The registry loader key tells us which transformers classes to use.
AUTO_CLASSES = {
    'seq_classification': ('AutoModelForSequenceClassification', 'AutoTokenizer'),
    'image_classification': ('AutoModelForImageClassification', 'AutoImageProcessor'),
    'object_detection': ('AutoModelForObjectDetection', 'AutoImageProcessor'),
    'detr': ('DetrForObjectDetection', 'DetrImageProcessor'),
    'zero_shot_detection': ('AutoModelForZeroShotObjectDetection', 'AutoProcessor'),
    'semantic_seg': ('AutoModelForSemanticSegmentation', 'AutoImageProcessor'),
    'universal_seg': ('Mask2FormerForUniversalSegmentation', 'AutoImageProcessor'),
    'nougat': ('VisionEncoderDecoderModel', 'NougatProcessor'),
    'trocr': ('VisionEncoderDecoderModel', 'TrOCRProcessor'),
    'clip': ('CLIPModel', 'CLIPProcessor'),
}


def models_dir() -> Path:
    from app.config import Config
    return Path(Config.MODELS_DIR)


def target_for(slug: str) -> Path:
    return models_dir() / BY_SLUG[slug].weights


def is_present(slug: str) -> bool:
    path = target_for(slug)
    return path.is_dir() and any(path.iterdir())


def fetch(slug: str) -> None:
    spec = BY_SLUG[slug]
    repo, method = SOURCES[slug]
    target = target_for(slug)
    target.mkdir(parents=True, exist_ok=True)
    print(f'-> {slug}: {repo}  ->  {target}')

    if method == 'snapshot':
        from huggingface_hub import snapshot_download
        snapshot_download(repo_id=repo, local_dir=str(target))

    elif method == 'insightface':
        from insightface.app import FaceAnalysis
        # insightface downloads <root>/models/<name>.zip and unpacks it itself.
        analyzer = FaceAnalysis(name=repo, root=str(target), providers=['CPUExecutionProvider'])
        analyzer.prepare(ctx_id=-1)

    else:
        import transformers
        model_cls, processor_cls = (getattr(transformers, n) for n in AUTO_CLASSES[spec.loader])
        model_cls.from_pretrained(repo).save_pretrained(target)
        processor_cls.from_pretrained(repo).save_pretrained(target)

    print(f'   done')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('slugs', nargs='*', help='registry slugs, e.g. classify/vit-base')
    parser.add_argument('--all', action='store_true', help='download every model with a source')
    parser.add_argument('--missing', action='store_true', help='download only what is not on disk')
    parser.add_argument('--list', action='store_true', help='show every model and whether it is present')
    args = parser.parse_args(argv)

    downloadable = [s.slug for s in MODELS if s.slug in SOURCES]

    if args.list or not (args.slugs or args.all or args.missing):
        width = max(len(s) for s in downloadable)
        for slug in downloadable:
            mark = 'present' if is_present(slug) else 'missing'
            print(f'{slug:<{width}}  {mark:<8} {SOURCES[slug][0]}')
        return 0

    if args.all:
        chosen = downloadable
    elif args.missing:
        chosen = [s for s in downloadable if not is_present(s)]
    else:
        unknown = [s for s in args.slugs if s not in SOURCES]
        if unknown:
            parser.error(f'no download source for: {", ".join(unknown)}')
        chosen = args.slugs

    if not chosen:
        print('Nothing to download.')
        return 0

    for slug in chosen:
        fetch(slug)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
