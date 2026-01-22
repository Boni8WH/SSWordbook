import sys
import os

# Add parent directory to path to import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db, EssayCorrectionRequest, CorrectionRequestImage

def test_latest_image():
    with app.app_context():
        # Get the latest request
        latest_req = EssayCorrectionRequest.query.order_by(EssayCorrectionRequest.created_at.desc()).first()
        
        if not latest_req:
            print("No requests found.")
            return

        print(f"Checking Request ID: {latest_req.id}")
        print(f"Created At: {latest_req.created_at}")
        print(f"Request Text: {latest_req.request_text[:20]}...")
        
        # Check DB images
        db_imgs = [img for img in latest_req.db_images if img.image_type == 'request']
        print(f"DB Images found: {len(db_imgs)}")
        
        if db_imgs:
            img_id = db_imgs[0].id
            print(f"Testing image ID: {img_id}")
            
            with app.test_client() as client:
                url = f'/correction_image/{img_id}'
                print(f"Fetching {url}...")
                response = client.get(url)
                
                print(f"Status Code: {response.status_code}")
                print(f"Content Type: {response.content_type}")
                print(f"Content Length: {response.content_length}")
                
                if response.status_code == 200:
                     print("SUCCESS: Image served correctly.")
                else:
                     print("FAILURE: Image fetch failed.")
        else:
            print("No DB images for this request.")
            
        # Check Legacy path
        print(f"Legacy Image Path: {latest_req.request_image_path}")

def run_test_with_db(uri):
    print(f"\n--- Testing with DB: {uri} ---")
    app.config['SQLALCHEMY_DATABASE_URI'] = uri
    # Need to dispose engine to force reconnection
    db.engine.dispose()
    test_latest_image()

if __name__ == '__main__':
    default_uri = app.config.get('SQLALCHEMY_DATABASE_URI')
    print(f"Default DB URI in app: {default_uri}")
    
    test_latest_image()
    
    # Try quiz_data.db explicitly if default was data.sqlite
    basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    quiz_db_path = os.path.join(basedir, 'quiz_data.db')
    if os.path.exists(quiz_db_path):
        uri = f'sqlite:///{quiz_db_path}'
        if uri != default_uri:
            run_test_with_db(uri)
