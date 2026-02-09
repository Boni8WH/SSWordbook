import sqlite3
from app import app, db
import os

def migrate():
    print("Starting map visibility migration...")
    
    with app.app_context():
        database_url = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        print(f"Database URI: {database_url}")
        
        # SQLite logic
        if "sqlite" in database_url:
            db_path = database_url.replace("sqlite:///", "")
            if not os.path.isabs(db_path):
                db_path = os.path.join(os.getcwd(), db_path)
                
            print(f"Connecting to SQLite at {db_path}...")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            try:
                # Check if column exists
                cursor.execute("PRAGMA table_info(map_image)")
                columns = [c[1] for c in cursor.fetchall()]
                
                if "is_active" not in columns:
                    print("Adding is_active column to map_image (SQLite)...")
                    # Default to 1 (True) for existing records
                    cursor.execute("ALTER TABLE map_image ADD COLUMN is_active BOOLEAN DEFAULT 1")
                    conn.commit()
                    print("Column added.")
                else:
                    print("is_active column already exists.")
            except Exception as e:
                print(f"Error in SQLite migration: {e}")
            finally:
                conn.close()
                
        # Postgres logic
        else:
            from sqlalchemy import text
            try:
                db.session.execute(text("ALTER TABLE map_image ADD COLUMN is_active BOOLEAN DEFAULT TRUE"))
                db.session.commit()
                print("Added is_active column to map_image (Postgres).")
            except Exception as e:
                db.session.rollback()
                if "already exists" in str(e).lower():
                    print("is_active column already exists.")
                else:
                    print(f"Error adding column: {e}")
                    
        # Ensure existing maps are active
        from sqlalchemy import text
        try:
            db.session.execute(text("UPDATE map_image SET is_active = TRUE WHERE is_active IS NULL"))
            db.session.commit()
            print("Verified existing maps are active.")
        except Exception as e:
            print(f"Update error: {e}")

if __name__ == "__main__":
    migrate()
