
import os
import sys
from app import app, db, User, RoomSetting

# .envファイルからDATABASE_URLを読み込む簡易ロジック
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

def init_db():
    # DATABASE_URL確認
    if not os.environ.get('DATABASE_URL'):
        print("⚠️ DATABASE_URL not set in environment or .env")
        # デフォルトのローカル設定を試みる（Docker用）
        os.environ['DATABASE_URL'] = "postgresql://world_history_user:password@localhost:5432/world_history_db"
    
    print(f"Connecting to: {os.environ['DATABASE_URL']}")

    with app.app_context():
        # 1. テーブル作成
        print("🛠 Creating all tables...")
        try:
            db.create_all()
            print("✅ Tables created.")
        except Exception as e:
            print(f"❌ Table creation failed: {e}")
            print("Is the Docker container running? (docker-compose up -d)")
            return

        # 2. ルーム作成 (Room 101)
        room_num = '101'
        room = RoomSetting.query.filter_by(room_number=room_num).first()
        if not room:
            room = RoomSetting(room_number=room_num, max_enabled_unit_number='9999', csv_filename="words.csv")
            db.session.add(room)
            print(f"✅ Created Room: {room_num}")
        else:
            print(f"ℹ️ Room {room_num} already exists.")

        # 3. 一般ユーザー作成 (testuser)
        student_id = '1'
        username = 'testuser'
        user_pass = 'pass1'
        room_pass = 'room101'
        
        user = User.query.filter_by(room_number=room_num, student_id=student_id).first()
        if not user:
            user = User(
                room_number=room_num,
                student_id=student_id,
                username=username,
                original_username=username,
                is_first_login=False
            )
            user.set_room_password(room_pass)
            user.set_individual_password(user_pass)
            db.session.add(user)
            print(f"✅ Created User: {username}")
        else:
            # パスワードリセットして確実にログインできるようにする
            user.set_room_password(room_pass)
            user.set_individual_password(user_pass)
            print(f"♻️  Reset User password for: {username}")

        # 4. 管理者ユーザー作成 (admin)
        admin_room = 'ADMIN'
        admin_name = 'admin'
        admin_pass = 'adminpass'
        
        admin = User.query.filter_by(room_number=admin_room, username=admin_name).first()
        if not admin:
            admin = User(
                room_number=admin_room,
                student_id='0',
                username=admin_name,
                original_username=admin_name,
                is_first_login=False
            )
            admin.set_room_password(admin_pass) # Dummy for admin
            admin.set_individual_password(admin_pass)
            db.session.add(admin)
            print(f"✅ Created Admin: {admin_name}")
        else:
            admin.set_individual_password(admin_pass)
            print(f"♻️  Reset Admin password for: {admin_name}")

        db.session.commit()
        print("\n=== ✨ Setup Completed! ===")
        print("You can now login with:\n")
        print("👑 [Admin]")
        print(f"  User: {admin_name}")
        print(f"  Pass: {admin_pass}")
        print("\n👤 [User]")
        print(f"  Room: {room_num}")
        print(f"  Pass: {room_pass}")
        print(f"  ID  : {student_id}")
        print(f"  Pass: {user_pass}")

if __name__ == '__main__':
    init_db()
