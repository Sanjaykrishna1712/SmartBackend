from flask import Blueprint, request, jsonify, make_response, send_file
from datetime import datetime, timedelta
import os
import re
import bcrypt
import jwt
import pandas as pd
from io import BytesIO
from bson import ObjectId
from pymongo import MongoClient
from functools import wraps
import random
import string
from werkzeug.utils import secure_filename

# Create blueprint
teachers_bp = Blueprint('teachers', __name__)

# Configuration
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
DATABASE_NAME = os.getenv('DATABASE_NAME', 'SmartEducation')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
JWT_ALGORITHM = 'HS256'

# Allowed file extensions for bulk upload
ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}
UPLOAD_FOLDER = 'uploads/teachers'

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# MongoDB connection functions
def get_mongo_client():
    """Get MongoDB client"""
    return MongoClient(MONGO_URI)

def get_db():
    """Get MongoDB database"""
    client = get_mongo_client()
    return client[DATABASE_NAME]

def close_mongo_client(client):
    """Close MongoDB connection"""
    if client:
        client.close()

# CORS headers function
def add_cors_headers(response):
    """Add CORS headers to response"""
    origin = request.headers.get('Origin', 'http://localhost:5173')
    response.headers.add("Access-Control-Allow-Origin", origin)
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
    response.headers.add("Access-Control-Allow-Credentials", "true")
    return response

# JWT Token functions
def generate_token(user_id, user_role, school_id=None):
    """Generate JWT token"""
    payload = {
        'user_id': user_id,
        'user_role': user_role,
        'school_id': school_id,
        'exp': datetime.utcnow() + timedelta(hours=24),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def decode_token(token):
    """Decode and verify JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# Authentication decorator
def token_required(f):
    """Decorator to require valid JWT token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Get token from header
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({
                'success': False,
                'error': 'Token is missing'
            }), 401
        
        # Decode token
        payload = decode_token(token)
        if not payload:
            return jsonify({
                'success': False,
                'error': 'Invalid or expired token'
            }), 401
        
        # Add user info to request
        request.user_id = payload.get('user_id')
        request.user_role = payload.get('user_role')
        request.school_id = payload.get('school_id')
        
        return f(*args, **kwargs)
    return decorated

# Validation functions
def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_phone(phone):
    """Validate phone number format"""
    pattern = r'^[\+]?[1-9][\d]{0,15}$'
    return re.match(pattern, phone) is not None

def hash_password(password):
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed_password):
    """Check if password matches hash"""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def serialize_document(doc):
    """Convert ObjectId to string for JSON serialization"""
    if doc and '_id' in doc:
        doc['_id'] = str(doc['_id'])
    
    # Convert datetime objects to string
    for key, value in doc.items():
        if isinstance(value, datetime):
            doc[key] = value.isoformat()
        elif isinstance(value, ObjectId):
            doc[key] = str(value)
    
    return doc

def generate_employee_id(school_code, count):
    """Generate unique employee ID"""
    year = datetime.now().year
    return f"{school_code}T{year}{str(count).zfill(4)}"

def generate_temp_password():
    """Generate a temporary password"""
    chars = string.ascii_letters + string.digits + '!@#$%^&*'
    return ''.join(random.choice(chars) for _ in range(10))

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ==================== TEACHER REGISTRATION/ADDITION ====================

