print("Flask App is Starting...")
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
from flask_mysqldb import MySQL
import cv2
import numpy as np
import os
import time
import base64
from ultralytics import YOLO
from reportlab.pdfgen import canvas
from datetime import datetime
import tempfile

app = Flask(__name__, static_url_path='/static')
CORS(app)

# Serve the homepage
@app.route('/')
def home():
    return render_template("index.html")

# MySQL Configuration
app.config['MYSQL_HOST'] = 'sql7.freesqldatabase.com'
app.config['MYSQL_USER'] = 'sql7772889'
app.config['MYSQL_PASSWORD'] = 'fhUSkTElXj'
app.config['MYSQL_DB'] = 'sql7772889'
app.config['MYSQL_PORT'] = 3306 

mysql = MySQL(app)

# Load YOLO Model
model = YOLO("best (1).pt")

UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), "road_defects_uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Live Frame-based Defect Detection with Bounding Boxes
@app.route('/detect_frame', methods=['POST'])
def detect_frame():
    file = request.files['frame']
    latitude = request.form.get('latitude')
    longitude = request.form.get('longitude')
    nparr = np.frombuffer(file.read(), np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    results = model(frame)
    defects = []
    for r in results:
        for box in r.boxes.xyxy:
            x1, y1, x2, y2 = map(int, box)
            defect_type = r.names[int(r.boxes.cls[0])]
            defects.append({"type": defect_type, "x1": x1, "y1": y1, "x2": x2, "y2": y2, "latitude": latitude, "longitude": longitude})
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cv2.putText(frame, defect_type, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    
    _, img_encoded = cv2.imencode('.jpg', frame)
    img_base64 = base64.b64encode(img_encoded).decode('utf-8')
    return jsonify({"defects": defects, "image": img_base64})

# Video-based Defect Detection and Storage
@app.route('/detect', methods=['POST'])
def detect():
    file = request.files['video']
    road_id = request.form['road_id']
    video_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(video_path)  # Save the uploaded video

    # Process the video and save the annotated version
    cap = cv2.VideoCapture(video_path)
    output_path = os.path.join(UPLOAD_FOLDER, "annotated_" + file.filename)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, 20.0, (int(cap.get(3)), int(cap.get(4))))

    defect_data = []
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        results = model(frame)
        for r in results:
            for box in r.boxes.xyxy:
                x1, y1, x2, y2 = map(int, box)
                defect_type = r.names[int(r.boxes.cls[0])]
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                cv2.putText(frame, defect_type, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                defect_data.append((road_id, defect_type, x1, y1, x2, y2))
        out.write(frame)

    cap.release()
    out.release()

    # Save defect data and video path to the database
    cursor = mysql.connection.cursor()
    for defect in defect_data:
        cursor.execute("INSERT INTO defects (road_id, defect_type, x1, y1, x2, y2) VALUES (%s, %s, %s, %s, %s, %s)", defect)
    cursor.execute("INSERT INTO videos (road_id, file_path) VALUES (%s, %s)", (road_id, output_path))
    mysql.connection.commit()
    cursor.close()

    # Calculate condition rating
    condition_rating = calculate_condition_rating(defect_data)

    # Automatically generate and save the PDF report
    generate_pdf_report(road_id, condition_rating)

    return jsonify({
        "annotated_video": output_path,
        "defects": defect_data,
        "condition_rating": condition_rating
    })
    
    # Automatically generate and save the PDF report
    generate_pdf_report(road_id)

    return jsonify({"annotated_video": output_path, "defects": defect_data})

# Helper function to generate and save the PDF report
def generate_pdf_report(road_id, condition_rating):
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT * FROM defects WHERE road_id=%s", (road_id,))
    defects = cursor.fetchall()

    pdf_path = os.path.join(UPLOAD_FOLDER, f"report_{road_id}.pdf")
    c = canvas.Canvas(pdf_path)
    c.drawString(100, 800, f"Condition Survey Report - Road ID: {road_id}")
    c.drawString(100, 780, f"Condition Rating: {condition_rating}%")

    y_position = 760
    for defect in defects:
        c.drawString(100, y_position, f"Defect: {defect[2]}, Location: ({defect[3]}, {defect[4]})")
        y_position -= 20

    c.save()
    cursor.execute("INSERT INTO reports (road_id, report_path, condition_rating) VALUES (%s, %s, %s)", (road_id, pdf_path, condition_rating))
    mysql.connection.commit()
    cursor.close()

# Define defect weights
DEFECT_WEIGHTS = {
        "stairstep_crack":5,
        "Roboflow is an end-to-end computer vision platform that helps you":3,
        "Rebar exposure - v4 2024-05-30 11-39am": 2,
        "Terminus V1 - v2 2024-10-09 10-12am":1,
        "Drobi Vision Crack - v2 2023-10-12 9-27am": 4,
        "This dataset was exported via roboflow.com on October 20- 2024 at 9-23 AM GMT":2,
        "damage_detection - v3 2024-10-23 9-09am":3,
        "This dataset was exported via roboflow.com on October 29- 2024 at 10-47 AM GMT":1,
        "-":1,
        "crack": 5
}

# Calculate condition rating
def calculate_condition_rating(defects):
    total_weight = 0
    for defect in defects:
        defect_type = defect[1].lower()  # defect_type is the 2nd element in the tuple
        total_weight += DEFECT_WEIGHTS.get(defect_type, 1)  # Default weight is 1
    # Normalize the rating to a scale of 0-100 (higher is better)
    max_weight = len(defects) * max(DEFECT_WEIGHTS.values())
    if max_weight == 0:
        return 100  # No defects, perfect condition
    condition_rating = 100 - (total_weight / max_weight) * 100
    return round(condition_rating, 2)

# Fetch Defect Locations for Live Map
@app.route('/get_defects', methods=['GET'])
def get_defects():
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT road_id, defect_type, latitude, longitude FROM defects")
    defects = cursor.fetchall()
    cursor.close()
    return jsonify(defects)

# Download video
@app.route('/download_video/<int:file_id>', methods=['GET'])
def download_video(file_id):
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT file_path FROM videos WHERE id = %s", (file_id,))
    result = cursor.fetchone()
    cursor.close()

    if result:
        file_path = result[0]
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            return jsonify({"error": "File not found"}), 404
    return jsonify({"error": "Invalid file ID"}), 400

# Download report
@app.route('/download_report/<int:file_id>', methods=['GET'])
def download_report(file_id):
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT report_path FROM reports WHERE id = %s", (file_id,))
    result = cursor.fetchone()
    cursor.close()

    if result:
        file_path = result[0]
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            return jsonify({"error": "File not found"}), 404
    return jsonify({"error": "Invalid file ID"}), 400

# Fetch all videos and reports
@app.route('/get_files', methods=['GET'])
def get_files():
    cursor = mysql.connection.cursor()
    
    # Fetch videos
    cursor.execute("SELECT id, road_id, file_path FROM videos")
    videos = cursor.fetchall()
    
    # Fetch reports
    cursor.execute("SELECT id, road_id, report_path, condition_rating FROM reports")
    reports = cursor.fetchall()
    
    cursor.close()
    return jsonify({"videos": videos, "reports": reports})

# Rename a video or report
@app.route('/rename_file', methods=['POST'])
def rename_file():
    data = request.json
    file_type = data.get('type')  # 'video' or 'report'
    file_id = data.get('id')
    new_name = data.get('new_name')
    
    if not file_type or not file_id or not new_name:
        return jsonify({"error": "Missing parameters"}), 400
    
    cursor = mysql.connection.cursor()
    try:
        if file_type == 'video':
            cursor.execute("UPDATE videos SET file_path = %s WHERE id = %s", (new_name, file_id))
        elif file_type == 'report':
            cursor.execute("UPDATE reports SET report_path = %s WHERE id = %s", (new_name, file_id))
        mysql.connection.commit()
        cursor.close()
        return jsonify({"message": "File renamed successfully"})
    except Exception as e:
        cursor.close()
        return jsonify({"error": str(e)}), 500

# Delete a video or report
@app.route('/delete_file', methods=['POST'])
def delete_file():
    data = request.json
    file_type = data.get('type')  # 'video' or 'report'
    file_id = data.get('id')
    
    if not file_type or not file_id:
        return jsonify({"error": "Missing parameters"}), 400
    
    cursor = mysql.connection.cursor()
    try:
        if file_type == 'video':
            cursor.execute("DELETE FROM videos WHERE id = %s", (file_id,))
        elif file_type == 'report':
            cursor.execute("DELETE FROM reports WHERE id = %s", (file_id,))
        mysql.connection.commit()
        cursor.close()
        return jsonify({"message": "File deleted successfully"})
    except Exception as e:
        cursor.close()
        return jsonify({"error": str(e)}), 500
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))