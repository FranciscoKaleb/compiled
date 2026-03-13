from flask import Blueprint, render_template, Response, current_app
import cv2
from insightface.app import FaceAnalysis
import time

page12_bp = Blueprint('model12', __name__)

face_app = None

def init_face_detector():
    global face_app
    if face_app is None:
        face_app = FaceAnalysis(providers=['CPUExecutionProvider'])
        face_app.prepare(ctx_id=0, det_size=(320, 320))
    return face_app

def generate_frames():
    camera = cv2.VideoCapture(0)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    camera.set(cv2.CAP_PROP_FPS, 30)
    
    detector = init_face_detector()
    frame_skip = 2
    frame_count = 0
    
    while True:
        success, frame = camera.read()
        if not success:
            break
        
        frame_count += 1
        if frame_count % frame_skip == 0:
            faces = detector.get(frame)
            
            for face in faces:
                bbox = face.bbox.astype(int)
                cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), 2)
        
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@page12_bp.route('/models/insightface4')
def model12_page():
    return render_template('models/page12.html', active_page='model12')

@page12_bp.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