@teachers_bp.route('/api/teachers/register', methods=['POST', 'OPTIONS'])
@token_required
def register_teacher():
    """Register a new teacher (Admin/Principal only)"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        
        # Check if user has permission (admin or principal)
        if request.user_role not in ['admin', 'principal']:
            return jsonify({
                'success': False,
                'error': 'Unauthorized access'
            }), 403
        
        # Validate required fields
        required_fields = ['name', 'email', 'phone', 'subject']
        missing_fields = [field for field in required_fields if field not in data or not str(data[field]).strip()]
        
        if missing_fields:
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400
        
        # Validate email
        email = data['email'].strip().lower()
        if not validate_email(email):
            return jsonify({
                'success': False,
                'error': 'Invalid email format'
            }), 400
        
        # Validate phone
        phone = data['phone'].strip()
        if not validate_phone(phone):
            return jsonify({
                'success': False,
                'error': 'Invalid phone number format'
            }), 400
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Check if email already exists
        if db.teachers.find_one({'email': email}):
            client.close()
            return jsonify({
                'success': False,
                'error': 'Email already registered'
            }), 400
        
        # Get school information for principal
        school_info = None
        school_code = None
        if request.user_role == 'principal':
            school = db.school_contacts.find_one({'_id': ObjectId(request.school_id)})
            if school:
                school_info = school
                school_code = school.get('school_code', 'SCH')
        else:
            # For admin, use provided school_id
            school_id = data.get('school_id')
            if school_id:
                school = db.school_contacts.find_one({'_id': ObjectId(school_id)})
                if school:
                    school_info = school
                    school_code = school.get('school_code', 'SCH')
            else:
                school_code = 'ADM'  # Default for admin added teachers
        
        # Generate employee ID
        teacher_count = db.teachers.count_documents({'school_code': school_code})
        employee_id = generate_employee_id(school_code, teacher_count + 1)
        
        # Generate temporary password
        temp_password = generate_temp_password()
        hashed_password = hash_password(temp_password)
        
        # Prepare teacher document
        teacher_doc = {
            'employee_id': employee_id,
            'school_id': str(school_info['_id']) if school_info else request.school_id,
            'school_code': school_code,
            'school_name': school_info.get('school_name', '') if school_info else '',
            'name': data['name'].strip(),
            'email': email,
            'phone': phone,
            'password': hashed_password,
            'subject': data['subject'].strip(),
            'classes': data.get('classes', []),
            'status': data.get('status', 'active'),
            'join_date': datetime.utcnow(),
            'qualifications': data.get('qualifications', []),
            'experience': data.get('experience', 0),
            'address': data.get('address', ''),
            'date_of_birth': datetime.strptime(data['date_of_birth'], '%Y-%m-%d') if data.get('date_of_birth') else None,
            'emergency_contact': data.get('emergency_contact', ''),
            'gender': data.get('gender', ''),
            'blood_group': data.get('blood_group', ''),
            'designation': data.get('designation', 'Teacher'),
            'department': data.get('department', ''),
            'salary': data.get('salary'),
            'role': 'teacher',
            'created_by': request.user_id,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Insert teacher
        result = db.teachers.insert_one(teacher_doc)
        teacher_id = str(result.inserted_id)
        
        # Add teacher ID to school's teachers list if principal
        if request.user_role == 'principal' and school_info:
            db.school_contacts.update_one(
                {'_id': ObjectId(request.school_id)},
                {'$push': {'teachers': teacher_id}}
            )
        
        client.close()
        
        # Return success with temporary password (in production, send via email)
        return jsonify({
            'success': True,
            'message': 'Teacher registered successfully',
            'data': {
                'teacher_id': teacher_id,
                'employee_id': employee_id,
                'email': email,
                'temp_password': temp_password,  # For admin/principal reference
                'message': 'Please share these credentials with the teacher'
            }
        }), 201
        
    except Exception as e:
        print(f"Error registering teacher: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to register teacher: {str(e)}'
        }), 500

# ==================== TEACHER LOGIN ====================

@teachers_bp.route('/api/teachers/login', methods=['POST', 'OPTIONS'])
def teacher_login():
    """Handle teacher login"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        
        email = data.get('email', '').lower().strip()
        password = data.get('password', '').strip()
        
        if not email or not password:
            return jsonify({
                'success': False,
                'error': 'Email and password are required'
            }), 400
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Find teacher
        teacher = db.teachers.find_one({'email': email})
        
        if not teacher:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Invalid credentials'
            }), 401
        
        # Check password
        if not check_password(password, teacher.get('password', '')):
            client.close()
            return jsonify({
                'success': False,
                'error': 'Invalid credentials'
            }), 401
        
        # Check if teacher is active
        if teacher.get('status') != 'active':
            client.close()
            return jsonify({
                'success': False,
                'error': 'Your account is not active'
            }), 403
        
        # Update last login
        db.teachers.update_one(
            {'_id': teacher['_id']},
            {'$set': {'last_login': datetime.utcnow()}}
        )
        
        # Generate token
        token = generate_token(
            user_id=str(teacher['_id']),
            user_role='teacher',
            school_id=teacher.get('school_id')
        )
        
        # Get school info
        school_info = {}
        if teacher.get('school_id'):
            school = db.school_contacts.find_one({'_id': ObjectId(teacher['school_id'])})
            if school:
                school_info = {
                    'school_id': str(school['_id']),
                    'school_name': school.get('school_name', ''),
                    'school_code': school.get('school_code', '')
                }
        
        # Prepare response data
        teacher_data = serialize_document(teacher)
        
        client.close()
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'data': {
                'token': token,
                'teacher': {
                    'id': teacher_data['_id'],
                    'employee_id': teacher_data.get('employee_id', ''),
                    'name': teacher_data.get('name', ''),
                    'email': teacher_data.get('email', ''),
                    'subject': teacher_data.get('subject', ''),
                    'role': teacher_data.get('role', 'teacher'),
                    'profile_image': teacher_data.get('profile_image', ''),
                    'school': school_info
                }
            }
        }), 200
        
    except Exception as e:
        print(f"Error in teacher login: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Login failed: {str(e)}'
        }), 500

