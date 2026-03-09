import sys
import os

# Add parent directory to path to import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db, EssayCorrectionRequest, CorrectionRequestImage

POSTGRES_URI = 'postgresql://world_history_user:password@localhost:5432/world_history_db'

def test_postgres():
    print(f"--- Connecting to Postgres: {POSTGRES_URI} ---")
    app.config['SQLALCHEMY_DATABASE_URI'] = POSTGRES_URI
    
    with app.app_context():
        db.engine.dispose()
        try:
            # Check connection
            req_count = EssayCorrectionRequest.query.count()
            print(f"Total EssayCorrectionRequests in Postgres: {req_count}")
            
            # Get latest
            latest_req = EssayCorrectionRequest.query.order_by(EssayCorrectionRequest.created_at.desc()).first()
            if latest_req:
                print(f"Latest Request ID: {latest_req.id}")
                print(f"Created At: {latest_req.created_at}")
                
                # Check DB images
                db_imgs = [img for img in latest_req.db_images if img.image_type == 'request']
                print(f"DB Images found: {len(db_imgs)}")
                
                if db_imgs:
                    img_id = db_imgs[0].id
                    print(f"Testing serve_correction_image for ID {img_id}...")
                    
                    with app.test_client() as client:
                        url = f'/correction_image/{img_id}'
                        resp = client.get(url)
                        print(f"Status: {resp.status_code}")
                        print(f"Type: {resp.content_type}")
                        print(f"Length: {resp.content_length}")
            else:
                print("No requests found in Postgres.")

        except Exception as e:
            print(f"Postgres connection failed: {e}")

if __name__ == '__main__':
    test_postgres()
