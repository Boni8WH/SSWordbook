import os
import sys
from app import app, db, User, RoomSetting

def add_test_user():
    with app.app_context():
        # Check if the room exists, if not create it
        room = RoomSetting.query.filter_by(room_number='987').first()
        if not room:
            room = RoomSetting(room_number='987', csv_filename='words.csv', max_enabled_unit_number='9999')
            db.session.add(room)
            print("Created test room '987'")

        # Check if user exists
        user = User.query.filter_by(room_number='987', student_id='user987').first()
        if user:
            print("Test user 'user987' in room '987' already exists.")
            # Ensure passwords are correct
            user.set_room_password('password987')
            user.set_individual_password('password987')
        else:
            user = User(
                room_number='987',
                student_id='user987',
                username='test_user_weak_problems',
                original_username='test_user_weak_problems',
                is_first_login=False
            )
            user.set_room_password('password987')
            user.set_individual_password('password987')
            db.session.add(user)
            print("Created test user 'user987' in room '987'")

        # Add some problem history to simulate weak problems
        # This needs to be a valid JSON string
        problem_history = {
            "001-001-A-Question1": {"correct_attempts": 1, "incorrect_attempts": 5, "correct_streak": 0},
            "001-002-B-Question2": {"correct_attempts": 2, "incorrect_attempts": 8, "correct_streak": 1},
            "002-001-C-Question3": {"correct_attempts": 10, "incorrect_attempts": 1, "correct_streak": 5} # Not a weak problem
        }
        user.problem_history = problem_history

        db.session.commit()
        print("Test user data updated successfully.")

if __name__ == "__main__":
    add_test_user()