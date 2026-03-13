from flask import Blueprint, render_template, request, jsonify
from PIL import Image, ImageDraw
import numpy as np
import base64
from io import BytesIO
from model_cache import get_model

page9_bp = Blueprint('model9', __name__)

@page9_bp.route('/models/insightface1')
def model9_page():
    return render_template('models/page9.html', active_page='model9')

@page9_bp.route('/models/insightface1/predict', methods=['POST'])
def predict9():
    file = request.files['image']
    image = Image.open(file.stream).convert('RGB')
    model9 = get_model('model9')
    
    img_array = np.array(image)
    faces = model9.get(img_array)
    
    draw = ImageDraw.Draw(image)
    for face in faces:
        bbox = face.bbox.astype(int)
        draw.rectangle([bbox[0], bbox[1], bbox[2], bbox[3]], outline="red", width=15)
    
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    face_count = len(faces)
    message = f"Found {face_count} face(s)" if face_count > 0 else "No faces found"
    
    return jsonify({'image_data': img_str, 'face_count': face_count, 'message': message})
