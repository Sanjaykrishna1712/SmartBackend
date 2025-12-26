# app/routes/students.py
from flask import Blueprint, request, jsonify, make_response, current_app
from datetime import datetime
import os
from pymongo import MongoClient
from bson import ObjectId
import bcrypt
import jwt
import pandas as pd
import io
import uuid
import re
from werkzeug.utils import secure_filename

students_bp = Blueprint('students', __name__)

# MongoDB connection setup
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
DATABASE_NAME = os.getenv('DATABASE_NAME', 'SmartEducation')

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

def serialize_document(doc):
    """Convert ObjectId to string for JSON serialization"""
    if doc and '_id' in doc:
        doc['_id'] = str(doc['_id'])
    return doc

def add_cors_headers(response):
    """Add CORS headers to response"""
    origin = request.headers.get('Origin', 'http://localhost:5173')
    response.headers.add("Access-Control-Allow-Origin", origin)
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
    response.headers.add("Access-Control-Allow-Credentials", "true")
    return response

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def generate_student_id():
    """Generate unique student ID"""
    return f"STU{datetime.now().strftime('%Y%m%d')}{uuid.uuid4().hex[:6].upper()}"

def generate_password():
    """Generate random password"""
    return str(uuid.uuid4().hex[:8])

def hash_password(password):
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

# ==================== GET ALL STUDENTS ====================

@students_bp.route('/students', methods=['GET', 'OPTIONS'])
def get_all_students():
    """Get all students with filtering and pagination"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        # Get query parameters
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        class_filter = request.args.get('class', '')
        section_filter = request.args.get('section', '')
        status_filter = request.args.get('status', '')
        search_term = request.args.get('search', '')
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        collection = db.students
        
        # Build query
        query = {}
        
        if class_filter:
            query['class'] = class_filter
        
        if section_filter:
            query['section'] = section_filter
        
        if status_filter:
            query['status'] = status_filter
        
        if search_term:
            query['$or'] = [
                {'name': {'$regex': search_term, '$options': 'i'}},
                {'roll_number': {'$regex': search_term, '$options': 'i'}},
                {'email': {'$regex': search_term, '$options': 'i'}},
                {'parent_name': {'$regex': search_term, '$options': 'i'}}
            ]
        
        # Get total count
        total_students = collection.count_documents(query)
        
        # Get paginated data
        skip = (page - 1) * limit
        students = list(collection.find(query).skip(skip).limit(limit).sort('created_at', -1))
        
        client.close()
        
        # Serialize ObjectId
        students = [serialize_document(student) for student in students]
        
        return jsonify({
            'success': True,
            'data': students,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total_students,
                'pages': (total_students + limit - 1) // limit
            }
        }), 200
        
    except Exception as e:
        print(f"Error fetching students: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to fetch students: {str(e)}'
        }), 500

# ==================== ADD SINGLE STUDENT ====================

@students_bp.route('/students', methods=['POST', 'OPTIONS'])
def add_student():
    """Add a single student"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'email', 'class', 'section']
        missing_fields = []
        
        for field in required_fields:
            if field not in data or not str(data[field]).strip():
                missing_fields.append(field)
        
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
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        students_collection = db.students
        
        # Check if email already exists
        existing_student = students_collection.find_one({'email': email})
        if existing_student:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Email already registered'
            }), 400
        
        # Generate student ID and password
        student_id = generate_student_id()
        password = generate_password()
        
        # Prepare student document
        student_doc = {
            'student_id': student_id,
            'name': data['name'].strip(),
            'email': email,
            'phone': data.get('phone', '').strip(),
            'roll_number': data.get('roll_number', student_id),
            'class': data['class'].strip(),
            'section': data['section'].strip(),
            'date_of_birth': data.get('date_of_birth', ''),
            'gender': data.get('gender', ''),
            'address': data.get('address', ''),
            'parent_name': data.get('parent_name', ''),
            'parent_phone': data.get('parent_phone', ''),
            'parent_email': data.get('parent_email', ''),
            'parent_occupation': data.get('parent_occupation', ''),
            'blood_group': data.get('blood_group', ''),
            'medical_conditions': data.get('medical_conditions', ''),
            'admission_date': data.get('admission_date', datetime.utcnow().strftime('%Y-%m-%d')),
            'attendance': float(data.get('attendance', 0)),
            'performance': float(data.get('performance', 0)),
            'status': data.get('status', 'active'),
            'hashed_password': hash_password(password),
            'initial_password': password,  # Store initial password for admin reference
            'profile_image': data.get('profile_image', ''),
            'created_by': data.get('created_by', 'admin'),
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Insert student
        result = students_collection.insert_one(student_doc)
        
        # Update school's student count if school_id is provided
        if data.get('school_id'):
            school_collection = db.school_contacts
            school_collection.update_one(
                {'_id': ObjectId(data['school_id'])},
                {'$inc': {'student_count': 1}}
            )
        
        client.close()
        
        # Remove password from response
        student_doc.pop('hashed_password', None)
        
        return jsonify({
            'success': True,
            'message': 'Student added successfully',
            'data': {
                'id': str(result.inserted_id),
                'student_id': student_id,
                'password': password,  # Return initial password for admin
                'student': serialize_document(student_doc)
            }
        }), 201
        
    except Exception as e:
        print(f"Error adding student: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to add student: {str(e)}'
        }), 500

