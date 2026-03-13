from flask import Blueprint, render_template, request, jsonify
from model_cache import get_model, get_tokenizer, get_processor
from PIL import Image
import numpy as np
import base64
from io import BytesIO

page10_bp = Blueprint('model10', __name__)

@page10_bp.route('/models/insightface2')
def model10_page():
    return render_template('models/page10.html', active_page='model10')

@page10_bp.route('/models/insightface2/predict', methods=['POST'])
def predict10():
    file1 = request.files['image1']
    file2 = request.files['image2']
    
    image1 = Image.open(file1.stream).convert('RGB')
    image2 = Image.open(file2.stream).convert('RGB')
    
    # Lazy load models
    
    img_array1 = np.array(image1)
    img_array2 = np.array(image2)
    
    faces1 = get_model('model9').get(img_array1)
    faces2 = get_model('model9').get(img_array2)
    
    buffered1 = BytesIO()
    image1.save(buffered1, format="PNG")
    img_str1 = base64.b64encode(buffered1.getvalue()).decode()
    
    buffered2 = BytesIO()
    image2.save(buffered2, format="PNG")
    img_str2 = base64.b64encode(buffered2.getvalue()).decode()
    
    if len(faces1) == 0 or len(faces2) == 0:
        message = "No face detected in one or both images"
        result = "error"
    else:
        embedding1 = faces1[0].embedding
        embedding2 = faces2[0].embedding
        
        similarity = np.dot(embedding1, embedding2) / (np.linalg.norm(embedding1) * np.linalg.norm(embedding2))
        
        threshold = 0.4
        if similarity > threshold:
            result = "same"
            message = f"Same person (similarity: {similarity:.2f})"
        else:
            result = "different"
            message = f"Different person (similarity: {similarity:.2f})"
    
    return jsonify({"similarity": float(similarity), "message": message})
