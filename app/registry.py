"""The model and tool catalogue.

This is the single source of truth for the whole app. The sidebar, the
catalogue pages, URL registration, weight loading and the legacy-URL redirect
table are all generated from the lists at the bottom of this file.

Adding a model is one `ModelSpec` entry plus a handler function — not a new
blueprint file, an `app.py` edit, a sidebar edit and a copied template.
"""
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Input controls a page can render, beyond the standard file picker.
# The runner in static/js/runner.js reads these straight off the rendered form.
# ---------------------------------------------------------------------------

THRESHOLD = {
    'name': 'threshold', 'kind': 'range', 'label': 'Confidence threshold',
    'min': 0.05, 'max': 0.95, 'step': 0.05, 'default': 0.5,
}
TAG_THRESHOLD = {
    'name': 'threshold', 'kind': 'range', 'label': 'Tag threshold',
    'min': 0.05, 'max': 0.95, 'step': 0.05, 'default': 0.35,
}
PROMPT = {
    'name': 'text', 'kind': 'text', 'label': 'Objects to find',
    'placeholder': 'cat. dog. person.',
    'help': 'Lowercase phrases separated by periods or commas.',
}
LABELS = {
    'name': 'labels', 'kind': 'text', 'label': 'Candidate labels',
    'placeholder': 'a cat, a dog, a car',
    'help': 'At least two labels, comma separated.',
}
def range_field(name, label, lo, hi, step, default, help=''):
    return {'name': name, 'kind': 'range', 'label': label, 'min': lo, 'max': hi,
            'step': step, 'default': default, 'help': help}


def text_field(name, label, placeholder='', help='', required=True):
    return {'name': name, 'kind': 'text', 'label': label, 'placeholder': placeholder,
            'help': help, 'required': required}


def select_field(name, label, options, default=None, help=''):
    """options: [(value, label), ...]"""
    return {'name': name, 'kind': 'select', 'label': label, 'options': options,
            'default': default if default is not None else options[0][0], 'help': help}


def textarea_field(name, label, placeholder='', help='', required=True, rows=6):
    return {'name': name, 'kind': 'textarea', 'label': label, 'placeholder': placeholder,
            'help': help, 'required': required, 'rows': rows}


def checkbox_field(name, label, default=False, help=''):
    return {'name': name, 'kind': 'checkbox', 'label': label, 'default': default, 'help': help}


def file_field(name, label, accept='*/*', help='', required=True):
    """A secondary file picker (e.g. a subtitle file next to the video)."""
    return {'name': name, 'kind': 'file', 'label': label, 'accept': accept,
            'help': help, 'required': required}


MIN_AREA = {
    'name': 'min_area', 'kind': 'range', 'label': 'Minimum blob area (px)',
    'min': 100, 'max': 5000, 'step': 100, 'default': 500,
}


@dataclass(frozen=True)
class ModelSpec:
    """One model demo page."""

    slug: str                 # URL path after /models/  e.g. "classify/vit-base"
    category: str             # grouping key, see CATEGORIES
    title: str                # headline shown on the page and the catalogue card
    subtitle: str             # the taxonomy label, e.g. "Two-stage detector"
    blurb: str                # one paragraph of explanation
    weights: str | None = None   # directory under app_files/models
    loader: str | None = None    # key into core.loader.LOADERS
    shares: str | None = None    # reuse another spec's loaded weights
    view: str = ''            # handler name inside its blueprint module
    input: str = 'image'      # image | text | two-images | video | webcam | stream
    render: str = 'predictions'  # how runner.js renders the response
    controls: tuple = ()
    legacy: tuple = ()        # old URLs that must 301 here
    extra: dict = field(default_factory=dict)

    @property
    def url(self) -> str:
        return f'/models/{self.slug}'

    @property
    def cache_key(self) -> str:
        """Which entry in the model cache this page's weights live under."""
        return self.shares or self.slug

    @property
    def endpoint(self) -> str:
        """Flask endpoint name, e.g. 'models.classify_vit_base'."""
        return 'models.' + self.slug.replace('/', '_').replace('-', '_')


