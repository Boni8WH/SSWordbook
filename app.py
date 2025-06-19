import os
import json
import csv
import re
from io import StringIO
from datetime import datetime
import pytz
import secrets
import string
from datetime import datetime, timedelta
from flask_mail import Mail, Message
import hashlib

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import inspect, text

# 日本時間のタイムゾーンオブジェクトを作成
JST = pytz.timezone('Asia/Tokyo')

# ===== Flask アプリケーション初期化 =====
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here_please_change_this_in_production'
basedir = os.path.abspath(os.path.dirname(__file__))

# ===== PostgreSQL設定（修正版） =====
def configure_production_database():
    """本番環境用のデータベース設定（修正版）"""
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
        print(f"✅ PostgreSQL接続設定完了")
        return True
    else:
        print("📄 ローカル環境用SQLite設定")
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'quiz_data.db')
        return False

# PostgreSQL設定の適用
is_postgres = configure_production_database()

# ===== その他の設定 =====
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = 3600 * 24 * 7
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', '587'))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME'])

# Mail初期化
mail = Mail(app)

# データベース初期化
db = SQLAlchemy()
db.init_app(app)

# CSV一時保存用フォルダ
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

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
    username = db.Column(db.String(80), nullable=False)
    room_number = db.Column(db.String(50), nullable=False)
    _room_password_hash = db.Column(db.String(128))
    student_id = db.Column(db.String(50), nullable=False)
    _individual_password_hash = db.Column(db.String(128))
    problem_history = db.Column(db.Text)
    incorrect_words = db.Column(db.Text)
    last_login = db.Column(db.DateTime, default=lambda: datetime.now(JST))

    __table_args__ = (
        db.UniqueConstraint('room_number', 'student_id', 'username', 
                          name='unique_room_student_username'),
    )

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
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), unique=True, nullable=False)
    original_filename = db.Column(db.String(100), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    word_count = db.Column(db.Integer, default=0)
    upload_date = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    description = db.Column(db.Text)
    
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

class PasswordResetToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    token = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    used_at = db.Column(db.DateTime)
    
    user = db.relationship('User', backref=db.backref('reset_tokens', lazy=True))
    
    def is_expired(self):
        now = datetime.now(JST)
        if self.expires_at.tzinfo is None:
            expires_at_aware = JST.localize(self.expires_at)
        else:
            expires_at_aware = self.expires_at
        return now > expires_at_aware
    
    def is_valid(self):
        return not self.used and not self.is_expired()
    
    def mark_as_used(self):
        self.used = True
        self.used_at = datetime.now(JST)

class CsvFileContent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), unique=True, nullable=False)
    original_filename = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    word_count = db.Column(db.Integer, default=0)
    upload_date = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    
    def get_csv_data(self):
        try:
            reader = csv.DictReader(StringIO(self.content))
            return list(reader)
        except Exception as e:
            print(f"CSV parsing error: {e}")
            return []

# ====================================================================
# ヘルパー関数
# ====================================================================