# ==================== BULK IMPORT STUDENTS ====================

@students_bp.route('/students/bulk-import', methods=['POST', 'OPTIONS'])
def bulk_import_students():
    """Bulk import students from Excel/CSV file"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
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
        
        # Validate file type
        allowed_extensions = {'xlsx', 'xls', 'csv'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            return jsonify({
                'success': False,
                'error': f'Invalid file type. Allowed: {", ".join(allowed_extensions)}'
            }), 400
        
        # Read file based on extension
        try:
            if file_ext == 'csv':
                df = pd.read_csv(io.BytesIO(file.read()))
            else:
                df = pd.read_excel(io.BytesIO(file.read()))
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Failed to read file: {str(e)}'
            }), 400
        
        # Check required columns
        required_columns = ['Name', 'Email', 'Class', 'Section']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            return jsonify({
                'success': False,
                'error': f'Missing required columns: {", ".join(missing_columns)}'
            }), 400
        
        # Validate and prepare student data
        students_to_insert = []
        errors = []
        
        for index, row in df.iterrows():
            try:
                # Clean and validate data
                name = str(row['Name']).strip()
                email = str(row['Email']).strip().lower()
                class_name = str(row['Class']).strip()
                section = str(row['Section']).strip().upper()
                
                # Validate required fields
                if not name or not email or not class_name or not section:
                    errors.append(f"Row {index + 2}: Missing required fields")
                    continue
                
                # Validate email
                if not validate_email(email):
                    errors.append(f"Row {index + 2}: Invalid email format: {email}")
                    continue
                
                # Generate student ID and password
                student_id = generate_student_id()
                password = generate_password()
                
                # Prepare student document
                student_doc = {
                    'student_id': student_id,
                    'name': name,
                    'email': email,
                    'phone': str(row.get('Phone', '')).strip(),
                    'roll_number': str(row.get('Roll Number', student_id)).strip(),
                    'class': class_name,
                    'section': section,
                    'date_of_birth': str(row.get('Date of Birth', '')).strip(),
                    'gender': str(row.get('Gender', '')).strip().lower(),
                    'address': str(row.get('Address', '')).strip(),
                    'parent_name': str(row.get('Parent Name', '')).strip(),
                    'parent_phone': str(row.get('Parent Phone', '')).strip(),
                    'parent_email': str(row.get('Parent Email', '')).strip(),
                    'parent_occupation': str(row.get('Parent Occupation', '')).strip(),
                    'blood_group': str(row.get('Blood Group', '')).strip(),
                    'medical_conditions': str(row.get('Medical Conditions', '')).strip(),
                    'admission_date': str(row.get('Admission Date', datetime.utcnow().strftime('%Y-%m-%d'))),
                    'attendance': float(row.get('Attendance', 0)),
                    'performance': float(row.get('Performance', 0)),
                    'status': str(row.get('Status', 'active')).strip().lower(),
                    'hashed_password': hash_password(password),
                    'initial_password': password,
                    'created_by': 'admin',
                    'created_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                }
                
                students_to_insert.append(student_doc)
                
            except Exception as e:
                errors.append(f"Row {index + 2}: {str(e)}")
        
        if errors and not students_to_insert:
            return jsonify({
                'success': False,
                'error': 'Failed to process file',
                'details': errors[:10]  # Return first 10 errors
            }), 400
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        students_collection = db.students
        
        # Check for duplicate emails
        existing_emails = set()
        if students_to_insert:
            emails = [student['email'] for student in students_to_insert]
            existing_students = list(students_collection.find(
                {'email': {'$in': emails}},
                {'email': 1}
            ))
            existing_emails = {student['email'] for student in existing_students}
        
        # Filter out duplicates
        filtered_students = []
        duplicate_emails = []
        
        for student in students_to_insert:
            if student['email'] in existing_emails:
                duplicate_emails.append(student['email'])
            else:
                filtered_students.append(student)
        
        # Insert students
        inserted_count = 0
        if filtered_students:
            result = students_collection.insert_many(filtered_students)
            inserted_count = len(result.inserted_ids)
        
        client.close()
        
        # Prepare response
        response_data = {
            'success': True,
            'message': f'Successfully imported {inserted_count} students',
            'data': {
                'total_processed': len(df),
                'successful': inserted_count,
                'failed': len(df) - inserted_count,
                'duplicates': len(duplicate_emails),
                'errors': errors[:10] if errors else [],
                'duplicate_emails': duplicate_emails[:10]
            }
        }
        
        if errors:
            response_data['warning'] = f'{len(errors)} rows had errors'
        
        return jsonify(response_data), 200
        
    except Exception as e:
        print(f"Error in bulk import: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to import students: {str(e)}'
        }), 500

# ==================== DOWNLOAD TEMPLATE ====================

@students_bp.route('/students/template', methods=['GET', 'OPTIONS'])
def download_template():
    """Download Excel template for student import"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        # Create sample data
        sample_data = {
            'Name': ['John Doe', 'Jane Smith'],
            'Email': ['john@school.edu', 'jane@school.edu'],
            'Class': ['10', '11'],
            'Section': ['A', 'B'],
            'Roll Number': ['2024001', '2024002'],
            'Phone': ['+1234567890', '+1234567891'],
            'Date of Birth': ['2008-05-15', '2007-03-20'],
            'Gender': ['male', 'female'],
            'Address': ['123 Main St', '456 Oak Ave'],
            'Parent Name': ['Mr. Doe', 'Mrs. Smith'],
            'Parent Phone': ['+1234567890', '+1234567891'],
            'Parent Email': ['parent@email.com', 'parent2@email.com'],
            'Parent Occupation': ['Engineer', 'Teacher'],
            'Blood Group': ['O+', 'A+'],
            'Medical Conditions': ['None', 'Asthma'],
            'Admission Date': ['2024-01-15', '2024-01-15'],
            'Attendance': [95.5, 92.3],
            'Performance': [88.7, 91.2],
            'Status': ['active', 'active']
        }
        
        # Create DataFrame
        df = pd.DataFrame(sample_data)
        
        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Students')
            
            # Add instructions sheet
            instructions = pd.DataFrame({
                'Column': ['Name', 'Email', 'Class', 'Section', 'Roll Number', 'Phone', 
                          'Date of Birth', 'Gender', 'Address', 'Parent Name', 'Parent Phone',
                          'Parent Email', 'Parent Occupation', 'Blood Group', 'Medical Conditions',
                          'Admission Date', 'Attendance', 'Performance', 'Status'],
                'Required': ['Yes', 'Yes', 'Yes', 'Yes', 'No', 'No', 'No', 'No', 'No', 'No',
                            'No', 'No', 'No', 'No', 'No', 'No', 'No', 'No', 'No'],
                'Description': ['Full name of student',
                               'Valid email address',
                               'Class/grade level',
                               'Section (A, B, C, etc.)',
                               'Roll number (auto-generated if empty)',
                               'Phone number with country code',
                               'Format: YYYY-MM-DD',
                               'male/female/other',
                               'Complete address',
                               "Parent/guardian's name",
                               "Parent/guardian's phone",
                               "Parent/guardian's email",
                               "Parent/guardian's occupation",
                               'Blood group if known',
                               'Any medical conditions',
                               'Format: YYYY-MM-DD',
                               'Attendance percentage (0-100)',
                               'Performance percentage (0-100)',
                               'active/inactive/graduated/transferred']
            })
            instructions.to_excel(writer, index=False, sheet_name='Instructions')
        
        output.seek(0)
        
        # Create response
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response.headers['Content-Disposition'] = 'attachment; filename=student_import_template.xlsx'
        
        return response
        
    except Exception as e:
        print(f"Error creating template: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to create template: {str(e)}'
        }), 500

