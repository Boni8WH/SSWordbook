from app import app, db
from sqlalchemy import text

def fix_nulls():
    with app.app_context():
        try:
            print("Updating NULL genres to empty string...")
            # SQLite compatible and Postgres compatible standard SQL
            db.session.execute(text("UPDATE map_image SET genre = '' WHERE genre IS NULL"))
            db.session.commit()
            print("Update complete.")
        except Exception as e:
            print(f"Error: {e}")
            db.session.rollback()

if __name__ == "__main__":
    fix_nulls()
