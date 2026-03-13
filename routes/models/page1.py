from flask import Blueprint, render_template, request
from markupsafe import escape
import torch
from model_cache import get_model, get_tokenizer

page1_bp = Blueprint('model1', __name__)

@page1_bp.route('/models/sentimentanalysis1')
def model1_page():
    return render_template('models/page1.html', active_page='model1')

@page1_bp.route('/models/sentimentanalysis1/predict', methods=['POST'])
def predict1():
    text = str(escape(request.form.get('text', '')))
    tokenizer1 = get_tokenizer('model1')
    model1 = get_model('model1')
    
    inputs = tokenizer1(text, return_tensors="pt", truncation=True, max_length=512)
    
    with torch.no_grad():
        outputs = model1(**inputs)
    
    prediction = torch.argmax(outputs.logits, dim=1).item()
    sentiment = "Positive" if prediction == 1 else "Negative"
    
    return render_template('models/page1.html', text=text, sentiment=sentiment, active_page='model1')
