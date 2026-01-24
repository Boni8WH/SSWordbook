from app import app, db, MapGenre, MapImage

def test_api_logic():
    with app.app_context():
        print("Testing MapGenre query...")
        genres = MapGenre.query.order_by(MapGenre.display_order).all()
        print(f"Found {len(genres)} genres.")
        
        print("Testing others_maps query...")
        others_maps = MapImage.query.filter(MapImage.genre_id == None).all()
        print(f"Found {len(others_maps)} maps in others.")
        
        result = []
        for g in genres:
            print(f"Processing genre: {g.name}")
            # Accessing relationship
            try:
                maps = g.maps
                print(f"  Maps type: {type(maps)}")
                # Iterate
                if hasattr(maps, 'all'):
                    print("  WARNING: maps is still dynamic (AppenderQuery)!")
                    maps = maps.all()
                
                maps_data = [{'id': m.id, 'name': m.name} for m in maps]
                print(f"  Serialized {len(maps_data)} maps.")
                
            except Exception as e:
                print(f"  ERROR accessing maps for genre {g.name}: {e}")
                raise e

        print("Testing serialization of others...")
        others_data = [{'id': m.id, 'name': m.name} for m in others_maps]
        print("Success.")

if __name__ == "__main__":
    try:
        test_api_logic()
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
