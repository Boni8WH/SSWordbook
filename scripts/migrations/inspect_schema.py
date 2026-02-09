from app import app, db
from sqlalchemy import inspect

def inspect_schema():
    with app.app_context():
        inspector = inspect(db.engine)
        tables = ['map_image', 'map_location', 'map_quiz_problem']
        
        for table in tables:
            print(f"\n--- Table: {table} ---")
            if table in inspector.get_table_names():
                columns = inspector.get_columns(table)
                for column in columns:
                    print(f"Column: {column['name']} ({column['type']})")
            else:
                print("Table NOT Found")

if __name__ == "__main__":
    inspect_schema()