# ==================== GET STUDENT BY ID ====================

@students_bp.route('/students/<student_id>', methods=['GET', 'OPTIONS'])
def get_student(student_id):
    """Get student by ID"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        client = get_mongo_client()
        db = get_db()
        collection = db.students
        
        student = collection.find_one({'student_id': student_id})
        
        if not student:
            student = collection.find_one({'_id': ObjectId(student_id)})
        
        client.close()
        
        if not student:
            return jsonify({
                'success': False,
                'error': 'Student not found'
            }), 404
        
        # Remove sensitive data
        student.pop('hashed_password', None)
        
        return jsonify({
            'success': True,
            'data': serialize_document(student)
        }), 200
        
    except Exception as e:
        print(f"Error fetching student: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to fetch student: {str(e)}'
        }), 500

# ==================== UPDATE STUDENT ====================

@students_bp.route('/students/<student_id>', methods=['PUT', 'OPTIONS'])
def update_student(student_id):
    """Update student information"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        
        client = get_mongo_client()
        db = get_db()
        collection = db.students
        
        # Find student
        student = collection.find_one({'student_id': student_id})
        if not student:
            student = collection.find_one({'_id': ObjectId(student_id)})
        
        if not student:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Student not found'
            }), 404
        
        # Prepare update data
        update_data = {}
        
        # Fields that can be updated
        update_fields = [
            'name', 'phone', 'class', 'section', 'date_of_birth', 'gender',
            'address', 'parent_name', 'parent_phone', 'parent_email',
            'parent_occupation', 'blood_group', 'medical_conditions',
            'attendance', 'performance', 'status', 'profile_image'
        ]
        
        for field in update_fields:
            if field in data:
                update_data[field] = data[field]
        
        # Email can only be updated if not already taken
        if 'email' in data:
            new_email = data['email'].strip().lower()
            if new_email != student['email']:
                # Check if new email exists
                existing = collection.find_one({'email': new_email})
                if existing:
                    client.close()
                    return jsonify({
                        'success': False,
                        'error': 'Email already in use'
                    }), 400
                update_data['email'] = new_email
        
        update_data['updated_at'] = datetime.utcnow()
        
        # Update student
        result = collection.update_one(
            {'_id': student['_id']},
            {'$set': update_data}
        )
        
        client.close()
        
        if result.modified_count == 0:
            return jsonify({
                'success': False,
                'error': 'No changes made'
            }), 400
        
        return jsonify({
            'success': True,
            'message': 'Student updated successfully'
        }), 200
        
    except Exception as e:
        print(f"Error updating student: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to update student: {str(e)}'
        }), 500

