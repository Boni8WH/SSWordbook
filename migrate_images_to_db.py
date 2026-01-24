import os
from app import app, db, MapImage

def migrate_images():
    with app.app_context():
        maps = MapImage.query.all()
        upload_dir = os.path.join(app.root_path, 'uploads', 'maps')
        
        count = 0
        for m in maps:
            if not m.image_data:
                file_path = os.path.join(upload_dir, m.filename)
                if os.path.exists(file_path):
                    print(f"Migrating {m.filename} to DB...")
                    with open(file_path, 'rb') as f:
                        m.image_data = f.read()
                    count += 1
                else:
                    print(f"⚠️ File not found: {file_path}")
        
        if count > 0:
            db.session.commit()
            print(f"✅ Successfully migrated {count} images to DB.")
        else:
            print("No images needed migration.")

if __name__ == "__main__":
    migrate_images()