# ==================== GET ALL TEACHERS ====================

@teachers_bp.route('/api/teachers', methods=['GET', 'OPTIONS'])
@token_required
def get_all_teachers():
    """Get all teachers with filtering and pagination"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        # Get query parameters
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        search = request.args.get('search', '').strip()
        status = request.args.get('status', 'all')
        subject = request.args.get('subject', 'all')
        sort_by = request.args.get('sort_by', 'name')
        sort_order = request.args.get('sort_order', 'asc')
        
        # Build query based on user role
        query = {}
        
        if request.user_role == 'teacher':
            # Teachers can only see themselves
            query['_id'] = ObjectId(request.user_id)
        elif request.user_role == 'principal':
            # Principals can see teachers from their school
            query['school_id'] = request.school_id
        # Admins can see all teachers
        
        # Apply filters
        if search:
            query['$or'] = [
                {'name': {'$regex': search, '$options': 'i'}},
                {'email': {'$regex': search, '$options': 'i'}},
                {'employee_id': {'$regex': search, '$options': 'i'}},
                {'subject': {'$regex': search, '$options': 'i'}}
            ]
        
        if status != 'all':
            query['status'] = status
        
        if subject != 'all':
            query['subject'] = subject
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Get total count
        total = db.teachers.count_documents(query)
        
        # Calculate pagination
        skip = (page - 1) * limit
        
        # Define sort
        sort_direction = 1 if sort_order == 'asc' else -1
        sort_field = sort_by if sort_by in ['name', 'join_date', 'experience', 'created_at'] else 'name'
        
        # Fetch teachers
        teachers_cursor = db.teachers.find(query)\
            .sort(sort_field, sort_direction)\
            .skip(skip)\
            .limit(limit)
        
        teachers = list(teachers_cursor)
        
        # Serialize documents
        teachers = [serialize_document(teacher) for teacher in teachers]
        
        # Remove password from response
        for teacher in teachers:
            teacher.pop('password', None)
        
        client.close()
        
        return jsonify({
            'success': True,
            'data': {
                'teachers': teachers,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total': total,
                    'pages': (total + limit - 1) // limit
                }
            }
        }), 200
        
    except Exception as e:
        print(f"Error fetching teachers: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to fetch teachers: {str(e)}'
        }), 500

# ==================== GET SINGLE TEACHER ====================

@teachers_bp.route('/api/teachers/<teacher_id>', methods=['GET', 'OPTIONS'])
@token_required
def get_teacher(teacher_id):
    """Get single teacher details"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        # Check permissions
        if request.user_role == 'teacher' and request.user_id != teacher_id:
            return jsonify({
                'success': False,
                'error': 'Unauthorized access'
            }), 403
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Find teacher
        teacher = db.teachers.find_one({'_id': ObjectId(teacher_id)})
        
        if not teacher:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Teacher not found'
            }), 404
        
        # Check if principal can access this teacher
        if request.user_role == 'principal':
            if teacher.get('school_id') != request.school_id:
                client.close()
                return jsonify({
                    'success': False,
                    'error': 'Unauthorized access'
                }), 403
        
        # Serialize document
        teacher_data = serialize_document(teacher)
        teacher_data.pop('password', None)
        
        # Get additional school info if available
        if teacher_data.get('school_id'):
            school = db.school_contacts.find_one({'_id': ObjectId(teacher_data['school_id'])})
            if school:
                teacher_data['school_info'] = {
                    'name': school.get('school_name', ''),
                    'code': school.get('school_code', '')
                }
        
        client.close()
        
        return jsonify({
            'success': True,
            'data': teacher_data
        }), 200
        
    except Exception as e:
        print(f"Error fetching teacher: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to fetch teacher: {str(e)}'
        }), 500

