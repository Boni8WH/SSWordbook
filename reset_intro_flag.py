import sys
from app import app, db, User

def reset_intro_flag(target):
    """
    指定されたターゲットのrpg_intro_seenフラグをリセット
    target: user_id (int) or 'all' (str)
    """
    with app.app_context():
        if target == 'all':
            # 全ユーザーのリセット
            try:
                User.query.update({User.rpg_intro_seen: False})
                db.session.commit()
                print("✅ Reset rpg_intro_seen for ALL users.")
            except Exception as e:
                db.session.rollback()
                print(f"❌ Error resetting all users: {e}")
        else:
            # 個別ユーザーのリセット
            try:
                user_id = int(target)
                user = User.query.get(user_id)
                if user:
                    user.rpg_intro_seen = False
                    db.session.commit()
                    print(f"✅ Reset rpg_intro_seen for user {user.username} (ID: {user_id})")
                    print(f"   Current state: rpg_intro_seen = {user.rpg_intro_seen}")
                else:
                    print(f"❌ User with ID {user_id} not found")
            except ValueError:
                print(f"❌ Invalid user ID: {target}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1]
        reset_intro_flag(target)
    else:
        print("Usage: python reset_intro_flag.py <user_id|all>")

