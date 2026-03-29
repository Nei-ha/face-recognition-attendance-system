from flask import Flask, render_template, Response, request, jsonify, session
from flask_cors import CORS
from supabase import create_client # Correct import for Supabase
import subprocess
import sys
from flask_socketio import SocketIO, emit




app = Flask(__name__)
CORS(app)  # Allow frontend requests from different origins

socketio = SocketIO(app, cors_allowed_origins="*")

@socketio.on('connect')
def handle_connect():
    print("Client connected")



# Use the Python interpreter from the current environment
subprocess.Popen([sys.executable, "att.py"])

subprocess.Popen([sys.executable, "signup.py"])
@app.route('/home')
def home_page():
    return "Welcome to the Home Page!"  # Replace with render_template('home.html') when ready


# Initialize Supabase client
SUPABASE_URL = "https://cqfrdqlgjdvcpriatakh.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNxZnJkcWxnamR2Y3ByaWF0YWtoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ3NDgzNTAsImV4cCI6MjA5MDMyNDM1MH0.j5LuQoCHL_1VLOXGhkHdWu4pNhr2oXpQebyFV18qiMw"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# LOGIN API
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    login_type = data.get('login_type')

    if not username or not password or not login_type:
        return jsonify({'error': 'Missing credentials'}), 400

    table_name = 'student_credentials' if login_type == 'student' else 'faculty_credentials'

    try:
        response = supabase.table(table_name).select("username, role").eq("username", username).eq("password", password).single().execute()
        user = response.data

        if user:
            session['user'] = username
            session['role'] = user["role"]  # Store role in session
            return jsonify({'message': 'Login successful', 'redirect': '/home', 'role': user["role"], 'username': username})  
        else:
            return jsonify({'error': 'Invalid username or password'}), 401

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user', None)
    return jsonify({'message': 'Logged out successfully'})

@app.route('/home')
def home():
    return "Welcome to the Home Page!"  # Replace with render_template('home.html') when ready

# STUDENT REPORT API
@app.route("/get_student_info", methods=["GET"])
def get_student_info():
    rollno = request.args.get("rollno")
    print(f"Received request for rollno: {rollno}")  # Debugging log

    if not rollno:
        print("Error: Roll number is missing")
        return jsonify({"error": "Roll number is required"}), 400

    # Fetch student details from Supabase
    student_query = supabase.table("student").select("*").eq("rollno", rollno).single().execute()
    

    if not student_query.data:
        print("Error: Student not found in database")
        return jsonify({"error": "Student not found"}), 404

    student = student_query.data
    print(f"Student Data: {student}")  # Debugging log

    # Fetch attendance records from Supabase
    attendance_query = supabase.table("attendance").select("*").eq("rollno", rollno).execute()

    attendance_records = attendance_query.data if attendance_query.data else []
    print(f"Attendance Data: {attendance_records}")  # Debugging log

    # Fetch course names
    for record in attendance_records:
        course_query = supabase.table("course").select("course_name").eq("course_id", record["course_id"]).single().execute()
        record["course_name"] = course_query.data["course_name"] if course_query.data else "Unknown Course"


    return jsonify({
        "student": student,
        "attendance": attendance_records
    })


@app.route("/get_faculty_info", methods=["GET"])
def get_faculty_info():
    course_id = request.args.get("course_id")
    branch = request.args.get("branch")
    semester = request.args.get("semester")
    section = request.args.get("section")

    if not all([course_id, branch, semester, section]):
        return jsonify({"error": "All parameters are required"}), 400

    # Step 1: Get faculty_id from faculty_enrolled
    faculty_query = (
        supabase.table("faculty_enrolled")
        .select("faculty_id")
        .eq("course_id", course_id)
        .eq("branch", branch)
        .eq("semester", semester)
        .eq("section", section)
        .execute()
    )

    if not faculty_query.data:
        return jsonify({"error": "No faculty found"}), 404

    faculty_id = faculty_query.data[0]["faculty_id"]

    # Step 2: Get faculty details from faculty table
    faculty_detail_query = (
        supabase.table("faculty")
        .select("name, image_url")
        .eq("faculty_id", faculty_id)
        .execute()
    )

    if not faculty_detail_query.data:
        return jsonify({"error": "Faculty details not found"}), 404

    faculty_info = {
        "faculty_id": faculty_id,
        "name": faculty_detail_query.data[0]["name"],
        "image_url": faculty_detail_query.data[0].get("image_url", "")
    }

    # Step 3: Fetch attendance entries > 75%
    above_75_query = (
        supabase.table("attendance")
        .select("rollno, percentage")
        .eq("course_id", course_id)
        .eq("section", section)
        .gt("percentage", 75)
        .execute()
    ).data

    # Step 4: Fetch attendance entries <= 75%
    below_75_query = (
        supabase.table("attendance")
        .select("rollno, percentage")
        .eq("course_id", course_id)
        .eq("section", section)
        .lte("percentage", 75)
        .execute()
    ).data

    # Helper to fetch student info by rollno
    def get_student_info(rollno):
        student_query = (
            supabase.table("student")
            .select("name, rollno, contact")
            .eq("rollno", rollno)
            .execute()
        )
        return student_query.data[0] if student_query.data else None

    # Combine with student info
    attendance_above_75 = []
    for entry in above_75_query:
        student_info = get_student_info(entry["rollno"])
        if student_info:
            attendance_above_75.append({
                "name": student_info["name"],
                "rollno": student_info["rollno"],
                "contact": student_info["contact"],
                "percentage": entry["percentage"]
            })

    attendance_below_75 = []
    for entry in below_75_query:
        student_info = get_student_info(entry["rollno"])
        if student_info:
            attendance_below_75.append({
                "name": student_info["name"],
                "rollno": student_info["rollno"],
                "contact": student_info["contact"],
                "percentage": entry["percentage"]
            })

    return jsonify({
        "faculty": faculty_info,
        "attendanceAbove75": attendance_above_75,
        "attendanceBelow75": attendance_below_75
    })






if __name__ == "__main__":
    app.secret_key = '09538gjhfd'
    socketio.run(app, debug=True, port=5000)