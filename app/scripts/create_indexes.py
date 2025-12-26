# scripts/create_indexes.py
from pymongo import MongoClient, ASCENDING, DESCENDING, TEXT

def create_student_indexes():
    client = MongoClient('mongodb://localhost:27017/')
    db = client['SmartEducation']
    
    # Create indexes for students collection
    students_collection = db.students
    
    # Basic indexes
    students_collection.create_index([('email', ASCENDING)], unique=True)
    students_collection.create_index([('student_id', ASCENDING)], unique=True)
    students_collection.create_index([('roll_number', ASCENDING)])
    students_collection.create_index([('class', ASCENDING), ('section', ASCENDING)])
    students_collection.create_index([('status', ASCENDING)])
    students_collection.create_index([('created_at', DESCENDING)])
    
    # Text index for search
    students_collection.create_index([
        ('name', TEXT),
        ('email', TEXT),
        ('roll_number', TEXT),
        ('parent_name', TEXT)
    ], default_language='english')
    db.teachers.create_index([('email', ASCENDING)], unique=True)
    db.teachers.create_index([('employee_id', ASCENDING)], unique=True)
    db.teachers.create_index([('school_id', ASCENDING)])
    db.teachers.create_index([('status', ASCENDING)])
    db.teachers.create_index([('subject', ASCENDING)])
    db.teachers.create_index([('name', TEXT), ('email', TEXT)])
    print("✅ Student indexes created successfully")
    client.close()

if __name__ == '__main__':
    create_student_indexes()