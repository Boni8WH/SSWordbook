from app import app, db, MapImage, MapGenre
from sqlalchemy import text

def migrate():
    with app.app_context():
        print("Starting Map Genre Migration...")
        
        # 1. Create table if not exists (using raw SQL for SQLite/Postgres compat or SQLAlchemy create_all)
        # Using create_all is safer for new tables
        db.create_all()
        print("Required tables created (if missing).")
        
        # 2. Add columns to MapImage if missing (genre_id, display_order)
        try:
            # Check for genre_id
            db.session.execute(text("SELECT genre_id FROM map_image LIMIT 1"))
        except Exception:
            print("Adding genre_id column...")
            db.session.rollback()
            try:
                db.session.execute(text("ALTER TABLE map_image ADD COLUMN genre_id INTEGER REFERENCES map_genre(id)"))
                db.session.commit()
            except Exception as e:
                print(f"Error adding genre_id: {e}")
                db.session.rollback()

        try:
            # Check for display_order
            db.session.execute(text("SELECT display_order FROM map_image LIMIT 1"))
        except Exception:
            print("Adding display_order column...")
            db.session.rollback()
            try:
                db.session.execute(text("ALTER TABLE map_image ADD COLUMN display_order INTEGER DEFAULT 0"))
                db.session.commit()
            except Exception as e:
                print(f"Error adding display_order: {e}")
                db.session.rollback()

        # 3. Migrate Data
        print("Migrating existing genres...")
        params = {}
        # Fetch all maps with string genre
        maps = MapImage.query.filter(MapImage.genre != None, MapImage.genre != "").all()
        
        # Get unique genres
        unique_genres = set([m.genre for m in maps])
        
        for g_name in unique_genres:
            # Check if genre exists
            genre_obj = MapGenre.query.filter_by(name=g_name).first()
            if not genre_obj:
                print(f"Creating genre: {g_name}")
                genre_obj = MapGenre(name=g_name)
                db.session.add(genre_obj)
                db.session.commit() # Commit to get ID
            
            # Link maps
            # We fetch maps again or filter from list, safer to query
            maps_in_genre = MapImage.query.filter_by(genre=g_name).all()
            for m in maps_in_genre:
                if m.genre_id is None:
                    m.genre_id = genre_obj.id
                    print(f"Linked map '{m.name}' to genre '{g_name}'")
            db.session.commit()
            
        print("Migration Complete.")

if __name__ == "__main__":
    migrate()
