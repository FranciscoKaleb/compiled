from flask import Blueprint, render_template, request, jsonify, send_file
import os
from rembg import remove
from PIL import Image

tool2_bp = Blueprint('tool2', __name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
TOOL_DIR = os.path.join(BASE_DIR, 'app_files', 'tools_files', '02_bg_remover')
ORIGINAL_DIR = os.path.join(TOOL_DIR, 'original')
BG_REMOVED_DIR = os.path.join(TOOL_DIR, 'bg_removed')
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

@tool2_bp.route('/tools/tool2')
def tool2():
    return render_template('tools/tool2.html', active_page='tool2')

@tool2_bp.route('/tools/tool2/upload', methods=['POST'])
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

@tool2_bp.route('/tools/tool2/remove_bg/<int:counter>/<ext>', methods=['POST'])
def remove_background(counter, ext):
    original_path = os.path.join(ORIGINAL_DIR, f"{counter}.{ext}")
    output_path = os.path.join(BG_REMOVED_DIR, f"{counter}.png")
    
    with open(original_path, 'rb') as input_file:
        input_data = input_file.read()
        output_data = remove(input_data)
    
    with open(output_path, 'wb') as output_file:
        output_file.write(output_data)
    
    return jsonify({'success': True})

@tool2_bp.route('/tools/tool2/preview/<int:counter>')
def preview_image(counter):
    file_path = os.path.join(BG_REMOVED_DIR, f"{counter}.png")
    return send_file(file_path, mimetype='image/png')

@tool2_bp.route('/tools/tool2/download/<int:counter>')
def download_image(counter):
    file_path = os.path.join(BG_REMOVED_DIR, f"{counter}.png")
    return send_file(file_path, as_attachment=True, download_name='bg_removed.png')
