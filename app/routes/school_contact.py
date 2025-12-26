# app/routes/school_contact.py
from flask import Blueprint, request, jsonify, make_response
from datetime import datetime
import re
import os
from pymongo import MongoClient
from bson import ObjectId
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header

school_contact_bp = Blueprint('school_contact', __name__)

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

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def serialize_document(doc):
    """Convert ObjectId to string for JSON serialization"""
    if doc and '_id' in doc:
        doc['_id'] = str(doc['_id'])
    return doc

# In school_contact.py
def add_cors_headers(response):
    """Add CORS headers to response"""
    origin = request.headers.get('Origin', 'http://localhost:5173')
    response.headers.add("Access-Control-Allow-Origin", origin)
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
    response.headers.add("Access-Control-Allow-Credentials", "true")
    return response

# ==================== EXISTING CONTACT FORM ENDPOINT ====================

@school_contact_bp.route('/school-contact', methods=['POST', 'OPTIONS'])  # REMOVED /api prefix
def create_school_contact():
    """Create a new school contact from contact form"""
    
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        # Debug: Print request headers
        print(f"📥 Headers: {dict(request.headers)}")
        print(f"📥 Content-Type: {request.content_type}")
        print(f"📥 Origin: {request.headers.get('Origin')}")
        
        # Get JSON data
        data = request.get_json()
        
        if not data:
            print("❌ No data provided")
            response = jsonify({
                'success': False,
                'error': 'No data provided'
            })
            return add_cors_headers(response), 400
        
        print(f"📥 Received data keys: {list(data.keys())}")
        
        # Validate required fields
        required_fields = ['schoolName', 'principalName', 'email', 'phone', 'schoolType']
        missing_fields = []
        
        for field in required_fields:
            if field not in data:
                missing_fields.append(field)
                print(f"❌ Missing field: {field}")
            elif not str(data[field]).strip():
                missing_fields.append(field)
                print(f"❌ Empty field: {field}")
        
        if missing_fields:
            response = jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing_fields)}',
                'missing_fields': missing_fields
            })
            return add_cors_headers(response), 400
        
        # Validate email
        email = data['email'].strip()
        if not validate_email(email):
            print(f"❌ Invalid email: {email}")
            response = jsonify({
                'success': False,
                'error': 'Invalid email format'
            })
            return add_cors_headers(response), 400
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        collection = db.school_contacts
        
        # Check if email already exists
        existing = collection.find_one({'email': email.lower()})
        if existing:
            client.close()
            print(f"❌ Email already exists: {email}")
            response = jsonify({
                'success': False,
                'error': 'Email already registered'
            })
            return add_cors_headers(response), 400
        
        # Prepare document with is_active default as false
        contact_doc = {
            'school_name': data['schoolName'].strip(),
            'principal_name': data['principalName'].strip(),
            'email': email.lower().strip(),
            'phone': data['phone'].strip(),
            'school_type': data['schoolType'].strip(),
            'student_count': data.get('studentCount', '').strip(),
            'address': data.get('address', '').strip(),
            'city': data.get('city', '').strip(),
            'state': data.get('state', '').strip(),
            'country': data.get('country', '').strip(),
            'website': data.get('website', '').strip(),
            'message': data.get('message', '').strip(),
            'preferred_contact': data.get('preferredContact', 'email'),
            'timeline': data.get('timeline', '3_months'),
            'grades': data.get('grades', []),
            'interests': data.get('interests', []),
            'is_approved': False,  # Default to false for admin review
            'is_active': False,    # Default to false, becomes true when approved
            'priority_level': 'normal',
            'source': 'contact_form',
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        print(f"📝 Inserting document for: {contact_doc['school_name']}")
        
        # Insert into database
        result = collection.insert_one(contact_doc)
        client.close()
        
        print(f"✅ Successfully inserted document with ID: {result.inserted_id}")
        
        response = jsonify({
            'success': True,
            'message': 'School contact submitted successfully',
            'data': {
                'id': str(result.inserted_id),
                'school_name': contact_doc['school_name'],
                'email': contact_doc['email']
            }
        })
        return add_cors_headers(response), 201
        
    except Exception as e:
        print(f"🔥 Error creating school contact: {str(e)}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        })
        return add_cors_headers(response), 500

# ==================== ADMIN ENDPOINTS ====================

@school_contact_bp.route('/admin/school-contacts', methods=['GET', 'OPTIONS'])  # REMOVED /api prefix
def get_school_contacts():
    """Get all school contacts with optional filters (Admin only)"""
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for GET contacts")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        # Get query parameters
        is_approved = request.args.get('is_approved')
        is_active = request.args.get('is_active')
        priority_level = request.args.get('priority_level')
        
        # Build query
        query = {}
        if is_approved is not None:
            query['is_approved'] = is_approved.lower() == 'true'
        if is_active is not None:
            query['is_active'] = is_active.lower() == 'true'
        if priority_level:
            query['priority_level'] = priority_level
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        collection = db.school_contacts
        
        # Fetch from MongoDB
        contacts = list(collection.find(query).sort('created_at', -1))
        client.close()
        
        # Serialize ObjectId
        contacts = [serialize_document(contact) for contact in contacts]
        
        response = jsonify({
            'success': True,
            'data': contacts,
            'count': len(contacts)
        })
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"Error fetching school contacts: {str(e)}")
        response = jsonify({
            'success': False,
            'error': 'Internal server error'
        })
        return add_cors_headers(response), 500

@school_contact_bp.route('/admin/school-contacts/pending', methods=['GET', 'OPTIONS'])  # REMOVED /api prefix
def get_pending_contacts():
    """Get only pending requests (is_active = false)"""
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for pending contacts")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        collection = db.school_contacts
        
        # Fetch only inactive requests (pending)
        contacts = list(collection.find({
            'is_active': False,
            'is_approved': False  # also not approved yet
        }).sort('created_at', -1))
        
        client.close()
        
        # Serialize ObjectId
        contacts = [serialize_document(contact) for contact in contacts]
        
        response = jsonify({
            'success': True,
            'data': contacts,
            'count': len(contacts)
        })
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"Error fetching pending contacts: {str(e)}")
        response = jsonify({
            'success': False,
            'error': 'Internal server error'
        })
        return add_cors_headers(response), 500

