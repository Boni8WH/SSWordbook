import sqlite3
import os

db_path = os.path.join(os.getcwd(), 'quiz_data.db')

def fix_schema():
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if title column exists in study_tip
        cursor.execute("PRAGMA table_info(study_tip)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'title' not in columns:
            print("Adding 'title' column to study_tip table...")
            cursor.execute("ALTER TABLE study_tip ADD COLUMN title VARCHAR(100)")
            conn.commit()
            print("Successfully added 'title' column.")
        else:
            print("'title' column already exists in study_tip table.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    fix_schema()
