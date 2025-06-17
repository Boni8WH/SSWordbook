# app.py の修正版 - エラー対策・重複削除
import os
import json
import csv
import re
from io import StringIO
from datetime import datetime
import pytz

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import inspect, text

# 日本時間のタイムゾーンオブジェクトを作成
JST = pytz.timezone('Asia/Tokyo')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here_please_change_this_in_production'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'quiz_data.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = 3600 * 24 * 7

# dbオブジェクトを初期化
db = SQLAlchemy()
db.init_app(app)

# CSV一時保存用フォルダ
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# 部屋ごとのCSVファイルを保存するフォルダ
ROOM_CSV_FOLDER = 'room_csv'
if not os.path.exists(ROOM_CSV_FOLDER):
    os.makedirs(ROOM_CSV_FOLDER)

# ====================================================================
# アプリ情報を取得するヘルパー関数
# ====================================================================
def get_app_info_dict(user_id=None, username=None, room_number=None):
    try:
        app_info = AppInfo.get_current_info()
        info_dict = app_info.to_dict()
        
        info_dict['isLoggedIn'] = user_id is not None
        info_dict['username'] = username
        info_dict['roomNumber'] = room_number
        
        return info_dict
    except Exception as e:
        print(f"Error getting app info: {e}")
        return {
            'appName': '世界史単語帳',
            'version': '1.0.0', 
            'lastUpdatedDate': '2025年6月15日',
            'updateContent': 'アプリケーションが開始されました。',
            'isLoggedIn': user_id is not None,
            'username': username,
            'roomNumber': room_number
        }

# ====================================================================
# データベースモデル定義
# ====================================================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    room_number = db.Column(db.String(50), nullable=False)
    _room_password_hash = db.Column(db.String(128))
    student_id = db.Column(db.String(50), nullable=False)
    _individual_password_hash = db.Column(db.String(128))
    problem_history = db.Column(db.Text)
    incorrect_words = db.Column(db.Text)
    last_login = db.Column(db.DateTime, default=lambda: datetime.now(JST))

    def set_room_password(self, password):
        self._room_password_hash = generate_password_hash(password)

    def check_room_password(self, password):
        return check_password_hash(self._room_password_hash, password)

    def set_individual_password(self, password):
        self._individual_password_hash = generate_password_hash(password)

    def check_individual_password(self, password):
        return check_password_hash(self._individual_password_hash, password)

    def get_problem_history(self):
        if self.problem_history:
            return json.loads(self.problem_history)
        return {}

    def set_problem_history(self, history):
        self.problem_history = json.dumps(history)

    def get_incorrect_words(self):
        if self.incorrect_words:
            return json.loads(self.incorrect_words)
        return []

    def set_incorrect_words(self, words):
        self.incorrect_words = json.dumps(words)

class RoomSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(50), unique=True, nullable=False)
    max_enabled_unit_number = db.Column(db.String(50), default="9999", nullable=False)
    csv_filename = db.Column(db.String(100), default="words.csv", nullable=False)

class RoomCsvFile(db.Model):
    """部屋ごとのカスタムCSVファイル情報を管理するモデル"""
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), unique=True, nullable=False)
    original_filename = db.Column(db.String(100), nullable=False)  # アップロード時の元のファイル名
    file_size = db.Column(db.Integer, nullable=False)  # バイト単位
    word_count = db.Column(db.Integer, default=0)  # 単語数
    upload_date = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    description = db.Column(db.Text)  # ファイルの説明（オプション）
    
    def __repr__(self):
        return f'<RoomCsvFile {self.filename} ({self.word_count} words)>'

class AppInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    app_name = db.Column(db.String(100), default="世界史単語帳", nullable=False)
    version = db.Column(db.String(20), default="1.0.0", nullable=False)
    last_updated_date = db.Column(db.String(50), default="2025年6月15日", nullable=False)
    update_content = db.Column(db.Text, default="アプリケーションが開始されました。", nullable=False)
    footer_text = db.Column(db.String(200), default="", nullable=True)
    contact_email = db.Column(db.String(100), default="", nullable=True)
    app_settings = db.Column(db.Text, default='{}')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    updated_by = db.Column(db.String(80), default="system")

    @classmethod
    def get_current_info(cls):
        app_info = cls.query.first()
        if not app_info:
            app_info = cls()
            db.session.add(app_info)
            try:
                db.session.commit()
            except Exception as e:
                print(f"Error creating app_info: {e}")
                db.session.rollback()
        return app_info

    def to_dict(self):
        return {
            'appName': self.app_name,
            'version': self.version,
            'lastUpdatedDate': self.last_updated_date,
            'updateContent': self.update_content,
            'footerText': self.footer_text,
            'contactEmail': self.contact_email
        }

# ====================================================================
# ヘルパー関数
# ====================================================================

# 部屋ごとの単語データを読み込む関数
def load_word_data_for_room(room_number):
    """指定された部屋の単語データを読み込む（CSV設定永続化対応）"""
    try:
        # データベースから部屋設定を取得
        room_setting = RoomSetting.query.filter_by(room_number=room_number).first()
        
        if room_setting and room_setting.csv_filename:
            csv_filename = room_setting.csv_filename
            print(f"🔍 部屋{room_number}の設定: {csv_filename}")
        else:
            csv_filename = "words.csv"
            print(f"⚠️ 部屋{room_number}の設定なし、デフォルト使用: {csv_filename}")
        
        # ファイルパスを決定
        if csv_filename == "words.csv":
            # デフォルトファイル
            csv_path = 'words.csv'
        else:
            # カスタムファイル
            room_csv_path = os.path.join(ROOM_CSV_FOLDER, csv_filename)
            if os.path.exists(room_csv_path):
                csv_path = room_csv_path
                print(f"✅ カスタムCSV使用: {room_csv_path}")
            else:
                # ファイルが見つからない場合はデフォルトにフォールバック
                csv_path = 'words.csv'
                print(f"❌ カスタムCSVが見つからない: {room_csv_path}, デフォルト使用")
                
                # データベースの設定も修正
                if room_setting:
                    room_setting.csv_filename = "words.csv"
                    db.session.commit()
                    print(f"🔧 部屋{room_number}の設定をデフォルトに修正")
        
        # ファイル読み込み
        word_data = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                row['enabled'] = row.get('enabled', '1') == '1'
                row['chapter'] = str(row['chapter'])
                row['number'] = str(row['number'])
                word_data.append(row)
        
        print(f"📊 読み込み完了: {len(word_data)}問 from {csv_path}")
        return word_data
        
    except FileNotFoundError:
        print(f"❌ ファイルエラー: {csv_path} が見つかりません")
        return []
    except Exception as e:
        print(f"❌ 読み込みエラー: {e}")
        return []

# 管理者用：全体のデフォルト単語データを読み込む関数
def load_default_word_data():
    """デフォルトのwords.csvを読み込む（管理者用）"""
    word_data = []
    try:
        with open('words.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                row['enabled'] = row.get('enabled', '1') == '1'
                row['chapter'] = str(row['chapter'])
                row['number'] = str(row['number'])
                word_data.append(row)
        print(f"Loaded {len(word_data)} words from default words.csv.")
    except FileNotFoundError:
        print("Error: デフォルトのwords.csv が見つかりません。")
        word_data = []
    except Exception as e:
        print(f"Error: デフォルトのwords.csv の読み込み中にエラーが発生しました: {e}")
        word_data = []
    
    return word_data

# 単元番号の比較を数値で行うためのヘルパー関数
def parse_unit_number(unit_str):
    if not isinstance(unit_str, str):
        return float('inf')
    
    parts = unit_str.split('-')
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return int(parts[0]) * 10000 + int(parts[1])
    elif unit_str.isdigit():
        return int(unit_str) * 1000000 
    return float('inf')

# 問題IDを生成するヘルパー関数
# app.py の get_problem_id 関数を以下に置き換え
# app.py の get_problem_id 関数を以下に置き換え

def get_problem_id(word):
    """統一された問題ID生成（JavaScript側と完全一致）"""
    try:
        chapter = str(word.get('chapter', '0')).zfill(3)
        number = str(word.get('number', '0')).zfill(3)
        question = str(word.get('question', ''))
        answer = str(word.get('answer', ''))
        
        # 問題文と答えから英数字と日本語文字のみ抽出（JavaScript側と同じ処理）
        import re
        question_clean = re.sub(r'[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', '', question[:15])
        answer_clean = re.sub(r'[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', '', answer[:10])
        
        # 統一フォーマット
        problem_id = f"{chapter}-{number}-{question_clean}-{answer_clean}"
        
        return problem_id
        
    except Exception as e:
        print(f'ID生成エラー: {e}')
        chapter = str(word.get('chapter', '0')).zfill(3)
        number = str(word.get('number', '0')).zfill(3)
        return f"{chapter}-{number}-error"

def fix_all_user_data():
    """全ユーザーの学習履歴を新しいID形式に統一"""
    
    # デフォルトの単語データを取得
    default_word_data = load_default_word_data()
    if not default_word_data:
        print("❌ 単語データが見つかりません")
        return False
    
    # 新しいID生成方式でマッピングを作成
    word_mapping = {}
    for word in default_word_data:
        new_id = get_problem_id(word)
        word_mapping[new_id] = word
    
    print(f"📋 問題データ: {len(word_mapping)}個")
    
    users = User.query.all()
    fixed_users = 0
    total_fixed_histories = 0
    
    for user in users:
        if user.username == 'admin':
            continue
            
        print(f"\n🔧 修正開始: {user.username}")
        
        old_history = user.get_problem_history()
        old_incorrect = user.get_incorrect_words()
        
        new_history = {}
        new_incorrect = []
        user_fixed_count = 0
        
        # 各履歴エントリを新しいIDで再構築
        for old_id, history_data in old_history.items():
            
            # まず新しいID形式かチェック
            best_match_word = None
            best_score = 0
            
            # 完全一致を探す
            for word in default_word_data:
                new_id = get_problem_id(word)
                if new_id == old_id:
                    best_match_word = word
                    best_score = 1000  # 完全一致は最高スコア
                    break
            
            # 完全一致しない場合は推測マッチング
            if best_score < 1000:
                # 古いIDからの情報抽出を試行
                parts = old_id.split('-')
                if len(parts) >= 2:
                    try:
                        old_chapter = int(parts[0].lstrip('0') or '0')
                        old_number = int(parts[1].lstrip('0') or '0')
                        
                        for word in default_word_data:
                            score = 0
                            word_chapter = int(str(word['chapter']))
                            word_number = int(str(word['number']))
                            
                            # 章と単元の完全一致は高スコア
                            if word_chapter == old_chapter and word_number == old_number:
                                score = 500
                                
                                # 問題文の類似性もチェック
                                if len(parts) > 2:
                                    old_text = ''.join(parts[2:]).lower()
                                    question_clean = str(word['question']).lower()
                                    question_clean = ''.join(c for c in question_clean if c.isalnum())
                                    
                                    if old_text and question_clean and old_text[:10] in question_clean:
                                        score += 100
                                
                                if score > best_score:
                                    best_score = score
                                    best_match_word = word
                                    
                    except ValueError:
                        continue
            
            # マッチした場合は新しいIDで保存
            if best_match_word and best_score >= 500:  # 章・単元一致が最低条件
                new_id = get_problem_id(best_match_word)
                new_history[new_id] = history_data
                user_fixed_count += 1
                
                # 苦手問題の判定
                incorrect_attempts = history_data.get('incorrect_attempts', 0)
                correct_streak = history_data.get('correct_streak', 0)
                
                if incorrect_attempts > 0 and correct_streak < 2:
                    if new_id not in new_incorrect:
                        new_incorrect.append(new_id)
                        
                print(f"  ✓ 修正: {old_id[:30]}... -> {new_id[:30]}...")
        
        if user_fixed_count > 0:
            user.set_problem_history(new_history)
            user.set_incorrect_words(new_incorrect)
            fixed_users += 1
            total_fixed_histories += user_fixed_count
            
            print(f"  📊 修正完了: {user_fixed_count}個の履歴, {len(new_incorrect)}個の苦手問題")
    
    try:
        db.session.commit()
        print(f"\n✅ 全体修正完了")
        print(f"   修正ユーザー数: {fixed_users}")
        print(f"   修正履歴数: {total_fixed_histories}")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"❌ 修正エラー: {e}")
        return False

