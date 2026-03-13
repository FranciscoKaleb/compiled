from flask import Blueprint, render_template, request, jsonify
from PIL import Image
import numpy as np
import base64
from io import BytesIO
from db_config import get_db_connection
from model_cache import get_model
import pickle

page11_bp = Blueprint('model11', __name__)

@page11_bp.route('/models/insightface3')
def model11_page():
    return render_template('models/page11.html', active_page='model11')

@page11_bp.route('/register11', methods=['POST'])
def register11():
    data = request.get_json()
    name = data.get('name')
    image_data = data.get('image')
    
    image_data = image_data.split(',')[1]
    image_bytes = base64.b64decode(image_data)
    image = Image.open(BytesIO(image_bytes)).convert('RGB')
    
    model9 = get_model('model9')
    img_array = np.array(image)
    faces = model9.get(img_array)
    
    if len(faces) == 0:
        return jsonify({'success': False, 'message': 'No face detected'})
    
    embedding = faces[0].embedding
    embedding_blob = pickle.dumps(embedding)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO users (name, embedding) VALUES (%s, %s)', (name, embedding_blob))
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({'success': True, 'message': f'User {name} registered successfully'})

@page11_bp.route('/login11', methods=['POST'])
def login11():
    data = request.get_json()
    image_data = data.get('image')
    
    image_data = image_data.split(',')[1]
    image_bytes = base64.b64decode(image_data)
    image = Image.open(BytesIO(image_bytes)).convert('RGB')
    
    model9 = get_model('model9')
    img_array = np.array(image)
    faces = model9.get(img_array)
    
    if len(faces) == 0:
        return jsonify({'success': False, 'message': 'No face detected'})
    
    embedding = faces[0].embedding
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, embedding FROM users')
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    
    best_match = None
    best_similarity = 0
    threshold = 0.65
    
    for user_id, name, embedding_blob in users:
        stored_embedding = pickle.loads(embedding_blob)
        similarity = np.dot(embedding, stored_embedding) / (np.linalg.norm(embedding) * np.linalg.norm(stored_embedding))
        
        if similarity > best_similarity:
            best_similarity = similarity
            best_match = name
    
    if best_similarity >= threshold:
        return jsonify({'success': True, 'message': f'Welcome {best_match}!', 'name': best_match, 'similarity': float(best_similarity)})
    else:
        return jsonify({'success': False, 'message': 'No user found'})
