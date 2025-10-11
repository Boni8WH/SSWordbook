import sys
import os
# Add the root directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app import app, db, User, RoomSetting, get_problem_id

with app.app_context():
    # --- Create/Update Test User ---
    room_number = "101"
    student_id = "1"
    username = "Test User"

    user_to_update = User.query.filter_by(room_number=room_number, student_id=student_id).first()

    if not user_to_update:
        print(f"User {username} not found. Creating a new one.")
        user_to_update = User(
            room_number=room_number,
            student_id=student_id,
            username=username,
            original_username=username,
            is_first_login=False
        )
        user_to_update.set_room_password("2024101")
        user_to_update.set_individual_password("TemplarsGoldIsMine")
        db.session.add(user_to_update)
    else:
        print(f"Found existing user: {username}")

    # --- Create realistic problem history ---
    problem1 = {'chapter': '1', 'number': '0', 'question': '化石人類のうち、直立二足歩行をしていたと推定される、最古の人類を何と呼ぶか。', 'answer': '猿人'}
    problem2 = {'chapter': '1', 'number': '0', 'question': '約240万年前に出現した、初歩的な打製石器やハンドアックスを用いたとされる化石人類を何と呼ぶか。', 'answer': '原人'}
    problem3 = {'chapter': '1', 'number': '2', 'question': 'シュメール人が粘土板に刻んだ文字は何か。', 'answer': '楔形文字'}

    problem_id1 = get_problem_id(problem1)
    problem_id2 = get_problem_id(problem2)
    problem_id3 = get_problem_id(problem3)

    user_to_update.problem_history = {
        problem_id1: {"correct_attempts": 1, "incorrect_attempts": 4, "correct_streak": 0}, # Accuracy: 20% (Weak)
        problem_id2: {"correct_attempts": 2, "incorrect_attempts": 3, "correct_streak": 1}, # Accuracy: 40% (Weak)
        problem_id3: {"correct_attempts": 5, "incorrect_attempts": 0, "correct_streak": 5}  # Accuracy: 100% (Not weak)
    }
    print("Set/Updated user's problem history with valid data.")

    # --- Create Room Setting ---
    room_setting = RoomSetting.query.filter_by(room_number=room_number).first()
    if not room_setting:
        room_setting = RoomSetting(room_number=room_number)
        db.session.add(room_setting)
        print(f"Added room setting for room: {room_number}")

    db.session.commit()
    print("Database changes committed.")