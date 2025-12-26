from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_pymongo import PyMongo
from pymongo import MongoClient
from bson import ObjectId
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
import logging
from datetime import datetime
import json

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for your React app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB configuration
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/SmartEducation')
DB_NAME = os.getenv('MONGO_DB_NAME', 'SmartEducation')

# Initialize MongoDB
try:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    mongo_connected = True
    logger.info(f"Connected to MongoDB: {DB_NAME}")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {str(e)}")
    mongo_connected = False

# Email configuration from environment variables
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
SMTP_USERNAME = os.getenv('SMTP_USERNAME')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
FROM_EMAIL = os.getenv('FROM_EMAIL', 'admin@intellilearn.com')
FROM_NAME = os.getenv('FROM_NAME', 'IntelliLearn Admin')

def create_approval_email_html(to_email, subject, message, institution_name):
    """Create HTML for approval email"""
    # Extract password from message if exists
    temp_password = None
    plan = "Basic"
    
    if 'Temporary Password: ' in message:
        try:
            temp_password = message.split('Temporary Password: ')[1].split('\n')[0]
        except:
            temp_password = "Check the email text"
    
    if 'Plan: ' in message:
        try:
            plan = message.split('Plan: ')[1].split('\n')[0]
        except:
            pass
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #4CAF50 0%, #2E7D32 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
            .credentials {{ background: #e8f4ff; border-left: 4px solid #2196F3; padding: 15px; margin: 20px 0; }}
            .button {{ display: inline-block; background: linear-gradient(135deg, #4CAF50 0%, #2E7D32 100%); color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin: 15px 0; }}
            .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #666; text-align: center; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🎓 IntelliLearn</h1>
            <h2>Your Account Has Been Approved!</h2>
        </div>
        
        <div class="content">
            <p>Dear {institution_name} Administrator,</p>
            
            <p>We are pleased to inform you that your institution's request to join IntelliLearn has been approved!</p>
            
            <div class="credentials">
                <h3>📋 Account Details:</h3>
                <p><strong>Institution:</strong> {institution_name}</p>
                <p><strong>Login Email:</strong> {to_email}</p>
                <p><strong>Temporary Password:</strong> <code>{temp_password if temp_password else 'Check the email text'}</code></p>
                <p><strong>Plan:</strong> {plan}</p>
            </div>
            
            <h3>🚀 Next Steps:</h3>
            <ol>
                <li>Visit: <a href="https://intellilearn.com/login">https://intellilearn.com/login</a></li>
                <li>Log in with the credentials above</li>
                <li>You will be prompted to change your password on first login</li>
            </ol>
            
            <p style="background: #fff3cd; padding: 15px; border-radius: 5px; border-left: 4px solid #ffc107;">
                ⚠️ <strong>Important:</strong> This password is temporary. Please change it immediately after first login for security.
            </p>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="https://intellilearn.com/login" class="button">Login to IntelliLearn</a>
            </div>
            
            <p>If you have any questions or need assistance, please contact our support team.</p>
            
            <p>Best regards,<br>
            <strong>IntelliLearn Team</strong></p>
        </div>
        
        <div class="footer">
            <p>This is an automated message. Please do not reply to this email.</p>
            <p>© {datetime.now().year} IntelliLearn. All rights reserved.</p>
        </div>
    </body>
    </html>
    """
    return html_content

def create_rejection_email_html(to_email, subject, message, institution_name):
    """Create HTML for rejection email"""
    # Extract rejection reason if exists
    rejection_reason = None
    if 'Rejection Reason:' in message:
        try:
            rejection_reason = message.split('Rejection Reason:')[1].split('\n')[0].strip()
        except:
            rejection_reason = "Please refer to the email content for details"
    else:
        # Try to extract reason from different formats
        for line in message.split('\n'):
            if 'reason:' in line.lower() or 'because' in line.lower():
                rejection_reason = line.strip()
                break
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #f44336 0%, #c62828 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
            .info-box {{ background: #ffebee; border-left: 4px solid #f44336; padding: 15px; margin: 20px 0; }}
            .button {{ display: inline-block; background: linear-gradient(135deg, #2196F3 0%, #1976D2 100%); color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin: 15px 0; }}
            .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #666; text-align: center; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🎓 IntelliLearn</h1>
            <h2>Application Status Update</h2>
        </div>
        
        <div class="content">
            <p>Dear {institution_name} Administrator,</p>
            
            <p>Thank you for your interest in IntelliLearn. After careful review of your application, we regret to inform you that we are unable to approve your request at this time.</p>
            
            <div class="info-box">
                <h3>📋 Application Details:</h3>
                <p><strong>Institution:</strong> {institution_name}</p>
                <p><strong>Application Email:</strong> {to_email}</p>
                <p><strong>Status:</strong> <span style="color: #f44336; font-weight: bold;">Not Approved</span></p>
                {f'<p><strong>Reason:</strong> {rejection_reason}</p>' if rejection_reason else ''}
            </div>
            
            <h3>💡 Next Steps:</h3>
            <ol>
                <li>You may reapply after addressing the concerns mentioned above</li>
                <li>If you believe this decision was made in error, please contact our support team</li>
                <li>You can submit a new application with additional documentation</li>
            </ol>
            
            <div style="background: #e3f2fd; padding: 15px; border-radius: 5px; border-left: 4px solid #2196F3; margin: 20px 0;">
                <h4 style="margin-top: 0;">Need Assistance?</h4>
                <p>Our support team is here to help you understand the requirements and guide you through the application process.</p>
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="https://intellilearn.com/contact" class="button">Contact Support</a>
                <a href="https://intellilearn.com/apply" style="margin-left: 10px;" class="button">Reapply Now</a>
            </div>
            
            <p>We appreciate your interest in IntelliLearn and hope to serve you in the future.</p>
            
            <p>Best regards,<br>
            <strong>IntelliLearn Review Team</strong></p>
        </div>
        
        <div class="footer">
            <p>This is an automated message. Please do not reply to this email.</p>
            <p>© {datetime.now().year} IntelliLearn. All rights reserved.</p>
        </div>
    </body>
    </html>
    """
    return html_content

def create_welcome_email_html(to_email, subject, message, institution_name):
    """Create HTML for welcome/notification emails"""
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #2196F3 0%, #1976D2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
            .info-box {{ background: #e3f2fd; border-left: 4px solid #2196F3; padding: 15px; margin: 20px 0; }}
            .button {{ display: inline-block; background: linear-gradient(135deg, #2196F3 0%, #1976D2 100%); color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin: 15px 0; }}
            .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #666; text-align: center; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🎓 IntelliLearn</h1>
            <h2>{subject}</h2>
        </div>
        
        <div class="content">
            <p>Dear {institution_name} Administrator,</p>
            
            <div style="white-space: pre-line; background: white; padding: 20px; border-radius: 5px; border: 1px solid #e0e0e0;">
                {message.replace('\n', '<br>')}
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="https://intellilearn.com/login" class="button">Visit IntelliLearn</a>
                <a href="https://intellilearn.com/contact" style="margin-left: 10px;" class="button">Contact Support</a>
            </div>
            
            <p>Best regards,<br>
            <strong>IntelliLearn Team</strong></p>
        </div>
        
        <div class="footer">
            <p>This is an automated message. Please do not reply to this email.</p>
            <p>© {datetime.now().year} IntelliLearn. All rights reserved.</p>
        </div>
    </body>
    </html>
    """
    return html_content

def send_email_via_smtp(to_email, subject, message, institution_name, email_type='approval'):
    """Send email using SMTP with different templates based on type"""
    try:
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f'{FROM_NAME} <{FROM_EMAIL}>'
        msg['To'] = to_email
        msg['Reply-To'] = FROM_EMAIL
        
        # Determine which HTML template to use
        if email_type == 'approval':
            html_content = create_approval_email_html(to_email, subject, message, institution_name)
        elif email_type == 'rejection':
            html_content = create_rejection_email_html(to_email, subject, message, institution_name)
        else:
            html_content = create_welcome_email_html(to_email, subject, message, institution_name)
        
        # Create plain text version
        text_content = message
        
        # Attach both versions
        msg.attach(MIMEText(text_content, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))
        
        # Connect to SMTP server
        logger.info(f"Connecting to SMTP server: {SMTP_SERVER}:{SMTP_PORT}")
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()  # Secure the connection
        
        # Login to SMTP server
        logger.info(f"Logging in as: {SMTP_USERNAME}")
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        
        # Send email
        logger.info(f"Sending {email_type} email to: {to_email}")
        server.send_message(msg)
        
        # Close connection
        server.quit()
        logger.info(f"Email sent successfully to {to_email}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {str(e)}")
        return False

@app.route('/api/send-email', methods=['POST'])
def send_email():
    """API endpoint to send email"""
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ['to_email', 'subject', 'message', 'institution_name']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400
        
        # Determine email type based on subject or content
        email_type = data.get('email_type', 'general')
        if 'approval' in data['subject'].lower() or 'approved' in data['subject'].lower():
            email_type = 'approval'
        elif 'rejection' in data['subject'].lower() or 'rejected' in data['subject'].lower() or 'not approved' in data['subject'].lower():
            email_type = 'rejection'
        
        # Send email
        success = send_email_via_smtp(
            to_email=data['to_email'],
            subject=data['subject'],
            message=data['message'],
            institution_name=data['institution_name'],
            email_type=email_type
        )
        
        # Log email in MongoDB if connected
        if mongo_connected:
            try:
                email_log = {
                    'to_email': data['to_email'],
                    'subject': data['subject'],
                    'institution_name': data['institution_name'],
                    'email_type': email_type,
                    'status': 'sent' if success else 'failed',
                    'timestamp': datetime.now(),
                    'ip_address': request.remote_addr,
                    'content_preview': data['message'][:200] + '...' if len(data['message']) > 200 else data['message']
                }
                result = db.email_logs.insert_one(email_log)
                logger.info(f"Email logged to MongoDB with ID: {result.inserted_id}")
            except Exception as e:
                logger.error(f"Failed to log email to MongoDB: {str(e)}")
        
        if success:
            return jsonify({
                'success': True,
                'message': f'{email_type.capitalize()} email sent successfully',
                'email_type': email_type
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to send email'
            }), 500
            
    except Exception as e:
        logger.error(f"Error in send-email endpoint: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@app.route('/api/send-approval-email', methods=['POST'])
def send_approval_email():
    """API endpoint specifically for approval emails"""
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ['to_email', 'institution_name', 'password', 'plan']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400
        
        # Create approval message
        message = f"""Dear {data['institution_name']} Administrator,

We are pleased to inform you that your institution's request to join IntelliLearn has been approved!

Account Details:
Institution: {data['institution_name']}
Login Email: {data['to_email']}
Temporary Password: {data['password']}
Plan: {data.get('plan', 'Basic')}

Next Steps:
1. Visit: https://intellilearn.com/login
2. Log in with the credentials above
3. You will be prompted to change your password on first login

Important: This password is temporary. Please change it immediately after first login for security.

Best regards,
IntelliLearn Team"""
        
        # Send approval email
        success = send_email_via_smtp(
            to_email=data['to_email'],
            subject=f"🎉 IntelliLearn Account Approved - {data['institution_name']}",
            message=message,
            institution_name=data['institution_name'],
            email_type='approval'
        )
        
        # Log to MongoDB
        if mongo_connected and success:
            try:
                email_log = {
                    'to_email': data['to_email'],
                    'subject': f"IntelliLearn Account Approved - {data['institution_name']}",
                    'institution_name': data['institution_name'],
                    'email_type': 'approval',
                    'status': 'sent',
                    'timestamp': datetime.now(),
                    'ip_address': request.remote_addr
                }
                db.email_logs.insert_one(email_log)
            except Exception as e:
                logger.error(f"Failed to log approval email: {str(e)}")
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Approval email sent successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to send approval email'
            }), 500
            
    except Exception as e:
        logger.error(f"Error in send-approval-email endpoint: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@app.route('/api/send-rejection-email', methods=['POST'])
def send_rejection_email():
    """API endpoint specifically for rejection emails"""
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ['to_email', 'institution_name']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400
        
        # Get rejection reason
        rejection_reason = data.get('rejection_reason', 'Your application did not meet our current requirements. Please review our guidelines and reapply.')
        
        # Create rejection message
        message = f"""Dear {data['institution_name']} Administrator,

Thank you for your interest in IntelliLearn. After careful review of your application, we regret to inform you that we are unable to approve your request at this time.

Rejection Reason: {rejection_reason}

Application Details:
Institution: {data['institution_name']}
Application Email: {data['to_email']}

Next Steps:
1. You may reapply after addressing the concerns mentioned above
2. If you believe this decision was made in error, please contact our support team
3. You can submit a new application with additional documentation

Need Assistance?
Our support team is here to help you understand the requirements and guide you through the application process.
Contact: support@intellilearn.com

We appreciate your interest in IntelliLearn and hope to serve you in the future.

Best regards,
IntelliLearn Review Team"""
        
        # Send rejection email
        success = send_email_via_smtp(
            to_email=data['to_email'],
            subject=f"❌ IntelliLearn Application Status - {data['institution_name']}",
            message=message,
            institution_name=data['institution_name'],
            email_type='rejection'
        )
        
        # Log to MongoDB
        if mongo_connected and success:
            try:
                email_log = {
                    'to_email': data['to_email'],
                    'subject': f"IntelliLearn Application Rejected - {data['institution_name']}",
                    'institution_name': data['institution_name'],
                    'email_type': 'rejection',
                    'rejection_reason': rejection_reason,
                    'status': 'sent',
                    'timestamp': datetime.now(),
                    'ip_address': request.remote_addr
                }
                db.email_logs.insert_one(email_log)
            except Exception as e:
                logger.error(f"Failed to log rejection email: {str(e)}")
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Rejection email sent successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to send rejection email'
            }), 500
            
    except Exception as e:
        logger.error(f"Error in send-rejection-email endpoint: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@app.route('/api/emails', methods=['GET'])
def get_emails():
    """Get email logs from MongoDB"""
    try:
        if not mongo_connected:
            return jsonify({
                'success': False,
                'error': 'MongoDB not connected'
            }), 500
        
        # Get query parameters
        limit = int(request.args.get('limit', 50))
        skip = int(request.args.get('skip', 0))
        email_type = request.args.get('type')
        institution = request.args.get('institution')
        status = request.args.get('status')
        
        # Build query
        query = {}
        if email_type:
            query['email_type'] = email_type
        if institution:
            query['institution_name'] = {'$regex': institution, '$options': 'i'}
        if status:
            query['status'] = status
        
        # Get email logs
        emails = list(db.email_logs.find(query).sort('timestamp', -1).skip(skip).limit(limit))
        
        # Convert ObjectId to string for JSON serialization
        for email in emails:
            email['_id'] = str(email['_id'])
            email['timestamp'] = email['timestamp'].isoformat()
        
        return jsonify({
            'success': True,
            'emails': emails,
            'total': db.email_logs.count_documents(query),
            'filters': {
                'type': email_type,
                'institution': institution,
                'status': status
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting emails: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

# ... (rest of the endpoints remain the same - health, stats, etc.)

@app.route('/api/dashboard-stats', methods=['GET'])
def dashboard_stats():
    """Get dashboard statistics for admin panel"""
    try:
        if not mongo_connected:
            return jsonify({
                'success': False,
                'error': 'MongoDB not connected'
            }), 500
        
        # Get counts by type
        approval_count = db.email_logs.count_documents({'email_type': 'approval', 'status': 'sent'})
        rejection_count = db.email_logs.count_documents({'email_type': 'rejection', 'status': 'sent'})
        general_count = db.email_logs.count_documents({'email_type': 'general', 'status': 'sent'})
        failed_count = db.email_logs.count_documents({'status': 'failed'})
        
        # Get today's emails
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = db.email_logs.count_documents({
            'timestamp': {'$gte': today_start},
            'status': 'sent'
        })
        
        # Get top institutions
        pipeline = [
            {'$match': {'status': 'sent'}},
            {'$group': {
                '_id': '$institution_name',
                'count': {'$sum': 1},
                'last_sent': {'$max': '$timestamp'}
            }},
            {'$sort': {'count': -1}},
            {'$limit': 10}
        ]
        top_institutions = list(db.email_logs.aggregate(pipeline))
        
        # Convert ObjectId and datetime
        for inst in top_institutions:
            if 'last_sent' in inst:
                inst['last_sent'] = inst['last_sent'].isoformat()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_sent': approval_count + rejection_count + general_count,
                'approval_count': approval_count,
                'rejection_count': rejection_count,
                'general_count': general_count,
                'failed_count': failed_count,
                'today_count': today_count,
                'top_institutions': top_institutions
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting dashboard stats: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

if __name__ == '__main__':
    # Check if SMTP credentials are configured
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        logger.warning("SMTP credentials not configured. Please set SMTP_USERNAME and SMTP_PASSWORD environment variables.")
    
    if not mongo_connected:
        logger.warning("MongoDB not connected. Email logging will be disabled.")
    
    app.run(host='0.0.0.0', port=5000, debug=True)