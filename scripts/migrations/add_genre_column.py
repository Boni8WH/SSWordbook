from app import app, db
from sqlalchemy import text

def migrate():
    with app.app_context():
        try:
            # Check if column exists - SQLite specific pragma
            result = db.session.execute(text("PRAGMA table_info(map_image)")).fetchall()
            columns = [row[1] for row in result]
            
            if 'genre' not in columns:
                print("Adding genre column to map_image...")
                db.session.execute(text("ALTER TABLE map_image ADD COLUMN genre VARCHAR(100)"))
                db.session.commit()
                print("Migration successful.")
            else:
                print("Column 'genre' already exists.")
                
        except Exception as e:
            print(f"Migration error: {e}")
            db.session.rollback()

if __name__ == "__main__":
    migrate()