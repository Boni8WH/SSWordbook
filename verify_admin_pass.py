from app import app, db, User, AdminUser
with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    if admin:
        print(f"Admin found: {admin}")
        print(f"Password 'adminpass' valid (Room): {admin.check_room_password('adminpass')}")
        print(f"Password 'adminpass' valid (Individual): {admin.check_individual_password('adminpass')}")
    else:
        print("Admin user not found in User table")

    admin_user = AdminUser.query.filter_by(username='admin').first()
    if admin_user:
        print(f"AdminUser found: {admin_user}")
        print(f"Password 'adminpass' valid: {admin_user.check_password('adminpass')}")
    else:
        print("Admin user not found in AdminUser table")