# ==================== UPDATE TEACHER ====================

@teachers_bp.route('/api/teachers/<teacher_id>', methods=['PUT', 'OPTIONS'])
@token_required
def update_teacher(teacher_id):
    """Update teacher information"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        
        # Check permissions
        if request.user_role == 'teacher' and request.user_id != teacher_id:
            return jsonify({
                'success': False,
                'error': 'You can only update your own profile'
            }), 403
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Find teacher
        teacher = db.teachers.find_one({'_id': ObjectId(teacher_id)})
        
        if not teacher:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Teacher not found'
            }), 404
        
        # Check if principal can update this teacher
        if request.user_role == 'principal':
            if teacher.get('school_id') != request.school_id:
                client.close()
                return jsonify({
                    'success': False,
                    'error': 'Unauthorized access'
                }), 403
        
        # Prepare update data
        update_data = {}
        
        # Fields that teachers can update themselves
        if request.user_role == 'teacher':
            allowed_fields = ['name', 'phone', 'address', 'date_of_birth', 
                             'emergency_contact', 'profile_image']
        else:
            # Admins/principals can update more fields
            allowed_fields = ['name', 'email', 'phone', 'subject', 'classes',
                             'status', 'qualifications', 'experience', 'address',
                             'date_of_birth', 'emergency_contact', 'gender',
                             'blood_group', 'designation', 'department', 'salary',
                             'profile_image']
        
        for field in allowed_fields:
            if field in data:
                if field == 'date_of_birth' and data[field]:
                    update_data[field] = datetime.strptime(data[field], '%Y-%m-%d')
                elif field == 'classes' and isinstance(data[field], str):
                    update_data[field] = [cls.strip() for cls in data[field].split(',') if cls.strip()]
                elif field == 'qualifications' and isinstance(data[field], str):
                    update_data[field] = [q.strip() for q in data[field].split(',') if q.strip()]
                else:
                    update_data[field] = data[field]
        
        # Add update timestamp
        update_data['updated_at'] = datetime.utcnow()
        
        # Update teacher
        result = db.teachers.update_one(
            {'_id': ObjectId(teacher_id)},
            {'$set': update_data}
        )
        
        if result.modified_count == 0:
            client.close()
            return jsonify({
                'success': True,
                'message': 'No changes made'
            }), 200
        
        client.close()
        
        return jsonify({
            'success': True,
            'message': 'Teacher updated successfully'
        }), 200
        
    except Exception as e:
        print(f"Error updating teacher: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to update teacher: {str(e)}'
        }), 500

# ==================== DELETE TEACHER ====================

@teachers_bp.route('/api/teachers/<teacher_id>', methods=['DELETE', 'OPTIONS'])
@token_required
def delete_teacher(teacher_id):
    """Delete a teacher (Admin/Principal only)"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        # Check permissions
        if request.user_role not in ['admin', 'principal']:
            return jsonify({
                'success': False,
                'error': 'Unauthorized access'
            }), 403
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Find teacher
        teacher = db.teachers.find_one({'_id': ObjectId(teacher_id)})
        
        if not teacher:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Teacher not found'
            }), 404
        
        # Check if principal can delete this teacher
        if request.user_role == 'principal':
            if teacher.get('school_id') != request.school_id:
                client.close()
                return jsonify({
                    'success': False,
                    'error': 'Unauthorized access'
                }), 403
        
        # Delete teacher
        result = db.teachers.delete_one({'_id': ObjectId(teacher_id)})
        
        # Remove teacher from school's teachers list if principal
        if request.user_role == 'principal':
            db.school_contacts.update_one(
                {'_id': ObjectId(request.school_id)},
                {'$pull': {'teachers': teacher_id}}
            )
        
        client.close()
        
        return jsonify({
            'success': True,
            'message': 'Teacher deleted successfully'
        }), 200
        
    except Exception as e:
        print(f"Error deleting teacher: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to delete teacher: {str(e)}'
        }), 500

