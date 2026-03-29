import cv2
import os
import numpy as np
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO
from supabase import create_client
import smtplib
import random
import string
from email.mime.text import MIMEText
from dotenv import load_dotenv

# Flask and SocketIO setup
app = Flask(__name__)
CORS(app)  # Allow frontend requests from different origins

socketio = SocketIO(app, cors_allowed_origins="*")



# Supabase credentials
SUPABASE_URL = "https://cqfrdqlgjdvcpriatakh.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNxZnJkcWxnamR2Y3ByaWF0YWtoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ3NDgzNTAsImV4cCI6MjA5MDMyNDM1MH0.j5LuQoCHL_1VLOXGhkHdWu4pNhr2oXpQebyFV18qiMw"
supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Load .env variables
load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")  # e.g., your Gmail
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")  # App password

otp_store = {}

def generate_otp():
    return ''.join(random.choices(string.digits, k=6))

def send_otp_email(recipient_email, otp):
    subject = "Your OTP for Signup Verification"
    body = f"Your OTP is: {otp}\n\nYou entered email: {recipient_email}\n\nRegards,\nFace Recognition System"
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = recipient_email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, recipient_email, msg.as_string())

def send_credentials_email(email, username, password, role):
    subject = f"{role.capitalize()} Registration Successful"
    body = f"Hello,\n\nYour {role} account has been created successfully!\n\nUsername: {username}\nPassword: {password}\n\nRegards,\nFace Recognition System"
    
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, email, msg.as_string())
    except Exception as e:
        print(f"Error sending credentials email: {e}")


@socketio.on("send_otp")
def handle_send_otp(data):
    email = data["email"]
    otp = generate_otp()
    otp_store[email] = otp
    send_otp_email(email, otp)
    socketio.emit("otp_sent", {"msg": f"OTP sent to {email}"})

@socketio.on("verify_otp")
def handle_verify_otp(data):
    email = data["email"]
    entered_otp = data["otp"]

    if otp_store.get(email) == entered_otp:
        socketio.emit("otp_verified", {"success": True, "email": email})
    else:
        socketio.emit("otp_verified", {"success": False})

# Directory to store temporary captured images
IMAGE_DIR = "captured_faces"
os.makedirs(IMAGE_DIR, exist_ok=True)

# Load Haar Cascade for face detection
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

def is_image_clear(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    return laplacian_var > 100

def capture_image(filename):
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        socketio.emit("message", {"msg": "Error: Could not open camera."})
        return None

    socketio.emit("message", {"msg": "Press 'Space' to capture the image and 'Esc' to exit."})
    while True:
        ret, frame = cap.read()
        if not ret:
            socketio.emit("message", {"msg": "Failed to capture image"})
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5, minSize=(100, 100))
        
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

        cv2.imshow("Capture Image", frame)
        key = cv2.waitKey(1)

        if key == 32 and len(faces) > 0:
            (x, y, w, h) = faces[0]
            face_img = frame[y:y+h, x:x+w]
            
            if is_image_clear(face_img):
                img_path = os.path.join(IMAGE_DIR, filename)
                cv2.imwrite(img_path, face_img)
                socketio.emit("message", {"msg": f"Image saved as {img_path}"})
                break
            else:
                socketio.emit("message", {"msg": "Image unclear. Please try again."})
        elif key == 27:
            socketio.emit("message", {"msg": "Image capture canceled."})
            break

    cap.release()
    cv2.destroyAllWindows()
    return img_path if 'img_path' in locals() else None

def upload_image_to_supabase(image_path, storage_path):
    with open(image_path, "rb") as img_file:
        image_data = img_file.read()

    response = supabase_client.storage.from_("user-images").upload(
        storage_path, image_data, {"content-type": "image/jpeg"}
    )

    if isinstance(response, dict) and "error" in response:
        socketio.emit("message", {"msg": f"Error uploading image: {response['error']}"})
        return None
    else:
        socketio.emit("message", {"msg": "📸Image uploaded successfully!"})
        return f"{SUPABASE_URL}/storage/v1/object/public/user_images/{storage_path}"


def add_student(data):
    name = data["name"]
    rollno = data["rollno"]
    branch = data["branch"]
    semester = data["semester"]
    section = data["section"]
    contact = data["contact"]
    username = data["username"]

    img_filename = f"{rollno}_{name.replace(' ', '')}.jpg"
    image_path = capture_image(img_filename)

    if image_path:
        storage_path = f"students/{img_filename}"
        image_url = upload_image_to_supabase(image_path, storage_path)

        if image_url:
            student_data = {
                "name": name,
                "rollno": rollno,
                "branch": branch,
                "semester": semester,
                "section": section,
                "contact": contact,
                "image_url": image_url
            }
            response = supabase_client.table("student").insert(student_data).execute()

            if response.data:
                credentials_data = {
                    "username": username,
                    "password": rollno,
                    "rollno": rollno,
                    "role": "user"
                }
                supabase_client.table("student_credentials").insert(credentials_data).execute()
                send_credentials_email(email=username, username=username, password=rollno, role="student")

            else:
                
                socketio.emit("message", {"msg":"Error inserting student:"})


def add_faculty(data):
    name = data["name"]
    faculty_id = data["faculty_id"]
    contact = data["contact"]
    username = data["username"]
    
    img_filename = f"{faculty_id}_{name.replace(' ', '')}.jpg"
    image_path = capture_image(img_filename)
    
    if image_path:
        storage_path = f"faculty/{img_filename}"
        image_url = upload_image_to_supabase(image_path, storage_path)
        
        if image_url:
            faculty_data = {
                "name": name,
                "faculty_id": faculty_id,
                "contact": contact,
                "image_url": image_url
            }
            response = supabase_client.table("faculty").insert(faculty_data).execute()
            socketio.emit("message", {"msg": "Faculty Table Insert Response:"}) 
            if response.data:
                credentials_data = {
                    "username": username,
                    "password": faculty_id,
                    "faculty_id": faculty_id,
                    "role": "faculty"
                }
                supabase_client.table("faculty_credentials").insert(credentials_data).execute()
                send_credentials_email(email=username, username=username, password=faculty_id, role="faculty")

            else:
                
                socketio.emit("message", {"msg":"Error inserting faculty:"})

@socketio.on("add_student")
def handle_add_student(data):
    try:
        add_student(data)
        socketio.emit("message", {"msg": "Student added successfully!"})
        socketio.emit("message", {"msg": "🎉 All done!"})
        socketio.emit("registration_complete")
    except Exception as e:
        print(f"Supabase Query Error: {str(e)}")  # Print error in backend
        socketio.emit("message", {"msg": f"Error: {str(e)}"})            


@socketio.on("add_faculty")
def handle_add_faculty(data):
    try:
        add_faculty(data)  # Call function only if valid
        socketio.emit("message", {"msg": "Faculty added successfully!"})
        socketio.emit("message", {"msg": "🎉 All done!"})
        socketio.emit("registration_complete")
    except Exception as e:
        print(f"Supabase Query Error: {str(e)}")  # Print error in backend
        socketio.emit("message", {"msg": f"Server error: {str(e)}"})


@app.route("/")
def index():
    return render_template("signup.html")

if __name__ == "__main__":
    socketio.run(app, debug=True, port=5002)