def load_word_data_for_room(room_number):
    """指定された部屋の単語データを読み込む（完全DB対応版）"""
    try:
        room_setting = RoomSetting.query.filter_by(room_number=room_number).first()
        
        if room_setting and room_setting.csv_filename:
            csv_filename = room_setting.csv_filename
        else:
            csv_filename = "words.csv"
        
        print(f"🔍 部屋{room_number}のCSVファイル: {csv_filename}")
        
        if csv_filename == "words.csv":
            word_data = []
            try:
                with open('words.csv', 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        row['enabled'] = row.get('enabled', '1') == '1'
                        row['chapter'] = str(row['chapter'])
                        row['number'] = str(row['number'])
                        word_data.append(row)
                print(f"✅ デフォルトファイル読み込み: {len(word_data)}問")
            except FileNotFoundError:
                print(f"❌ デフォルトファイルが見つかりません: words.csv")
                return []
        else:
            csv_file = CsvFileContent.query.filter_by(filename=csv_filename).first()
            if csv_file:
                try:
                    content = csv_file.content
                    reader = csv.DictReader(StringIO(content))
                    word_data = []
                    for row in reader:
                        row['enabled'] = row.get('enabled', '1') == '1'
                        row['chapter'] = str(row['chapter'])
                        row['number'] = str(row['number'])
                        word_data.append(row)
                    print(f"✅ データベースからCSV読み込み: {len(word_data)}問 from {csv_filename}")
                except Exception as parse_error:
                    print(f"❌ CSVパースエラー: {parse_error}")
                    return []
            else:
                print(f"❌ データベースにCSVが見つかりません: {csv_filename}")
                print("🔄 デフォルトファイルにフォールバック")
                return load_word_data_for_room("default")
        
        return word_data
        
    except Exception as e:
        print(f"❌ 読み込みエラー: {e}")
        import traceback
        traceback.print_exc()
        return []

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

def parse_unit_number(unit_str):
    if not isinstance(unit_str, str):
        return float('inf')
    
    parts = unit_str.split('-')
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return int(parts[0]) * 10000 + int(parts[1])
    elif unit_str.isdigit():
        return int(unit_str) * 1000000 
    return float('inf')

def get_problem_id(word):
    """統一された問題ID生成（JavaScript側と完全一致）"""
    try:
        chapter = str(word.get('chapter', '0')).zfill(3)
        number = str(word.get('number', '0')).zfill(3)
        question = str(word.get('question', ''))
        answer = str(word.get('answer', ''))
        
        import re
        question_clean = re.sub(r'[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', '', question[:15])
        answer_clean = re.sub(r'[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', '', answer[:10])
        
        problem_id = f"{chapter}-{number}-{question_clean}-{answer_clean}"
        
        return problem_id
        
    except Exception as e:
        print(f'ID生成エラー: {e}')
        chapter = str(word.get('chapter', '0')).zfill(3)
        number = str(word.get('number', '0')).zfill(3)
        return f"{chapter}-{number}-error"

def fix_all_user_data():
    """全ユーザーの学習履歴を新しいID形式に統一"""
    default_word_data = load_default_word_data()
    if not default_word_data:
        print("❌ 単語データが見つかりません")
        return False
    
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
        
        for old_id, history_data in old_history.items():
            best_match_word = None
            best_score = 0
            
            for word in default_word_data:
                new_id = get_problem_id(word)
                if new_id == old_id:
                    best_match_word = word
                    best_score = 1000
                    break
            
            if best_score < 1000:
                parts = old_id.split('-')
                if len(parts) >= 2:
                    try:
                        old_chapter = int(parts[0].lstrip('0') or '0')
                        old_number = int(parts[1].lstrip('0') or '0')
                        
                        for word in default_word_data:
                            score = 0
                            word_chapter = int(str(word['chapter']))
                            word_number = int(str(word['number']))
                            
                            if word_chapter == old_chapter and word_number == old_number:
                                score = 500
                                
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
            
            if best_match_word and best_score >= 500:
                new_id = get_problem_id(best_match_word)
                new_history[new_id] = history_data
                user_fixed_count += 1
                
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

def migrate_database():
    """データベーススキーマの変更を処理する（PostgreSQL専用版）"""
    with app.app_context():
        print("🔄 データベースマイグレーションを開始...")
        
        try:
            inspector = inspect(db.engine)
            
            if inspector.has_table('user'):
                columns = [col['name'] for col in inspector.get_columns('user')]
                print(f"📋 既存のUserテーブルカラム: {columns}")
                
                if 'last_login' not in columns:
                    print("🔧 last_loginカラムを追加します...")
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE "user" ADD COLUMN last_login TIMESTAMP'))
                        conn.commit()
                    print("✅ last_loginカラムを追加しました。")
                else:
                    print("last_loginカラムは既に存在します。")
            
            if inspector.has_table('room_setting'):
                columns = [col['name'] for col in inspector.get_columns('room_setting')]
                print(f"📋 既存のRoomSettingテーブルカラム: {columns}")
                
                if 'csv_filename' not in columns:
                    print("🔧 csv_filenameカラムを追加します...")
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE room_setting ADD COLUMN csv_filename VARCHAR(100) DEFAULT \'words.csv\''))
                        conn.commit()
                    print("✅ csv_filenameカラムを追加しました。")
                
                missing_columns = []
                for col_name in ['created_at', 'updated_at']:
                    if col_name not in columns:
                        missing_columns.append(col_name)
                
                if missing_columns:
                    with db.engine.connect() as conn:
                        for col_name in missing_columns:
                            print(f"🔧 {col_name}カラムを追加します...")
                            conn.execute(text(f'ALTER TABLE room_setting ADD COLUMN {col_name} TIMESTAMP'))
                            print(f"✅ {col_name}カラムを追加しました。")
                        conn.commit()
            
            if inspector.has_table('password_reset_token'):
                columns = [col['name'] for col in inspector.get_columns('password_reset_token')]
                if 'used_at' not in columns:
                    print("🔧 password_reset_tokenテーブルにused_atカラムを追加します...")
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE password_reset_token ADD COLUMN used_at TIMESTAMP'))
                        conn.commit()
                    print("✅ used_atカラムを追加しました。")
            else:
                print("🔧 password_reset_tokenテーブルを作成します...")
                db.create_all()
                print("✅ password_reset_tokenテーブルを作成しました。")
            
            if not inspector.has_table('csv_file_content'):
                print("🔧 csv_file_contentテーブルを作成します...")
                db.create_all()
                print("✅ csv_file_contentテーブルを作成しました。")
            else:
                print("csv_file_contentテーブルは既に存在します。")
            
            print("✅ データベースマイグレーションが完了しました。")
            
        except Exception as e:
            print(f"⚠️ マイグレーション中にエラーが発生しました: {e}")
            import traceback
            traceback.print_exc()

def create_tables_and_admin_user():
    """データベース初期化関数（PostgreSQLスキーマ対応版）"""
    with app.app_context():
        print("🔧 データベース初期化を開始...")
        
        try:
            db_url = app.config.get('SQLALCHEMY_DATABASE_URI', '')
            is_postgres = 'postgresql' in db_url.lower()
            
            if not is_postgres:
                print("⚠️ 警告: PostgreSQL以外のデータベースが検出されました")
                print(f"DB URL: {db_url[:50]}...")
            
            inspector = inspect(db.engine)
            
            existing_tables = []
            if is_postgres:
                public_tables = inspector.get_table_names(schema='public')
                default_tables = inspector.get_table_names()
                existing_tables = list(set(public_tables + default_tables))
                print(f"📋 PostgreSQL接続: publicスキーマ={len(public_tables)}テーブル, デフォルト={len(default_tables)}テーブル")
            else:
                existing_tables = inspector.get_table_names()
            
            if existing_tables:
                print(f"📋 既存のテーブル: {existing_tables}")
                migrate_database()
            else:
                print("📋 新しいデータベースを検出しました")
            
            db.create_all()
            print("✅ テーブルを確認/作成しました。")
            
            try:
                admin_user = User.query.filter_by(username='admin', room_number='ADMIN').first()
                
                if not admin_user:
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
                
            try:
                app_info = AppInfo.get_current_info()
                print("✅ アプリ情報を確認/作成しました")
                
            except Exception as e:
                print(f"⚠️ アプリ情報処理エラー: {e}")
                
            print("🎉 データベース初期化が完了しました！")
                
        except Exception as e:
            print(f"❌ データベース初期化エラー: {e}")
            db.session.rollback()
            raise

