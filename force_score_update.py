from app import app, db, User, UserStats

def boost_score():
    with app.app_context():
        user = User.query.get(4) # 開発者
        if not user:
            print("User 4 not found.")
            return

        stats = UserStats.get_or_create(user.id)
        print(f"Current Score: {stats.total_correct}")
        
        stats.total_correct = 1005
        db.session.add(stats)
        db.session.commit()
        
        print(f"New Score: {stats.total_correct}")
        print("Score updated. Please reload the index page.")

if __name__ == "__main__":
    boost_score()
