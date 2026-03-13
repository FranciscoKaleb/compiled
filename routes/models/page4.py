from flask import Blueprint, render_template, request, jsonify
from model_cache import get_model, get_tokenizer, get_processor
from PIL import Image
import torch
import torch.nn.functional as F
import base64
from io import BytesIO

page4_bp = Blueprint('model4', __name__)

@page4_bp.route('/models/objectdetection2')
def model4_page():
    return render_template('models/page4.html', active_page='model4')

@page4_bp.route('/models/objectdetection2/predict', methods=['POST'])
def predict4():
    file = request.files['image']
    image = Image.open(file.stream).convert('RGB')
    
    inputs = get_processor('model4')(images=image, return_tensors="pt")
    
    with torch.no_grad():
        outputs = get_model('model4')(**inputs)
    
    logits = outputs.logits
    probabilities = F.softmax(logits, dim=-1)[0]
    
    probs, indices = torch.topk(probabilities, k=min(5, len(probabilities)))
    id2label = get_model('model4').config.id2label
    predictions = [[id2label[idx.item()], prob.item() * 100] for idx, prob in zip(indices, probs)]
    
    return jsonify({'predictions': predictions})
