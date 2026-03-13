from flask import Blueprint, render_template

gallery_bp = Blueprint('gallery', __name__)

@gallery_bp.route('/gallery')
def gallery_page():
    return render_template('gallery/index.html')
