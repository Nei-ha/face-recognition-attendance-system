import cv2
import os
import numpy as np
from supabase import create_client
import requests

# Supabase credentials
SUPABASE_URL = "https://cqfrdqlgjdvcpriatakh.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNxZnJkcWxnamR2Y3ByaWF0YWtoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ3NDgzNTAsImV4cCI6MjA5MDMyNDM1MH0.j5LuQoCHL_1VLOXGhkHdWu4pNhr2oXpQebyFV18qiMw"
supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Directory to store temporary captured images
IMAGE_DIR = "captured_faces"
os.makedirs(IMAGE_DIR, exist_ok=True)

# Load Haar Cascade for face detection
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

def is_image_clear(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    return laplacian_var > 100  # Higher value means clearer image

def capture_image(filename):
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open camera.")
        return None

    print("Press 'Space' to capture the image and 'Esc' to exit.")
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to capture image")
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5, minSize=(100, 100))
        
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

        cv2.imshow("Capture Image", frame)
        key = cv2.waitKey(1)

        if key == 32 and len(faces) > 0:  # Space key to capture
            (x, y, w, h) = faces[0]  # Take the first detected face
            face_img = frame[y:y+h, x:x+w]
            
            if is_image_clear(face_img):
                img_path = os.path.join(IMAGE_DIR, filename)
                cv2.imwrite(img_path, face_img)
                print(f"Image saved as {img_path}")
                break
            else:
                print("Image unclear. Please try again.")
        elif key == 27:  # Escape key to exit
            print("Image capture canceled.")
            break

    cap.release()
    cv2.destroyAllWindows()
    return img_path if 'img_path' in locals() else None

def upload_image_to_supabase(image_path, storage_path):
    with open(image_path, "rb") as img_file:
        image_data = img_file.read()
    
    response = supabase_client.storage.from_("user-images").upload(storage_path, image_data, {"content-type": "image/jpeg"})
    
    if response:
        print("Image uploaded successfully!")
        return f"{SUPABASE_URL}/storage/v1/object/public/user_images/{storage_path}"
    else:
        print("Error uploading image:", response)
        return None

def add_student():
    name = input("Enter Student Name: ")
    rollno = input("Enter Roll Number: ")
    branch = input("Enter Branch: ")
    semester = int(input("Enter Semester: "))  
    section = input("Enter Section: ")
    contact = int(input("Enter Contact Number: "))

    img_filename = f"{rollno}_{name.replace(' ', '')}.jpg"
    image_path = capture_image(img_filename)
    
    if image_path:
        storage_path = f"students/{img_filename}"
        image_url = upload_image_to_supabase(image_path, storage_path)
        
        if image_url:
            data = {
                "name": name,
                "rollno": rollno,
                "branch": branch,
                "semester": semester,
                "section": section,
                "contact": contact,
                "image_url": image_url
            }
            response = supabase_client.table("student").insert(data).execute()
            print("Student added successfully!", response)

def add_faculty():
    name = input("Enter Faculty Name: ")
    faculty_id = input("Enter Faculty ID: ")
    contact = input("Enter Contact Number: ")
    
    img_filename = f"{faculty_id}_{name.replace(' ', '')}.jpg"
    image_path = capture_image(img_filename)
    
    if image_path:
        storage_path = f"faculty/{img_filename}"
        image_url = upload_image_to_supabase(image_path, storage_path)
        
        if image_url:
            data = {
                "name": name,
                "faculty_id": faculty_id,
                "contact": contact,
                "image_url": image_url
            }
            response = supabase_client.table("faculty").insert(data).execute()
            print("Faculty added successfully!", response)

def main():
    print("1. Add Student\n2. Add Faculty")
    choice = input("Enter choice (1/2): ")
    if choice == "1":
        add_student()
    elif choice == "2":
        add_faculty()
    else:
        print("Invalid choice")

if __name__ == "__main__":
    main()