# Add OPTIONS method to all PUT endpoints
@school_contact_bp.route('/admin/school-contacts/<contact_id>/approve', methods=['PUT', 'OPTIONS'])  # REMOVED /api prefix
def approve_contact(contact_id):
    """Approve a school contact request"""
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for approve")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        collection = db.school_contacts
        
        # Generate a random password (you can make this more secure)
        import random
        import string
        password = ''.join(random.choices(string.ascii_letters + string.digits + '!@#$%^&*', k=12))
        
        update_data = {
            'is_approved': True,
            'is_active': True,  # Set to true when approved
            'accepted_plan': data.get('accepted_plan', 'basic'),
            'admin_notes': data.get('admin_notes', f'Approved on {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}'),
            'initial_password': password,  # Store initial password (hashed in production)
            'approved_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Update the document
        result = collection.update_one(
            {'_id': ObjectId(contact_id)},
            {'$set': update_data}
        )
        
        client.close()
        
        if result.modified_count == 0:
            response = jsonify({
                'success': False,
                'error': 'Contact not found or already approved'
            })
            return add_cors_headers(response), 404
        
        # Return password for admin to send manually
        response = jsonify({
            'success': True,
            'message': 'Contact approved successfully',
            'data': {
                'contact_id': contact_id,
                'password': password,  # In production, this should be sent via email, not returned
                'plan': data.get('accepted_plan', 'basic')
            }
        })
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"Error approving contact: {str(e)}")
        response = jsonify({
            'success': False,
            'error': 'Internal server error'
        })
        return add_cors_headers(response), 500

@school_contact_bp.route('/admin/school-contacts/<contact_id>/reject', methods=['PUT', 'OPTIONS'])  # REMOVED /api prefix
def reject_contact(contact_id):
    """Reject a school contact request"""
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for reject")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        collection = db.school_contacts
        
        update_data = {
            'is_approved': False,
            'is_active': False,  # Keep as false for rejected
            'rejection_reason': data.get('rejection_reason', ''),
            'admin_notes': data.get('admin_notes', f'Rejected on {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}'),
            'rejected_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Update the document
        result = collection.update_one(
            {'_id': ObjectId(contact_id)},
            {'$set': update_data}
        )
        
        client.close()
        
        if result.modified_count == 0:
            response = jsonify({
                'success': False,
                'error': 'Contact not found'
            })
            return add_cors_headers(response), 404
        
        response = jsonify({
            'success': True,
            'message': 'Contact rejected successfully'
        })
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"Error rejecting contact: {str(e)}")
        response = jsonify({
            'success': False,
            'error': 'Internal server error'
        })
        return add_cors_headers(response), 500

@school_contact_bp.route('/admin/school-contacts/<contact_id>/review', methods=['PUT', 'OPTIONS'])  # REMOVED /api prefix
def review_contact(contact_id):
    """Mark a contact for review"""
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for review")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        collection = db.school_contacts
        
        update_data = {
            'review_notes': data.get('review_notes', ''),
            'admin_notes': data.get('admin_notes', f'Marked for review on {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}'),
            'priority_level': data.get('priority_level', 'high'),
            'updated_at': datetime.utcnow()
        }
        
        # Update the document
        result = collection.update_one(
            {'_id': ObjectId(contact_id)},
            {'$set': update_data}
        )
        
        client.close()
        
        if result.modified_count == 0:
            response = jsonify({
                'success': False,
                'error': 'Contact not found'
            })
            return add_cors_headers(response), 404
        
        response = jsonify({
            'success': True,
            'message': 'Contact marked for review'
        })
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"Error updating contact review: {str(e)}")
        response = jsonify({
            'success': False,
            'error': 'Internal server error'
        })
        return add_cors_headers(response), 500

