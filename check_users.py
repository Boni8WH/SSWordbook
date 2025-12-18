import sqlite3
import os

db_path = 'quiz_data.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT username, student_id FROM user")
        users = cursor.fetchall()
        print(f"Users found ({len(users)}):")
        for u in users:
            print(f"- {u[0]} (ID: {u[1]})")
    except Exception as e:
        print(f"Error querying users: {e}")
    finally:
        conn.close()
else:
    print("quiz_data.db not found")
