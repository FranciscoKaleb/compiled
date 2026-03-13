from flask import Blueprint, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import os
from PyPDF2 import PdfMerger

tool1_bp = Blueprint('tool1', __name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
TOOL_DIR = os.path.join(BASE_DIR, 'app_files', 'tools_files', '01_pdf_combiner')
TEMP_DIR = os.path.join(TOOL_DIR, 'temp')
SAVE_DIR = os.path.join(TOOL_DIR, 'save')
COUNTER_FILE = os.path.join(TOOL_DIR, 'counter.txt')

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

@tool1_bp.route('/tools/tool1')
def tool1():
    return render_template('tools/tool1.html', active_page='tool1')

@tool1_bp.route('/tools/tool1/upload', methods=['POST'])
def upload_pdfs():
    files = request.files.getlist('files')
    
    if not files:
        return jsonify({'error': 'No files uploaded'}), 400
    
    # Check if all files are PDFs
    for file in files:
        if not file.filename.endswith('.pdf'):
            return jsonify({'error': 'All files must be PDF'}), 400
    
    # Increment counter and create folders
    counter = increment_counter()
    temp_folder = os.path.join(TEMP_DIR, str(counter))
    save_folder = os.path.join(SAVE_DIR, str(counter))
    os.makedirs(temp_folder, exist_ok=True)
    os.makedirs(save_folder, exist_ok=True)
    
    # Save files with numbered names
    for idx, file in enumerate(files, 1):
        filename = f"{idx}.pdf"
        file.save(os.path.join(temp_folder, filename))
    
    # Combine PDFs
    merger = PdfMerger()
    for idx in range(1, len(files) + 1):
        merger.append(os.path.join(temp_folder, f"{idx}.pdf"))
    
    combined_path = os.path.join(save_folder, 'combined.pdf')
    merger.write(combined_path)
    merger.close()
    
    return jsonify({'success': True, 'counter': counter})

@tool1_bp.route('/tools/tool1/download/<int:counter>')
def download_pdf(counter):
    file_path = os.path.join(SAVE_DIR, str(counter), 'combined.pdf')
    return send_file(file_path, as_attachment=True, download_name='combined.pdf')
