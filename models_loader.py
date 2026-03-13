from transformers import AutoModelForSequenceClassification, AutoTokenizer, AutoModelForImageClassification, AutoImageProcessor, AutoProcessor, AutoModelForZeroShotObjectDetection, NougatProcessor, VisionEncoderDecoderModel
import os

def load_models(base_path):
    models = {}
    
    model1_path = os.path.join(base_path, "models", "my_model")
    models['model1'] = AutoModelForSequenceClassification.from_pretrained(model1_path, local_files_only=True)
    models['tokenizer1'] = AutoTokenizer.from_pretrained(model1_path, local_files_only=True)
    
    model2_path = os.path.join(base_path, "models", "bert1_sentiment_model")
    models['model2'] = AutoModelForSequenceClassification.from_pretrained(model2_path, local_files_only=True)
    models['tokenizer2'] = AutoTokenizer.from_pretrained(model2_path, local_files_only=True)
    
    model3_path = os.path.join(base_path, "models", "vit_model")
    models['model3'] = AutoModelForImageClassification.from_pretrained(model3_path, local_files_only=True)
    models['processor3'] = AutoImageProcessor.from_pretrained(model3_path, local_files_only=True)
    
    model4_path = os.path.join(base_path, "models", "vit_large_model")
    models['model4'] = AutoModelForImageClassification.from_pretrained(model4_path, local_files_only=True)
    models['processor4'] = AutoImageProcessor.from_pretrained(model4_path, local_files_only=True)
    
    model5_path = os.path.join(base_path, "models", "grounding_dino")
    models['model5'] = AutoModelForZeroShotObjectDetection.from_pretrained(model5_path, local_files_only=True)
    models['processor5'] = AutoProcessor.from_pretrained(model5_path, local_files_only=True)
    
    model6_path = os.path.join(base_path, "models", "nougat_base")
    models['model6'] = VisionEncoderDecoderModel.from_pretrained(model6_path, local_files_only=True)
    models['processor6'] = NougatProcessor.from_pretrained(model6_path, local_files_only=True)
    
    model7_path = os.path.join(base_path, "models", "Human_NonHuman_Model")
    models['model7'] = AutoModelForImageClassification.from_pretrained(model7_path, local_files_only=True)
    models['processor7'] = AutoImageProcessor.from_pretrained(model7_path, local_files_only=True)
    
    from transformers import DetrImageProcessor, DetrForObjectDetection
    model8_path = os.path.join(base_path, "models", "detr-resnet-50")
    models['model8'] = DetrForObjectDetection.from_pretrained(model8_path, local_files_only=True)
    models['processor8'] = DetrImageProcessor.from_pretrained(model8_path, local_files_only=True)
    
    from insightface.app import FaceAnalysis
    insightface_path = os.path.join(base_path, "models", "insightface_models")
    models['model9'] = FaceAnalysis(providers=['CPUExecutionProvider'], root=insightface_path)
    models['model9'].prepare(ctx_id=-1)
    
    return models
