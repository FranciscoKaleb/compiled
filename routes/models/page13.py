from flask import Blueprint, render_template, Response
import cv2
from insightface.app import FaceAnalysis
import numpy as np
from db_config import get_db_connection
import pickle

page13_bp = Blueprint('model13', __name__)

face_app = None
tracked_faces = {}
embedding_cache = None

def init_face_detector():
    global face_app
    if face_app is None:
        face_app = FaceAnalysis(providers=['CPUExecutionProvider'])
        face_app.prepare(ctx_id=0, det_size=(320, 320))
    return face_app

def load_embeddings_cache():
    global embedding_cache
    if embedding_cache is None:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, embedding FROM users")
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        embedding_cache = []
        for name, embedding_blob in results:
            embedding = pickle.loads(embedding_blob)
            embedding_cache.append((name, embedding))
    return embedding_cache

def recognize_face(embedding, threshold=0.65):
    db_faces = load_embeddings_cache()
    if len(db_faces) == 0:
        return "Unknown"
    
    embeddings_array = np.array([e[1] for e in db_faces])
    similarities = np.dot(embeddings_array, embedding) / (np.linalg.norm(embeddings_array, axis=1) * np.linalg.norm(embedding))
    best_idx = np.argmax(similarities)
    best_similarity = similarities[best_idx]
    
    if best_similarity >= threshold:
        return db_faces[best_idx][0]
    return "Unknown"

def calculate_iou(box1, box2):
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - intersection
    
    return intersection / union if union > 0 else 0

def generate_frames():
    global tracked_faces, embedding_cache
    embedding_cache = None
    load_embeddings_cache()
    
    camera = cv2.VideoCapture(0)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    camera.set(cv2.CAP_PROP_FPS, 24)
    
    detector = init_face_detector()
    frame_count = 0
    
    while True:
        success, frame = camera.read()
        if not success:
            break
        
        frame_count += 1
        if frame_count % 10 == 0:
            faces = detector.get(frame)
            new_tracked = {}
            
            for face in faces:
                bbox = face.bbox.astype(int)
                bbox_tuple = tuple(bbox)
                
                matched = False
                for tracked_bbox, face_data in tracked_faces.items():
                    if calculate_iou(bbox, tracked_bbox) > 0.5:
                        if face_data['confirmed']:
                            new_tracked[bbox_tuple] = face_data
                        else:
                            name = recognize_face(face.embedding)
                            if name == face_data['name']:
                                face_data['match_count'] += 1
                                if face_data['match_count'] >= 2:
                                    face_data['confirmed'] = True
                            else:
                                face_data['name'] = name
                                face_data['match_count'] = 1
                            new_tracked[bbox_tuple] = face_data
                        matched = True
                        break
                
                if not matched:
                    name = recognize_face(face.embedding)
                    new_tracked[bbox_tuple] = {
                        'name': name,
                        'match_count': 1,
                        'confirmed': False
                    }
            
            tracked_faces = new_tracked
        
        for bbox, face_data in tracked_faces.items():
            cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), 2)
            cv2.putText(frame, face_data['name'], (bbox[0], bbox[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@page13_bp.route('/models/insightface5')
def model13_page():
    return render_template('models/page13.html', active_page='model13')

@page13_bp.route('/video_feed13')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
