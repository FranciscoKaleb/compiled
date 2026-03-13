from flask import Blueprint, render_template, request, jsonify
from model_cache import get_model, get_tokenizer, get_processor
from PIL import Image
import torch

page7_bp = Blueprint('model7', __name__)

@page7_bp.route('/models/objectdetection5')
def model7_page():
    return render_template('models/page7.html', active_page='model7')

@page7_bp.route('/models/objectdetection5/predict', methods=['POST'])
def predict7():
    file = request.files['image']
    image = Image.open(file.stream).convert('RGB')
    
    inputs = get_processor('model7')(images=image, return_tensors="pt")
    
    with torch.no_grad():
        outputs = get_model('model7')(**inputs)
    
    logits = outputs.logits
    predicted_class = logits.argmax(-1).item()
    label = get_model('model7').config.id2label[predicted_class]
    
    return jsonify({'label': label})
