from app import app, db
from sqlalchemy import text

def migrate():
    with app.app_context():
        print("Starting Map Difficulty Migration...")
        
        try:
            # Check for difficulty column
            db.session.execute(text("SELECT difficulty FROM map_quiz_problem LIMIT 1"))
            print("Column 'difficulty' already exists.")
        except Exception:
            print("Adding difficulty column...")
            db.session.rollback()
            try:
                # Add column with default 2
                db.session.execute(text("ALTER TABLE map_quiz_problem ADD COLUMN difficulty INTEGER DEFAULT 2"))
                db.session.commit()
                print("Column added successfully.")
            except Exception as e:
                print(f"Error adding difficulty: {e}")
                db.session.rollback()
                
        print("Migration Complete.")

if __name__ == "__main__":
    migrate()
