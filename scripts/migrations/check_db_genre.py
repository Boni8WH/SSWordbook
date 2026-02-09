from app import app, db, MapImage
from sqlalchemy import text, inspect

def check_data():
    with app.app_context():
        # Check Columns
        inspector = inspect(db.engine)
        columns = [c['name'] for c in inspector.get_columns('map_image')]
        print(f"Columns in map_image: {columns}")
        
        if 'genre' not in columns:
            print("CRITICAL: 'genre' column missing from database!")
        
        # Check recent entries
        print("\n--- Recent 5 Map Entries ---")
        maps = MapImage.query.order_by(MapImage.created_at.desc()).limit(5).all()
        for m in maps:
            # Access raw row if model attribute doesn't map (though it should if app.py is updated)
            # using db.session.execute to be sure of raw DB value
            raw_row = db.session.execute(
                text("SELECT id, name, genre FROM map_image WHERE id = :id"), 
                {'id': m.id}
            ).fetchone()
            print(f"ID: {m.id}, Name: {m.name}, Genre (Model): {getattr(m, 'genre', 'N/A')}, Genre (Raw): {raw_row[2]}")

if __name__ == "__main__":
    check_data()
