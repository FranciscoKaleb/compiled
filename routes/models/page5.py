from flask import Blueprint, render_template, request, jsonify
from model_cache import get_model, get_tokenizer, get_processor
from markupsafe import escape
from PIL import Image, ImageDraw
import torch
import base64
from io import BytesIO

page5_bp = Blueprint('model5', __name__)

@page5_bp.route('/models/objectdetection3')
def model5_page():
    return render_template('models/page5.html', active_page='model5')

@page5_bp.route('/models/objectdetection3/predict', methods=['POST'])
def predict5():
    file = request.files['image']
    text = str(escape(request.form.get('text', '')))
    image = Image.open(file.stream).convert('RGB')
    
    inputs = get_processor('model5')(images=image, text=text, return_tensors="pt")
    
    with torch.no_grad():
        outputs = get_model('model5')(**inputs)
    
    target_sizes = torch.tensor([image.size[::-1]])
    results = get_processor('model5').post_process_grounded_object_detection(outputs, target_sizes=target_sizes, threshold=0.3)[0]
    
    draw = ImageDraw.Draw(image)
    for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
        box = [round(i, 2) for i in box.tolist()]
        draw.rectangle(box, outline="red", width=4)
        draw.text((box[0], box[1]), f"{label}: {round(score.item(), 2)}", fill="red")
    
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    detections = [f"{label}: {round(score.item(), 2)}" for score, label in zip(results["scores"], results["labels"])]
    
    return jsonify({'detections': detections, 'image_data': img_str})
