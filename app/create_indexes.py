from pymongo import MongoClient, ASCENDING, TEXT
import os

MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
DATABASE_NAME = os.getenv('DATABASE_NAME', 'SmartEducation')

client = MongoClient(MONGO_URI)
db = client[DATABASE_NAME]

# Create indexes for teachers collection
db.teachers.create_index([('email', ASCENDING)], unique=True)
db.teachers.create_index([('employee_id', ASCENDING)], unique=True)
db.teachers.create_index([('school_id', ASCENDING)])
db.teachers.create_index([('status', ASCENDING)])
db.teachers.create_index([('subject', ASCENDING)])
db.teachers.create_index([('name', TEXT), ('email', TEXT)])

print("✅ Teacher indexes created successfully")
client.close()