# ==================== DELETE STUDENT ====================

@students_bp.route('/students/<student_id>', methods=['DELETE', 'OPTIONS'])
def delete_student(student_id):
    """Delete student"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        client = get_mongo_client()
        db = get_db()
        collection = db.students
        
        # Find student
        student = collection.find_one({'student_id': student_id})
        if not student:
            student = collection.find_one({'_id': ObjectId(student_id)})
        
        if not student:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Student not found'
            }), 404
        
        # Soft delete (update status) or hard delete
        # For soft delete:
        # collection.update_one(
        #     {'_id': student['_id']},
        #     {'$set': {'status': 'deleted', 'deleted_at': datetime.utcnow()}}
        # )
        
        # For hard delete:
        result = collection.delete_one({'_id': student['_id']})
        
        client.close()
        
        return jsonify({
            'success': True,
            'message': 'Student deleted successfully'
        }), 200
        
    except Exception as e:
        print(f"Error deleting student: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to delete student: {str(e)}'
        }), 500

# ==================== BULK DELETE STUDENTS ====================

@students_bp.route('/students/bulk-delete', methods=['POST', 'OPTIONS'])
def bulk_delete_students():
    """Bulk delete students"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        
        if not data or 'student_ids' not in data:
            return jsonify({
                'success': False,
                'error': 'No student IDs provided'
            }), 400
        
        student_ids = data['student_ids']
        
        if not isinstance(student_ids, list) or len(student_ids) == 0:
            return jsonify({
                'success': False,
                'error': 'Invalid student IDs'
            }), 400
        
        client = get_mongo_client()
        db = get_db()
        collection = db.students
        
        # Convert string IDs to ObjectId if needed
        object_ids = []
        for sid in student_ids:
            try:
                object_ids.append(ObjectId(sid))
            except:
                # Try to find by student_id
                student = collection.find_one({'student_id': sid})
                if student:
                    object_ids.append(student['_id'])
        
        # Delete students
        result = collection.delete_many({'_id': {'$in': object_ids}})
        
        client.close()
        
        return jsonify({
            'success': True,
            'message': f'Successfully deleted {result.deleted_count} students'
        }), 200
        
    except Exception as e:
        print(f"Error in bulk delete: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to delete students: {str(e)}'
        }), 500