@app.route('/admin/fix_all_data', methods=['POST'])
def admin_fix_all_data():
    if not session.get('admin_logged_in'):
        flash('管理者権限がありません。', 'danger')
        return redirect(url_for('login_page'))
    
    try:
        success = fix_all_user_data()
        if success:
            flash('全ユーザーデータの修正が完了しました。', 'success')
        else:
            flash('データ修正中にエラーが発生しました。', 'danger')
    except Exception as e:
        flash(f'データ修正エラー: {str(e)}', 'danger')
    
    return redirect(url_for('admin_page'))

# データベースマイグレーション関数
def migrate_database():
    """データベーススキーマの変更を処理する"""
    with app.app_context():
        print("🔄 データベースマイグレーションを開始...")
        
        try:
            # SQLiteの場合、カラムの追加をチェック
            inspector = inspect(db.engine)
            
            # Userテーブルの確認
            if inspector.has_table('user'):
                columns = [col['name'] for col in inspector.get_columns('user')]
                print(f"📋 既存のUserテーブルカラム: {columns}")
                
                # last_loginカラムが存在しない場合は追加
                if 'last_login' not in columns:
                    print("🔧 last_loginカラムを追加します...")
                    # SQLAlchemy 2.0対応の書き方
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE user ADD COLUMN last_login DATETIME'))
                        conn.commit()
                    print("✅ last_loginカラムを追加しました。")
            
            # RoomSettingテーブルの確認
            if inspector.has_table('room_setting'):
                columns = [col['name'] for col in inspector.get_columns('room_setting')]
                print(f"📋 既存のRoomSettingテーブルカラム: {columns}")
                
                # csv_filenameカラムが存在しない場合は追加
                if 'csv_filename' not in columns:
                    print("🔧 csv_filenameカラムを追加します...")
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE room_setting ADD COLUMN csv_filename VARCHAR(100) DEFAULT "words.csv"'))
                        conn.commit()
                    print("✅ csv_filenameカラムを追加しました。")
                
            # AppInfoテーブルの確認
            if inspector.has_table('app_info'):
                columns = [col['name'] for col in inspector.get_columns('app_info')]
                missing_columns = []
                
                expected_columns = [
                    ('footer_text', 'VARCHAR(200)'),
                    ('contact_email', 'VARCHAR(100)'),
                    ('app_settings', 'TEXT'),
                    ('created_at', 'DATETIME'),
                    ('updated_at', 'DATETIME'),
                    ('updated_by', 'VARCHAR(80)')
                ]
                
                for col_name, col_type in expected_columns:
                    if col_name not in columns:
                        missing_columns.append((col_name, col_type))
                
                if missing_columns:
                    with db.engine.connect() as conn:
                        for col_name, col_type in missing_columns:
                            print(f"🔧 {col_name}カラムを追加します...")
                            conn.execute(text(f'ALTER TABLE app_info ADD COLUMN {col_name} {col_type}'))
                            print(f"✅ {col_name}カラムを追加しました。")
                        conn.commit()
            
            # 4. userテーブルにlast_loginカラムを追加（重複チェック）
            if inspector.has_table('user'):
                user_columns = [col['name'] for col in inspector.get_columns('user')]
                
                if 'last_login' not in user_columns:
                    print("userテーブルにlast_loginカラムを追加します...")
                    with db.engine.connect() as conn:
                        conn.execute(text("ALTER TABLE user ADD COLUMN last_login DATETIME"))
                        # 既存ユーザーには現在時刻を設定
                        conn.execute(text("UPDATE user SET last_login = datetime('now', 'localtime') WHERE last_login IS NULL"))
                        conn.commit()
                    print("✅ last_loginカラムを追加しました。")
                else:
                    print("last_loginカラムは既に存在します。")
            
            # 5. RoomCsvFileテーブルの作成
            if inspector.has_table('room_csv_file'):
                print("room_csv_fileテーブルは既に存在します。")
            else:
                print("room_csv_fileテーブルを作成します...")
                try:
                    with db.engine.connect() as conn:
                        conn.execute(text('''
                            CREATE TABLE room_csv_file (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                filename VARCHAR(100) NOT NULL UNIQUE,
                                original_filename VARCHAR(100) NOT NULL,
                                file_size INTEGER NOT NULL,
                                word_count INTEGER DEFAULT 0,
                                upload_date DATETIME DEFAULT (datetime('now', 'localtime')),
                                description TEXT
                            )
                        '''))
                        conn.commit()
                    print("✅ room_csv_fileテーブルを作成しました。")
                except Exception as e:
                    print(f"⚠️ room_csv_fileテーブル作成でエラー（続行）: {e}")

            # 6. 既存CSVファイルをroom_csv_fileテーブルに登録（初回のみ）
            try:
                if os.path.exists(ROOM_CSV_FOLDER):
                    for filename in os.listdir(ROOM_CSV_FOLDER):
                        if filename.endswith('.csv'):
                            # データベースに既に登録されているかチェック
                            with db.engine.connect() as conn:
                                result = conn.execute(text("SELECT COUNT(*) FROM room_csv_file WHERE filename = :filename"), 
                                                    {"filename": filename})
                                exists = result.scalar() > 0
                            
                            if not exists:
                                file_path = os.path.join(ROOM_CSV_FOLDER, filename)
                                file_size = os.path.getsize(file_path)
                                
                                # 単語数をカウント
                                word_count = 0
                                try:
                                    with open(file_path, 'r', encoding='utf-8') as f:
                                        reader = csv.DictReader(f)
                                        word_count = sum(1 for row in reader)
                                except:
                                    word_count = 0
                                
                                # データベースに登録
                                with db.engine.connect() as conn:
                                    conn.execute(text('''
                                        INSERT INTO room_csv_file (filename, original_filename, file_size, word_count)
                                        VALUES (:filename, :original_filename, :file_size, :word_count)
                                    '''), {
                                        "filename": filename,
                                        "original_filename": filename,
                                        "file_size": file_size,
                                        "word_count": word_count
                                    })
                                    conn.commit()
                                
                                print(f"📝 既存CSVファイルを登録: {filename} ({word_count}問)")
            except Exception as e:
                print(f"⚠️ 既存CSVファイル登録でエラー（続行）: {e}")
            
            print("✅ データベースマイグレーションが完了しました。")
            
        except Exception as e:
            print(f"⚠️ マイグレーション中にエラーが発生しました（続行します）: {e}")
            import traceback
            traceback.print_exc()

# データベース初期化関数（完全リセット対応版）
def create_tables_and_admin_user():
    with app.app_context():
        print("🔧 データベース初期化を開始...")
        
        # ===== RENDER環境対策 =====
        reset_database = os.environ.get('RESET_DATABASE', 'false').lower() == 'true'
        is_render_env = os.environ.get('RENDER') == 'true'
        
        if reset_database:
            print("⚠️ 警告: RESET_DATABASE=true が設定されています！")
            if is_render_env:
                print("🚨 Render環境でのデータベースリセットが検出されました")
                print("💡 本番運用では RESET_DATABASE=false に設定してください")
            else:
                print("🏠 ローカル環境でのリセットです")
        
        try:
            # 既存のテーブル確認
            inspector = inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
            if reset_database and existing_tables:
                print("🔄 データベースを完全リセットします...")
                db.drop_all()
                db.create_all()
                print("✅ データベースを完全リセットしました。")
                force_create_admin = True
            elif existing_tables:
                print(f"📋 既存のテーブル: {existing_tables}")
                migrate_database()
                db.create_all()
                print("✅ テーブルを確認/更新しました。")
                force_create_admin = False
            else:
                print("📋 新しいデータベースを作成します。")
                db.create_all()
                print("✅ テーブルを作成しました。")
                force_create_admin = True
            
            # ===== 管理者ユーザー確認/作成 =====
            try:
                admin_user = User.query.filter_by(username='admin', room_number='ADMIN').first()
                
                if not admin_user or force_create_admin:
                    if admin_user:
                        print("🔄 既存の管理者ユーザーを削除して再作成します...")
                        db.session.delete(admin_user)
                    
                    print("👤 管理者ユーザーを作成します...")
                    admin_user = User(
                        username='admin',
                        room_number='ADMIN',
                        student_id='000',
                        problem_history='{}',
                        incorrect_words='[]'
                    )
                    admin_user.last_login = datetime.now(JST)
                    admin_user.set_room_password('Avignon1309')
                    admin_user.set_individual_password('Avignon1309')
                    db.session.add(admin_user)
                    db.session.commit()
                    print("✅ 管理者ユーザー 'admin' を作成しました（パスワード: Avignon1309）")
                else:
                    print("✅ 管理者ユーザー 'admin' は既に存在します。")
                    
            except Exception as e:
                print(f"⚠️ 管理者ユーザー処理エラー: {e}")
                db.session.rollback()
                
                # フォールバック: 強制的に管理者ユーザーを作成
                try:
                    admin_user = User(
                        username='admin',
                        room_number='ADMIN',
                        student_id='000',
                        problem_history='{}',
                        incorrect_words='[]'
                    )
                    admin_user.set_room_password('Avignon1309')
                    admin_user.set_individual_password('Avignon1309')
                    db.session.add(admin_user)
                    db.session.commit()
                    print("✅ フォールバック: 管理者ユーザーを作成しました")
                except Exception as fallback_error:
                    print(f"❌ 管理者ユーザー作成失敗: {fallback_error}")
                
            # ===== アプリ情報確認/作成 =====
            try:
                app_info = AppInfo.get_current_info()
                print("✅ アプリ情報を確認/作成しました")
                
            except Exception as e:
                print(f"⚠️ アプリ情報処理エラー: {e}")
                try:
                    default_app_info = AppInfo()
                    db.session.add(default_app_info)
                    db.session.commit()
                    print("✅ フォールバック: デフォルトアプリ情報を作成しました")
                except Exception as fallback_error:
                    print(f"❌ アプリ情報作成失敗: {fallback_error}")
                
        except Exception as e:
            print(f"❌ データベース初期化エラー: {e}")
            db.session.rollback()
            
            # ===== Render対応: 強制初期化 =====
            if is_render_env:
                print("🔄 Render環境での強制初期化を実行...")
                try:
                    db.drop_all()
                    db.create_all()
                    
                    # 最小限の管理者ユーザー作成
                    admin_user = User(
                        username='admin',
                        room_number='ADMIN',
                        student_id='000',
                        problem_history='{}',
                        incorrect_words='[]'
                    )
                    admin_user.set_room_password('Avignon1309')
                    admin_user.set_individual_password('Avignon1309')
                    db.session.add(admin_user)
                    
                    # デフォルトアプリ情報
                    default_app_info = AppInfo()
                    db.session.add(default_app_info)
                    
                    db.session.commit()
                    print("✅ Render環境での強制初期化が完了しました")
                    
                except Exception as render_error:
                    print(f"🚨 Render強制初期化失敗: {render_error}")
                    raise
            else:
                raise
        
        print("🎉 データベース初期化が完了しました！")

# ===== PostgreSQL設定（Render用） =====
def configure_production_database():
    """本番環境用のデータベース設定"""
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        print("🐘 PostgreSQL設定を適用中...")
        
        # PostgreSQL用のURLフォーマット修正
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_timeout': 20,
            'pool_recycle': -1,
            'pool_pre_ping': True,
            'connect_args': {
                'connect_timeout': 10,
            }
        }
        print(f"✅ PostgreSQL接続設定完了: {database_url[:50]}...")
        return True
    else:
        print("📄 SQLite設定を維持")
        return False
    
# ===== データ永続化チェック機能 =====
def check_data_persistence():
    """データの永続化状況をチェック"""
    try:
        user_count = User.query.count()
        admin_count = User.query.filter_by(room_number='ADMIN').count()
        room_settings_count = RoomSetting.query.count()
        
        print(f"📊 データ永続化状況:")
        print(f"   総ユーザー数: {user_count}")
        print(f"   管理者ユーザー: {admin_count}")
        print(f"   部屋設定数: {room_settings_count}")
        
        if admin_count == 0:
            print("⚠️ 管理者ユーザーが見つかりません！")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ データ永続化チェックエラー: {e}")
        return False

