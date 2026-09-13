"""Development entry point.

    python run.py                 # http://127.0.0.1:5000
    PORT=5055 python run.py       # another port
    flask --app run <command>     # db upgrade, routes-smoke, faces ...
"""
import os

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(
        host=os.environ.get('HOST', '127.0.0.1'),
        port=int(os.environ.get('PORT', 5000)),
        debug=app.config['DEBUG'],
        threaded=True,          # long-polling, SSE and WebSockets each hold a thread
    )