@dataclass(frozen=True)
class ToolSpec:
    slug: str
    category: str             # grouping key, see TOOL_CATEGORIES
    title: str
    subtitle: str
    blurb: str
    view: str                 # handler name; also the page endpoint
    input: str = 'file'       # file | files | text | none
    accept: str = '*/*'       # <input accept=...> for the picker
    hint: str = ''            # text under the picker
    fields: tuple = ()        # extra controls, same dicts the models use
    render: str = 'download'  # download | image | video | text | table | custom
    button: str = 'Run'
    template: str | None = None   # custom template; None = the generic runner
    needs: tuple = ()         # system binaries, e.g. ('ffmpeg',)
    legacy: tuple = ()

    @property
    def url(self) -> str:
        return f'/tools/{self.slug}'

    @property
    def endpoint(self) -> str:
        return 'tools.' + self.view


CATEGORIES = [
    ('text', 'Text', 'Sentiment and sequence classification'),
    ('classify', 'Image Classification', 'Assigning labels to a whole image'),
    ('detect', 'Object Detection', 'Locating objects with bounding boxes'),
    ('segment', 'Segmentation', 'Labelling images pixel by pixel'),
    ('ocr', 'OCR / Document AI', 'Reading text out of images'),
    ('face', 'Face Analysis', 'Detection, comparison and identification'),
    ('track', 'Object Tracking', 'Following things across video frames'),
]

CATEGORY_TITLES = {key: title for key, title, _ in CATEGORIES}


