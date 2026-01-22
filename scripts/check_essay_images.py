import os
import sys

# Add parent directory to path to import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db, EssayCorrectionRequest, CorrectionRequestImage

def verify_essay_request_images():
    with app.app_context():
        stats = {
            'total_requests': 0,
            'with_db_image': 0,
            'with_legacy_path': 0,
            'both': 0,
            'neither_but_has_text': 0,
            'image_missing': 0
        }
        
        requests = EssayCorrectionRequest.query.all()
        stats['total_requests'] = len(requests)
        
        print(f"Total Requests: {len(requests)}")
        print("-" * 50)
        
        for req in requests:
            db_imgs = CorrectionRequestImage.query.filter_by(
                request_id=req.id, 
                image_type='request'
            ).all()
            
            has_db = len(db_imgs) > 0
            has_legacy = bool(req.request_image_path)
            
            if has_db:
                stats['with_db_image'] += 1
            if has_legacy:
                stats['with_legacy_path'] += 1
            if has_db and has_legacy:
                stats['both'] += 1
            
            if not has_db and not has_legacy:
                if req.request_text:
                    stats['neither_but_has_text'] += 1
                else:
                    stats['image_missing'] += 1
            elif not has_db and has_legacy:
                print(f"[Legacy Only] Request ID: {req.id}, Path: {req.request_image_path}")
                # Check if path looks like what we expect
                if req.request_image_path.startswith('http'):
                    print("  -> Is S3 URL")
                else:
                    print("  -> Is Local Path")
                    # Check if file exists
                    full_path = os.path.join(app.static_folder, 'uploads/essay_images', req.request_image_path)
                    if os.path.exists(full_path):
                        print("  -> Local file FOUND")
                    else:
                        print(f"  -> Local file NOT FOUND at {full_path}")
                        
        print("-" * 50)
        print("Statistics:")
        for k, v in stats.items():
            print(f"{k}: {v}")

if __name__ == "__main__":
    verify_essay_request_images()
