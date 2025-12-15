from app import app, db, User, load_word_data_for_room, get_problem_id

def trigger_restriction():
    with app.app_context():
        user = User.query.filter_by(username='testuser').first()
        if not user:
            print("User 'testuser' not found.")
            return

        # Load words to get valid IDs
        word_data = load_word_data_for_room(user.room_number)
        if not word_data:
            print("No word data found.")
            return

        # Get first 25 problem IDs
        problem_ids = []
        for word in word_data[:25]:
            pid = get_problem_id(word)
            problem_ids.append(pid)

        if len(problem_ids) < 20:
            print(f"Not enough words to trigger restriction (found {len(problem_ids)}). Need 20+.")
            return

        # Set incorrect words
        user.set_incorrect_words(problem_ids)
        
        # Also set restriction triggered flag in DB if column exists
        if hasattr(user, 'restriction_triggered'):
            user.restriction_triggered = True
            user.restriction_released = False
            print("Set DB restriction flags.")

        db.session.commit()
        print(f"Added {len(problem_ids)} weak problems to testuser.")
        print("Restriction should be triggered.")

if __name__ == '__main__':
    trigger_restriction()
