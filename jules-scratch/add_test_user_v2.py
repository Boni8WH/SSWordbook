import os
import sys
import csv
from io import StringIO
from app import app, db, User, RoomSetting, get_problem_id

def add_realistic_test_user():
    with app.app_context():
        # --- Create Test Room and User ---
        room = RoomSetting.query.filter_by(room_number='987').first()
        if not room:
            room = RoomSetting(room_number='987', csv_filename='words.csv', max_enabled_unit_number='9999')
            db.session.add(room)
            print("Created test room '987'")

        user = User.query.filter_by(room_number='987', student_id='user987').first()
        if user:
            print("Test user 'user987' in room '987' already exists.")
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

        # --- Create Realistic Problem History ---

        # 1. Load actual word data
        word_data = []
        try:
            with open('words.csv', 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                word_data = list(reader)
        except FileNotFoundError:
            print("❌ words.csv not found. Cannot create realistic history.")
            return

        if len(word_data) < 5:
            print("❌ Not enough data in words.csv to create history.")
            return

        # 2. Select some questions and generate real problem IDs
        weak_problem_1_word = word_data[0] # "猿人"
        weak_problem_2_word = word_data[4] # "原人"
        strong_problem_word = word_data[10] # "新人"

        weak_problem_1_id = get_problem_id(weak_problem_1_word)
        weak_problem_2_id = get_problem_id(weak_problem_2_word)
        strong_problem_id = get_problem_id(strong_problem_word)

        print(f"Generated ID 1 (weak): {weak_problem_1_id}")
        print(f"Generated ID 2 (weak): {weak_problem_2_id}")
        print(f"Generated ID 3 (strong): {strong_problem_id}")

        # 3. Create the problem history dictionary with real IDs
        problem_history = {
            weak_problem_1_id: {"correct_attempts": 1, "incorrect_attempts": 5, "correct_streak": 0},
            weak_problem_2_id: {"correct_attempts": 2, "incorrect_attempts": 8, "correct_streak": 1},
            strong_problem_id: {"correct_attempts": 10, "incorrect_attempts": 1, "correct_streak": 5}
        }

        # Also create incorrect words list
        incorrect_words = [weak_problem_1_id, weak_problem_2_id]

        user.problem_history = problem_history
        user.incorrect_words = incorrect_words

        db.session.commit()
        print("✅ Test user data updated with realistic problem history.")

if __name__ == "__main__":
    add_realistic_test_user()