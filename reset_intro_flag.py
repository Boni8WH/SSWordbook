from app import app, db, User

def reset_intro_flag(user_id):
    """指定されたユーザーのrpg_intro_seenフラグをリセット"""
    with app.app_context():
        user = User.query.get(user_id)
        if user:
            user.rpg_intro_seen = False
            db.session.commit()
            print(f"✅ Reset rpg_intro_seen for user {user.username} (ID: {user_id})")
            print(f"   Current state: rpg_intro_seen = {user.rpg_intro_seen}")
        else:
            print(f"❌ User with ID {user_id} not found")

if __name__ == "__main__":
    reset_intro_flag(4)