# ==================== GET STUDENT STATISTICS ====================

@students_bp.route('/students/statistics', methods=['GET', 'OPTIONS'])
def get_student_statistics():
    """Get student statistics"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        client = get_mongo_client()
        db = get_db()
        collection = db.students
        
        # Get total count
        total_students = collection.count_documents({})
        
        # Get counts by status
        status_counts = {
            'active': collection.count_documents({'status': 'active'}),
            'inactive': collection.count_documents({'status': 'inactive'}),
            'graduated': collection.count_documents({'status': 'graduated'}),
            'transferred': collection.count_documents({'status': 'transferred'})
        }
        
        # Get counts by class
        class_counts = list(collection.aggregate([
            {'$group': {'_id': '$class', 'count': {'$sum': 1}}},
            {'$sort': {'_id': 1}}
        ]))
        
        # Get average attendance and performance
        stats = list(collection.aggregate([
            {'$group': {
                '_id': None,
                'avg_attendance': {'$avg': '$attendance'},
                'avg_performance': {'$avg': '$performance'},
                'top_performers': {
                    '$sum': {
                        '$cond': [{'$gte': ['$performance', 90]}, 1, 0]
                    }
                }
            }}
        ]))
        
        client.close()
        
        statistics = {
            'total_students': total_students,
            'status_counts': status_counts,
            'class_counts': {item['_id']: item['count'] for item in class_counts if item['_id']},
            'average_attendance': stats[0]['avg_attendance'] if stats else 0,
            'average_performance': stats[0]['avg_performance'] if stats else 0,
            'top_performers': stats[0]['top_performers'] if stats else 0
        }
        
        return jsonify({
            'success': True,
            'data': statistics
        }), 200
        
    except Exception as e:
        print(f"Error getting statistics: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to get statistics: {str(e)}'
        }), 500