# ==================== BULK IMPORT TEACHERS ====================

@teachers_bp.route('/api/teachers/bulk-import', methods=['POST', 'OPTIONS'])
@token_required
def bulk_import_teachers():
    """Bulk import teachers from Excel/CSV file"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        # Check permissions
        if request.user_role not in ['admin', 'principal']:
            return jsonify({
                'success': False,
                'error': 'Unauthorized access'
            }), 403
        
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No file uploaded'
            }), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No file selected'
            }), 400
        
        if not allowed_file(file.filename):
            return jsonify({
                'success': False,
                'error': 'File type not allowed. Please upload Excel (.xlsx, .xls) or CSV files.'
            }), 400
        
        # Save file temporarily
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        # Read file based on extension
        if filename.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)
        
        # Required columns
        required_columns = ['name', 'email', 'phone', 'subject']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            os.remove(filepath)
            return jsonify({
                'success': False,
                'error': f'Missing required columns: {", ".join(missing_columns)}'
            }), 400
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Get school info for principal
        school_info = None
        school_code = None
        if request.user_role == 'principal':
            school = db.school_contacts.find_one({'_id': ObjectId(request.school_id)})
            if school:
                school_info = school
                school_code = school.get('school_code', 'SCH')
        else:
            # For admin, check if school_id is provided
            school_id = request.form.get('school_id')
            if school_id:
                school = db.school_contacts.find_one({'_id': ObjectId(school_id)})
                if school:
                    school_info = school
                    school_code = school.get('school_code', 'SCH')
            else:
                school_code = 'ADM'
        
        # Process each row
        success_count = 0
        error_count = 0
        errors = []
        
        # Get current teacher count for ID generation
        teacher_count = db.teachers.count_documents({'school_code': school_code})
        
        for index, row in df.iterrows():
            try:
                # Skip empty rows
                if pd.isna(row['name']) or pd.isna(row['email']):
                    continue
                
                email = str(row['email']).strip().lower()
                
                # Check if email already exists
                if db.teachers.find_one({'email': email}):
                    errors.append(f"Row {index + 2}: Email {email} already exists")
                    error_count += 1
                    continue
                
                # Generate employee ID
                teacher_count += 1
                employee_id = generate_employee_id(school_code, teacher_count)
                
                # Generate temporary password
                temp_password = generate_temp_password()
                hashed_password = hash_password(temp_password)
                
                # Parse classes if provided
                classes = []
                if 'classes' in row and pd.notna(row['classes']):
                    classes = [cls.strip() for cls in str(row['classes']).split(',') if cls.strip()]
                
                # Parse qualifications if provided
                qualifications = []
                if 'qualifications' in row and pd.notna(row['qualifications']):
                    qualifications = [q.strip() for q in str(row['qualifications']).split(',') if q.strip()]
                
                # Prepare teacher document
                teacher_doc = {
                    'employee_id': employee_id,
                    'school_id': str(school_info['_id']) if school_info else (request.school_id if request.user_role == 'principal' else None),
                    'school_code': school_code,
                    'school_name': school_info.get('school_name', '') if school_info else '',
                    'name': str(row['name']).strip(),
                    'email': email,
                    'phone': str(row['phone']).strip(),
                    'password': hashed_password,
                    'subject': str(row['subject']).strip(),
                    'classes': classes,
                    'status': str(row.get('status', 'active')).strip(),
                    'join_date': datetime.utcnow(),
                    'qualifications': qualifications,
                    'experience': int(row.get('experience', 0)) if pd.notna(row.get('experience')) else 0,
                    'address': str(row.get('address', '')).strip() if pd.notna(row.get('address')) else '',
                    'date_of_birth': datetime.strptime(row['date_of_birth'], '%Y-%m-%d') if 'date_of_birth' in row and pd.notna(row['date_of_birth']) else None,
                    'emergency_contact': str(row.get('emergency_contact', '')).strip() if pd.notna(row.get('emergency_contact')) else '',
                    'gender': str(row.get('gender', '')).strip() if pd.notna(row.get('gender')) else '',
                    'blood_group': str(row.get('blood_group', '')).strip() if pd.notna(row.get('blood_group')) else '',
                    'designation': str(row.get('designation', 'Teacher')).strip() if pd.notna(row.get('designation')) else 'Teacher',
                    'department': str(row.get('department', '')).strip() if pd.notna(row.get('department')) else '',
                    'salary': float(row['salary']) if 'salary' in row and pd.notna(row['salary']) else None,
                    'role': 'teacher',
                    'created_by': request.user_id,
                    'created_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                }
                
                # Insert teacher
                result = db.teachers.insert_one(teacher_doc)
                teacher_id = str(result.inserted_id)
                
                # Add teacher to school's teachers list if principal
                if request.user_role == 'principal' and school_info:
                    db.school_contacts.update_one(
                        {'_id': ObjectId(request.school_id)},
                        {'$push': {'teachers': teacher_id}}
                    )
                
                success_count += 1
                
            except Exception as row_error:
                errors.append(f"Row {index + 2}: {str(row_error)}")
                error_count += 1
        
        # Clean up temp file
        os.remove(filepath)
        client.close()
        
        return jsonify({
            'success': True,
            'message': f'Bulk import completed. Success: {success_count}, Failed: {error_count}',
            'data': {
                'success_count': success_count,
                'error_count': error_count,
                'errors': errors[:10]  # Return first 10 errors
            }
        }), 200
        
    except Exception as e:
        print(f"Error in bulk import: {str(e)}")
        # Clean up temp file if exists
        if 'filepath' in locals() and os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({
            'success': False,
            'error': f'Failed to import teachers: {str(e)}'
        }), 500

# ==================== DOWNLOAD BULK IMPORT TEMPLATE ====================

@teachers_bp.route('/api/teachers/bulk-import/template', methods=['GET', 'OPTIONS'])
@token_required
def download_import_template():
    """Download bulk import template"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        # Check permissions
        if request.user_role not in ['admin', 'principal']:
            return jsonify({
                'success': False,
                'error': 'Unauthorized access'
            }), 403
        
        # Create template data
        template_data = [
            {
                'name': 'Dr. Sarah Johnson',
                'email': 'sarah.johnson@school.edu',
                'phone': '+1234567890',
                'subject': 'Mathematics',
                'classes': '10-A, 10-B, 11-A',
                'status': 'active',
                'qualifications': 'Ph.D in Mathematics, M.Ed',
                'experience': 8,
                'address': '123 Math Street',
                'date_of_birth': '1985-03-15',
                'emergency_contact': '+1987654321',
                'gender': 'female',
                'blood_group': 'A+',
                'designation': 'Senior Teacher',
                'department': 'Science',
                'salary': 65000
            },
            {
                'name': 'Mr. Robert Chen',
                'email': 'robert.chen@school.edu',
                'phone': '+1987654321',
                'subject': 'Physics',
                'classes': '9-A, 9-B',
                'status': 'active',
                'qualifications': 'M.Sc Physics',
                'experience': 6,
                'address': '456 Physics Avenue',
                'date_of_birth': '1988-07-22',
                'emergency_contact': '+1234567890',
                'gender': 'male',
                'blood_group': 'B+',
                'designation': 'Teacher',
                'department': 'Science',
                'salary': 55000
            }
        ]
        
        # Create DataFrame
        df = pd.DataFrame(template_data)
        
        # Create Excel file in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Teachers Template', index=False)
        
        output.seek(0)
        
        # Create response
        response = make_response(output.getvalue())
        response.headers.set('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response.headers.set('Content-Disposition', 'attachment', filename='teachers_import_template.xlsx')
        response.headers.set('Access-Control-Expose-Headers', 'Content-Disposition')
        
        return response
        
    except Exception as e:
        print(f"Error generating template: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to generate template: {str(e)}'
        }), 500

