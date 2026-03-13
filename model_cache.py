from transformers import AutoModelForSequenceClassification, AutoTokenizer, AutoModelForImageClassification, AutoImageProcessor, AutoProcessor, AutoModelForZeroShotObjectDetection, NougatProcessor, VisionEncoderDecoderModel, DetrImageProcessor, DetrForObjectDetection
from insightface.app import FaceAnalysis
import os

_models = {}
_base_path = None

def set_base_path(path):
    global _base_path
    _base_path = path

def _load_model(model_name):
    if model_name in _models:
        return _models[model_name]
    
    if model_name == 'model1':
        path = os.path.join(_base_path, "app_files", "models", "my_model")
        _models['model1'] = AutoModelForSequenceClassification.from_pretrained(path, local_files_only=True)
        _models['tokenizer1'] = AutoTokenizer.from_pretrained(path, local_files_only=True)
        return _models['model1']
    
    elif model_name == 'model2':
        path = os.path.join(_base_path, "app_files", "models", "bert1_sentiment_model")
        _models['model2'] = AutoModelForSequenceClassification.from_pretrained(path, local_files_only=True)
        _models['tokenizer2'] = AutoTokenizer.from_pretrained(path, local_files_only=True)
        return _models['model2']
    
    elif model_name == 'model3':
        path = os.path.join(_base_path, "app_files", "models", "vit_model")
        _models['model3'] = AutoModelForImageClassification.from_pretrained(path, local_files_only=True)
        _models['processor3'] = AutoImageProcessor.from_pretrained(path, local_files_only=True)
        return _models['model3']
    
    elif model_name == 'model4':
        path = os.path.join(_base_path, "app_files", "models", "vit_large_model")
        _models['model4'] = AutoModelForImageClassification.from_pretrained(path, local_files_only=True)
        _models['processor4'] = AutoImageProcessor.from_pretrained(path, local_files_only=True)
        return _models['model4']
    
    elif model_name == 'model5':
        path = os.path.join(_base_path, "app_files", "models", "grounding_dino")
        _models['model5'] = AutoModelForZeroShotObjectDetection.from_pretrained(path, local_files_only=True)
        _models['processor5'] = AutoProcessor.from_pretrained(path, local_files_only=True)
        return _models['model5']
    
    elif model_name == 'model6':
        path = os.path.join(_base_path, "app_files", "models", "nougat_base")
        _models['model6'] = VisionEncoderDecoderModel.from_pretrained(path, local_files_only=True)
        _models['processor6'] = NougatProcessor.from_pretrained(path, local_files_only=True)
        return _models['model6']
    
    elif model_name == 'model7':
        path = os.path.join(_base_path, "app_files", "models", "Human_NonHuman_Model")
        _models['model7'] = AutoModelForImageClassification.from_pretrained(path, local_files_only=True)
        _models['processor7'] = AutoImageProcessor.from_pretrained(path, local_files_only=True)
        return _models['model7']
    
    elif model_name == 'model8':
        path = os.path.join(_base_path, "app_files", "models", "detr-resnet-50")
        _models['model8'] = DetrForObjectDetection.from_pretrained(path, local_files_only=True)
        _models['processor8'] = DetrImageProcessor.from_pretrained(path, local_files_only=True)
        return _models['model8']
    
    elif model_name == 'model9':
        path = os.path.join(_base_path, "app_files", "models", "insightface_models")
        app = FaceAnalysis(providers=['CPUExecutionProvider'], root=path)
        app.prepare(ctx_id=-1)
        _models['model9'] = app
        return _models['model9']

def get_model(model_name):
    return _load_model(model_name)

def get_tokenizer(model_name):
    _load_model(model_name)
    return _models.get(f'tokenizer{model_name[-1]}')

def get_processor(model_name):
    _load_model(model_name)
    return _models.get(f'processor{model_name[-1]}')
