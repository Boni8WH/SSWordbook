
from app import app, db, User, UserStats
from werkzeug.security import generate_password_hash
import datetime

def create_high_score_user():
    with app.app_context():
        # User作成
        username = "test_rpg"
        password = "password123"
        room_number = "101" # 既存の部屋番号などに合わせる必要がありますが、とりあえず101
        
        user = User.query.filter_by(username=username).first()
        if user:
            print(f"User {username} already exists. Updating stats...")
        else:
            print(f"Creating user {username}...")
            # Userモデルの制約に合わせて修正
            user = User(
                username=username,
                original_username=username,
                room_number=room_number,
                student_id="test001", # ユニーク制約回避のため適当に
                is_first_login=False
            )
            # パスワード設定メソッドを使用
            user.set_room_password(room_number) # 部屋パスワード=部屋番号と仮定
            user.set_individual_password(password)
            
            db.session.add(user)
            db.session.commit()
            print(f"Created user: {username} (Room: {room_number}, ID: test001) / Password: {password}")

        # UserStats作成/更新
        stats = UserStats.query.filter_by(user_id=user.id).first()
        if not stats:
            stats = UserStats(user_id=user.id, room_number=room_number)
            db.session.add(stats)
        
        # スコアを強制設定
        stats.balance_score = 1500.0  # 1000以上にする
        stats.total_score = 2000
        stats.correct_count = 200
        stats.total_problems_answered = 250
        
        db.session.commit()
        print(f"Updated stats for {username}: Balance Score = {stats.balance_score}")

if __name__ == "__main__":
    create_high_score_user()
