from flask import Flask, render_template, Response, request, jsonify, session , send_from_directory
from flask_cors import CORS
import face_recognition
import cv2
import os
import time
import numpy as np
from supabase import create_client
from time import sleep
import json
import sys
from flask_socketio import SocketIO, emit

app = Flask(__name__)
CORS(app)  # Enable CORS if needed
socketio = SocketIO(app, cors_allowed_origins="*")

@app.route('/thankyou.wav')
def get_wav():
    return send_from_directory('.', 'thankyou.wav')

# Flask route for sending the warning sound
@app.route('/warning.mp3')
def get_warning_mp3():
    return send_from_directory('.', 'warning.mp3')

# Define the path to images for the status
image_status_map = {
    "already_marked": "image_status/already_marked.png",
    "unregistered": "image_status/unregistered.png",
    "marked": "image_status/marked.png",
    "align_face": "image_status/align_face.png",
    "phone_detected": "image_status/device.png"
}

@socketio.on('connect')
def handle_connect():
    print("Client connected")

# Collect messages to send to the frontend
response_messages = []

@app.route("/")
def attendance():
    return "Attendance System Running"

# Supabase credentials
SUPABASE_URL = "https://cqfrdqlgjdvcpriatakh.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNxZnJkcWxnamR2Y3ByaWF0YWtoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ3NDgzNTAsImV4cCI6MjA5MDMyNDM1MH0.j5LuQoCHL_1VLOXGhkHdWu4pNhr2oXpQebyFV18qiMw"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Image directory
KNOWN_FACES_DIR = "captured_faces"
os.makedirs(KNOWN_FACES_DIR, exist_ok=True)

# Flask route to start attendance
@app.route('/start_attendance', methods=['POST'])
def start_attendance():
    global response_messages  # Keep track of messages
    response_messages = []  # Reset messages for a new request
    try:
        data = request.json
        course_id = data.get("course_id")
        faculty_id = data.get("faculty_id")
        section = data.get("section")
        num_classes = int(data.get("num_classes"))

        if not all([course_id, faculty_id, section, num_classes]):
            return jsonify({"error": "Missing input fields"}), 400

        # Call main function (face detection & attendance)
        main(course_id, faculty_id, section, num_classes)

        # Return collected messages to frontend
        return jsonify({"messages": response_messages})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Define fixed face alignment box (X, Y, Width, Height)
ALIGN_BOX = (200, 100, 250, 300)


def load_known_faces():
    known_encodings = []
    known_rollnos = []
    
    for filename in os.listdir(KNOWN_FACES_DIR):
        path = os.path.join(KNOWN_FACES_DIR, filename)
        image = face_recognition.load_image_file(path)
        encoding = face_recognition.face_encodings(image)

        if encoding:  # Ensure encoding exists
            rollno = '_'.join(filename.split('_')[:3])  # Extract roll number (first 3 parts)
            known_encodings.append(encoding[0])
            known_rollnos.append(rollno)
        else:
            print(f" Warning: No face detected in {filename}")
    
    print(f" Loaded {len(known_encodings)} known faces.")
    return known_encodings, known_rollnos



    
def update_total_classes(course_id, section, faculty_id, num_classes):
    """
    Updates the total_classes column by incrementing it for all students 
    in the given course and section (only once per session).
    """
    try:
        # Fetch all records where course_id, section, and faculty_id match
        response = supabase.table("attendance").select("rollno, total_classes") \
            .eq("course_id", course_id).eq("section", section).eq("faculty_id", faculty_id).execute()
        
        if response.data:
            # Increment total_classes for all matching students
            update_response = supabase.table("attendance").update({
                "total_classes": response.data[0]['total_classes'] + num_classes
            }).eq("course_id", course_id).eq("section", section).eq("faculty_id", faculty_id).execute()

            if update_response.data:
                print(f" Total classes updated (+{num_classes}) for Course: {course_id}, Section: {section}")
            else:
                print(" Failed to update total classes")
        else:
            print(f" No students found in attendance for Course {course_id}, Section {section}")
    except Exception as e:
        print(f"Database Error: {e}")

def mark_attendance(rollno, course_id, num_classes):
    try:
        # Fetch current attendance data
        response = supabase.table("attendance").select("classes_attended, total_classes") \
            .eq("rollno", rollno).eq("course_id", course_id).execute()
        
        if response.data:
            data = response.data[0]
            current_attended = data['classes_attended']
            
            # Update attendance
            update_response = supabase.table("attendance").update({
                "classes_attended": current_attended + num_classes
            }).eq("rollno", rollno).eq("course_id", course_id).execute()
            
            if update_response.data:
                print(f" Attendance updated for Roll No: {rollno} (+{num_classes} classes attended)")
            else:
                print(f" Failed to update attendance for {rollno}")
        else:
            print(f" Roll No {rollno} not found in attendance table for course {course_id}")
    except Exception as e:
        print(f"Database Error: {e}")