@school_contact_bp.route('/admin/school-contacts/<contact_id>/activate', methods=['PUT', 'OPTIONS'])  # REMOVED /api prefix
def activate_contact(contact_id):
    """Activate an inactive contact (without full approval)"""
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for activate")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        collection = db.school_contacts
        
        update_data = {
            'is_active': True,
            'is_approved': data.get('is_approved', False),  # Optional: approve at same time
            'admin_notes': data.get('admin_notes', f'Activated on {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}'),
            'activated_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Update the document
        result = collection.update_one(
            {'_id': ObjectId(contact_id)},
            {'$set': update_data}
        )
        
        client.close()
        
        if result.modified_count == 0:
            response = jsonify({
                'success': False,
                'error': 'Contact not found'
            })
            return add_cors_headers(response), 404
        
        response = jsonify({
            'success': True,
            'message': 'Contact activated successfully'
        })
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"Error activating contact: {str(e)}")
        response = jsonify({
            'success': False,
            'error': 'Internal server error'
        })
        return add_cors_headers(response), 500

@school_contact_bp.route('/admin/school-contacts/<contact_id>/deactivate', methods=['PUT', 'OPTIONS'])  # REMOVED /api prefix
def deactivate_contact(contact_id):
    """Deactivate an active contact"""
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for deactivate")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        collection = db.school_contacts
        
        update_data = {
            'is_active': False,
            'admin_notes': data.get('admin_notes', f'Deactivated on {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}'),
            'deactivated_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Update the document
        result = collection.update_one(
            {'_id': ObjectId(contact_id)},
            {'$set': update_data}
        )
        
        client.close()
        
        if result.modified_count == 0:
            response = jsonify({
                'success': False,
                'error': 'Contact not found'
            })
            return add_cors_headers(response), 404
        
        response = jsonify({
            'success': True,
            'message': 'Contact deactivated successfully'
        })
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"Error deactivating contact: {str(e)}")
        response = jsonify({
            'success': False,
            'error': 'Internal server error'
        })
        return add_cors_headers(response), 500


