from flask import Blueprint, render_template, request, jsonify
from model_cache import get_model, get_tokenizer, get_processor
from PIL import Image
import torch
import base64
from io import BytesIO

page6_bp = Blueprint('model6', __name__)

@page6_bp.route('/models/objectdetection4')
def model6_page():
    return render_template('models/page6.html', active_page='model6')

@page6_bp.route('/models/objectdetection4/predict', methods=['POST'])
def predict6():
    file = request.files['image']
    image = Image.open(file.stream).convert('RGB')
    
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    try:
        inputs = get_processor('model6').image_processor(
            image, 
            return_tensors="pt",
            do_crop_margin=True,
            do_align_long_axis=False,
            do_pad=True
        )
        pixel_values = inputs.pixel_values
        
        with torch.inference_mode():
            generated_ids = get_model('model6').generate(
                pixel_values,
                max_new_tokens=1024,
                do_sample=False
            )
        
        text = get_processor('model6').batch_decode(generated_ids, skip_special_tokens=True)[0]
    except Exception as e:
        text = f"Error: {str(e)}"
    
    return jsonify({'text': text, 'image_data': img_str})