# ==================== EXPORT TEACHERS ====================

@teachers_bp.route('/api/teachers/export', methods=['GET', 'OPTIONS'])
@token_required
def export_teachers():
    """Export teachers to Excel"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        # Build query based on user role
        query = {}
        
        if request.user_role == 'principal':
            query['school_id'] = request.school_id
        elif request.user_role == 'teacher':
            return jsonify({
                'success': False,
                'error': 'Unauthorized access'
            }), 403
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Fetch all teachers based on query
        teachers_cursor = db.teachers.find(query)
        teachers = list(teachers_cursor)
        
        # Prepare data for export
        export_data = []
        for teacher in teachers:
            teacher_data = serialize_document(teacher)
            export_data.append({
                'Employee ID': teacher_data.get('employee_id', ''),
                'Name': teacher_data.get('name', ''),
                'Email': teacher_data.get('email', ''),
                'Phone': teacher_data.get('phone', ''),
                'Subject': teacher_data.get('subject', ''),
                'Classes': ', '.join(teacher_data.get('classes', [])),
                'Status': teacher_data.get('status', ''),
                'Join Date': teacher_data.get('join_date', ''),
                'Qualifications': ', '.join(teacher_data.get('qualifications', [])),
                'Experience (years)': teacher_data.get('experience', 0),
                'Address': teacher_data.get('address', ''),
                'Date of Birth': teacher_data.get('date_of_birth', ''),
                'Emergency Contact': teacher_data.get('emergency_contact', ''),
                'Gender': teacher_data.get('gender', ''),
                'Blood Group': teacher_data.get('blood_group', ''),
                'Designation': teacher_data.get('designation', ''),
                'Department': teacher_data.get('department', ''),
                'Salary': teacher_data.get('salary', ''),
                'School': teacher_data.get('school_name', '')
            })
        
        client.close()
        
        # Create DataFrame
        df = pd.DataFrame(export_data)
        
        # Create Excel file in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Teachers Export', index=False)
        
        output.seek(0)
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'teachers_export_{timestamp}.xlsx'
        
        # Create response
        response = make_response(output.getvalue())
        response.headers.set('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response.headers.set('Content-Disposition', 'attachment', filename=filename)
        response.headers.set('Access-Control-Expose-Headers', 'Content-Disposition')
        
        return response
        
    except Exception as e:
        print(f"Error exporting teachers: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to export teachers: {str(e)}'
        }), 500

# ==================== CHANGE TEACHER STATUS ====================

@teachers_bp.route('/api/teachers/<teacher_id>/status', methods=['PUT', 'OPTIONS'])
@token_required
def change_teacher_status(teacher_id):
    """Change teacher status (active/inactive)"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        
        # Check permissions
        if request.user_role not in ['admin', 'principal']:
            return jsonify({
                'success': False,
                'error': 'Unauthorized access'
            }), 403
        
        new_status = data.get('status')
        
        if new_status not in ['active', 'inactive']:
            return jsonify({
                'success': False,
                'error': 'Invalid status. Must be "active" or "inactive"'
            }), 400
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Find teacher
        teacher = db.teachers.find_one({'_id': ObjectId(teacher_id)})
        
        if not teacher:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Teacher not found'
            }), 404
        
        # Check if principal can update this teacher
        if request.user_role == 'principal':
            if teacher.get('school_id') != request.school_id:
                client.close()
                return jsonify({
                    'success': False,
                    'error': 'Unauthorized access'
                }), 403
        
        # Update status
        result = db.teachers.update_one(
            {'_id': ObjectId(teacher_id)},
            {'$set': {
                'status': new_status,
                'updated_at': datetime.utcnow()
            }}
        )
        
        client.close()
        
        return jsonify({
            'success': True,
            'message': f'Teacher status updated to {new_status}'
        }), 200
        
    except Exception as e:
        print(f"Error changing teacher status: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to change status: {str(e)}'
        }), 500

