from app import app, db, User

with app.app_context():
    count = User.query.filter_by(room_number='MANAGER').count()
    users = User.query.filter_by(room_number='MANAGER').all()
    print(f"Count: {count}")
    for user in users:
        print(f"User: {user.username} (ID: {user.id}, StudentID: {user.student_id})")
