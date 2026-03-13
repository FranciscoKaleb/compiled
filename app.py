from flask import Flask, render_template
from model_cache import set_base_path
from routes.models.page1 import page1_bp
from routes.models.page2 import page2_bp
from routes.models.page3 import page3_bp
from routes.models.page4 import page4_bp
from routes.models.page5 import page5_bp
from routes.models.page6 import page6_bp
from routes.models.page7 import page7_bp
from routes.models.page8 import page8_bp
from routes.models.page9 import page9_bp
from routes.models.page10 import page10_bp
from routes.models.page11 import page11_bp
from routes.models.page12 import page12_bp
from routes.models.page13 import page13_bp
from routes.tools.pdf_combiner import tool1_bp
from routes.tools.bg_remover import tool2_bp
from routes.tools.reduce_quality import tool3_bp
from routes.blockchain import blockchain_bp
from routes.blockchain2 import blockchain2_bp
from routes.gallery import gallery_bp
from db_config import init_db
import os

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
app.secret_key = 'your-secret-key-change-this'

set_base_path(os.path.dirname(__file__))
init_db()

# Register model blueprints
app.register_blueprint(page1_bp)
app.register_blueprint(page2_bp)
app.register_blueprint(page3_bp)
app.register_blueprint(page4_bp)
app.register_blueprint(page5_bp)
app.register_blueprint(page6_bp)
app.register_blueprint(page7_bp)
app.register_blueprint(page8_bp)
app.register_blueprint(page9_bp)
app.register_blueprint(page10_bp)
app.register_blueprint(page11_bp)
app.register_blueprint(page12_bp)
app.register_blueprint(page13_bp)

# Register tool blueprints
app.register_blueprint(tool1_bp)
app.register_blueprint(tool2_bp)
app.register_blueprint(tool3_bp)

# Register blockchain blueprints
app.register_blueprint(blockchain_bp)
app.register_blueprint(blockchain2_bp)

# Register gallery blueprint
app.register_blueprint(gallery_bp)

@app.route('/')
def home():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