# ==================== TEACHER STATISTICS ====================

@teachers_bp.route('/api/teachers/statistics', methods=['GET', 'OPTIONS'])
@token_required
def get_teacher_statistics():
    """Get teacher statistics"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        # Build query based on user role
        query = {}
        
        if request.user_role == 'principal':
            query['school_id'] = request.school_id
        elif request.user_role == 'teacher':
            # Teachers can only see their own statistics
            query['_id'] = ObjectId(request.user_id)
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Get statistics
        total_teachers = db.teachers.count_documents(query)
        
        active_teachers = db.teachers.count_documents({**query, 'status': 'active'})
        inactive_teachers = db.teachers.count_documents({**query, 'status': 'inactive'})
        
        # Get subject distribution
        subjects = db.teachers.aggregate([
            {'$match': query},
            {'$group': {'_id': '$subject', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ])
        
        subject_distribution = {doc['_id']: doc['count'] for doc in subjects}
        
        # Get average experience
        experience_stats = db.teachers.aggregate([
            {'$match': query},
            {'$group': {
                '_id': None,
                'avg_experience': {'$avg': '$experience'},
                'min_experience': {'$min': '$experience'},
                'max_experience': {'$max': '$experience'}
            }}
        ])
        
        experience_data = list(experience_stats)
        avg_experience = experience_data[0]['avg_experience'] if experience_data else 0
        
        # Get new teachers this year
        current_year = datetime.now().year
        start_of_year = datetime(current_year, 1, 1)
        
        new_teachers_this_year = db.teachers.count_documents({
            **query,
            'join_date': {'$gte': start_of_year}
        })
        
        client.close()
        
        return jsonify({
            'success': True,
            'data': {
                'total_teachers': total_teachers,
                'active_teachers': active_teachers,
                'inactive_teachers': inactive_teachers,
                'subject_distribution': subject_distribution,
                'average_experience': round(avg_experience, 1) if avg_experience else 0,
                'new_teachers_this_year': new_teachers_this_year
            }
        }), 200
        
    except Exception as e:
        print(f"Error getting teacher statistics: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to get statistics: {str(e)}'
        }), 500

# ==================== CHANGE PASSWORD ====================

@teachers_bp.route('/api/teachers/change-password', methods=['POST', 'OPTIONS'])
@token_required
def change_password():
    """Change teacher password"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        
        current_password = data.get('current_password', '').strip()
        new_password = data.get('new_password', '').strip()
        
        if not current_password or not new_password:
            return jsonify({
                'success': False,
                'error': 'Current password and new password are required'
            }), 400
        
        if len(new_password) < 8:
            return jsonify({
                'success': False,
                'error': 'New password must be at least 8 characters long'
            }), 400
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Find teacher
        teacher = db.teachers.find_one({'_id': ObjectId(request.user_id)})
        
        if not teacher:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Teacher not found'
            }), 404
        
        # Check current password
        if not check_password(current_password, teacher.get('password', '')):
            client.close()
            return jsonify({
                'success': False,
                'error': 'Current password is incorrect'
            }), 401
        
        # Hash new password
        hashed_password = hash_password(new_password)
        
        # Update password
        db.teachers.update_one(
            {'_id': ObjectId(request.user_id)},
            {'$set': {
                'password': hashed_password,
                'updated_at': datetime.utcnow(),
                'password_changed_at': datetime.utcnow()
            }}
        )
        
        client.close()
        
        return jsonify({
            'success': True,
            'message': 'Password changed successfully'
        }), 200
        
    except Exception as e:
        print(f"Error changing password: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to change password: {str(e)}'
        }), 500

