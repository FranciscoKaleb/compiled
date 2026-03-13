from flask import Blueprint, render_template, request
from model_cache import get_model, get_tokenizer
from markupsafe import escape
import torch

page2_bp = Blueprint('model2', __name__)

@page2_bp.route('/models/sentimentanalysis2')
def model2_page():
    return render_template('models/page2.html', active_page='model2')

@page2_bp.route('/models/sentimentanalysis2/predict', methods=['POST'])
def predict2():
    text = str(escape(request.form.get('text', '')))
    
    inputs = get_tokenizer('model2')(text, return_tensors="pt", truncation=True, max_length=512)
    
    with torch.no_grad():
        outputs = get_model('model2')(**inputs)
    
    prediction = torch.argmax(outputs.logits, dim=1).item()
    labels = ["Negative", "Neutral", "Positive"]
    sentiment = labels[prediction]
    
    return render_template('models/page2.html', text=text, sentiment=sentiment, active_page='model2')