# ===== 環境変数設定推奨機能 =====
def print_render_recommendations():
    """Render環境での推奨設定を表示"""
    is_render = os.environ.get('RENDER') == 'true'
    reset_db = os.environ.get('RESET_DATABASE', 'false').lower() == 'true'
    has_postgres = bool(os.environ.get('DATABASE_URL'))
    
    print("\n" + "="*60)
    print("🚀 RENDER環境設定推奨事項")
    print("="*60)
    
    if is_render:
        print("✅ Render環境を検出")
        
        if reset_db:
            print("⚠️ RESET_DATABASE=true が設定されています")
            print("💡 本番運用時は以下を設定してください:")
            print("   Environment Variable: RESET_DATABASE = false")
        else:
            print("✅ RESET_DATABASE=false (推奨)")
        
        if has_postgres:
            print("✅ PostgreSQLデータベースが設定されています")
        else:
            print("⚠️ PostgreSQLデータベースが推奨されます")
            print("💡 Render Dashboardで PostgreSQL Add-on を追加してください")
        
        print("\n📋 推奨環境変数設定:")
        print("   RESET_DATABASE = false")
        print("   PYTHON_VERSION = 3.11.9")
        if not has_postgres:
            print("   DATABASE_URL = <PostgreSQL接続URL>")
        
    else:
        print("🏠 ローカル環境で実行中")
    
    print("="*60 + "\n")

# ====================================================================
# ルーティング
# ====================================================================

@app.route('/test')
def test_page():
    return "<h1>Test Page</h1><p>This is a simple test page.</p>"

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/')
def index():
    try:
        if 'user_id' not in session:
            flash('学習を開始するにはログインしてください。', 'info')
            return redirect(url_for('login_page'))
        
        current_user = User.query.get(session['user_id'])
        if not current_user:
            flash('ユーザーが見つかりません。再ログインしてください。', 'danger')
            return redirect(url_for('logout'))

        # JavaScript用のapp_info（従来の形式）
        app_info_for_js = get_app_info_dict(
            user_id=session.get('user_id'),
            username=session.get('username'), 
            room_number=session.get('room_number')
        )
        
        word_data = load_word_data_for_room(current_user.room_number)
        
        room_setting = RoomSetting.query.filter_by(room_number=current_user.room_number).first()
        max_enabled_unit_num_str = room_setting.max_enabled_unit_number if room_setting else "9999"
        parsed_max_enabled_unit_num = parse_unit_number(max_enabled_unit_num_str)

        all_chapter_unit_status = {}
        for word in word_data:
            chapter_num = word['chapter']
            unit_num = word['number']
            category_name = word.get('category', '未分類')
            
            is_word_enabled_in_csv = word['enabled']
            is_unit_enabled_by_room_setting = parse_unit_number(unit_num) <= parsed_max_enabled_unit_num
            is_unit_globally_enabled = is_word_enabled_in_csv and is_unit_enabled_by_room_setting

            if chapter_num not in all_chapter_unit_status:
                all_chapter_unit_status[chapter_num] = {'units': {}, 'name': f'第{chapter_num}章'}
            
            if unit_num not in all_chapter_unit_status[chapter_num]['units']:
                all_chapter_unit_status[chapter_num]['units'][unit_num] = {
                    'categoryName': category_name,
                    'enabled': is_unit_globally_enabled
                }
            else:
                if is_unit_globally_enabled:
                    all_chapter_unit_status[chapter_num]['units'][unit_num]['enabled'] = True

        sorted_all_chapter_unit_status = dict(sorted(all_chapter_unit_status.items(), 
                                                    key=lambda item: int(item[0]) if item[0].isdigit() else float('inf')))

        # フッター用のコンテキストを取得
        context = get_template_context()
        
        # ★ 修正: app_infoの重複を避けるため、contextからapp_infoを削除してから結合
        footer_app_info = context.pop('app_info', None)
        
        return render_template('index.html', 
                               app_info=app_info_for_js,  # JavaScript用（従来形式）
                               chapter_data=sorted_all_chapter_unit_status,
                               footer_app_info=footer_app_info,  # フッター用（新しい名前）
                               **context)  # その他のコンテキスト
    
    except Exception as e:
        print(f"Error in index route: {e}")
        import traceback
        traceback.print_exc()
        return f"Internal Server Error: {e}", 500

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    try:
        if request.method == 'POST':
            login_type = request.form.get('login_type', 'user')
            
            if login_type == 'admin':
                admin_username = request.form.get('admin_username')
                admin_password = request.form.get('admin_password')
                
                admin_user = User.query.filter_by(username=admin_username, room_number='ADMIN', student_id='000').first()
                
                if admin_user and admin_user.check_individual_password(admin_password):
                    session['user_id'] = admin_user.id
                    session['username'] = admin_user.username
                    session['room_number'] = admin_user.room_number
                    session['admin_logged_in'] = True
                    session.permanent = True
                    
                    admin_user.last_login = datetime.now(JST)
                    db.session.commit()
                    
                    flash('管理者としてログインしました。', 'success')
                    return redirect(url_for('admin_page'))
                else:
                    flash('管理者のユーザー名またはパスワードが間違っています。', 'danger')
            
            else:
                room_number = request.form.get('room_number')
                room_password = request.form.get('room_password')
                student_id = request.form.get('student_id')
                individual_password = request.form.get('individual_password')

                user = User.query.filter_by(room_number=room_number, student_id=student_id).first()

                if user and user.check_individual_password(individual_password) and user.check_room_password(room_password):
                    session['user_id'] = user.id
                    session['username'] = user.username
                    session['room_number'] = user.room_number
                    session['admin_logged_in'] = False
                    session.permanent = True
                    
                    user.last_login = datetime.now(JST)
                    db.session.commit()

                    flash('ログインしました。', 'success')
                    return redirect(url_for('index'))
                else:
                    flash('部屋番号、出席番号、またはパスワードが間違っています。', 'danger')
        
        # フッター用のコンテキストを取得
        context = get_template_context()
        return render_template('login.html', **context)
        
    except Exception as e:
        print(f"Error in login route: {e}")
        import traceback
        traceback.print_exc()
        return f"Login Error: {e}", 500

@app.route('/logout')
def logout():
    try:
        session.pop('user_id', None)
        session.pop('username', None)
        session.pop('room_number', None)
        session.pop('admin_logged_in', None)
        flash('ログアウトしました。', 'info')
        return redirect(url_for('login_page'))
    except Exception as e:
        print(f"Error in logout: {e}")
        return redirect(url_for('login_page'))

# パスワード変更ページ
@app.route('/password_change', methods=['GET', 'POST'])
def password_change_page():
    try:
        if request.method == 'POST':
            room_number = request.form.get('room_number')
            room_password = request.form.get('room_password')
            student_id = request.form.get('student_id')
            old_password = request.form.get('old_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')

            user = User.query.filter_by(room_number=room_number, student_id=student_id).first()

            if not user:
                flash('指定された部屋番号・出席番号のユーザーが見つかりません。', 'danger')
            elif not user.check_room_password(room_password):
                flash('入室パスワードが間違っています。', 'danger')
            elif not user.check_individual_password(old_password):
                flash('現在の個別パスワードが間違っています。', 'danger')
            elif not new_password:
                flash('新しいパスワードを入力してください。', 'danger')
            elif new_password != confirm_password:
                flash('新しいパスワードが一致しません。', 'danger')
            else:
                user.set_individual_password(new_password)
                db.session.commit()
                flash('パスワードが更新されました。再度ログインしてください。', 'success')
                session.pop('user_id', None)
                session.pop('username', None)
                session.pop('room_number', None)
                session.pop('admin_logged_in', None)
                return redirect(url_for('login_page'))
        
        context = get_template_context()
        return render_template('password_change.html', **context)
    except Exception as e:
        print(f"Error in password_change_page: {e}")
        import traceback
        traceback.print_exc()
        return f"Password Change Error: {e}", 500

# ====================================================================
# APIエンドポイント
# ====================================================================

@app.route('/api/word_data')
def api_word_data():
    try:
        if 'user_id' not in session:
            return jsonify(status='error', message='認証されていません。'), 401

        current_user_id = session.get('user_id')
        current_user = User.query.get(current_user_id)
        
        if not current_user:
            return jsonify(status='error', message='ユーザーが見つかりません。'), 404

        word_data = load_word_data_for_room(current_user.room_number)
        
        room_setting = RoomSetting.query.filter_by(room_number=current_user.room_number).first()
        max_enabled_unit_num_str = room_setting.max_enabled_unit_number if room_setting else "9999"
        parsed_max_enabled_unit_num = parse_unit_number(max_enabled_unit_num_str)

        filtered_word_data = []
        for word in word_data:
            unit_num = word['number']
            is_word_enabled_in_csv = word['enabled']
            is_unit_enabled_by_room_setting = parse_unit_number(unit_num) <= parsed_max_enabled_unit_num

            if is_word_enabled_in_csv and is_unit_enabled_by_room_setting:
                filtered_word_data.append(word)
        
        return jsonify(filtered_word_data)
        
    except Exception as e:
        print(f"Error in api_word_data: {e}")
        return jsonify(status='error', message=str(e)), 500

@app.route('/api/load_quiz_progress')
def api_load_quiz_progress():
    try:
        if 'user_id' not in session:
            return jsonify(status='error', message='Not authenticated'), 401
        
        current_user = User.query.get(session['user_id'])
        if not current_user:
            return jsonify(status='error', message='ユーザーが見つかりません。'), 404

        return jsonify(status='success', 
                       problemHistory=current_user.get_problem_history(),
                       incorrectWords=current_user.get_incorrect_words(),
                       quizProgress={})
    except Exception as e:
        print(f"Error in api_load_quiz_progress: {e}")
        return jsonify(status='error', message=str(e)), 500

@app.route('/api/save_progress', methods=['POST'])
def save_quiz_progress():
    try:
        if 'user_id' not in session:
            return jsonify(status='error', message='ログインしていません。'), 401
        
        data = request.get_json()
        received_problem_history = data.get('problemHistory', {})
        received_incorrect_words = data.get('incorrectWords', [])

        current_user = User.query.get(session['user_id'])
        if not current_user:
            return jsonify(status='error', message='ユーザーが見つかりません。'), 404

        current_user.set_problem_history(received_problem_history)
        current_user.set_incorrect_words(received_incorrect_words)
        db.session.commit()

        return jsonify(status='success', message='進捗が保存されました。')
        
    except Exception as e:
        print(f"Error saving progress: {e}")
        db.session.rollback()
        return jsonify(status='error', message=f'進捗の保存中にエラーが発生しました: {str(e)}'), 500

# app.pyに追加する詳細な保存・読み込みデバッグルート

