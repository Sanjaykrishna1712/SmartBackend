# app/__init__.py
from flask import Flask, request
from flask_cors import CORS, cross_origin
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

def create_app():
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')
    app.config['MONGO_URI'] = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
    app.config['DATABASE_NAME'] = os.getenv('DATABASE_NAME', 'SmartEducation')
    
    # Get allowed origins
    allowed_origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5173,http://localhost:3000').split(',')
    
    print(f"✅ Allowed CORS origins: {allowed_origins}")
    
    # Initialize CORS
    CORS(app, 
         resources={
             r"/api/*": {
                 "origins": allowed_origins,
                 "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                 "allow_headers": ["Content-Type", "Authorization", "Accept"],
                 "supports_credentials": True
             }
         }
    )
    
    # Initialize MongoDB
    try:
        client = MongoClient(app.config['MONGO_URI'])
        app.db = client[app.config['DATABASE_NAME']]
        print("✅ Connected to MongoDB successfully")
    except Exception as e:
        print(f"❌ MongoDB connection error: {e}")
        app.db = None
    
    # Import and register blueprints
    try:
        from app.routes.school_contact import school_contact_bp
    except ImportError:
        # Alternative import path
        from .routes.school_contact import school_contact_bp
    
    app.register_blueprint(school_contact_bp, url_prefix='/api')
    from app.routes.login import login_bp
    app.register_blueprint(login_bp, url_prefix='/api')
    from app.routes.teachers import teachers_bp
    app.register_blueprint(teachers_bp, url_prefix='/api')
    from app.routes.students import students_bp
    app.register_blueprint(students_bp, url_prefix='/api')
    # Debug: Print all registered routes
    print("\n📋 Registered Routes:")
    for rule in app.url_map.iter_rules():
        print(f"  {rule.endpoint}: {rule.rule}")
    print()
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        print(f"❌ 404 Error: {request.method} {request.path} not found")
        return {
            'success': False,
            'error': 'Endpoint not found'
        }, 404
    
    @app.errorhandler(500)
    def internal_error(error):
        print(f"❌ 500 Error: {error}")
        return {
            'success': False,
            'error': 'Internal server error'
        }, 500
    
    return app