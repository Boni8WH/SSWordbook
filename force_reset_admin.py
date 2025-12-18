from app import app, db, User

with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    if admin:
        admin.set_individual_password('adminpass')
        admin.set_room_password('adminpass') # Just in case
        db.session.commit()
        print("✅ Admin password reset to 'adminpass'")
    else:
        print("❌ Admin user not found")