@app.route('/api/save_progress_debug', methods=['POST'])
def save_quiz_progress_debug():
    """デバッグ情報付きの進捗保存"""
    try:
        if 'user_id' not in session:
            return jsonify(status='error', message='ログインしていません。'), 401
        
        data = request.get_json()
        received_problem_history = data.get('problemHistory', {})
        received_incorrect_words = data.get('incorrectWords', [])

        current_user = User.query.get(session['user_id'])
        if not current_user:
            return jsonify(status='error', message='ユーザーが見つかりません。'), 404

        # 保存前の状態を記録
        old_history = current_user.get_problem_history()
        old_incorrect = current_user.get_incorrect_words()
        
        print(f"\n=== 進捗保存デバッグ ({current_user.username}) ===")
        print(f"保存前の履歴数: {len(old_history)}")
        print(f"受信した履歴数: {len(received_problem_history)}")
        print(f"保存前の苦手問題数: {len(old_incorrect)}")
        print(f"受信した苦手問題数: {len(received_incorrect_words)}")
        
        # 新しく追加された履歴を特定
        new_entries = {}
        for problem_id, history in received_problem_history.items():
            if problem_id not in old_history:
                new_entries[problem_id] = history
                print(f"新規履歴: {problem_id} -> {history}")
            elif old_history[problem_id] != history:
                print(f"更新履歴: {problem_id}")
                print(f"  旧: {old_history[problem_id]}")
                print(f"  新: {history}")
        
        print(f"新規追加される履歴数: {len(new_entries)}")

        # 実際に保存
        current_user.set_problem_history(received_problem_history)
        current_user.set_incorrect_words(received_incorrect_words)
        db.session.commit()

        # 保存後の確認
        saved_history = current_user.get_problem_history()
        saved_incorrect = current_user.get_incorrect_words()
        
        print(f"保存後の履歴数: {len(saved_history)}")
        print(f"保存後の苦手問題数: {len(saved_incorrect)}")
        print("=== 進捗保存デバッグ終了 ===\n")

        return jsonify(
            status='success', 
            message='進捗が保存されました。',
            debug_info={
                'old_history_count': len(old_history),
                'new_history_count': len(received_problem_history),
                'saved_history_count': len(saved_history),
                'new_entries_count': len(new_entries),
                'old_incorrect_count': len(old_incorrect),
                'new_incorrect_count': len(received_incorrect_words),
                'saved_incorrect_count': len(saved_incorrect)
            }
        )
        
    except Exception as e:
        print(f"Error saving progress: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify(status='error', message=f'進捗の保存中にエラーが発生しました: {str(e)}'), 500

@app.route('/debug/trace_answer_flow')
def debug_trace_answer_flow():
    """回答フローの詳細なトレース"""
    if 'user_id' not in session:
        return jsonify(error='ログインが必要です'), 401
    
    current_user = User.query.get(session['user_id'])
    if not current_user:
        return jsonify(error='ユーザーが見つかりません'), 404
    
    word_data = load_word_data_for_room(current_user.room_number)
    user_history = current_user.get_problem_history()
    
    # 最近の5問の詳細分析
    sample_words = word_data[:5]
    trace_results = []
    
    for word in sample_words:
        # 1. 問題IDの生成
        python_id = get_problem_id(word)
        
        # 2. 履歴の確認
        history_entry = user_history.get(python_id, {})
        
        # 3. 進捗ページでの処理をシミュレート
        room_setting = RoomSetting.query.filter_by(room_number=current_user.room_number).first()
        max_enabled_unit_num_str = room_setting.max_enabled_unit_number if room_setting else "9999"
        parsed_max_enabled_unit_num = parse_unit_number(max_enabled_unit_num_str)
        
        is_word_enabled_in_csv = word['enabled']
        is_unit_enabled_by_room_setting = parse_unit_number(word['number']) <= parsed_max_enabled_unit_num
        is_counted_in_progress = is_word_enabled_in_csv and is_unit_enabled_by_room_setting
        
        correct_attempts = history_entry.get('correct_attempts', 0)
        incorrect_attempts = history_entry.get('incorrect_attempts', 0)
        total_attempts = correct_attempts + incorrect_attempts
        
        trace_results.append({
            'question': word['question'][:50] + '...' if len(word['question']) > 50 else word['question'],
            'answer': word['answer'],
            'chapter': word['chapter'],
            'number': word['number'],
            'category': word['category'],
            'enabled_in_csv': is_word_enabled_in_csv,
            'enabled_by_room_setting': is_unit_enabled_by_room_setting,
            'counted_in_progress': is_counted_in_progress,
            'generated_id': python_id,
            'has_history': python_id in user_history,
            'history_entry': history_entry,
            'total_attempts': total_attempts,
            'correct_attempts': correct_attempts,
            'incorrect_attempts': incorrect_attempts,
            'accuracy_rate': (correct_attempts / total_attempts * 100) if total_attempts > 0 else 0
        })
    
    return jsonify({
        'user_info': {
            'username': current_user.username,
            'room_number': current_user.room_number
        },
        'room_settings': {
            'max_enabled_unit_number': max_enabled_unit_num_str,
            'parsed_max_enabled_unit_num': parsed_max_enabled_unit_num
        },
        'total_history_entries': len(user_history),
        'total_word_data': len(word_data),
        'trace_results': trace_results
    })

@app.route('/debug/manual_test_save', methods=['POST'])
def debug_manual_test_save():
    """手動でテスト用の学習履歴を作成"""
    if 'user_id' not in session:
        return jsonify(error='ログインが必要です'), 401
    
    current_user = User.query.get(session['user_id'])
    if not current_user:
        return jsonify(error='ユーザーが見つかりません'), 404
    
    word_data = load_word_data_for_room(current_user.room_number)
    if not word_data:
        return jsonify(error='単語データが見つかりません'), 404
    
    # 最初の3問に対してテスト履歴を作成
    current_history = current_user.get_problem_history()
    test_words = word_data[:3]
    
    for word in test_words:
        problem_id = get_problem_id(word)
        
        # テスト用の履歴データを追加
        if problem_id not in current_history:
            current_history[problem_id] = {
                'correct_attempts': 2,
                'incorrect_attempts': 1,
                'correct_streak': 1,
                'last_answered': datetime.now().isoformat()
            }
            print(f"テスト履歴追加: {word['question']} -> {problem_id}")
    
    # 保存
    current_user.set_problem_history(current_history)
    
    try:
        db.session.commit()
        print(f"テスト履歴保存完了: {len(test_words)}問")
        
        return jsonify({
            'status': 'success',
            'message': f'{len(test_words)}問のテスト履歴を追加しました',
            'test_words': [
                {
                    'question': word['question'],
                    'generated_id': get_problem_id(word)
                }
                for word in test_words
            ],
            'total_history_count': len(current_history)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500

@app.route('/api/clear_quiz_progress', methods=['POST'])
def api_clear_quiz_progress():
    return jsonify(status='success', message='一時的なクイズ進捗クリア要求を受信しました（サーバー側は変更なし）。')

# ====================================================================
# 進捗ページ
# ====================================================================

# app.pyの進捗ページルートを以下に置き換え

@app.route('/progress')
def progress_page():
    try:
        if 'user_id' not in session:
            flash('進捗を確認するにはログインしてください。', 'info')
            return redirect(url_for('login_page'))

        current_user = User.query.get(session['user_id'])
        if not current_user:
            flash('ユーザーが見つかりません。', 'danger')
            return redirect(url_for('logout'))

        print(f"\n=== 進捗ページ処理開始 ===")
        print(f"ユーザー: {current_user.username} (部屋: {current_user.room_number})")

        user_problem_history = current_user.get_problem_history()
        print(f"学習履歴数: {len(user_problem_history)}")
        
        # 部屋ごとの単語データを取得
        word_data = load_word_data_for_room(current_user.room_number)
        print(f"部屋の単語データ数: {len(word_data)}")
        
        room_setting = RoomSetting.query.filter_by(room_number=current_user.room_number).first()
        max_enabled_unit_num_str = room_setting.max_enabled_unit_number if room_setting else "9999"
        parsed_max_enabled_unit_num = parse_unit_number(max_enabled_unit_num_str)
        print(f"最大単元番号: {max_enabled_unit_num_str}")

        unit_progress_summary = {}

        # 有効な単語データで単元進捗を初期化
        for word in word_data:
            chapter_num = word['chapter']
            unit_num = word['number']
            category_name = word.get('category', '未分類')
            
            is_word_enabled_in_csv = word['enabled']
            is_unit_enabled_by_room_setting = parse_unit_number(unit_num) <= parsed_max_enabled_unit_num

            if is_word_enabled_in_csv and is_unit_enabled_by_room_setting:
                if unit_num not in unit_progress_summary:
                    unit_progress_summary[unit_num] = {
                        'categoryName': category_name,
                        'attempted_problems': set(),
                        'mastered_problems': set(),
                        'total_questions_in_unit': 0,
                        'total_attempts': 0
                    }
                unit_progress_summary[unit_num]['total_questions_in_unit'] += 1

        print(f"有効な単元数: {len(unit_progress_summary)}")

        # 学習履歴を処理
        matched_problems = 0
        unmatched_problems = 0
        
        for problem_id, history in user_problem_history.items():
            # 問題IDに対応する単語を検索
            matched_word = None
            for word in word_data:
                generated_id = get_problem_id(word)
                if generated_id == problem_id:
                    matched_word = word
                    break

            if matched_word:
                matched_problems += 1
                unit_number_of_word = matched_word['number']
                
                is_word_enabled_in_csv = matched_word['enabled']
                is_unit_enabled_by_room_setting = parse_unit_number(unit_number_of_word) <= parsed_max_enabled_unit_num

                if is_word_enabled_in_csv and is_unit_enabled_by_room_setting:
                    if unit_number_of_word in unit_progress_summary:
                        correct_attempts = history.get('correct_attempts', 0)
                        incorrect_attempts = history.get('incorrect_attempts', 0)
                        total_problem_attempts = correct_attempts + incorrect_attempts
                        
                        unit_progress_summary[unit_number_of_word]['total_attempts'] += total_problem_attempts
                        
                        if total_problem_attempts > 0:
                            unit_progress_summary[unit_number_of_word]['attempted_problems'].add(problem_id)
                            
                            # マスター判定：正答率80%以上
                            accuracy_rate = (correct_attempts / total_problem_attempts) * 100
                            if accuracy_rate >= 80.0:
                                unit_progress_summary[unit_number_of_word]['mastered_problems'].add(problem_id)
                                print(f"マスター問題: {matched_word['question']} (正答率: {accuracy_rate:.1f}%)")
            else:
                unmatched_problems += 1
                print(f"マッチしない問題ID: {problem_id}")
        
        print(f"マッチした問題: {matched_problems}, マッチしない問題: {unmatched_problems}")
        
        # 単元別進捗をソート
        sorted_user_progress_by_unit = []
        for unit_num in sorted(unit_progress_summary.keys(), key=lambda x: parse_unit_number(x)):
            data = unit_progress_summary[unit_num]
            sorted_user_progress_by_unit.append((unit_num, {
                'categoryName': data['categoryName'],
                'attempted_problems': list(data['attempted_problems']),
                'mastered_problems': list(data['mastered_problems']),
                'total_questions_in_unit': data['total_questions_in_unit'],
                'total_attempts': data['total_attempts']
            }))

        print(f"進捗のある単元数: {len(sorted_user_progress_by_unit)}")

        # ランキング計算（部屋ごとの単語データを使用）
        current_room_number = current_user.room_number
        
        all_users_for_ranking = User.query.filter_by(room_number=current_room_number).all()
        ranking_data = []

        room_setting_for_ranking = RoomSetting.query.filter_by(room_number=current_room_number).first()
        max_enabled_unit_num_str_for_ranking = room_setting_for_ranking.max_enabled_unit_number if room_setting_for_ranking else "9999"
        parsed_max_enabled_unit_num_for_ranking = parse_unit_number(max_enabled_unit_num_str_for_ranking)
        
        total_questions_for_room_ranking = 0
        for word in word_data:
            is_word_enabled_in_csv = word['enabled']
            is_unit_enabled_by_room_setting = parse_unit_number(word['number']) <= parsed_max_enabled_unit_num_for_ranking
            if is_word_enabled_in_csv and is_unit_enabled_by_room_setting:
                total_questions_for_room_ranking += 1

        for user_obj in all_users_for_ranking:
            if user_obj.username == 'admin':
                continue
                
            total_attempts = 0
            total_correct = 0
            
            mastered_problem_ids = set()

            user_obj_problem_history = user_obj.get_problem_history()

            if isinstance(user_obj_problem_history, dict):
                for problem_id, history in user_obj_problem_history.items():
                    matched_word = None
                    for word in word_data:
                        generated_id = get_problem_id(word)
                        if generated_id == problem_id:
                            matched_word = word
                            break

                    if matched_word:
                        is_word_enabled_in_csv = matched_word['enabled']
                        is_unit_enabled_by_room_setting = parse_unit_number(matched_word['number']) <= parsed_max_enabled_unit_num_for_ranking

                        if is_word_enabled_in_csv and is_unit_enabled_by_room_setting:
                            correct_attempts = history.get('correct_attempts', 0)
                            incorrect_attempts = history.get('incorrect_attempts', 0)
                            problem_total_attempts = correct_attempts + incorrect_attempts
                            
                            total_attempts += problem_total_attempts
                            total_correct += correct_attempts
                            
                            if problem_total_attempts > 0:
                                accuracy_rate = (correct_attempts / problem_total_attempts) * 100
                                if accuracy_rate >= 80.0:
                                    mastered_problem_ids.add(problem_id)
            
            user_mastered_count = len(mastered_problem_ids)
            coverage_rate = (user_mastered_count / total_questions_for_room_ranking * 100) if total_questions_for_room_ranking > 0 else 0
            
            # バランス型スコア計算: 総回答数 × 正答率 / 100
            balance_score = (total_attempts * (total_correct / total_attempts)) if total_attempts > 0 else 0

            ranking_data.append({
                'username': user_obj.username,
                'total_attempts': total_attempts,
                'total_correct': total_correct,
                'accuracy_rate': (total_correct / total_attempts * 100) if total_attempts > 0 else 0,
                'coverage_rate': coverage_rate,
                'mastered_count': user_mastered_count,
                'total_questions_for_room': total_questions_for_room_ranking,
                'balance_score': balance_score
            })

        # バランススコアで降順ソート
        ranking_data.sort(key=lambda x: (x['balance_score'], x['total_attempts']), reverse=True)
        top_10_ranking = ranking_data[:10]

        print(f"ランキング対象ユーザー数: {len(ranking_data)}")
        print("=== 進捗ページ処理完了 ===\n")

        # フッター表示のためにapp_infoを取得
        app_info = AppInfo.get_current_info()

        context = get_template_context()
        
        return render_template('progress.html',
                               current_user=current_user,
                               user_progress_by_unit=sorted_user_progress_by_unit,
                               top_10_ranking=top_10_ranking,
                               **context)
    except Exception as e:
        print(f"Error in progress_page: {e}")
        import traceback
        traceback.print_exc()
        return f"Progress Error: {e}", 500

# ====================================================================
# 管理者ページ
# ====================================================================

# app.pyのadmin_pageルートを以下に置き換え

@app.route('/admin')
def admin_page():
    try:
        if not session.get('admin_logged_in'):
            flash('管理者権限がありません。', 'danger')
            return redirect(url_for('login_page'))

        print("🔍 管理者ページ表示開始...")

        users = User.query.all()
        room_settings = RoomSetting.query.all()
        
        # 部屋設定のマッピングを作成
        room_max_unit_settings = {rs.room_number: rs.max_enabled_unit_number for rs in room_settings}
        room_csv_settings = {rs.room_number: rs.csv_filename for rs in room_settings}
        
        print(f"📊 部屋設定状況:")
        for room_num, csv_file in room_csv_settings.items():
            print(f"  部屋{room_num}: {csv_file}")
        
        # 部屋番号のリストを取得（ユーザーがいる部屋と設定のある部屋を統合）
        unique_room_numbers = set()
        for user in users:
            if user.room_number != 'ADMIN':
                unique_room_numbers.add(user.room_number)
        
        for setting in room_settings:
            if setting.room_number != 'ADMIN':
                unique_room_numbers.add(setting.room_number)
        
        print(f"📋 管理対象部屋: {sorted(unique_room_numbers)}")
        
        # 各部屋の設定が正しく存在するかチェック
        for room_num in unique_room_numbers:
            if room_num not in room_csv_settings:
                print(f"⚠️ 部屋{room_num}のCSV設定が見つかりません - デフォルト設定を作成")
                # デフォルト設定を作成
                default_room_setting = RoomSetting(
                    room_number=room_num,
                    max_enabled_unit_number="9999",
                    csv_filename="words.csv"
                )
                db.session.add(default_room_setting)
                room_max_unit_settings[room_num] = "9999"
                room_csv_settings[room_num] = "words.csv"
        
        try:
            db.session.commit()
            print("✅ デフォルト設定作成完了")
        except Exception as e:
            print(f"⚠️ デフォルト設定作成エラー: {e}")
            db.session.rollback()
        
        context = get_template_context()
        
        template_context = {
            'users': users,
            'room_max_unit_settings': room_max_unit_settings,
            'room_csv_settings': room_csv_settings,
            'ROOM_CSV_FOLDER': ROOM_CSV_FOLDER,
            **context
        }
        
        print("✅ 管理者ページ表示準備完了")
        return render_template('admin.html', **template_context)
        
    except Exception as e:
        print(f"❌ 管理者ページエラー: {e}")
        import traceback
        traceback.print_exc()
        return f"Admin Error: {e}", 500

# アプリ情報管理
# app.py の admin_app_info 関数を以下に置き換え

# 緊急デバッグ用（問題が続く場合のみ使用）

@app.route('/admin/app_info', methods=['GET', 'POST'])
def admin_app_info():
    try:
        if not session.get('admin_logged_in'):
            flash('管理者権限がありません。', 'danger')
            return redirect(url_for('login_page'))

        print("=== admin_app_info デバッグ開始 ===")
        
        # データベース接続テスト
        try:
            app_info = AppInfo.query.first()
            print(f"app_info取得結果: {app_info}")
            
            if not app_info:
                print("app_info が存在しません。新規作成します。")
                app_info = AppInfo()
                db.session.add(app_info)
                db.session.commit()
                print("新しいapp_infoを作成しました。")
                
        except Exception as db_error:
            print(f"データベースエラー: {db_error}")
            # フェイルセーフ：デフォルト値でapp_infoオブジェクトを作成
            class MockAppInfo:
                def __init__(self):
                    self.app_name = "世界史単語帳"
                    self.version = "1.0.0"
                    self.last_updated_date = "2025年6月15日"
                    self.update_content = "アプリケーションが開始されました。"
                    self.footer_text = ""
                    self.contact_email = ""
                    self.updated_by = "system"
                    self.updated_at = datetime.now(JST)
                    
            app_info = MockAppInfo()
            print("MockAppInfoを使用します。")
        
        if request.method == 'POST':
            print("POST リクエストを処理中...")
            try:
                app_info.app_name = request.form.get('app_name', '世界史単語帳').strip()
                app_info.version = request.form.get('version', '1.0.0').strip()
                app_info.last_updated_date = request.form.get('last_updated_date', '').strip()
                app_info.update_content = request.form.get('update_content', '').strip()
                app_info.footer_text = request.form.get('footer_text', '').strip()
                app_info.contact_email = request.form.get('contact_email', '').strip()
                
                if hasattr(app_info, 'updated_by'):
                    app_info.updated_by = session.get('username', 'admin')
                    app_info.updated_at = datetime.now(JST)
                    
                    db.session.commit()
                    flash('アプリ情報を更新しました。', 'success')
                else:
                    flash('テストモードのため、実際の保存は行われませんでした。', 'warning')
                    
                return redirect(url_for('admin_app_info'))
                
            except Exception as post_error:
                print(f"POST処理エラー: {post_error}")
                db.session.rollback()
                flash(f'更新エラー: {str(post_error)}', 'danger')
        
        print("テンプレートをレンダリング中...")
        return render_template('admin_app_info.html', app_info=app_info)
        
    except Exception as e:
        print(f"=== 致命的エラー ===")
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()
        
        flash('アプリ情報管理ページでエラーが発生しました。管理者ページに戻ります。', 'danger')
        return redirect(url_for('admin_page'))

@app.route('/admin/app_info/reset', methods=['POST'])
def admin_app_info_reset():
    try:
        if not session.get('admin_logged_in'):
            flash('管理者権限がありません。', 'danger')
            return redirect(url_for('login_page'))

        app_info = AppInfo.get_current_info()
        
        # デフォルト値にリセット
        app_info.app_name = "世界史単語帳"
        app_info.version = "1.0.0"
        app_info.last_updated_date = "2025年6月15日"
        app_info.update_content = "アプリケーションが開始されました。"
        app_info.footer_text = ""
        app_info.contact_email = ""
        app_info.updated_by = session.get('username', 'admin')
        app_info.updated_at = datetime.now(JST)
        
        db.session.commit()
        flash('アプリ情報をデフォルト値にリセットしました。', 'success')
        
        return redirect(url_for('admin_app_info'))
    except Exception as e:
        print(f"Error in admin_app_info_reset: {e}")
        db.session.rollback()
        flash(f'アプリ情報のリセット中にエラーが発生しました: {str(e)}', 'danger')
        return redirect(url_for('admin_app_info'))

# ユーザー管理
@app.route('/admin/add_user', methods=['POST'])
def admin_add_user():
    try:
        if not session.get('admin_logged_in'):
            flash('管理者権限がありません。', 'danger')
            return redirect(url_for('login_page'))

        room_number = request.form.get('room_number')
        room_password = request.form.get('room_password')
        student_id = request.form.get('student_id')
        individual_password = request.form.get('individual_password')
        username = request.form.get('username')

        if not all([room_number, room_password, student_id, individual_password, username]):
            flash('すべての項目を入力してください。', 'danger')
            return redirect(url_for('admin_page'))

        if User.query.filter_by(username=username).first():
            flash('そのアカウント名はすでに存在します。別のアカウント名を使用してください。', 'danger')
            return redirect(url_for('admin_page'))

        new_user = User(room_number=room_number, student_id=student_id, username=username)
        new_user.set_room_password(room_password)
        new_user.set_individual_password(individual_password)
        new_user.problem_history = "{}"
        new_user.incorrect_words = "[]"

        db.session.add(new_user)
        db.session.commit()
        
        if not RoomSetting.query.filter_by(room_number=room_number).first():
            default_room_setting = RoomSetting(room_number=room_number, max_enabled_unit_number="9999", csv_filename="words.csv")
            db.session.add(default_room_setting)
            db.session.commit()
            flash(f'部屋 {room_number} の設定をデフォルトで作成しました。', 'info')

        flash(f'ユーザー {username} を登録しました。', 'success')
        return redirect(url_for('admin_page'))
    except Exception as e:
        print(f"Error in admin_add_user: {e}")
        flash(f'ユーザー追加中にエラーが発生しました: {e}', 'danger')
        return redirect(url_for('admin_page'))

# app.pyに追加するルート（admin_upload_usersの修正版）

@app.route('/admin/upload_users', methods=['POST'])
def admin_upload_users():
    if not session.get('admin_logged_in'):
        flash('管理者権限がありません。', 'danger')
        return redirect(url_for('admin_page'))

    if 'file' not in request.files:
        flash('ファイルが選択されていません。', 'danger')
        return redirect(url_for('admin_page'))

    file = request.files['file']
    if file.filename == '':
        flash('ファイルが選択されていません。', 'danger')
        return redirect(url_for('admin_page'))

    if file and file.filename.endswith('.csv'):
        try:
            # CSVファイルを読み込み
            stream = StringIO(file.stream.read().decode("utf-8"))
            reader = csv.DictReader(stream)
            
            users_added_count = 0
            errors = []
            skipped_existing = 0

            for row_num, row in enumerate(reader, start=2):  # ヘッダー行を考慮して2から開始
                try:
                    # データの取得と検証
                    room_number = row.get('部屋番号', '').strip()
                    room_password = row.get('入室パスワード', '').strip()
                    student_id = row.get('出席番号', '').strip()
                    individual_password = row.get('個別パスワード', '').strip()
                    username = row.get('アカウント名', '').strip()

                    # 必須項目チェック
                    if not all([room_number, room_password, student_id, individual_password, username]):
                        errors.append(f"行{row_num}: 必須項目が不足しています")
                        continue

                    # 既存ユーザーチェック（ユーザー名または部屋番号+出席番号の重複）
                    existing_user = User.query.filter(
                        (User.username == username) | 
                        ((User.room_number == room_number) & (User.student_id == student_id))
                    ).first()
                    
                    if existing_user:
                        if existing_user.username == username:
                            errors.append(f"行{row_num}: アカウント名'{username}'は既に存在します")
                        else:
                            errors.append(f"行{row_num}: 部屋{room_number}の出席番号{student_id}は既に存在します")
                        skipped_existing += 1
                        continue

                    # 新規ユーザー作成
                    new_user = User(
                        room_number=room_number,
                        student_id=student_id,
                        username=username
                    )
                    new_user.set_room_password(room_password)
                    new_user.set_individual_password(individual_password)
                    new_user.problem_history = "{}"
                    new_user.incorrect_words = "[]"
                    new_user.last_login = datetime.now(JST)

                    db.session.add(new_user)
                    users_added_count += 1

                except Exception as e:
                    errors.append(f"行{row_num}: データ処理エラー - {str(e)}")
                    continue

            # データベースにコミット
            try:
                db.session.commit()
                
                # 新しい部屋のデフォルト設定を作成
                added_rooms = set()
                for row in csv.DictReader(StringIO(file.stream.read().decode("utf-8"))):
                    room_num = row.get('部屋番号', '').strip()
                    if room_num and room_num not in added_rooms:
                        if not RoomSetting.query.filter_by(room_number=room_num).first():
                            default_room_setting = RoomSetting(
                                room_number=room_num,
                                max_enabled_unit_number="9999",
                                csv_filename="words.csv"
                            )
                            db.session.add(default_room_setting)
                            added_rooms.add(room_num)
                
                db.session.commit()
                
                # 結果メッセージ
                if users_added_count > 0:
                    flash(f'✅ {users_added_count}人のユーザーを追加しました。', 'success')
                
                if skipped_existing > 0:
                    flash(f'⚠️ {skipped_existing}人のユーザーは既に存在するため、スキップされました。', 'warning')
                    
                if errors:
                    error_summary = f"❌ {len(errors)}件のエラーが発生しました。"
                    if len(errors) <= 5:
                        error_summary += " " + " / ".join(errors)
                    else:
                        error_summary += f" 最初の5件: {' / '.join(errors[:5])}"
                    flash(error_summary, 'danger')
                    
            except Exception as e:
                db.session.rollback()
                flash(f'データベースエラーが発生しました: {str(e)}', 'danger')
                
        except UnicodeDecodeError:
            flash('CSVファイルの文字エンコーディングを確認してください（UTF-8である必要があります）。', 'danger')
        except Exception as e:
            flash(f'CSVファイルの処理中にエラーが発生しました: {str(e)}', 'danger')
    else:
        flash('CSVファイルを選択してください。', 'danger')

    return redirect(url_for('admin_page'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def admin_delete_user(user_id):
    try:
        if not session.get('admin_logged_in'):
            flash('管理者権限がありません。', 'danger')
            return redirect(url_for('login_page'))

        user_to_delete = User.query.get(user_id)
        if not user_to_delete:
            flash('指定されたユーザーが見つかりません。', 'danger')
            return redirect(url_for('admin_page'))

        db.session.delete(user_to_delete)
        db.session.commit()
        flash(f'ユーザー "{user_to_delete.username}" (部屋番号: {user_to_delete.room_number}, 出席番号: {user_to_delete.student_id}) を削除しました。', 'success')
        
        return redirect(url_for('admin_page'))
    except Exception as e:
        print(f"Error in admin_delete_user: {e}")
        db.session.rollback()
        flash(f'ユーザー削除中にエラーが発生しました: {e}', 'danger')
        return redirect(url_for('admin_page'))

# 部屋設定管理
@app.route('/admin/get_room_setting', methods=['POST'])
def admin_get_room_setting():
    """部屋設定を取得するAPI"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify(status='error', message='管理者権限がありません。'), 403

        data = request.get_json()
        room_number = data.get('room_number')

        if not room_number:
            return jsonify(status='error', message='部屋番号が指定されていません。'), 400

        print(f"🔍 部屋設定取得: {room_number}")

        # 部屋設定を取得
        room_setting = RoomSetting.query.filter_by(room_number=room_number).first()

        if room_setting:
            result = {
                'status': 'success',
                'room_number': room_setting.room_number,
                'max_enabled_unit_number': room_setting.max_enabled_unit_number,
                'csv_filename': room_setting.csv_filename
            }
            print(f"✅ 部屋設定取得成功: {room_setting.csv_filename}")
        else:
            # デフォルト設定を返す
            result = {
                'status': 'success',
                'room_number': room_number,
                'max_enabled_unit_number': '9999',
                'csv_filename': 'words.csv'
            }
            print(f"📄 デフォルト設定を返却: {room_number}")

        return jsonify(result)
        
    except Exception as e:
        print(f"❌ 部屋設定取得エラー: {e}")
        return jsonify(status='error', message=str(e)), 500

@app.route('/admin/update_room_unit_setting', methods=['POST'])
def admin_update_room_unit_setting():
    try:
        if not session.get('admin_logged_in'):
            return jsonify(status='error', message='管理者権限がありません。'), 403

        data = request.get_json()
        room_number = data.get('room_number')
        max_unit = data.get('max_unit')

        if max_unit is None or max_unit == '':
            max_unit_to_save = "9999"
        else:
            max_unit_to_save = str(max_unit)

        if not room_number:
            return jsonify(status='error', message='部屋番号が指定されていません。'), 400

        room_setting = RoomSetting.query.filter_by(room_number=room_number).first()

        if room_setting:
            room_setting.max_enabled_unit_number = max_unit_to_save
        else:
            new_room_setting = RoomSetting(room_number=room_number, max_enabled_unit_number=max_unit_to_save, csv_filename="words.csv")
            db.session.add(new_room_setting)
        
        db.session.commit()
        return jsonify(status='success', message=f'部屋 {room_number} の単元設定を {max_unit_to_save} に更新しました。')
    except Exception as e:
        print(f"Error in admin_update_room_unit_setting: {e}")
        return jsonify(status='error', message=str(e)), 500

@app.route('/admin/update_room_csv_setting', methods=['POST'])
def admin_update_room_csv_setting():
    try:
        if not session.get('admin_logged_in'):
            return jsonify(status='error', message='管理者権限がありません。'), 403

        data = request.get_json()
        room_number = data.get('room_number')
        csv_filename = data.get('csv_filename')

        print(f"🔧 CSV設定更新リクエスト: 部屋{room_number} -> {csv_filename}")

        if not room_number:
            return jsonify(status='error', message='部屋番号が指定されていません。'), 400

        if not csv_filename:
            csv_filename = "words.csv"

        # ファイルの存在確認（words.csv以外の場合）
        if csv_filename != "words.csv":
            file_path = os.path.join(ROOM_CSV_FOLDER, csv_filename)
            if not os.path.exists(file_path):
                print(f"⚠️ 指定されたCSVファイルが見つかりません: {file_path}")
                return jsonify(
                    status='error', 
                    message=f'指定されたCSVファイル "{csv_filename}" が見つかりません。'
                ), 400

        # 部屋設定を取得または作成
        room_setting = RoomSetting.query.filter_by(room_number=room_number).first()

        if room_setting:
            # 既存設定を更新
            old_filename = room_setting.csv_filename
            room_setting.csv_filename = csv_filename
            room_setting.updated_at = datetime.now(JST)
            print(f"📝 既存設定更新: {old_filename} -> {csv_filename}")
        else:
            # 新規設定を作成
            room_setting = RoomSetting(
                room_number=room_number,
                max_enabled_unit_number="9999",
                csv_filename=csv_filename
            )
            db.session.add(room_setting)
            print(f"➕ 新規設定作成: 部屋{room_number} with {csv_filename}")
        
        # データベースにコミット
        db.session.commit()
        
        # 保存後の確認
        saved_setting = RoomSetting.query.filter_by(room_number=room_number).first()
        if saved_setting:
            actual_filename = saved_setting.csv_filename
            print(f"✅ 保存確認成功: 部屋{room_number} = {actual_filename}")
            
            if actual_filename != csv_filename:
                print(f"⚠️ 保存値が異なります: 期待値={csv_filename}, 実際値={actual_filename}")
                return jsonify(
                    status='error', 
                    message=f'設定の保存に失敗しました。期待値と実際値が異なります。'
                ), 500
        else:
            print(f"❌ 保存確認失敗: 部屋{room_number}の設定が見つかりません")
            return jsonify(status='error', message='設定の保存確認に失敗しました。'), 500
        
        return jsonify(
            status='success', 
            message=f'部屋 {room_number} のCSVファイル設定を {csv_filename} に更新しました。',
            room_number=room_number,
            csv_filename=actual_filename
        )
        
    except Exception as e:
        print(f"❌ CSV設定更新エラー: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify(status='error', message=str(e)), 500
    
def verify_room_settings():
    """起動時に部屋設定の整合性をチェック"""
    print("\n🔍 部屋設定の整合性確認中...")
    
    try:
        settings = RoomSetting.query.all()
        print(f"📋 登録済み部屋設定: {len(settings)}件")
        
        for setting in settings:
            csv_path = setting.csv_filename
            if csv_path != "words.csv":
                full_path = os.path.join(ROOM_CSV_FOLDER, csv_path)
                if not os.path.exists(full_path):
                    print(f"⚠️ 部屋{setting.room_number}: {csv_path} が見つからない -> デフォルトに変更")
                    setting.csv_filename = "words.csv"
                else:
                    print(f"✅ 部屋{setting.room_number}: {csv_path} 確認OK")
            else:
                print(f"📄 部屋{setting.room_number}: デフォルト使用")
        
        db.session.commit()
        print("✅ 部屋設定確認完了\n")
        
    except Exception as e:
        print(f"❌ 部屋設定確認エラー: {e}\n")

@app.route('/admin/delete_room_setting/<string:room_number>', methods=['POST'])
def admin_delete_room_setting(room_number):
    try:
        if not session.get('admin_logged_in'):
            flash('管理者権限がありません。', 'danger')
            return redirect(url_for('login_page'))

        room_setting_to_delete = RoomSetting.query.filter_by(room_number=room_number).first()
        if not room_setting_to_delete:
            flash(f'部屋 "{room_number}" の設定が見つかりません。', 'danger')
            return redirect(url_for('admin_page'))

        db.session.delete(room_setting_to_delete)
        db.session.commit()
        flash(f'部屋 "{room_number}" の設定を削除しました。この部屋のユーザーはデフォルト設定になります。', 'success')
        
        return redirect(url_for('admin_page'))
    except Exception as e:
        print(f"Error in admin_delete_room_setting: {e}")
        db.session.rollback()
        flash(f'部屋設定削除中にエラーが発生しました: {e}', 'danger')
        return redirect(url_for('admin_page'))

# CSV管理
# app.pyのadmin_upload_room_csvルートをデバッグ版に置き換え

@app.route('/admin/upload_room_csv', methods=['POST'])
def admin_upload_room_csv():
    try:
        print("🔍 CSV アップロード開始...")
        
        if not session.get('admin_logged_in'):
            flash('管理者権限がありません。', 'danger')
            return redirect(url_for('admin_page'))

        if 'file' not in request.files:
            print("❌ ファイルが選択されていません")
            flash('ファイルが選択されていません。', 'danger')
            return redirect(url_for('admin_page'))

        file = request.files['file']
        print(f"📁 受信ファイル: {file.filename}")

        if file.filename == '':
            print("❌ ファイル名が空です")
            flash('ファイルが選択されていません。', 'danger')
            return redirect(url_for('admin_page'))

        if file and file.filename.endswith('.csv'):
            # 元のファイル名をそのまま使用（セキュリティ対応）
            original_filename = file.filename
            filename = secure_filename(original_filename)
            
            # ROOM_CSV_FOLDERの存在確認と作成
            if not os.path.exists(ROOM_CSV_FOLDER):
                print(f"📁 フォルダを作成: {ROOM_CSV_FOLDER}")
                os.makedirs(ROOM_CSV_FOLDER)
            
            file_path = os.path.join(ROOM_CSV_FOLDER, filename)
            print(f"💾 保存先: {file_path}")
            
            try:
                # ファイル保存
                file.save(file_path)
                print(f"✅ ファイル保存成功: {file_path}")
                
                # ファイルの存在確認
                if not os.path.exists(file_path):
                    print(f"❌ 保存後にファイルが見つかりません: {file_path}")
                    flash('ファイルの保存に失敗しました。', 'danger')
                    return redirect(url_for('admin_page'))
                
                # ファイルサイズ確認
                file_size = os.path.getsize(file_path)
                print(f"📊 ファイルサイズ: {file_size} bytes")
                
                if file_size == 0:
                    print("❌ ファイルサイズが0です")
                    os.remove(file_path)
                    flash('アップロードされたファイルが空です。', 'danger')
                    return redirect(url_for('admin_page'))
                
                # CSVファイルの形式を検証
                word_count = 0
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        print(f"📄 ファイル内容の最初の100文字: {content[:100]}")
                        
                    with open(file_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        required_columns = ['chapter', 'number', 'category', 'question', 'answer', 'enabled']
                        
                        print(f"📋 検出されたヘッダー: {reader.fieldnames}")
                        
                        if not reader.fieldnames:
                            os.remove(file_path)
                            flash('CSVファイルにヘッダー行がありません。', 'danger')
                            return redirect(url_for('admin_page'))
                        
                        missing_cols = [col for col in required_columns if col not in reader.fieldnames]
                        if missing_cols:
                            os.remove(file_path)
                            flash(f'CSVファイルに必要な列が不足しています: {", ".join(missing_cols)}', 'danger')
                            print(f"❌ 不足している列: {missing_cols}")
                            return redirect(url_for('admin_page'))
                        
                        # 全行をチェックして単語数をカウント
                        for i, row in enumerate(reader):
                            # 必須データの存在確認
                            missing_data = []
                            for col in ['chapter', 'number', 'question', 'answer']:
                                if not row.get(col, '').strip():
                                    missing_data.append(col)
                            
                            if missing_data:
                                os.remove(file_path)
                                flash(f'CSVファイルの{i+2}行目に必須データが不足しています: {", ".join(missing_data)}', 'danger')
                                print(f"❌ {i+2}行目のデータ不足: {missing_data}")
                                return redirect(url_for('admin_page'))
                            word_count += 1
                        
                        print(f"📊 検証完了: {word_count}問")
                        
                        if word_count == 0:
                            os.remove(file_path)
                            flash('CSVファイルにデータが含まれていません。', 'danger')
                            return redirect(url_for('admin_page'))
                        
                except Exception as csv_error:
                    print(f"❌ CSV読み込みエラー: {csv_error}")
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    flash(f'CSVファイルの読み込み中にエラーが発生しました: {str(csv_error)}', 'danger')
                    return redirect(url_for('admin_page'))
                
                # RoomCsvFileテーブルに記録（存在する場合のみ）
                try:
                    # テーブルの存在確認
                    inspector = inspect(db.engine)
                    if inspector.has_table('room_csv_file'):
                        print("📝 room_csv_fileテーブルに記録中...")
                        
                        # 既存のファイル記録があれば更新、なければ新規作成
                        csv_file_record = RoomCsvFile.query.filter_by(filename=filename).first()
                        if csv_file_record:
                            print(f"🔄 既存レコード更新: {filename}")
                            csv_file_record.original_filename = original_filename
                            csv_file_record.file_size = file_size
                            csv_file_record.word_count = word_count
                            csv_file_record.upload_date = datetime.now(JST)
                        else:
                            print(f"➕ 新規レコード作成: {filename}")
                            csv_file_record = RoomCsvFile(
                                filename=filename,
                                original_filename=original_filename,
                                file_size=file_size,
                                word_count=word_count
                            )
                            db.session.add(csv_file_record)
                        
                        db.session.commit()
                        print("✅ データベース記録完了")
                    else:
                        print("⚠️ room_csv_fileテーブルが存在しません（ファイルのみ保存）")
                        
                except Exception as db_error:
                    print(f"⚠️ データベース記録エラー（ファイルは保存済み）: {db_error}")
                    db.session.rollback()
                
                # 最終確認
                final_check_path = os.path.join(ROOM_CSV_FOLDER, filename)
                if os.path.exists(final_check_path):
                    final_size = os.path.getsize(final_check_path)
                    print(f"✅ 最終確認成功: {final_check_path} ({final_size} bytes)")
                    
                    # 成功メッセージ
                    file_size_kb = round(file_size / 1024, 1)
                    flash(f'✅ CSVファイル "{filename}" をアップロードしました', 'success')
                    flash(f'📊 ファイル情報: {word_count}問, {file_size_kb}KB', 'info')
                    flash('💡 各部屋の設定で、このファイルを使用するように設定してください。', 'info')
                else:
                    print(f"❌ 最終確認失敗: ファイルが見つかりません")
                    flash('ファイルのアップロードに失敗しました。', 'danger')
                
            except Exception as save_error:
                print(f"❌ ファイル保存エラー: {save_error}")
                if os.path.exists(file_path):
                    os.remove(file_path)
                flash(f'ファイルの保存中にエラーが発生しました: {str(save_error)}', 'danger')
        else:
            print("❌ CSVファイルではありません")
            flash('CSVファイルを選択してください。', 'danger')

        return redirect(url_for('admin_page'))
    except Exception as e:
        print(f"❌ 全体エラー: {e}")
        import traceback
        traceback.print_exc()
        flash(f'ファイルアップロード中にエラーが発生しました: {e}', 'danger')
        return redirect(url_for('admin_page'))

# admin_list_room_csv_filesルートもデバッグ版に修正
@app.route('/admin/list_room_csv_files')
def admin_list_room_csv_files():
    try:
        print("🔍 CSVファイル一覧取得開始...")
        
        if not session.get('admin_logged_in'):
            return jsonify(status='error', message='管理者権限がありません。'), 403

        # フォルダの存在確認
        if not os.path.exists(ROOM_CSV_FOLDER):
            print(f"📁 フォルダが存在しません: {ROOM_CSV_FOLDER}")
            return jsonify(status='success', files=[])
        
        print(f"📁 フォルダパス: {ROOM_CSV_FOLDER}")
        
        csv_files = []
        all_files = os.listdir(ROOM_CSV_FOLDER)
        print(f"📋 フォルダ内の全ファイル: {all_files}")
        
        for filename in all_files:
            if filename.endswith('.csv'):
                file_path = os.path.join(ROOM_CSV_FOLDER, filename)
                
                try:
                    file_size = os.path.getsize(file_path)
                    modified_time = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
                    
                    # 単語数をカウント
                    word_count = 0
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            reader = csv.DictReader(f)
                            word_count = sum(1 for row in reader)
                    except Exception as count_error:
                        print(f"⚠️ {filename}の単語数カウントエラー: {count_error}")
                        word_count = 0
                    
                    csv_files.append({
                        'filename': filename,
                        'size': file_size,
                        'modified': modified_time,
                        'word_count': word_count
                    })
                    
                    print(f"✅ ファイル情報取得: {filename} ({word_count}問, {file_size}bytes)")
                    
                except Exception as file_error:
                    print(f"⚠️ {filename}の情報取得エラー: {file_error}")
                    continue
        
        print(f"📊 検出されたCSVファイル数: {len(csv_files)}")
        return jsonify(status='success', files=csv_files)
        
    except Exception as e:
        print(f"❌ CSVファイル一覧取得エラー: {e}")
        import traceback
        traceback.print_exc()
        return jsonify(status='error', message=str(e)), 500

@app.route('/admin/delete_room_csv/<filename>', methods=['POST'])
def admin_delete_room_csv(filename):
    try:
        if not session.get('admin_logged_in'):
            flash('管理者権限がありません。', 'danger')
            return redirect(url_for('admin_page'))

        file_path = os.path.join(ROOM_CSV_FOLDER, secure_filename(filename))
        
        if os.path.exists(file_path):
            os.remove(file_path)
            
            # このファイルを使用している部屋設定をデフォルトに戻す
            room_settings = RoomSetting.query.filter_by(csv_filename=filename).all()
            for setting in room_settings:
                setting.csv_filename = "words.csv"
            db.session.commit()
            
            flash(f'CSVファイル "{filename}" を削除し、関連する部屋設定をデフォルトに戻しました。', 'success')
        else:
            flash('指定されたファイルが見つかりません。', 'danger')

        return redirect(url_for('admin_page'))
    except Exception as e:
        print(f"Error in admin_delete_room_csv: {e}")
        flash(f'ファイル削除中にエラーが発生しました: {e}', 'danger')
        return redirect(url_for('admin_page'))

# データエクスポート関数
@app.route('/admin/download_users_csv')
def download_users_csv():
    if not session.get('admin_logged_in'):
        flash('管理者権限がありません。', 'danger')
        return redirect(url_for('login_page'))

    users = User.query.all()
    si = StringIO()
    cw = csv.writer(si)

    cw.writerow(['部屋番号', '入室パスワードハッシュ', '出席番号', 'アカウント名', '個別パスワードハッシュ'])

    for user in users:
        cw.writerow([
            user.room_number,
            user._room_password_hash,
            user.student_id,
            user.username,
            user._individual_password_hash
        ])
    
    output = si.getvalue()
    response = Response(output, mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=users_data.csv"
    return response

@app.route('/admin/download_room_settings_csv')
def download_room_settings_csv():
    if not session.get('admin_logged_in'):
        flash('管理者権限がありません。', 'danger')
        return redirect(url_for('login_page'))

    room_settings = RoomSetting.query.all()
    si = StringIO()
    cw = csv.writer(si)

    cw.writerow(['部屋番号', '有効な最大単元番号', 'CSVファイル名'])

    for setting in room_settings:
        cw.writerow([setting.room_number, setting.max_enabled_unit_number, setting.csv_filename])
    
    output = si.getvalue()
    response = Response(output, mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=room_settings_data.csv"
    return response

@app.route('/admin/download_users_template_csv')
def download_users_template_csv():
    if not session.get('admin_logged_in'):
        flash('管理者権限がありません。', 'danger')
        return redirect(url_for('login_page'))

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['部屋番号', '入室パスワード', '出席番号', '個別パスワード', 'アカウント名'])
    
    output = si.getvalue()
    response = Response(output, mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=users_template.csv"
    return response

@app.route('/admin/download_room_settings_template_csv')
def download_room_settings_template_csv():
    if not session.get('admin_logged_in'):
        flash('管理者権限がありません。', 'danger')
        return redirect(url_for('login_page'))

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['部屋番号', '有効な最大単元番号', 'CSVファイル名'])
    
    output = si.getvalue()
    response = Response(output, mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=room_settings_template.csv"
    return response

# ====================================================================
# デバッグ・管理機能
# ====================================================================
@app.route('/admin/debug_progress')
def admin_debug_progress():
    """進捗データの整合性を確認するデバッグページ"""
    try:
        if not session.get('admin_logged_in'):
            flash('管理者権限がありません。', 'danger')
            return redirect(url_for('login_page'))
        
        debug_info = []
        users = User.query.all()
        
        for user in users:
            if user.username == 'admin':
                continue
                
            # 部屋ごとの単語データを取得
            word_data = load_word_data_for_room(user.room_number)
            user_history = user.get_problem_history()
            user_incorrect = user.get_incorrect_words()
            
            matched_problems = 0
            unmatched_problems = []
            
            for problem_id in user_history.keys():
                matched_word = next((word for word in word_data if get_problem_id(word) == problem_id), None)
                if matched_word:
                    matched_problems += 1
                else:
                    unmatched_problems.append(problem_id)
            
            debug_info.append({
                'username': user.username,
                'room_number': user.room_number,
                'total_history_entries': len(user_history),
                'matched_problems': matched_problems,
                'unmatched_problems': len(unmatched_problems),
                'unmatched_list': unmatched_problems[:5],
                'incorrect_words_count': len(user_incorrect)
            })
        
        # デフォルトの単語データを使用してテスト
        default_word_data = load_default_word_data()
        test_words = default_word_data[:3]
        id_test_results = []
        
        for word in test_words:
            generated_id = get_problem_id(word)
            id_test_results.append({
                'question': word['question'][:50] + '...' if len(word['question']) > 50 else word['question'],
                'chapter': word['chapter'],
                'number': word['number'],
                'generated_id': generated_id
            })
        
        # ★ 修正: 共通コンテキストを取得（app_infoも含む）
        context = get_template_context()
        
        return render_template('admin_debug.html', 
                             debug_info=debug_info, 
                             id_test_results=id_test_results,
                             **context)  # app_infoは既にcontextに含まれている
    except Exception as e:
        print(f"Error in admin_debug_progress: {e}")
        import traceback
        traceback.print_exc()
        return f"Debug Error: {e}", 500



# 1. 共通のapp_info取得関数を定義
def get_template_context():
    """全テンプレートで共通に使用するコンテキストを取得"""
    try:
        app_info = AppInfo.get_current_info()
        return {'app_info': app_info}
    except Exception as e:
        print(f"Error getting app_info: {e}")
        return {'app_info': None}



# ====================================================================
# エラーハンドラー
# ====================================================================

@app.errorhandler(500)
def internal_error(error):
    print(f"500 Error: {error}")
    db.session.rollback()
    return "Internal Server Error - Please check the logs", 500

@app.errorhandler(404)
def not_found_error(error):
    return "Page Not Found", 404

# app.pyに以下のデバッグ用ルートを追加

@app.route('/debug/user_data')
def debug_user_data():
    """ユーザーの学習データをデバッグ表示"""
    if 'user_id' not in session:
        return jsonify(error='ログインが必要です'), 401
    
    current_user = User.query.get(session['user_id'])
    if not current_user:
        return jsonify(error='ユーザーが見つかりません'), 404
    
    # ユーザーの生データを取得
    user_problem_history = current_user.get_problem_history()
    user_incorrect_words = current_user.get_incorrect_words()
    
    # 部屋ごとの単語データを取得
    word_data = load_word_data_for_room(current_user.room_number)
    
    # 問題IDのマッピングをチェック
    id_mapping = {}
    unmatched_ids = []
    
    for problem_id in user_problem_history.keys():
        matched_word = None
        for word in word_data:
            generated_id = get_problem_id(word)
            if generated_id == problem_id:
                matched_word = word
                break
        
        if matched_word:
            id_mapping[problem_id] = {
                'question': matched_word['question'],
                'answer': matched_word['answer'],
                'chapter': matched_word['chapter'],
                'number': matched_word['number']
            }
        else:
            unmatched_ids.append(problem_id)
    
    debug_info = {
        'user_info': {
            'username': current_user.username,
            'room_number': current_user.room_number,
            'student_id': current_user.student_id
        },
        'raw_problem_history': user_problem_history,
        'raw_incorrect_words': user_incorrect_words,
        'total_word_data_count': len(word_data),
        'problem_history_count': len(user_problem_history),
        'incorrect_words_count': len(user_incorrect_words),
        'matched_problems': len(id_mapping),
        'unmatched_problems': len(unmatched_ids),
        'id_mapping': id_mapping,
        'unmatched_ids': unmatched_ids[:10],  # 最初の10件のみ表示
        'sample_word_ids': [
            {
                'word': word,
                'generated_id': get_problem_id(word)
            }
            for word in word_data[:5]  # 最初の5件のサンプル
        ]
    }
    
    return jsonify(debug_info)

@app.route('/debug/fix_problem_ids', methods=['POST'])
def debug_fix_problem_ids():
    """問題IDの不整合を修正"""
    if 'user_id' not in session:
        return jsonify(error='ログインが必要です'), 401
    
    current_user = User.query.get(session['user_id'])
    if not current_user:
        return jsonify(error='ユーザーが見つかりません'), 404
    
    # 古い形式のIDから新しい形式のIDに変換
    def generate_old_problem_id(word):
        """推測される古いID生成方法"""
        question_for_id = str(word['question']).strip()
        cleaned_question = re.sub(r'[^a-zA-Z0-9]', '', question_for_id).lower()
        chapter_str = str(word['chapter'])
        number_str = str(word['number'])
        return f"{chapter_str}-{number_str}-{cleaned_question}"
    
    word_data = load_word_data_for_room(current_user.room_number)
    user_problem_history = current_user.get_problem_history()
    user_incorrect_words = current_user.get_incorrect_words()
    
    # IDマッピングを作成
    old_to_new_mapping = {}
    for word in word_data:
        old_id = generate_old_problem_id(word)
        new_id = get_problem_id(word)
        old_to_new_mapping[old_id] = new_id
    
    # 学習履歴を変換
    new_problem_history = {}
    converted_count = 0
    
    for old_id, history in user_problem_history.items():
        if old_id in old_to_new_mapping:
            new_id = old_to_new_mapping[old_id]
            new_problem_history[new_id] = history
            converted_count += 1
        else:
            # 既に新しい形式の場合はそのまま保持
            new_problem_history[old_id] = history
    
    # 苦手問題リストを変換
    new_incorrect_words = []
    converted_incorrect_count = 0
    
    for old_id in user_incorrect_words:
        if old_id in old_to_new_mapping:
            new_id = old_to_new_mapping[old_id]
            if new_id not in new_incorrect_words:
                new_incorrect_words.append(new_id)
                converted_incorrect_count += 1
        else:
            # 既に新しい形式の場合はそのまま保持
            if old_id not in new_incorrect_words:
                new_incorrect_words.append(old_id)
    
    # データベースを更新
    current_user.set_problem_history(new_problem_history)
    current_user.set_incorrect_words(new_incorrect_words)
    
    try:
        db.session.commit()
        return jsonify({
            'status': 'success',
            'converted_history_count': converted_count,
            'converted_incorrect_count': converted_incorrect_count,
            'total_history_count': len(new_problem_history),
            'total_incorrect_count': len(new_incorrect_words)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500

# app.py に追加する構文エラー修正版

@app.route('/debug/smart_id_fix', methods=['POST'])
def debug_smart_id_fix():
    """既存の学習履歴IDを分析して、問題との照合を行う"""
    if 'user_id' not in session:
        return jsonify({'error': 'ログインが必要です'}), 401
    
    current_user = User.query.get(session['user_id'])
    if not current_user:
        return jsonify({'error': 'ユーザーが見つかりません'}), 404
    
    try:
        word_data = load_word_data_for_room(current_user.room_number)
        old_history = current_user.get_problem_history()
        old_incorrect = current_user.get_incorrect_words()
        
        print(f"\n=== スマートID修正開始 ({current_user.username}) ===")
        print(f"既存履歴: {len(old_history)}個")
        print(f"単語データ: {len(word_data)}個")
        
        # 既存のIDを分析
        existing_ids = list(old_history.keys())
        if existing_ids:
            print(f"既存IDサンプル: {existing_ids[:3]}")
        
        new_history = {}
        matched_count = 0
        
        # 各既存IDに対して最適な問題を見つける
        for existing_id, history_data in old_history.items():
            best_match = None
            best_score = 0
            
            # IDから情報を抽出
            parts = existing_id.split('-')
            if len(parts) >= 3:
                try:
                    id_chapter = int(parts[0])
                    id_number = int(parts[1]) 
                    id_text = '-'.join(parts[2:])  # 残りの部分
                    
                    # 対応する問題を探す
                    for word in word_data:
                        score = 0
                        
                        # 章と単元が一致するか
                        word_chapter = int(str(word['chapter']))
                        word_number = int(str(word['number']))
                        
                        if word_chapter == id_chapter and word_number == id_number:
                            score += 100  # 完全一致は高スコア
                        elif word_chapter == id_chapter:
                            score += 50   # 章のみ一致
                        
                        # 問題文の類似度チェック
                        question_text = str(word['question'])
                        question_clean = ''.join(c for c in question_text if c.isalnum())
                        id_text_clean = ''.join(c for c in id_text if c.isalnum())
                        
                        # 問題文の最初の部分が含まれているかチェック
                        if len(question_clean) > 0 and len(id_text_clean) > 0:
                            if id_text_clean in question_clean or question_clean[:20] in id_text_clean:
                                score += 30
                        
                        if score > best_score:
                            best_score = score
                            best_match = word
                
                    # f-stringを使わない修正版（該当部分のみ）

                    # 章と単元が一致する場合のみマッチとして採用
                    if best_match and best_score >= 100:
                        # 新しいIDを統一方式で生成
                        chapter_str = str(best_match['chapter']).zfill(3)
                        number_str = str(best_match['number']).zfill(3)
                        question_text = str(best_match['question'])
                        answer_text = str(best_match['answer'])
                        
                        # 問題文と答えから英数字のみ抽出
                        question_clean = ''.join(c for c in question_text[:15] if c.isalnum())
                        answer_clean = ''.join(c for c in answer_text[:10] if c.isalnum())
                        
                        # 統一フォーマット（f-stringを使わない）
                        new_id = chapter_str + '-' + number_str + '-' + question_clean + '-' + answer_clean
                        new_history[new_id] = history_data
                        matched_count += 1
                        
                        match_info = '章' + str(best_match['chapter']) + '単元' + str(best_match['number'])
                        existing_id_short = existing_id[:30] if len(existing_id) > 30 else existing_id
                        print('  マッチ: ' + existing_id_short + '... -> ' + match_info)
                
                except (ValueError, KeyError) as e:
                    print(f"  ID解析エラー: {existing_id} - {str(e)}")
                    continue
        
        # 苦手問題リストも更新
        new_incorrect = []
        for new_id, history in new_history.items():
            incorrect_attempts = history.get('incorrect_attempts', 0)
            correct_streak = history.get('correct_streak', 0)
            
            if incorrect_attempts > 0 and correct_streak < 2:
                new_incorrect.append(new_id)
        
        # 結果をデータベースに保存
        current_user.set_problem_history(new_history)
        current_user.set_incorrect_words(new_incorrect)
        db.session.commit()
        
        print(f"マッチした履歴: {matched_count}個")
        print(f"新しい苦手問題: {len(new_incorrect)}個")
        print("=== スマートID修正完了 ===\n")
        
        return jsonify({
            'status': 'success',
            'old_history_count': len(old_history),
            'matched_count': matched_count,
            'new_history_count': len(new_history),
            'new_incorrect_count': len(new_incorrect),
            'message': f'{matched_count}個の履歴をマッチングしました'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"スマート修正エラー: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# app.py に追加する修正用ルート

@app.route('/debug/force_fix_user_data', methods=['POST'])
def debug_force_fix_user_data():
    """強制的にユーザーデータを修正"""
    if 'user_id' not in session:
        return jsonify(error='ログインが必要です'), 401
    
    current_user = User.query.get(session['user_id'])
    if not current_user:
        return jsonify(error='ユーザーが見つかりません'), 404
    
    try:
        # 部屋の単語データを取得
        word_data = load_word_data_for_room(current_user.room_number)
        user_history = current_user.get_problem_history()
        
        print(f"\n=== 強制修正開始 ({current_user.username}) ===")
        print(f"現在の履歴数: {len(user_history)}")
        
        # 新しい問題ID形式で履歴を再構築
        new_history = {}
        fixed_count = 0
        
        for word in word_data:
            # 新しいID生成
            new_id = get_problem_id(word)
            
            # 既存の履歴から対応する項目を探す
            found_history = None
            
            # 1. 完全一致を探す
            if new_id in user_history:
                found_history = user_history[new_id]
            else:
                # 2. 古い形式のIDを推測して探す
                old_id_patterns = [
                    f"{word['chapter']}-{word['number']}-{word['question'][:10].replace(' ', '').lower()}",
                    f"{word['chapter']}-{word['number']}-{word['answer'][:10].replace(' ', '').lower()}",
                ]
                
                for old_pattern in old_id_patterns:
                    if old_pattern in user_history:
                        found_history = user_history[old_pattern]
                        print(f"履歴発見: {old_pattern} -> {new_id}")
                        break
            
            if found_history:
                new_history[new_id] = found_history
                fixed_count += 1
        
        print(f"修正された履歴数: {fixed_count}")
        
        # 苦手問題リストも同様に修正
        user_incorrect = current_user.get_incorrect_words()
        new_incorrect = []
        
        for word in word_data:
            new_id = get_problem_id(word)
            if new_id in new_history:
                history = new_history[new_id]
                # 苦手問題の条件をチェック
                if (history.get('incorrect_attempts', 0) > 0 and 
                    history.get('correct_streak', 0) < 2):
                    if new_id not in new_incorrect:
                        new_incorrect.append(new_id)
        
        print(f"修正された苦手問題数: {len(new_incorrect)}")
        
        # データベースに保存
        current_user.set_problem_history(new_history)
        current_user.set_incorrect_words(new_incorrect)
        db.session.commit()
        
        print("=== 強制修正完了 ===\n")
        
        return jsonify({
            'status': 'success',
            'fixed_history_count': fixed_count,
            'total_history_count': len(new_history),
            'fixed_incorrect_count': len(new_incorrect),
            'message': 'ユーザーデータを強制修正しました'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"強制修正エラー: {e}")
        return jsonify(error=str(e)), 500
    
# ====================================================================
# アプリケーション起動
# ====================================================================

# ===== メイン起動処理の修正 =====
if __name__ == '__main__':
    try:
        # 環境設定
        print_render_recommendations()
        
        # PostgreSQL設定（該当する場合）
        is_postgres = configure_production_database()
        
        # データベース初期化
        create_tables_and_admin_user()
        
        # 部屋設定確認
        verify_room_settings()
        
        # データ永続化確認
        if not check_data_persistence():
            print("⚠️ データ永続化に問題がある可能性があります")
        
        # サーバー起動
        port = int(os.environ.get('PORT', 5001))
        debug_mode = os.environ.get('RENDER') != 'true'  # Render環境ではdebug=False
        
        print(f"🌐 サーバーを起動します: http://0.0.0.0:{port}")
        print(f"🔧 デバッグモード: {debug_mode}")
        
        app.run(host='0.0.0.0', port=port, debug=debug_mode)
        
    except Exception as e:
        print(f"💥 アプリケーション起動失敗: {e}")
        import traceback
        traceback.print_exc()