def main(course_id, faculty_id, section, num_classes):
  
    
    # Load known faces
    known_encodings, known_rollnos = load_known_faces()
    
    


    if not known_encodings:
        socketio.emit("attendance_status", {"message": " No known faces found. Exiting..."})
        return 

    # Update total_classes ONCE for the session
    update_total_classes(course_id, section, faculty_id, num_classes)



    # Open webcam
    video_capture = cv2.VideoCapture(0)
    last_detected_time = time.time()
    marked_students = set()  # Track students already marked in this session

    # Fixed face alignment box (centered)
    box_size = 200  # Adjust size for proper alignment
    frame_width = int(video_capture.get(3))
    frame_height = int(video_capture.get(4))
    box_x1 = (frame_width // 2) - (box_size // 2)
    box_y1 = (frame_height // 2) - (box_size // 2)
    box_x2 = box_x1 + box_size
    box_y2 = box_y1 + box_size

    last_message = ""

    while True:
    
        ret, frame = video_capture.read()
        if not ret:
            socketio.emit("attendance_status", {"message": f" Webcam not detected. Exiting..."})
            break

        # Convert to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Detect face locations
        face_locations = face_recognition.face_locations(rgb_frame)

        if face_locations:
            print(f" Detected {len(face_locations)} face(s).")

        # Encode faces
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

        for face_encoding, face_location in zip(face_encodings, face_locations):
            top, right, bottom, left = face_location

            # Check if the region contains a phone (simplified placeholder logic)
            is_phone_screen = check_for_phone_screen(frame, top, right, bottom, left)
            if is_phone_screen:
                # If a phone is detected, do not mark attendance, and play a warning
                socketio.emit("attendance_status", {
                    "image": image_status_map["phone_detected"],
                    "message": " Phone screen detected. Attendance cannot be marked.",
                    'phone_detected': True
                })
                socketio.emit("play_warning_sound", {"play_sound": True})
                continue  #  Use continue to skip marking but not exit

            # Ensure face is within the fixed rectangle
            margin = 10  # Allow slight flexibility
            if (left >= box_x1 - margin and right <= box_x2 + margin and
                top >= box_y1 - margin and bottom <= box_y2 + margin):

                matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.5)
                distances = face_recognition.face_distance(known_encodings, face_encoding)
                if len(distances) > 0:
                    best_match_index = np.argmin(distances)
                    if distances[best_match_index] > 0.5:  # Confidence threshold
                        best_match_index = None  # Reject false positives
                else:
                    best_match_index = None


                if best_match_index is not None and matches[best_match_index]:
                    rollno = known_rollnos[best_match_index]
                    
                    if rollno in marked_students:
                        image = image_status_map["already_marked"]
                        new_message = f" Attendance already marked for {rollno}"
                        if new_message != last_message:
                            socketio.emit("attendance_status", {"image": image, "message": new_message})
                            last_message = new_message
                    else:
                        mark_attendance(rollno, course_id, num_classes)
                        marked_students.add(rollno)  # Mark this student for this session
                        image = image_status_map["marked"]
                        new_message = f" Marked attendance for {rollno}"
                        if new_message != last_message:
                            socketio.emit("attendance_status", {
                                "image": image, 
                                "message": new_message,
                                "play_sound": True  # <-- Add this flag
                            })
                            last_message = new_message

                    # Draw green rectangle for recognized face
                    cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                    cv2.putText(frame, rollno, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                else:
                    # If no match found, treat as unregistered
                    image = image_status_map["unregistered"]
                    new_message = " Unregistered face detected"
                    if new_message != last_message:
                        socketio.emit("attendance_status", {"image": image, "message": new_message})
                        last_message = new_message

                    cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)
                    cv2.putText(frame, "Unregistered", (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

            else:
                image = image_status_map["align_face"]
                new_message = " Please align your face within the box"
                if new_message != last_message:
                    socketio.emit("attendance_status", {"image": image, "message": new_message})
                    last_message = new_message



        # Draw fixed alignment rectangle
        cv2.rectangle(frame, (box_x1, box_y1), (box_x2, box_y2), (255, 255, 0), 2)
        cv2.putText(frame, "Align Your Face Here", (box_x1, box_y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

        # Show the video frame
        cv2.imshow("Attendance System", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            socketio.emit("attendance_status", {"message": f"Exiting Attendance Session..."})
            break

    video_capture.release()
    cv2.destroyAllWindows()
    return response_messages
# Simple function to detect phone screen (Placeholder Logic)
def check_for_phone_screen(frame, top, right, bottom, left):
    face_region = frame[top:bottom, left:right]

    if face_region.size == 0:
        return False

    # Convert to grayscale and compute mean brightness
    gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
    mean_brightness = np.mean(gray)

    # Threshold based on brightness - adjust as needed
    return mean_brightness > 180  # 180 is a brightness threshold (tweak if needed)


if __name__ == "__main__":
    socketio.run(app, debug=True, port=5001)