def generate_reset_token():
    """セキュアなリセットトークンを生成"""
    return secrets.token_urlsafe(32)

def generate_temp_password():
    """一時パスワードを生成"""
    characters = string.ascii_letters + string.digits
    return ''.join(secrets.choice(characters) for _ in range(8))

def send_password_reset_email(user, email, token):
    """パスワード再発行メールを送信（エラーハンドリング強化版）"""
    try:
        print(f"🔍 メール送信開始: {email}")
        
        mail_server = app.config.get('MAIL_SERVER')
        mail_username = app.config.get('MAIL_USERNAME')
        mail_password = app.config.get('MAIL_PASSWORD')
        mail_sender = app.config.get('MAIL_DEFAULT_SENDER')
        
        print(f"🔍 メール設定確認:")
        print(f"  MAIL_SERVER: {mail_server}")
        print(f"  MAIL_USERNAME: {mail_username}")
        print(f"  MAIL_DEFAULT_SENDER: {mail_sender}")
        print(f"  MAIL_PASSWORD: {'設定済み' if mail_password else '未設定'}")
        
        if not all([mail_server, mail_username, mail_password, mail_sender]):
            missing = []
            if not mail_server: missing.append('MAIL_SERVER')
            if not mail_username: missing.append('MAIL_USERNAME') 
            if not mail_password: missing.append('MAIL_PASSWORD')
            if not mail_sender: missing.append('MAIL_DEFAULT_SENDER')
            raise Exception(f"メール設定が不完全です。不足: {', '.join(missing)}")
        
        app_info = AppInfo.get_current_info()
        
        reset_url = url_for('password_reset', token=token, _external=True)
        print(f"🔍 リセットURL: {reset_url}")
        
        subject = f'[{app_info.app_name}] パスワード再発行のご案内'
        
        # HTML版メール本文
        html_body = f'''
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                <h2 style="color: #2c3e50; text-align: center;">{app_info.app_name}</h2>
                <h3 style="color: #34495e;">パスワード再発行のご案内</h3>
                
                <p>いつもご利用いただきありがとうございます。</p>
                
                <p>以下のアカウントのパスワード再発行が要求されました：</p>
                <ul style="background-color: #f8f9fa; padding: 15px; border-radius: 5px;">
                    <li><strong>部屋番号:</strong> {user.room_number}</li>
                    <li><strong>出席番号:</strong> {user.student_id}</li>
                    <li><strong>アカウント名:</strong> {user.username}</li>
                    <li><strong>送信先メール:</strong> {email}</li>
                </ul>
                
                <p>下記のリンクをクリックして、新しいパスワードを設定してください：</p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_url}" 
                       style="display: inline-block; padding: 12px 30px; background-color: #3498db; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">
                        パスワードを再設定する
                    </a>
                </div>
                
                <div style="background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h4 style="color: #856404; margin-top: 0;">⚠️ 重要事項</h4>
                    <ul style="color: #856404; margin-bottom: 0;">
                        <li>このリンクは<strong>1時間以内</strong>に使用してください</li>
                        <li>リンクは<strong>1回のみ</strong>使用可能です</li>
                        <li>パスワード再発行を要求していない場合は、このメールを無視してください</li>
                    </ul>
                </div>
                
                <p>リンクがクリックできない場合は、以下のURLをコピーしてブラウザのアドレスバーに貼り付けてください：</p>
                <p style="word-break: break-all; background-color: #f8f9fa; padding: 10px; border-radius: 3px; font-family: monospace;">
                    {reset_url}
                </p>
                
                <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                
                <p style="font-size: 0.9em; color: #666;">
                    このメールに心当たりがない場合は、誰かが間違ってあなたのメールアドレスを入力した可能性があります。<br>
                    その場合は、このメールを無視していただいて構いません。
                </p>
                
                <p style="font-size: 0.9em; color: #666; text-align: center; margin-top: 30px;">
                    {app_info.app_name} システム<br>
                    {app_info.contact_email if app_info.contact_email else ''}
                </p>
            </div>
        </body>
        </html>
        '''
        
        # テキスト版メール本文
        text_body = f'''
{app_info.app_name} パスワード再発行のご案内

いつもご利用いただきありがとうございます。

以下のアカウントのパスワード再発行が要求されました：
- 部屋番号: {user.room_number}
- 出席番号: {user.student_id}
- アカウント名: {user.username}
- 送信先メール: {email}

下記のリンクにアクセスして、新しいパスワードを設定してください：
{reset_url}

【重要事項】
- このリンクは1時間以内に使用してください
- リンクは1回のみ使用可能です
- パスワード再発行を要求していない場合は、このメールを無視してください

このメールに心当たりがない場合は、誰かが間違ってあなたのメールアドレスを入力した可能性があります。
その場合は、このメールを無視していただいて構いません。

{app_info.app_name} システム
{app_info.contact_email if app_info.contact_email else ''}
        '''
        
        print(f"🔍 メッセージ作成中...")
        msg = Message(
            subject=subject,
            recipients=[email],
            html=html_body,
            body=text_body,
            sender=mail_sender
        )
        
        print(f"🔍 メッセージ詳細:")
        print(f"  件名: {subject}")
        print(f"  送信者: {mail_sender}")
        print(f"  受信者: {email}")
        
        print(f"🔍 メール送信実行中...")
        mail.send(msg)
        print(f"✅ パスワード再発行メール送信成功: {email}")
        
        return True
        
    except Exception as e:
        print(f"❌ メール送信エラー: {e}")
        print(f"❌ エラータイプ: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        
        if 'authentication' in str(e).lower():
            print("❌ Gmail認証エラー: アプリパスワードを確認してください")
        elif 'connection' in str(e).lower():
            print("❌ 接続エラー: SMTPサーバーへの接続に失敗しました")
        elif 'timeout' in str(e).lower():
            print("❌ タイムアウトエラー: ネットワーク接続を確認してください")
        
        raise e

def is_mail_configured():
    """メール設定が完了しているかをチェック"""
    required_settings = [
        'MAIL_SERVER',
        'MAIL_USERNAME', 
        'MAIL_PASSWORD',
        'MAIL_DEFAULT_SENDER'
    ]
    
    for setting in required_settings:
        value = app.config.get(setting)
        if not value or (isinstance(value, str) and not value.strip()):
            return False
    
    return True

def get_template_context():
    """全テンプレートで共通に使用するコンテキストを取得"""
    try:
        app_info = AppInfo.get_current_info()
        return {'app_info': app_info}
    except Exception as e:
        print(f"Error getting app_info: {e}")
        return {'app_info': None}

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

        context = get_template_context()
        footer_app_info = context.pop('app_info', None)
        
        return render_template('index.html', 
                               app_info=app_info_for_js,
                               chapter_data=sorted_all_chapter_unit_status,
                               footer_app_info=footer_app_info,
                               **context)
    
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

@app.route('/password_reset_request', methods=['GET', 'POST'])
def password_reset_request():
    try:
        mail_configured = is_mail_configured()
        
        if request.method == 'POST':
            room_number = request.form.get('room_number', '').strip()
            student_id = request.form.get('student_id', '').strip()
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            
            if not all([room_number, student_id, username, email]):
                flash('すべての項目を入力してください。', 'danger')
                context = get_template_context()
                context['mail_configured'] = mail_configured
                return render_template('password_reset_request.html', **context)
            
            if not mail_configured:
                flash('メール送信機能が設定されていないため、パスワード再発行を実行できません。管理者にお問い合わせください。', 'danger')
                context = get_template_context()
                context['mail_configured'] = mail_configured
                return render_template('password_reset_request.html', **context)
            
            user = User.query.filter_by(
                room_number=room_number, 
                student_id=student_id,
                username=username
            ).first()
            
            if not user:
                flash('入力された情報に一致するアカウントが見つかった場合、パスワード再発行のご案内をメールで送信しました。メールをご確認ください。', 'success')
                return redirect(url_for('login_page'))
            
            existing_tokens = PasswordResetToken.query.filter_by(
                user_id=user.id, 
                used=False
            ).all()
            for token in existing_tokens:
                token.used = True
                token.used_at = datetime.now(JST)
            
            reset_token = generate_reset_token()
            expires_at = datetime.now(JST) + timedelta(hours=1)
            
            password_reset_token = PasswordResetToken(
                user_id=user.id,
                token=reset_token,
                expires_at=expires_at
            )
            
            db.session.add(password_reset_token)
            db.session.commit()
            
            try:
                print(f"🔍 メール送信処理開始...")
                success = send_password_reset_email(user, email, reset_token)
                if success:
                    flash('入力された情報に一致するアカウントが見つかりました。パスワード再発行のご案内をメールで送信しました。メールをご確認ください。', 'success')
                    print(f"✅ メール送信完了")
                else:
                    flash('メール送信に失敗しました。しばらく後に再度お試しください。', 'danger')
                    password_reset_token.used = True
                    db.session.commit()
            except Exception as email_error:
                print(f"❌ メール送信例外: {email_error}")
                import traceback
                traceback.print_exc()
                
                error_msg = str(email_error).lower()
                if 'authentication' in error_msg:
                    flash('メール送信の認証に失敗しました。システム管理者にお問い合わせください。', 'danger')
                elif 'connection' in error_msg or 'timeout' in error_msg:
                    flash('メールサーバーへの接続に失敗しました。しばらく後に再度お試しください。', 'danger')
                else:
                    flash('メール送信中にエラーが発生しました。システム管理者にお問い合わせください。', 'danger')
                
                password_reset_token.used = True
                db.session.commit()
            
            return redirect(url_for('login_page'))
        
        context = get_template_context()
        context['mail_configured'] = mail_configured
        return render_template('password_reset_request.html', **context)
        
    except Exception as e:
        print(f"Error in password_reset_request: {e}")
        import traceback
        traceback.print_exc()
        flash('システムエラーが発生しました。管理者にお問い合わせください。', 'danger')
        return redirect(url_for('login_page'))

@app.route('/password_reset/<token>', methods=['GET', 'POST'])
def password_reset(token):
    """パスワード再設定の実行"""
    try:
        print(f"🔍 Password reset requested for token: {token}")
        print(f"🔍 Request method: {request.method}")
        
        reset_token = PasswordResetToken.query.filter_by(token=token).first()
        print(f"🔍 Token found in database: {reset_token is not None}")
        
        if reset_token:
            print(f"🔍 Token user_id: {reset_token.user_id}")
            print(f"🔍 Token used: {reset_token.used}")
            print(f"🔍 Token expires_at: {reset_token.expires_at}")
            print(f"🔍 Current time: {datetime.now(JST)}")
            print(f"🔍 Token is_valid: {reset_token.is_valid()}")
        
        if not reset_token or not reset_token.is_valid():
            if not reset_token:
                print("❌ Token not found in database")
            else:
                print(f"❌ Token invalid - used: {reset_token.used}, expired: {reset_token.is_expired()}")
            flash('無効なリンクまたは期限切れです。新しいパスワード再発行をリクエストしてください。', 'danger')
            return redirect(url_for('password_reset_request'))
        
        if request.method == 'POST':
            new_password = request.form.get('new_password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            
            if not new_password or not confirm_password:
                flash('パスワードを入力してください。', 'danger')
                context = get_template_context()
                context.update({
                    'token': token,
                    'user': reset_token.user,
                    'minutes_remaining': max(0, int((reset_token.expires_at - datetime.now(JST)).total_seconds() / 60))
                })
                return render_template('password_reset.html', **context)
            
            if new_password != confirm_password:
                flash('パスワードが一致しません。', 'danger')
                context = get_template_context()
                context.update({
                    'token': token,
                    'user': reset_token.user,
                    'minutes_remaining': max(0, int((reset_token.expires_at - datetime.now(JST)).total_seconds() / 60))
                })
                return render_template('password_reset.html', **context)
            
            if len(new_password) < 6:
                flash('パスワードは6文字以上で入力してください。', 'danger')
                context = get_template_context()
                context.update({
                    'token': token,
                    'user': reset_token.user,
                    'minutes_remaining': max(0, int((reset_token.expires_at - datetime.now(JST)).total_seconds() / 60))
                })
                return render_template('password_reset.html', **context)
            
            user = reset_token.user
            user.set_individual_password(new_password)
            
            reset_token.mark_as_used()
            
            db.session.commit()
            
            flash('パスワードが正常に更新されました。新しいパスワードでログインしてください。', 'success')
            return redirect(url_for('login_page'))
        
        now = datetime.now(JST)
        
        if reset_token.expires_at.tzinfo is None:
            expires_at_aware = JST.localize(reset_token.expires_at)
        else:
            expires_at_aware = reset_token.expires_at

        time_remaining = expires_at_aware - now
        minutes_remaining = max(0, int(time_remaining.total_seconds() / 60))
        
        context = get_template_context()
        context.update({
            'token': token,
            'user': reset_token.user,
            'minutes_remaining': minutes_remaining
        })
        
        return render_template('password_reset.html', **context)
        
    except Exception as e:
        print(f"❌ Error in password_reset: {e}")
        import traceback
        traceback.print_exc()
        
        flash('システムエラーが発生しました。管理者にお問い合わせください。', 'danger')
        return redirect(url_for('login_page'))

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

        old_history = current_user.get_problem_history()
        old_incorrect = current_user.get_incorrect_words()
        
        print(f"\n=== 進捗保存デバッグ ({current_user.username}) ===")
        print(f"保存前の履歴数: {len(old_history)}")
        print(f"受信した履歴数: {len(received_problem_history)}")
        print(f"保存前の苦手問題数: {len(old_incorrect)}")
        print(f"受信した苦手問題数: {len(received_incorrect_words)}")
        
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

        current_user.set_problem_history(received_problem_history)
        current_user.set_incorrect_words(received_incorrect_words)
        db.session.commit()

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

@app.route('/api/clear_quiz_progress', methods=['POST'])
def api_clear_quiz_progress():
    return jsonify(status='success', message='一時的なクイズ進捗クリア要求を受信しました（サーバー側は変更なし）。')

# ====================================================================
# 進捗ページ
# ====================================================================

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
        
        word_data = load_word_data_for_room(current_user.room_number)
        print(f"部屋の単語データ数: {len(word_data)}")
        
        room_setting = RoomSetting.query.filter_by(room_number=current_user.room_number).first()
        max_enabled_unit_num_str = room_setting.max_enabled_unit_number if room_setting else "9999"
        parsed_max_enabled_unit_num = parse_unit_number(max_enabled_unit_num_str)
        print(f"最大単元番号: {max_enabled_unit_num_str}")

        unit_progress_summary = {}

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

        matched_problems = 0
        unmatched_problems = 0
        
        for problem_id, history in user_problem_history.items():
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
                            
                            accuracy_rate = (correct_attempts / total_problem_attempts) * 100
                            if accuracy_rate >= 80.0:
                                unit_progress_summary[unit_number_of_word]['mastered_problems'].add(problem_id)
                                print(f"マスター問題: {matched_word['question']} (正答率: {accuracy_rate:.1f}%)")
            else:
                unmatched_problems += 1
                print(f"マッチしない問題ID: {problem_id}")
        
        print(f"マッチした問題: {matched_problems}, マッチしない問題: {unmatched_problems}")
        
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

        ranking_data.sort(key=lambda x: (x['balance_score'], x['total_attempts']), reverse=True)
        top_10_ranking = ranking_data[:10]

        print(f"ランキング対象ユーザー数: {len(ranking_data)}")
        print("=== 進捗ページ処理完了 ===\n")

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

@app.route('/admin')
def admin_page():
    try:
        if not session.get('admin_logged_in'):
            flash('管理者権限がありません。', 'danger')
            return redirect(url_for('login_page'))

        print("🔍 管理者ページ表示開始...")

        users = User.query.all()
        room_settings = RoomSetting.query.all()
        
        room_max_unit_settings = {rs.room_number: rs.max_enabled_unit_number for rs in room_settings}
        room_csv_settings = {rs.room_number: rs.csv_filename for rs in room_settings}
        
        print(f"📊 部屋設定状況:")
        for room_num, csv_file in room_csv_settings.items():
            print(f"  部屋{room_num}: {csv_file}")
        
        unique_room_numbers = set()
        for user in users:
            if user.room_number != 'ADMIN':
                unique_room_numbers.add(user.room_number)
        
        for setting in room_settings:
            if setting.room_number != 'ADMIN':
                unique_room_numbers.add(setting.room_number)
        
        print(f"📋 管理対象部屋: {sorted(unique_room_numbers)}")
        
        for room_num in unique_room_numbers:
            if room_num not in room_csv_settings:
                print(f"⚠️ 部屋{room_num}のCSV設定が見つかりません - デフォルト設定を作成")
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
            **context
        }
        
        print("✅ 管理者ページ表示準備完了")
        return render_template('admin.html', **template_context)
        
    except Exception as e:
        print(f"❌ 管理者ページエラー: {e}")
        import traceback
        traceback.print_exc()
        return f"Admin Error: {e}", 500

@app.route('/admin/app_info', methods=['GET', 'POST'])
def admin_app_info():
    try:
        if not session.get('admin_logged_in'):
            flash('管理者権限がありません。', 'danger')
            return redirect(url_for('login_page'))

        print("=== admin_app_info デバッグ開始 ===")
        
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

        existing_user = User.query.filter_by(
            room_number=room_number, 
            username=username
        ).first()
                    
        if existing_user:
            flash(f'部屋{room_number}にユーザー名{username}は既に存在します。', 'danger')
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

        flash(f'ユーザー {username} (部屋: {room_number}, 出席番号: {student_id}) を登録しました。', 'success')
        return redirect(url_for('admin_page'))
    except Exception as e:
        print(f"Error in admin_add_user: {e}")
        flash(f'ユーザー追加中にエラーが発生しました: {e}', 'danger')
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

        room_setting = RoomSetting.query.filter_by(room_number=room_number).first()

        if room_setting:
            old_filename = room_setting.csv_filename
            room_setting.csv_filename = csv_filename
            print(f"📝 既存設定更新: {old_filename} -> {csv_filename}")
        else:
            room_setting = RoomSetting(
                room_number=room_number,
                max_enabled_unit_number="9999",
                csv_filename=csv_filename
            )
            db.session.add(room_setting)
            print(f"➕ 新規設定作成: 部屋{room_number} with {csv_filename}")
        
        db.session.commit()
        
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

@app.route('/admin/upload_room_csv', methods=['POST'])
def admin_upload_room_csv():
    try:
        print("🔍 CSV アップロード開始（完全DB保存版）...")
        
        if not session.get('admin_logged_in'):
            flash('管理者権限がありません。', 'danger')
            return redirect(url_for('admin_page'))

        if 'file' not in request.files:
            flash('ファイルが選択されていません。', 'danger')
            return redirect(url_for('admin_page'))

        file = request.files['file']
        if file.filename == '' or not file.filename.endswith('.csv'):
            flash('CSVファイルを選択してください。', 'danger')
            return redirect(url_for('admin_page'))

        content = file.read().decode('utf-8')
        filename = secure_filename(file.filename)
        original_filename = file.filename
        file_size = len(content.encode('utf-8'))
        
        print(f"📁 ファイル情報: {filename}, サイズ: {file_size}bytes")
        
        word_count = 0
        try:
            reader = csv.DictReader(StringIO(content))
            required_columns = ['chapter', 'number', 'category', 'question', 'answer', 'enabled']
            
            if not reader.fieldnames:
                flash('CSVファイルにヘッダー行がありません。', 'danger')
                return redirect(url_for('admin_page'))
            
            missing_cols = [col for col in required_columns if col not in reader.fieldnames]
            if missing_cols:
                flash(f'CSVファイルに必要な列が不足しています: {", ".join(missing_cols)}', 'danger')
                return redirect(url_for('admin_page'))
            
            # 全行をチェックして単語数をカウント
            for i, row in enumerate(reader):
                missing_data = []
                for col in ['chapter', 'number', 'question', 'answer']:
                    if not row.get(col, '').strip():
                        missing_data.append(col)
                
                if missing_data:
                    flash(f'CSVファイルの{i+2}行目に必須データが不足しています: {", ".join(missing_data)}', 'danger')
                    return redirect(url_for('admin_page'))
                word_count += 1
            
            if word_count == 0:
                flash('CSVファイルにデータが含まれていません。', 'danger')
                return redirect(url_for('admin_page'))
                
        except Exception as csv_error:
            flash(f'CSVファイルの読み込み中にエラーが発生しました: {str(csv_error)}', 'danger')
            return redirect(url_for('admin_page'))
        
        print(f"✅ CSV検証完了: {word_count}問")
        
        # ★重要：データベースに保存（ファイルシステムは使わない）
        try:
            # 既存のファイル記録があれば更新、なければ新規作成
            csv_file_record = CsvFileContent.query.filter_by(filename=filename).first()
            if csv_file_record:
                print(f"🔄 既存レコード更新: {filename}")
                csv_file_record.original_filename = original_filename
                csv_file_record.content = content
                csv_file_record.file_size = file_size
                csv_file_record.word_count = word_count
                csv_file_record.upload_date = datetime.now(JST)
            else:
                print(f"➕ 新規レコード作成: {filename}")
                csv_file_record = CsvFileContent(
                    filename=filename,
                    original_filename=original_filename,
                    content=content,
                    file_size=file_size,
                    word_count=word_count
                )
                db.session.add(csv_file_record)
            
            db.session.commit()
            
            file_size_kb = round(file_size / 1024, 1)
            flash(f'✅ CSVファイル "{filename}" をデータベースに保存しました', 'success')
            flash(f'📊 ファイル情報: {word_count}問, {file_size_kb}KB', 'info')
            flash('💾 ファイルはデータベースに保存されているため、再デプロイ後も保持されます', 'info')
            
            print(f"✅ データベース保存完了: {filename}")
            
        except Exception as db_error:
            print(f"❌ データベース保存エラー: {db_error}")
            db.session.rollback()
            flash(f'データベース保存中にエラーが発生しました: {str(db_error)}', 'danger')

        return redirect(url_for('admin_page'))
        
    except Exception as e:
        print(f"❌ 全体エラー: {e}")
        import traceback
        traceback.print_exc()
        flash(f'ファイルアップロード中にエラーが発生しました: {e}', 'danger')
        return redirect(url_for('admin_page'))

@app.route('/admin/list_room_csv_files')
def admin_list_room_csv_files():
    try:
        print("🔍 CSV ファイル一覧取得開始（DB版）...")
        
        if not session.get('admin_logged_in'):
            return jsonify(status='error', message='管理者権限がありません。'), 403

        # ★重要：データベースからCSVファイル一覧を取得（ファイルシステムは使わない）
        csv_files_data = []
        try:
            csv_records = CsvFileContent.query.filter(CsvFileContent.filename != 'words.csv').all()
            
            for record in csv_records:
                csv_files_data.append({
                    'filename': record.filename,
                    'size': record.file_size,
                    'modified': record.upload_date.strftime('%Y-%m-%d %H:%M:%S'),
                    'word_count': record.word_count
                })
                print(f"📋 ファイル: {record.filename} ({record.word_count}問)")
            
            print(f"✅ データベースから{len(csv_files_data)}個のファイルを取得")
            
        except Exception as db_error:
            print(f"❌ データベース取得エラー: {db_error}")
            return jsonify(status='error', message=f'データベースエラー: {str(db_error)}'), 500
        
        return jsonify(status='success', files=csv_files_data)
        
    except Exception as e:
        print(f"❌ CSV ファイル一覧取得エラー: {e}")
        import traceback
        traceback.print_exc()
        return jsonify(status='error', message=str(e)), 500

@app.route('/admin/delete_room_csv/<filename>', methods=['POST'])
def admin_delete_room_csv(filename):
    try:
        if not session.get('admin_logged_in'):
            flash('管理者権限がありません。', 'danger')
            return redirect(url_for('admin_page'))

        filename = secure_filename(filename)
        print(f"🗑️ CSVファイル削除開始: {filename}")

        # ★重要：データベースから削除（ファイルシステムは使わない）
        csv_record = CsvFileContent.query.filter_by(filename=filename).first()
        if csv_record:
            db.session.delete(csv_record)
            print(f"✅ データベースから削除: {filename}")
            
            # このファイルを使用している部屋設定をデフォルトに戻す
            room_settings = RoomSetting.query.filter_by(csv_filename=filename).all()
            updated_rooms = []
            for setting in room_settings:
                setting.csv_filename = "words.csv"
                updated_rooms.append(setting.room_number)
            
            db.session.commit()
            
            if updated_rooms:
                flash(f'CSVファイル "{filename}" を削除し、部屋 {", ".join(updated_rooms)} の設定をデフォルトに戻しました。', 'success')
            else:
                flash(f'CSVファイル "{filename}" を削除しました。', 'success')
                
            print(f"✅ 削除完了: {filename}")
        else:
            flash('指定されたファイルが見つかりません。', 'danger')
            print(f"❌ ファイルが見つかりません: {filename}")

        return redirect(url_for('admin_page'))
        
    except Exception as e:
        print(f"❌ ファイル削除エラー: {e}")
        db.session.rollback()
        flash(f'ファイル削除中にエラーが発生しました: {e}', 'danger')
        return redirect(url_for('admin_page'))

@app.route('/admin/upload_users', methods=['POST'])
def admin_upload_users():
    if not session.get('admin_logged_in'):
        flash('管理者権限がありません。', 'danger')
        return redirect(url_for('login_page'))

    if 'file' not in request.files:
        flash('ファイルが選択されていません。', 'danger')
        return redirect(url_for('admin_page'))

    file = request.files['file']
    if file.filename == '' or not file.filename.endswith('.csv'):
        flash('CSVファイルを選択してください。', 'danger')
        return redirect(url_for('admin_page'))

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

                # 重複チェック（部屋番号 + ユーザー名の組み合わせ）
                existing_user = User.query.filter_by(
                    room_number=room_number, 
                    username=username
                ).first()
                
                if existing_user:
                    errors.append(f"行{row_num}: 部屋{room_number}にユーザー名{username}は既に存在します")
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
            
            # ファイルを再読み込みして部屋番号を取得
            file.stream.seek(0)  # ファイルポインタを先頭に戻す
            stream_for_rooms = StringIO(file.stream.read().decode("utf-8"))
            reader_for_rooms = csv.DictReader(stream_for_rooms)
            
            for row in reader_for_rooms:
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
                flash(f'⚠️ {skipped_existing}人のユーザーは重複するため、スキップされました。', 'warning')
                
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
# データベース管理・修正機能
# ====================================================================

@app.route('/admin/check_data_status')
def admin_check_data_status():
    """データベースの現在状態を確認"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify(status='error', message='管理者権限がありません。'), 403

        # 全ユーザーデータをチェック
        users = User.query.all()
        default_word_data = load_default_word_data()
        
        user_status = []
        total_history_entries = 0
        total_matched = 0
        total_unmatched = 0
        
        for user in users:
            if user.username == 'admin':
                continue
                
            user_history = user.get_problem_history()
            matched_count = 0
            unmatched_ids = []
            
            for problem_id in user_history.keys():
                # 新しい方式で照合
                found_match = False
                for word in default_word_data:
                    if get_problem_id(word) == problem_id:
                        found_match = True
                        break
                
                if found_match:
                    matched_count += 1
                else:
                    unmatched_ids.append(problem_id)
            
            user_status.append({
                'username': user.username,
                'room_number': user.room_number,
                'total_history': len(user_history),
                'matched': matched_count,
                'unmatched': len(unmatched_ids),
                'sample_unmatched': unmatched_ids[:3]
            })
            
            total_history_entries += len(user_history)
            total_matched += matched_count
            total_unmatched += len(unmatched_ids)
        
        return jsonify({
            'status': 'success',
            'summary': {
                'total_users': len(user_status),
                'total_history_entries': total_history_entries,
                'total_matched': total_matched,
                'total_unmatched': total_unmatched,
                'match_rate': round((total_matched / total_history_entries * 100) if total_history_entries > 0 else 0, 1)
            },
            'user_details': user_status
        })
        
    except Exception as e:
        print(f"Error in admin_check_data_status: {e}")
        return jsonify(status='error', message=str(e)), 500

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

# ====================================================================
# テンプレート用コンテキスト関数
# ====================================================================

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

# ====================================================================
# 起動時処理・チェック機能
# ====================================================================

def verify_room_settings():
    """起動時に部屋設定の整合性をチェック（DB版）"""
    print("\n🔍 部屋設定の整合性確認中（DB版）...")
    
    try:
        with app.app_context():
            settings = RoomSetting.query.all()
            print(f"📋 登録済み部屋設定: {len(settings)}件")
            
            for setting in settings:
                csv_filename = setting.csv_filename
                if csv_filename != "words.csv":
                    # ★重要：ファイルシステムではなくデータベースで確認
                    csv_record = CsvFileContent.query.filter_by(filename=csv_filename).first()
                    if not csv_record:
                        print(f"⚠️ 部屋{setting.room_number}: {csv_filename} がデータベースに見つからない -> デフォルトに変更")
                        setting.csv_filename = "words.csv"
                    else:
                        print(f"✅ 部屋{setting.room_number}: {csv_filename} 確認OK（DB内）")
                else:
                    print(f"📄 部屋{setting.room_number}: デフォルト使用")
            
            db.session.commit()
            print("✅ 部屋設定確認完了（DB版）\n")
        
    except Exception as e:
        print(f"❌ 部屋設定確認エラー: {e}\n")

def check_data_persistence():
    """データの永続化状況をチェック"""
    try:
        with app.app_context():
            user_count = User.query.count()
            admin_count = User.query.filter_by(room_number='ADMIN').count()
            room_settings_count = RoomSetting.query.count()
            csv_files_count = CsvFileContent.query.count()
            
            print(f"📊 データ永続化状況:")
            print(f"   総ユーザー数: {user_count}")
            print(f"   管理者ユーザー: {admin_count}")
            print(f"   部屋設定数: {room_settings_count}")
            print(f"   保存CSVファイル数: {csv_files_count}")
            
            if admin_count == 0:
                print("⚠️ 管理者ユーザーが見つかりません！")
                return False
            
            return True
        
    except Exception as e:
        print(f"❌ データ永続化チェックエラー: {e}")
        return False

def print_render_recommendations():
    """Render環境での推奨設定を表示"""
    is_render = os.environ.get('RENDER') == 'true'
    has_postgres = bool(os.environ.get('DATABASE_URL'))
    
    print("\n" + "="*60)
    print("🚀 RENDER環境設定推奨事項")
    print("="*60)
    
    if is_render:
        print("✅ Render環境を検出")
        
        if has_postgres:
            print("✅ PostgreSQLデータベースが設定されています")
        else:
            print("⚠️ PostgreSQLデータベースが推奨されます")
            print("💡 Render Dashboardで PostgreSQL Add-on を追加してください")
        
        print("\n📋 推奨環境変数設定:")
        print("   PYTHON_VERSION = 3.11.9")
        if not has_postgres:
            print("   DATABASE_URL = <PostgreSQL接続URL>")
        
    else:
        print("🏠 ローカル環境で実行中")
    
    print("="*60 + "\n")

def enhanced_startup_check():
    """起動時の詳細チェック"""
    try:
        with app.app_context():
            print("\n" + "="*60)
            print("🔍 詳細起動チェック")
            print("="*60)
            
            # PostgreSQL接続確認
            db_url = app.config.get('SQLALCHEMY_DATABASE_URI', '')
            print(f"📊 DB URL: {db_url[:50]}...")
            
            # ユーザー詳細
            all_users = User.query.all()
            print(f"📊 総ユーザー数: {len(all_users)}")
            
            # 部屋別ユーザー数
            room_counts = {}
            for user in all_users:
                room = user.room_number
                if room not in room_counts:
                    room_counts[room] = []
                room_counts[room].append(user.username)
            
            for room, users in room_counts.items():
                print(f"📊 部屋{room}: {len(users)}人 - {users}")
            
            # 最近のユーザー登録
            recent_users = User.query.filter(User.room_number != 'ADMIN').order_by(User.id.desc()).limit(5).all()
            if recent_users:
                print(f"📊 最新ユーザー5人:")
                for user in recent_users:
                    print(f"  ID{user.id}: {user.username} (部屋{user.room_number}, 出席{user.student_id})")
            
            # CSVファイル確認
            csv_files = CsvFileContent.query.all()
            print(f"📊 保存済CSVファイル: {len(csv_files)}個")
            for csv_file in csv_files:
                print(f"  {csv_file.filename} ({csv_file.word_count}問)")
            
            print("="*60 + "\n")
            
    except Exception as e:
        print(f"❌ 起動チェックエラー: {e}")

def diagnose_mail_config():
    """メール設定を診断"""
    print("\n=== メール設定診断 ===")
    required_vars = ['MAIL_SERVER', 'MAIL_USERNAME', 'MAIL_PASSWORD', 'MAIL_DEFAULT_SENDER']
    
    for var in required_vars:
        value = os.environ.get(var)
        if value:
            if 'PASSWORD' in var:
                print(f"{var}: {'*' * len(value)} (設定済み)")
            else:
                print(f"{var}: {value}")
        else:
            print(f"{var}: ❌ 未設定")
    
    print("===================\n")

# アプリ起動時に診断実行
diagnose_mail_config()

# ===== メイン起動処理 =====
if __name__ == '__main__':
    try:
        # 環境設定の表示
        print_render_recommendations()
        
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
        enhanced_startup_check()
        
        app.run(host='0.0.0.0', port=port, debug=debug_mode)
        
    except Exception as e:
        print(f"💥 起動失敗: {e}")
        import traceback
        traceback.print_exc()