MODELS: list[ModelSpec] = [
    # --- text --------------------------------------------------------------
    ModelSpec(
        slug='text/sentiment-distilbert', category='text',
        title='DistilBERT', subtitle='Binary sentiment',
        blurb='A distilled BERT fine-tuned on SST-2. Classifies a sentence as '
              'positive or negative.',
        weights='DistilBERT', loader='seq_classification',
        view='sentiment', input='text', render='sentiment',
        legacy=('/models/sentimentanalysis1',),
        extra={'labels': ['Negative', 'Positive']},
    ),
    ModelSpec(
        slug='text/sentiment-roberta', category='text',
        title='XLM-RoBERTa', subtitle='Three-way sentiment',
        blurb='A multilingual RoBERTa sentiment model with a neutral class, '
              'fine-tuned locally by scripts/train_sentiment.py.',
        weights='bert1_sentiment_model', loader='seq_classification',
        view='sentiment', input='text', render='sentiment',
        legacy=('/models/sentimentanalysis2',),
        extra={'labels': ['Negative', 'Neutral', 'Positive']},
    ),

    # --- image classification ----------------------------------------------
    ModelSpec(
        slug='classify/vit-base', category='classify',
        title='ViT Base', subtitle='Multi-class classification',
        blurb='Vision Transformer (base, 16x16 patches) trained on ImageNet-1k. '
              'Returns the five most likely classes.',
        weights='vit_model', loader='image_classification',
        view='topk', legacy=('/models/objectdetection1',),
        extra={'k': 5},
    ),
    ModelSpec(
        slug='classify/vit-large', category='classify',
        title='ViT Large', subtitle='Multi-class classification',
        blurb='The larger ViT: more accurate than the base model and noticeably '
              'slower on CPU.',
        weights='vit_large_model', loader='image_classification',
        view='topk', legacy=('/models/objectdetection2',),
        extra={'k': 5},
    ),
    ModelSpec(
        slug='classify/human-nonhuman', category='classify',
        title='Human vs Non-Human', subtitle='Binary classification',
        blurb='A two-class classifier answering a single question: is there a '
              'person in this image?',
        weights='Human_NonHuman_Model', loader='image_classification',
        view='single_label', render='label',
        legacy=('/models/objectdetection5',),
    ),
    ModelSpec(
        slug='classify/multi-label', category='classify',
        title='WD ViT Tagger v3', subtitle='Multi-label classification',
        blurb='An ONNX tagger that assigns many independent tags at once, split '
              'into ratings, characters and general tags.',
        weights='wd_vit_tagger_v3', loader='onnx_tagger',
        view='tagger', render='tags', controls=(TAG_THRESHOLD,),
        legacy=('/models/multilabel',),
    ),
    ModelSpec(
        slug='classify/hierarchical', category='classify',
        title='BEiT ImageNet-22k', subtitle='Hierarchical classification',
        blurb='Trained across 21,841 WordNet classes, so predictions sit at '
              'varying levels of a hierarchy. Returns the top ten.',
        weights='beit_base_22k', loader='image_classification',
        view='topk', legacy=('/models/hierarchical',),
        extra={'k': 10},
    ),
    ModelSpec(
        slug='classify/fine-grained', category='classify',
        title='Dog Breeds ViT', subtitle='Fine-grained classification',
        blurb='A ViT fine-tuned on 120 dog breeds — distinguishing classes that '
              'differ only in small details.',
        weights='dog_breeds_vit', loader='image_classification',
        view='topk', legacy=('/models/finegrained',),
        extra={'k': 5},
    ),
    ModelSpec(
        slug='classify/zero-shot', category='classify',
        title='CLIP ViT-L/14', subtitle='Zero-shot classification',
        blurb='Scores an image against labels you invent at request time, with '
              'no training for those classes.',
        weights='clip_vit_large', loader='clip',
        view='zero_shot', controls=(LABELS,),
        legacy=('/models/zeroshot',),
    ),

    # --- object detection ---------------------------------------------------
    ModelSpec(
        slug='detect/detr-resnet50', category='detect',
        title='DETR ResNet-50', subtitle='Anchor-based detector',
        blurb='The original Detection Transformer. This page filters the output '
              'down to people only.',
        weights='detr-resnet-50', loader='detr',
        view='detect_people', render='detections',
        legacy=('/models/objectdetection6',),
    ),
    ModelSpec(
        slug='detect/detr-resnet101', category='detect',
        title='DETR ResNet-101', subtitle='Two-stage detector',
        blurb='DETR with a deeper backbone — stronger features, slower inference.',
        weights='detr_resnet101', loader='detr',
        view='detect', render='detections', controls=(THRESHOLD,),
        legacy=('/models/detection-twostage',),
    ),
    ModelSpec(
        slug='detect/yolos-small', category='detect',
        title='YOLOS Small', subtitle='One-stage detector',
        blurb='A plain ViT trained to detect directly, in a single pass.',
        weights='yolos_small', loader='object_detection',
        view='detect', render='detections', controls=(THRESHOLD,),
        legacy=('/models/detection-onestage',),
    ),
    ModelSpec(
        slug='detect/rt-detr', category='detect',
        title='RT-DETR R50', subtitle='Anchor-free detector',
        blurb='A real-time transformer detector that predicts boxes without '
              'anchor priors.',
        weights='rtdetr_r50vd', loader='object_detection',
        view='detect', render='detections', controls=(THRESHOLD,),
        legacy=('/models/detection-anchorfree',),
    ),
    ModelSpec(
        slug='detect/grounding-dino', category='detect',
        title='Grounding DINO', subtitle='Open-vocabulary detector',
        blurb='Detects whatever you describe in words, rather than a fixed list '
              'of classes.',
        weights='grounding_dino', loader='zero_shot_detection',
        view='grounded_detect', render='detections', controls=(PROMPT,),
        legacy=('/models/objectdetection3',),
    ),

    # --- segmentation -------------------------------------------------------
    ModelSpec(
        slug='segment/semantic', category='segment',
        title='SegFormer B2', subtitle='Semantic segmentation',
        blurb='Labels every pixel with one of 150 ADE20K classes. Two chairs '
              'are one "chair" region.',
        weights='segformer_b2_ade', loader='semantic_seg',
        view='semantic', render='segments',
        legacy=('/models/segmentation-semantic',),
    ),
    ModelSpec(
        slug='segment/instance', category='segment',
        title='Mask2Former (instance)', subtitle='Instance segmentation',
        blurb='A separate mask per object, so two chairs are two distinct '
              'instances.',
        weights='mask2former_coco_instance', loader='universal_seg',
        view='instance', render='segments', controls=(THRESHOLD,),
        legacy=('/models/segmentation-instance',),
    ),
    ModelSpec(
        slug='segment/panoptic', category='segment',
        title='Mask2Former (panoptic)', subtitle='Panoptic segmentation',
        blurb='Semantic and instance segmentation combined: countable "things" '
              'get instances, uncountable "stuff" gets regions.',
        weights='mask2former_coco_panoptic', loader='universal_seg',
        view='panoptic', render='segments',
        legacy=('/models/segmentation-panoptic',),
    ),

    # --- OCR ----------------------------------------------------------------
    ModelSpec(
        slug='ocr/nougat', category='ocr',
        title='Nougat Base', subtitle='Document understanding',
        blurb='Converts a page of an academic PDF into markdown, including '
              'maths and tables.',
        weights='nougat_base', loader='nougat',
        view='nougat', render='text',
        legacy=('/models/objectdetection4',),
    ),
    ModelSpec(
        slug='ocr/trocr', category='ocr',
        title='TrOCR Base', subtitle='Printed text recognition',
        blurb='Reads a cropped line of printed text. Feed it one line at a '
              'time, not a whole page.',
        weights='trocr_base_printed', loader='trocr',
        view='trocr', render='text',
        legacy=('/models/textrecognition',),
    ),

    # --- face ---------------------------------------------------------------
    ModelSpec(
        slug='face/detect', category='face',
        title='Face Detection', subtitle='InsightFace buffalo_l',
        blurb='Finds every face in an image and draws its bounding box.',
        weights='insightface_models', loader='insightface',
        view='detect', render='annotated',
        legacy=('/models/insightface1',),
    ),
    ModelSpec(
        slug='face/compare', category='face',
        title='Face Comparison', subtitle='1:1 verification',
        blurb='Compares two photographs and reports the cosine similarity of '
              'their face embeddings.',
        shares='face/detect', view='compare',
        input='two-images', render='similarity',
        legacy=('/models/insightface2',),
    ),
    ModelSpec(
        slug='face/identify', category='face',
        title='Face Identification', subtitle='1:N enrolment and matching',
        blurb='Enrol a face against a name, then identify it later. Embeddings '
              'are stored in the database; the photograph is not.',
        shares='face/detect', view='identify',
        input='webcam', render='custom',
        legacy=('/models/insightface3',),
    ),
    ModelSpec(
        slug='face/live-detect', category='face',
        title='Live Face Detection', subtitle='Server camera stream',
        blurb='Runs detection on the machine hosting this app, streamed back as '
              'MJPEG.',
        shares='face/detect', view='live_detect',
        input='stream', render='custom',
        legacy=('/models/insightface4',),
    ),
    ModelSpec(
        slug='face/live-identify', category='face',
        title='Live Face Identification', subtitle='Server camera stream',
        blurb='The same stream, matched against enrolled people frame by frame '
              'with IoU tracking to steady the labels.',
        shares='face/detect', view='live_identify',
        input='stream', render='custom',
        legacy=('/models/insightface5',),
    ),

    # --- tracking -----------------------------------------------------------
    ModelSpec(
        slug='track/single', category='track',
        title='Single Object Tracking', subtitle='CSRT',
        blurb='Draw a box around one thing in your webcam feed and the tracker '
              'follows it. No neural network — a classical correlation filter.',
        view='single', input='webcam', render='custom',
        legacy=('/models/tracking-sot',),
    ),
    ModelSpec(
        slug='track/multi', category='track',
        title='Multiple Object Tracking', subtitle='SORT + background subtraction',
        blurb='Detects moving blobs by background subtraction and keeps a '
              'stable id on each one across frames.',
        view='multi', input='webcam', render='custom',
        controls=(MIN_AREA,), legacy=('/models/tracking-mot',),
    ),
    ModelSpec(
        slug='track/flow', category='track',
        title='Optical Flow', subtitle='Lucas-Kanade',
        blurb='Tracks corner features through an uploaded video and draws the '
              'path each one takes.',
        view='flow', input='video', render='custom',
        legacy=('/models/tracking-flow',),
    ),
]


