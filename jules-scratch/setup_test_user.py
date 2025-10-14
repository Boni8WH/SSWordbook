import os
import json
import csv
import re
from app import db, User, RoomSetting
from werkzeug.security import generate_password_hash

# --- Configuration ---
ROOM_NUMBER = "999"
ROOM_PASSWORD = "password999"

# User 1: For testing "My Weak Problems"
USER_1_STUDENT_ID = "student999"
USER_1_USERNAME = "test_weak_user"
USER_1_INDIVIDUAL_PASSWORD = "password123"

# User 2: For testing "Everyone's Weak Problems"
USER_2_STUDENT_ID = "student1000"
USER_2_USERNAME = "another_user"
USER_2_INDIVIDUAL_PASSWORD = "password456"

# --- Helper to generate problem IDs (must match app.py) ---
def get_problem_id(word):
    """Generates a problem ID based on word details."""
    try:
        chapter = str(word.get('chapter', '0')).zfill(3)
        number = str(word.get('number', '0')).zfill(3)
        question = str(word.get('question', '')).strip()
        answer = str(word.get('answer', '')).strip()

        question_clean = re.sub(r'[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', '', question[:15])
        answer_clean = re.sub(r'[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', '', answer[:10])

        return f"{chapter}-{number}-{question_clean}-{answer_clean}"
    except Exception as e:
        print(f"Error generating problem ID: {e}")
        return "error-id"

def setup_test_environment():
    """Sets up the test room and users in the database."""
    print("--- Starting Test Environment Setup ---")

    # Load word data
    try:
        with open('words.csv', 'r', encoding='utf-8') as f:
            word_data = list(csv.DictReader(f))
        print(f"Loaded {len(word_data)} words from words.csv")
    except FileNotFoundError:
        print("❌ ERROR: words.csv not found. Cannot set up test data.")
        return

    # Find specific problems for testing
    personal_weak_problem_word = next((w for w in word_data if w['question'] == "三十年戦争を終結させ、主権国家体制を確立し、オランダとスイスの独立を正式に承認した国際条約を何と呼ぶか。"), None)
    room_weak_problem_word = next((w for w in word_data if w['question'] == "三十年戦争のきっかけとなった、プロテスタント貴族の反乱が起こった神聖ローマ帝国内の地域はどこか。"), None)

    if not personal_weak_problem_word or not room_weak_problem_word:
        print("❌ ERROR: Could not find required test problems in words.csv.")
        return

    personal_weak_problem_id = get_problem_id(personal_weak_problem_word)
    room_weak_problem_id = get_problem_id(room_weak_problem_word)

    # --- Create Test Data ---
    # 1. Create or update RoomSetting
    room_setting = RoomSetting.query.filter_by(room_number=ROOM_NUMBER).first()
    if not room_setting:
        room_setting = RoomSetting(room_number=ROOM_NUMBER, csv_filename='words.csv')
        db.session.add(room_setting)
        print(f"Created new room setting for room '{ROOM_NUMBER}'.")
    else:
        room_setting.csv_filename = 'words.csv' # Ensure it's set correctly
        print(f"Room setting for '{ROOM_NUMBER}' already exists, updated CSV filename.")

    # 2. Delete existing test users to ensure a clean slate
    User.query.filter_by(room_number=ROOM_NUMBER).delete()
    print(f"Deleted existing users in room '{ROOM_NUMBER}'.")

    # 3. Create User 1
    user1_history = {
        # This is the main problem to check for in "My Weak Problems"
        personal_weak_problem_id: {
            "correct_attempts": 1,
            "incorrect_attempts": 10, # Low accuracy
            "correct_streak": 0,
            "last_answered": "2025-10-14T12:00:00Z"
        },
        # This problem will also be weak for the room, but less so for the user
        room_weak_problem_id: {
            "correct_attempts": 5,
            "incorrect_attempts": 5, # 50% accuracy
            "correct_streak": 1,
            "last_answered": "2025-10-14T12:01:00Z"
        }
    }

    user1 = User(
        room_number=ROOM_NUMBER,
        student_id=USER_1_STUDENT_ID,
        username=USER_1_USERNAME,
        original_username=USER_1_USERNAME,
            problem_history=user1_history,
        is_first_login=False,
        _room_password_hash=generate_password_hash(ROOM_PASSWORD),
        _individual_password_hash=generate_password_hash(USER_1_INDIVIDUAL_PASSWORD)
    )
    db.session.add(user1)
    print(f"Created User 1: '{USER_1_USERNAME}'")

    # 4. Create User 2
    user2_history = {
        # This problem is very weak for this user, making it the top room weak problem
        room_weak_problem_id: {
            "correct_attempts": 1,
            "incorrect_attempts": 20, # Very low accuracy
            "correct_streak": 0,
            "last_answered": "2025-10-14T12:02:00Z"
        }
    }

    user2 = User(
        room_number=ROOM_NUMBER,
        student_id=USER_2_STUDENT_ID,
        username=USER_2_USERNAME,
        original_username=USER_2_USERNAME,
            problem_history=user2_history,
        is_first_login=False,
        _room_password_hash=generate_password_hash(ROOM_PASSWORD),
        _individual_password_hash=generate_password_hash(USER_2_INDIVIDUAL_PASSWORD)
    )
    db.session.add(user2)
    print(f"Created User 2: '{USER_2_USERNAME}'")

    # 5. Commit all changes
    try:
        db.session.commit()
        print("Successfully committed all changes to the database.")
    except Exception as e:
        db.session.rollback()
        print(f"❌ DATABASE ERROR: {e}")
        print("Rolled back database changes.")

    print("--- Test Environment Setup Complete ---")

if __name__ == "__main__":
    # This script needs to be run within the Flask app context.
    # Use `PYTHONPATH=. python jules-scratch/setup_test_user.py`
    from app import app
    with app.app_context():
        setup_test_environment()