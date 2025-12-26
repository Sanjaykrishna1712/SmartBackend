from flask import Blueprint, request, jsonify, make_response
from datetime import datetime, timedelta
import os
from pymongo import MongoClient
from bson import ObjectId
import bcrypt
import jwt
import re

# Create blueprint
login_bp = Blueprint('login', __name__)

# JWT Secret Key (use environment variable in production)
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24

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
    response.headers.add("Access-Control-Allow-Origin", "http://localhost:5173")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
    response.headers.add("Access-Control-Allow-Credentials", "true")
    return response

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def hash_password(password):
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed_password):
    """Check if password matches hash"""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def generate_token(user_id, user_role):
    """Generate JWT token"""
    payload = {
        'user_id': user_id,
        'user_role': user_role,
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def decode_token(token):
    """Decode and verify JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None  # Token expired
    except jwt.InvalidTokenError:
        return None  # Invalid token

# ==================== PRINCIPAL LOGIN ====================

@login_bp.route('/auth/principal-login', methods=['POST', 'OPTIONS'])
def principal_login():
    """Handle principal login with MongoDB verification"""
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for principal-login")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        print(f"📥 Principal login attempt with data: {data}")
        
        email = data.get('email', '').lower().strip()
        password = data.get('password', '').strip()
        principal_code = data.get('principalCode', '').strip()
        
        # Validate inputs
        if not email or not password:
            response = jsonify({
                'success': False,
                'error': 'Email and password are required'
            })
            return add_cors_headers(response), 400
        
        if not validate_email(email):
            response = jsonify({
                'success': False,
                'error': 'Invalid email format'
            })
            return add_cors_headers(response), 400
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        collection = db.school_contacts
        
        # Build query - check by email OR principal_code if provided
        query = {'email': email}
        if principal_code:
            query = {'$or': [{'email': email}, {'principal_code': principal_code}]}
        
        # Find the school contact
        school_contact = collection.find_one(query)
        
        if not school_contact:
            print(f"❌ No school contact found for email: {email}")
            client.close()
            response = jsonify({
                'success': False,
                'error': 'No account found with these credentials'
            })
            return add_cors_headers(response), 404
        
        # Check if account is approved
        if not school_contact.get('is_approved', False):
            print(f"❌ Account not approved for email: {email}")
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Your account is pending approval. Please contact support.'
            })
            return add_cors_headers(response), 403
        
        # Check if account is active
        if not school_contact.get('is_active', False):
            print(f"❌ Account not active for email: {email}")
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Your account is not active. Please contact support.'
            })
            return add_cors_headers(response), 403
        
        # Check password
        stored_password = school_contact.get('initial_password', '')
        stored_hashed_password = school_contact.get('hashed_password', '')
        
        # Check password (support both plain text for demo and hashed for production)
        password_valid = False
        
        if stored_hashed_password:
            # Check hashed password (production)
            password_valid = check_password(password, stored_hashed_password)
        elif stored_password:
            # Check plain text password (demo)
            password_valid = (password == stored_password)
        else:
            # No password stored (should not happen)
            print(f"❌ No password stored for email: {email}")
            password_valid = False
        
        if not password_valid:
            print(f"❌ Password mismatch for email: {email}")
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Invalid credentials'
            })
            return add_cors_headers(response), 401
        
        # Password is valid - update last login
        collection.update_one(
            {'_id': school_contact['_id']},
            {'$set': {'last_login': datetime.utcnow()}}
        )
        
        # Serialize the document
        principal = serialize_document(school_contact)
        client.close()
        
        # Generate JWT token
        token = generate_token(str(school_contact['_id']), 'principal')
        
        # Prepare response data
        response_data = {
            'success': True,
            'message': 'Login successful',
            'data': {
                'principal': {
                    '_id': principal['_id'],
                    'email': principal['email'],
                    'principal_name': principal['principal_name'],
                    'school_name': principal['school_name'],
                    'principal_code': principal.get('principal_code', '')
                },
                'school': {
                    'school_name': principal['school_name'],
                    'school_type': principal['school_type'],
                    'student_count': principal.get('student_count', ''),
                    'address': principal.get('address', ''),
                    'city': principal.get('city', ''),
                    'state': principal.get('state', ''),
                    'country': principal.get('country', ''),
                    'is_approved': principal['is_approved'],
                    'is_active': principal['is_active'],
                    'accepted_plan': principal.get('accepted_plan', 'basic')
                },
                'token': token,
                'expires_in': JWT_EXPIRATION_HOURS * 3600  # seconds
            }
        }
        
        print(f"✅ Principal login successful for: {principal['email']}")
        response = jsonify(response_data)
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"❌ Error in principal login: {str(e)}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            'success': False,
            'error': f'Login failed: {str(e)}'
        })
        return add_cors_headers(response), 500

# ==================== SUPER ADMIN LOGIN ====================

@login_bp.route('/auth/superadmin-login', methods=['POST', 'OPTIONS'])
def superadmin_login():
    """Handle super admin login"""
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for superadmin-login")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        print(f"📥 Super admin login attempt")
        
        email = data.get('email', '').lower().strip()
        password = data.get('password', '').strip()
        
        # Validate inputs
        if not email or not password:
            response = jsonify({
                'success': False,
                'error': 'Email and password are required'
            })
            return add_cors_headers(response), 400
        
        # Hardcoded super admin credentials (store in database in production)
        SUPER_ADMINS = {
            'admin@gmail.com': {
                'password': 'admin',  # Plain text for demo - hash in production
                'name': 'System Administrator',
                'superadmin_code': 'SUPER001'
            }
        }
        
        # Check if email exists in super admins
        if email not in SUPER_ADMINS:
            print(f"❌ No super admin found for email: {email}")
            response = jsonify({
                'success': False,
                'error': 'No account found with these credentials'
            })
            return add_cors_headers(response), 404
        
        admin_info = SUPER_ADMINS[email]
        
        # Check password
        if password != admin_info['password']:  # In production, use password hashing
            print(f"❌ Password mismatch for super admin: {email}")
            response = jsonify({
                'success': False,
                'error': 'Invalid credentials'
            })
            return add_cors_headers(response), 401
        
        # Generate JWT token
        token = generate_token(f"superadmin_{email}", 'superadmin')
        
        # Prepare response data
        response_data = {
            'success': True,
            'message': 'Super admin login successful',
            'data': {
                'superadmin': {
                    'email': email,
                    'name': admin_info['name'],
                    'superadmin_code': admin_info['superadmin_code']
                },
                'token': token,
                'expires_in': JWT_EXPIRATION_HOURS * 3600
            }
        }
        
        print(f"✅ Super admin login successful for: {email}")
        response = jsonify(response_data)
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"❌ Error in super admin login: {str(e)}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            'success': False,
            'error': f'Login failed: {str(e)}'
        })
        return add_cors_headers(response), 500

# ==================== TEACHER LOGIN ====================

@login_bp.route('/auth/teacher-login', methods=['POST', 'OPTIONS'])
def teacher_login():
    """Handle teacher login"""
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for teacher-login")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        print(f"📥 Teacher login attempt")
        
        email = data.get('email', '').lower().strip()
        password = data.get('password', '').strip()
        teacher_code = data.get('teacherCode', '').strip()
        
        # For demo purposes - in production, connect to teachers database
        DEMO_TEACHERS = {
            'teacher@school.edu': {
                'password': 'password123',
                'name': 'Sarah Johnson',
                'teacher_code': 'TCH001',
                'subject': 'Mathematics'
            }
        }
        
        # Check if email exists
        if email not in DEMO_TEACHERS:
            # Check by teacher code if provided
            if teacher_code:
                for teacher_email, teacher_info in DEMO_TEACHERS.items():
                    if teacher_info.get('teacher_code') == teacher_code:
                        email = teacher_email
                        break
                else:
                    email = None
        
        if not email or email not in DEMO_TEACHERS:
            print(f"❌ No teacher found")
            response = jsonify({
                'success': False,
                'error': 'No account found with these credentials'
            })
            return add_cors_headers(response), 404
        
        teacher_info = DEMO_TEACHERS[email]
        
        # Check password
        if password != teacher_info['password']:
            print(f"❌ Password mismatch for teacher: {email}")
            response = jsonify({
                'success': False,
                'error': 'Invalid credentials'
            })
            return add_cors_headers(response), 401
        
        # Generate JWT token
        token = generate_token(f"teacher_{email}", 'teacher')
        
        # Prepare response data
        response_data = {
            'success': True,
            'message': 'Teacher login successful',
            'data': {
                'teacher': {
                    'email': email,
                    'name': teacher_info['name'],
                    'teacher_code': teacher_info['teacher_code'],
                    'subject': teacher_info['subject']
                },
                'token': token,
                'expires_in': JWT_EXPIRATION_HOURS * 3600
            }
        }
        
        print(f"✅ Teacher login successful for: {email}")
        response = jsonify(response_data)
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"❌ Error in teacher login: {str(e)}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            'success': False,
            'error': f'Login failed: {str(e)}'
        })
        return add_cors_headers(response), 500

# ==================== STUDENT LOGIN ====================

@login_bp.route('/auth/student-login', methods=['POST', 'OPTIONS'])
def student_login():
    """Handle student login"""
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for student-login")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        print(f"📥 Student login attempt")
        
        email = data.get('email', '').lower().strip()
        password = data.get('password', '').strip()
        student_id = data.get('studentId', '').strip()
        
        # For demo purposes - in production, connect to students database
        DEMO_STUDENTS = {
            'student@school.edu': {
                'password': 'password123',
                'name': 'Emma Wilson',
                'student_id': 'STU2024001',
                'grade': '10th Grade'
            }
        }
        
        # Check if email exists
        if email not in DEMO_STUDENTS:
            # Check by student ID if provided
            if student_id:
                for student_email, student_info in DEMO_STUDENTS.items():
                    if student_info.get('student_id') == student_id:
                        email = student_email
                        break
                else:
                    email = None
        
        if not email or email not in DEMO_STUDENTS:
            print(f"❌ No student found")
            response = jsonify({
                'success': False,
                'error': 'No account found with these credentials'
            })
            return add_cors_headers(response), 404
        
        student_info = DEMO_STUDENTS[email]
        
        # Check password
        if password != student_info['password']:
            print(f"❌ Password mismatch for student: {email}")
            response = jsonify({
                'success': False,
                'error': 'Invalid credentials'
            })
            return add_cors_headers(response), 401
        
        # Generate JWT token
        token = generate_token(f"student_{email}", 'student')
        
        # Prepare response data
        response_data = {
            'success': True,
            'message': 'Student login successful',
            'data': {
                'student': {
                    'email': email,
                    'name': student_info['name'],
                    'student_id': student_info['student_id'],
                    'grade': student_info['grade']
                },
                'token': token,
                'expires_in': JWT_EXPIRATION_HOURS * 3600
            }
        }
        
        print(f"✅ Student login successful for: {email}")
        response = jsonify(response_data)
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"❌ Error in student login: {str(e)}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            'success': False,
            'error': f'Login failed: {str(e)}'
        })
        return add_cors_headers(response), 500

# ==================== TOKEN VERIFICATION ====================

@login_bp.route('/auth/verify-token', methods=['POST', 'OPTIONS'])
def verify_token():
    """Verify JWT token"""
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for verify-token")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        token = data.get('token', '').strip()
        
        if not token:
            response = jsonify({
                'success': False,
                'error': 'Token is required'
            })
            return add_cors_headers(response), 400
        
        # Decode token
        payload = decode_token(token)
        
        if not payload:
            response = jsonify({
                'success': False,
                'error': 'Invalid or expired token'
            })
            return add_cors_headers(response), 401
        
        # Token is valid
        response_data = {
            'success': True,
            'message': 'Token is valid',
            'data': {
                'user_id': payload.get('user_id'),
                'user_role': payload.get('user_role'),
                'expires_at': payload.get('exp')
            }
        }
        
        response = jsonify(response_data)
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"❌ Error verifying token: {str(e)}")
        response = jsonify({
            'success': False,
            'error': f'Token verification failed: {str(e)}'
        })
        return add_cors_headers(response), 500

# ==================== LOGOUT ====================

@login_bp.route('/auth/logout', methods=['POST', 'OPTIONS'])
def logout():
    """Handle logout (invalidate token on client side)"""
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for logout")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        # In a production system, you might want to:
        # 1. Add token to blacklist
        # 2. Store blacklist in Redis or database
        # 3. Check blacklist on each request
        
        response_data = {
            'success': True,
            'message': 'Logout successful'
        }
        
        print("✅ User logged out successfully")
        response = jsonify(response_data)
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"❌ Error in logout: {str(e)}")
        response = jsonify({
            'success': False,
            'error': f'Logout failed: {str(e)}'
        })
        return add_cors_headers(response), 500

# ==================== CHANGE PASSWORD ====================

@login_bp.route('/auth/change-password', methods=['POST', 'OPTIONS'])
def change_password():
    """Change password for principals"""
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for change-password")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        token = data.get('token', '').strip()
        current_password = data.get('current_password', '').strip()
        new_password = data.get('new_password', '').strip()
        
        # Validate inputs
        if not token or not current_password or not new_password:
            response = jsonify({
                'success': False,
                'error': 'All fields are required'
            })
            return add_cors_headers(response), 400
        
        if len(new_password) < 8:
            response = jsonify({
                'success': False,
                'error': 'New password must be at least 8 characters long'
            })
            return add_cors_headers(response), 400
        
        # Verify token
        payload = decode_token(token)
        if not payload or payload.get('user_role') != 'principal':
            response = jsonify({
                'success': False,
                'error': 'Invalid or expired token'
            })
            return add_cors_headers(response), 401
        
        user_id = payload.get('user_id')
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        collection = db.school_contacts
        
        # Find the principal
        principal = collection.find_one({'_id': ObjectId(user_id)})
        
        if not principal:
            client.close()
            response = jsonify({
                'success': False,
                'error': 'User not found'
            })
            return add_cors_headers(response), 404
        
        # Check current password
        stored_password = principal.get('initial_password', '')
        stored_hashed_password = principal.get('hashed_password', '')
        
        current_password_valid = False
        
        if stored_hashed_password:
            current_password_valid = check_password(current_password, stored_hashed_password)
        elif stored_password:
            current_password_valid = (current_password == stored_password)
        
        if not current_password_valid:
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Current password is incorrect'
            })
            return add_cors_headers(response), 401
        
        # Hash new password
        new_hashed_password = hash_password(new_password)
        
        # Update password in database
        collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {
                'hashed_password': new_hashed_password,
                'password_changed_at': datetime.utcnow()
            }}
        )
        
        client.close()
        
        response_data = {
            'success': True,
            'message': 'Password changed successfully'
        }
        
        print(f"✅ Password changed for user: {user_id}")
        response = jsonify(response_data)
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"❌ Error changing password: {str(e)}")
        response = jsonify({
            'success': False,
            'error': f'Failed to change password: {str(e)}'
        })
        return add_cors_headers(response), 500