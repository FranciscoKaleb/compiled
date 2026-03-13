from flask import Blueprint, render_template, request, jsonify, send_file
import os
from PIL import Image

tool3_bp = Blueprint('tool3', __name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
TOOL_DIR = os.path.join(BASE_DIR, 'app_files', 'tools_files', '03_reduce_quality')
ORIGINAL_DIR = os.path.join(TOOL_DIR, 'original')
REDUCED_DIR = os.path.join(TOOL_DIR, 'reduced')
COUNTER_FILE = os.path.join(TOOL_DIR, 'counter.txt')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'bmp'}

def get_counter():
    if os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, 'r') as f:
            return int(f.read().strip())
    return 0

def increment_counter():
    counter = get_counter() + 1
    with open(COUNTER_FILE, 'w') as f:
        f.write(str(counter))
    return counter

def is_valid_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@tool3_bp.route('/tools/tool3')
def tool3():
    return render_template('tools/tool3.html', active_page='tool3')

@tool3_bp.route('/tools/tool3/upload', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    
    if not is_valid_image(file.filename):
        return jsonify({'error': 'Not a valid photo. Please upload PNG, JPG, JPEG, WEBP, or BMP'}), 400
    
    counter = increment_counter()
    ext = file.filename.rsplit('.', 1)[1].lower()
    original_filename = f"{counter}.{ext}"
    original_path = os.path.join(ORIGINAL_DIR, original_filename)
    
    file.save(original_path)
    
    return jsonify({'success': True, 'counter': counter, 'ext': ext})

@tool3_bp.route('/tools/tool3/reduce/<int:counter>/<ext>/<int:percentage>', methods=['POST'])
def reduce_quality(counter, ext, percentage):
    original_path = os.path.join(ORIGINAL_DIR, f"{counter}.{ext}")
    output_path = os.path.join(REDUCED_DIR, f"{counter}.jpg")
    
    img = Image.open(original_path)
    
    # Calculate new dimensions
    new_width = int(img.width * percentage / 100)
    new_height = int(img.height * percentage / 100)
    
    # Resize image
    resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Save with reduced quality
    resized_img.convert('RGB').save(output_path, 'JPEG', quality=percentage)
    
    return jsonify({'success': True})

@tool3_bp.route('/tools/tool3/preview/<int:counter>')
def preview_image(counter):
    file_path = os.path.join(REDUCED_DIR, f"{counter}.jpg")
    return send_file(file_path, mimetype='image/jpeg')

@tool3_bp.route('/tools/tool3/download/<int:counter>')
def download_image(counter):
    file_path = os.path.join(REDUCED_DIR, f"{counter}.jpg")
    return send_file(file_path, as_attachment=True, download_name='reduced_quality.jpg')
