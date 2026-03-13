from flask import Blueprint, render_template, request, jsonify
from model_cache import get_model, get_tokenizer, get_processor
from PIL import Image, ImageDraw
import torch
import base64
from io import BytesIO

page8_bp = Blueprint('model8', __name__)

@page8_bp.route('/models/objectdetection6')
def model8_page():
    return render_template('models/page8.html', active_page='model8')

@page8_bp.route('/models/objectdetection6/predict', methods=['POST'])
def predict8():
    file = request.files['image']
    image = Image.open(file.stream).convert('RGB')
    
    inputs = get_processor('model8')(images=image, return_tensors="pt")
    
    with torch.no_grad():
        outputs = get_model('model8')(**inputs)
    
    target_sizes = torch.tensor([image.size[::-1]])
    results = get_processor('model8').post_process_object_detection(outputs, target_sizes=target_sizes, threshold=0.5)[0]
    
    faces = []
    draw = ImageDraw.Draw(image)
    
    for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
        label_name = get_model('model8').config.id2label[label.item()]
        if label_name == "person":
            box = [round(i, 2) for i in box.tolist()]
            draw.rectangle(box, outline="red", width=15)
            faces.append(box)
    
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    face_count = len(faces)
    message = f"Found {face_count} face(s)" if face_count > 0 else "No faces found"
    
    return jsonify({'image_data': img_str, 'face_count': face_count, 'message': message})
