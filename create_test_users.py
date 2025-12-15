from app import app, db, User, RoomSetting, AdminUser
from werkzeug.security import generate_password_hash

def create_test_data():
    with app.app_context():
        # Create Room Setting
        room = RoomSetting.query.filter_by(room_number='101').first()
        if not room:
            room = RoomSetting(room_number='101', max_enabled_unit_number='9999', csv_filename='words.csv')
            db.session.add(room)
            print("Created Room 101")
        
        # Create Regular User
        user = User.query.filter_by(room_number='101', student_id='1').first()
        if not user:
            user = User(
                room_number='101',
                student_id='1',
                username='testuser',
                original_username='testuser',
                is_first_login=False
            )
            user.set_room_password('room101')
            user.set_individual_password('pass1')
            db.session.add(user)
            print("Created User: testuser (Room: 101, ID: 1, Pass: room101 / pass1)")
        else:
            # Update password just in case
            user.set_room_password('room101')
            user.set_individual_password('pass1')
            print("Updated User: testuser")

        # Create Admin User (using User table as per login logic)
        admin = User.query.filter_by(room_number='ADMIN', username='admin').first()
        if not admin:
            admin = User(
                room_number='ADMIN',
                student_id='0',
                username='admin',
                original_username='admin',
                is_first_login=False
            )
            admin.set_individual_password('adminpass') # Admin login uses individual password check
            # Room password is not used for admin login but field is required
            admin.set_room_password('adminpass') 
            db.session.add(admin)
            print("Created Admin User: admin (Pass: adminpass)")
        else:
            admin.set_individual_password('adminpass')
            print("Updated Admin User: admin")

        # Create Second Admin User
        admin2 = User.query.filter_by(room_number='ADMIN', username='admin2').first()
        if not admin2:
            admin2 = User(
                room_number='ADMIN',
                student_id='999',
                username='admin2',
                original_username='admin2',
                is_first_login=False
            )
            admin2.set_individual_password('adminpass2')
            admin2.set_room_password('adminpass2')
            db.session.add(admin2)
            print("Created Admin User: admin2 (Pass: adminpass2)")


        db.session.commit()
        print("Test data created successfully.")

if __name__ == '__main__':
    create_test_data()