# ==================== RESET PASSWORD (Admin/Principal) ====================

@teachers_bp.route('/api/teachers/<teacher_id>/reset-password', methods=['POST', 'OPTIONS'])
@token_required
def reset_teacher_password(teacher_id):
    """Reset teacher password (Admin/Principal only)"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        # Check permissions
        if request.user_role not in ['admin', 'principal']:
            return jsonify({
                'success': False,
                'error': 'Unauthorized access'
            }), 403
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Find teacher
        teacher = db.teachers.find_one({'_id': ObjectId(teacher_id)})
        
        if not teacher:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Teacher not found'
            }), 404
        
        # Check if principal can reset password for this teacher
        if request.user_role == 'principal':
            if teacher.get('school_id') != request.school_id:
                client.close()
                return jsonify({
                    'success': False,
                    'error': 'Unauthorized access'
                }), 403
        
        # Generate new temporary password
        temp_password = generate_temp_password()
        hashed_password = hash_password(temp_password)
        
        # Update password
        db.teachers.update_one(
            {'_id': ObjectId(teacher_id)},
            {'$set': {
                'password': hashed_password,
                'updated_at': datetime.utcnow(),
                'password_changed_at': datetime.utcnow()
            }}
        )
        
        client.close()
        
        return jsonify({
            'success': True,
            'message': 'Password reset successfully',
            'data': {
                'employee_id': teacher.get('employee_id', ''),
                'email': teacher.get('email', ''),
                'temp_password': temp_password  # For admin/principal to share with teacher
            }
        }), 200
        
    except Exception as e:
        print(f"Error resetting password: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to reset password: {str(e)}'
        }), 500