@school_contact_bp.route('/admin/send-email', methods=['POST', 'OPTIONS'])
def send_email():
    """Send email notification"""
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for send-email")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        
        # Get email configuration from environment variables
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', 587))
        smtp_username = os.getenv('SMTP_USERNAME')
        smtp_password = os.getenv('SMTP_PASSWORD')
        from_email = os.getenv('FROM_EMAIL')
        from_name = os.getenv('FROM_NAME', 'IntelliLearn Admin')
        
        # Validate required configuration
        if not all([smtp_server, smtp_username, smtp_password, from_email]):
            print("❌ SMTP configuration is incomplete")
            response = jsonify({
                'success': False,
                'error': 'Email server configuration is incomplete'
            })
            return add_cors_headers(response), 500
        
        # Get email data
        to_email = data.get('to_email')
        subject = data.get('subject')
        message_body = data.get('message')
        
        if not all([to_email, subject, message_body]):
            print("❌ Missing email data")
            response = jsonify({
                'success': False,
                'error': 'Missing required email fields'
            })
            return add_cors_headers(response), 400
        
        print(f"📧 Preparing to send email to: {to_email}")
        print(f"📧 Subject: {subject}")
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = f"{from_name} <{from_email}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Add HTML and plain text versions
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                .footer {{ text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; color: #666; font-size: 12px; }}
                .button {{ display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
                .logo {{ font-size: 24px; font-weight: bold; margin-bottom: 10px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="logo">IntelliLearn</div>
                    <div>AI-Powered Education Platform</div>
                </div>
                <div class="content">
                    {message_body.replace('\n', '<br>')}
                    <br><br>
                    <div class="footer">
                        <p>© 2024 IntelliLearn. All rights reserved.</p>
                        <p>This is an automated message, please do not reply to this email.</p>
                        <p>Need help? Contact our support team at support@intellilearn.com</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Add HTML version
        msg.attach(MIMEText(html_content, 'html'))
        
        # Add plain text version as alternative
        plain_text = message_body
        msg.attach(MIMEText(plain_text, 'plain'))
        
        # Send email
        try:
            # Connect to SMTP server
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()  # Upgrade to secure connection
            server.login(smtp_username, smtp_password)
            
            # Send email
            server.send_message(msg)
            server.quit()
            
            print(f"✅ Email successfully sent to {to_email}")
            
            # Log the email in database (optional)
            client = get_mongo_client()
            db = get_db()
            collection = db.email_logs  # Create this collection if it doesn't exist
            
            email_log = {
                'to_email': to_email,
                'subject': subject,
                'message': message_body,
                'sent_at': datetime.utcnow(),
                'status': 'sent'
            }
            collection.insert_one(email_log)
            client.close()
            
            response = jsonify({
                'success': True,
                'message': 'Email sent successfully'
            })
            return add_cors_headers(response), 200
            
        except smtplib.SMTPAuthenticationError:
            print("❌ SMTP authentication failed")
            response = jsonify({
                'success': False,
                'error': 'Email server authentication failed. Check your credentials.'
            })
            return add_cors_headers(response), 500
            
        except smtplib.SMTPException as e:
            print(f"❌ SMTP error: {str(e)}")
            response = jsonify({
                'success': False,
                'error': f'Failed to send email: {str(e)}'
            })
            return add_cors_headers(response), 500
            
        except Exception as e:
            print(f"❌ Email sending error: {str(e)}")
            response = jsonify({
                'success': False,
                'error': f'Failed to send email: {str(e)}'
            })
            return add_cors_headers(response), 500
            
    except Exception as e:
        print(f"❌ Error in send_email endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        })
        return add_cors_headers(response), 500
# In your Flask backend (app.py)
@school_contact_bp.route('/admin/institutions/approved', methods=['GET', 'OPTIONS'])
def get_approved_institutions():
    """Get all approved institutions"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        client = get_mongo_client()
        db = get_db()
        collection = db.school_contacts
        
        institutions = list(collection.find({
            "is_approved": True
        }).sort("created_at", -1))
        
        client.close()
        
        # Convert ObjectId to string
        for inst in institutions:
            inst['_id'] = str(inst['_id'])
            
        return jsonify({
            "success": True,
            "data": institutions,
            "count": len(institutions)
        }), 200
        
    except Exception as e:
        print(f"Error fetching approved institutions: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@school_contact_bp.route('/admin/institutions/<institution_id>/status', methods=['PUT', 'OPTIONS'])
def update_institution_status(institution_id):
    """Update institution active status"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        new_status = data.get('is_active')
        
        if new_status is None:
            return jsonify({
                "success": False,
                "error": "is_active field is required"
            }), 400
        
        client = get_mongo_client()
        db = get_db()
        collection = db.school_contacts
        
        result = collection.update_one(
            {"_id": ObjectId(institution_id)},
            {"$set": {"is_active": new_status, "updated_at": datetime.utcnow()}}
        )
        
        client.close()
        
        if result.modified_count == 0:
            return jsonify({
                "success": False,
                "error": "Institution not found or status unchanged"
            }), 404
            
        return jsonify({
            "success": True,
            "message": f"Institution {'activated' if new_status else 'deactivated'} successfully"
        })
        
    except Exception as e:
        print(f"Error updating institution status: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@school_contact_bp.route('/api/admin/institutions/<institution_id>/send-credentials', methods=['POST'])
def send_institution_credentials(institution_id):
    try:
        # Get institution details
        institution = db.school_contacts.find_one({"_id": ObjectId(institution_id)})
        
        if not institution:
            return jsonify({
                "success": False,
                "error": "Institution not found"
            }), 404
        
        # Generate a new password
        new_password = generate_secure_password()
        
        # Hash the password
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        
        # Update password in database
        db.school_contacts.update_one(
            {"_id": ObjectId(institution_id)},
            {"$set": {"initial_password": new_password}}
        )
        
        # Send email with credentials
        email_subject = f"Your IntelliLearn Credentials - {institution['school_name']}"
        email_message = f"""
Dear {institution['principal_name']},

Your IntelliLearn account has been created successfully!

**Login Credentials:**
- Email: {institution['email']}
- Password: {new_password}
- Login URL: https://platform.intellilearn.com/login

**Important Security Notes:**
1. Please change your password after first login
2. Never share your credentials with anyone
3. Contact support if you suspect any unauthorized access

**Getting Started:**
1. Log in to your account
2. Complete your institution profile
3. Invite teachers and students
4. Explore our learning resources

If you have any questions, please contact our support team at support@intellilearn.com.

Best regards,
IntelliLearn Team
        """
        
        # Send email using your email service
        send_email(
            to_email=institution['email'],
            subject=email_subject,
            message=email_message,
            from_email="support@intellilearn.com"
        )
        
        return jsonify({
            "success": True,
            "message": "Credentials sent successfully",
            "password": new_password  # Only for admin reference
        })
        
    except Exception as e:
        print(f"Error sending credentials: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500