from app.tools_catalog import TOOL_CATEGORIES, TOOLS  # noqa: E402


BY_SLUG = {spec.slug: spec for spec in MODELS}
TOOLS_BY_SLUG = {spec.slug: spec for spec in TOOLS}


def models_by_category() -> list[tuple[str, str, str, list[ModelSpec]]]:
    """(key, title, description, specs) per category, in CATEGORIES order."""
    grouped = []
    for key, title, description in CATEGORIES:
        specs = [s for s in MODELS if s.category == key]
        if specs:
            grouped.append((key, title, description, specs))
    return grouped


def tools_by_category() -> list[tuple[str, str, str, list[ToolSpec]]]:
    grouped = []
    for key, title, description in TOOL_CATEGORIES:
        specs = [t for t in TOOLS if t.category == key]
        if specs:
            grouped.append((key, title, description, specs))
    return grouped


def legacy_redirects() -> list[tuple[str, str]]:
    """(old_path, new_path) for every retired URL."""
    pairs = []
    for spec in MODELS:
        pairs.extend((old, spec.url) for old in spec.legacy)
    for tool in TOOLS:
        pairs.extend((old, tool.url) for old in tool.legacy)
    pairs += [('/blockchain/view-chain', '/blockchain/ledger'), ('/blockchain2', '/blockchain/permissioned'),
              ('/blockchain2/login', '/blockchain/permissioned'), ('/blockchain2/authorized-node/dashboard', '/blockchain/permissioned'),
              ('/blockchain2/node/dashboard', '/blockchain/permissioned')]
    return pairs
