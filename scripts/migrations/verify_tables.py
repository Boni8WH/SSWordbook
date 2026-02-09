from app import app, db, MapImage, MapLocation, MapQuizProblem
from sqlalchemy import inspect

def check_tables():
    with app.app_context():
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        required_tables = ['map_image', 'map_location', 'map_quiz_problem', 'mq_log']
        
        all_exist = True
        for table in required_tables:
            if table in tables:
                print(f"OK: Table '{table}' exists.")
            else:
                print(f"MISSING: Table '{table}' does NOT exist.")
                all_exist = False
        
        if all_exist:
            print("SUCCESS: All tables present.")
        else:
            print("FAILURE: Some tables are missing. Attempting to create them...")
            try:
                # Trigger migration manually if needed
                from app import _create_map_quiz_tables
                _create_map_quiz_tables()
                print("Migration function called.")
            except ImportError:
                 print("Could not import migration function.")

if __name__ == "__main__":
    check_tables()
