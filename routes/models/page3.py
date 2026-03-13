from flask import Blueprint, render_template, request, jsonify
from model_cache import get_model, get_tokenizer, get_processor
from PIL import Image
import torch
import torch.nn.functional as F
import base64
from io import BytesIO

page3_bp = Blueprint('model3', __name__)

@page3_bp.route('/models/objectdetection1')
def model3_page():
    return render_template('models/page3.html', active_page='model3')

@page3_bp.route('/models/objectdetection1/predict', methods=['POST'])
def predict3():
    file = request.files['image']
    image = Image.open(file.stream).convert('RGB')
    
    inputs = get_processor('model3')(images=image, return_tensors="pt")
    
    with torch.no_grad():
        outputs = get_model('model3')(**inputs)
    
    logits = outputs.logits
    probabilities = F.softmax(logits, dim=-1)[0]
    
    probs, indices = torch.topk(probabilities, k=min(5, len(probabilities)))
    id2label = get_model('model3').config.id2label
    predictions = [[id2label[idx.item()], prob.item() * 100] for idx, prob in zip(indices, probs)]
    
    return jsonify({'predictions': predictions})
