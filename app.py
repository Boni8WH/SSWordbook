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
import logging
import math

log_level = logging.INFO if os.environ.get('RENDER') == 'true' else logging.DEBUG
logging.basicConfig(
    level=log_level,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# SQLAlchemyのログを抑制（本番環境のみ）
if os.environ.get('RENDER') == 'true':
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
logger.info(f"ログレベル設定: {logging.getLevelName(log_level)} ({'本番' if os.environ.get('RENDER') == 'true' else 'ローカル'}環境)")

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import inspect, text

# 日本時間のタイムゾーンオブジェクトを作成
JST = pytz.timezone('Asia/Tokyo')

# ===== Flaskアプリの作成 =====
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here_please_change_this_in_production'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = 3600 * 24 * 7

database_url = os.environ.get('DATABASE_URL')

if database_url:
    logger.info("🐘 PostgreSQL設定を適用中...")
    
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
    logger.info("✅ PostgreSQL接続設定完了")
    is_postgres = True
else:
    logger.warning("📄 DATABASE_URLが未設定 - SQLiteを使用")
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'quiz_data.db')
    is_postgres = False

# ===== メール設定 =====
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', '587'))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME'])

mail = Mail(app)

# ===== SQLAlchemy初期化（1回のみ） =====
db = SQLAlchemy(app)

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# 部屋ごとのCSVファイルを保存するフォルダ
ROOM_CSV_FOLDER = 'room_csv'

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
        info_dict['schoolName'] = getattr(app_info, 'school_name', '朋優学院')
        
        return info_dict
    except Exception as e:
        print(f"Error getting app info: {e}")
        # エラー時も最新のDB情報を取得しようと試行
        try:
            app_info = AppInfo.query.first()
            if app_info:
                return {
                    'appName': app_info.app_name,
                    'version': app_info.version,
                    'lastUpdatedDate': app_info.last_updated_date,
                    'updateContent': app_info.update_content,
                    'footerText': app_info.footer_text,
                    'contactEmail': app_info.contact_email,
                    'schoolName': getattr(app_info, 'school_name', '朋優学院'),
                    'isLoggedIn': user_id is not None,
                    'username': username,
                    'roomNumber': room_number
                }
        except:
            pass
        
        # 最終フォールバック
        return {
            'appName': '世界史単語帳',
            'version': '1.0.0', 
            'lastUpdatedDate': '2025年6月15日',
            'schoolName': '朋優学院', 
            'updateContent': 'アプリケーションが開始されました。',
            'isLoggedIn': user_id is not None,
            'username': username,
            'roomNumber': room_number
        }

def convert_to_jst(dt):
    """UTCからJSTに変換"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # naive datetimeの場合、UTCとして扱ってJSTに変換
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(JST)

# テンプレートで使用できるようにフィルターとして登録
@app.template_filter('to_jst')
def to_jst_filter(dt):
    if dt is None:
        return None
    
    # 強制的に文字列に変換して9時間加算
    try:
        from datetime import datetime, timedelta
        
        # 文字列から datetime に変換
        if isinstance(dt, str):
            dt_obj = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
        else:
            dt_obj = dt
        
        # 9時間加算
        jst_dt = dt_obj + timedelta(hours=9)
        return jst_dt.strftime('%Y-%m-%d %H:%M')
        
    except Exception as e:
        print(f"🔍 エラー: {e}")
        return str(dt)

# ====================================================================
# データベースモデル定義
# ====================================================================

# app.py の User モデルの定義を以下に置き換え
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)  # 現在のアカウント名
    original_username = db.Column(db.String(80), nullable=False)  # 最初に登録したアカウント名（新規追加）
    room_number = db.Column(db.String(50), nullable=False)
    _room_password_hash = db.Column(db.String(255))
    student_id = db.Column(db.String(50), nullable=False)
    _individual_password_hash = db.Column(db.String(255))
    problem_history = db.Column(db.Text)
    incorrect_words = db.Column(db.Text)
    last_login = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    username_changed_at = db.Column(db.DateTime)  # アカウント名変更日時（新規追加）

    # 複合ユニーク制約を追加：部屋番号 + 出席番号 + ユーザー名の組み合わせでユニーク
    __table_args__ = (
        db.UniqueConstraint('room_number', 'student_id', 'username', 
                          name='unique_room_student_username'),
    )

    # 既存のメソッドはそのまま
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

    # 新規メソッド：アカウント名変更
    def change_username(self, new_username):
        """アカウント名を変更する"""
        if not self.original_username:
            # 初回変更の場合、現在の名前を original_username に保存
            self.original_username = self.username
        
        self.username = new_username
        self.username_changed_at = datetime.now(JST)

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
    school_name = db.Column(db.String(100), default="朋優学院", nullable=False)
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
            'contactEmail': self.contact_email,
            'schoolName': getattr(self, 'school_name', '朋優学院')  # ★ 追加
        }

class PasswordResetToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)  # ★CASCADE追加
    token = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    used_at = db.Column(db.DateTime)
    
    # ★relationshipにpassiveキーワード追加
    user = db.relationship('User', backref=db.backref('reset_tokens', lazy=True, passive_deletes=True))
    
    def is_expired(self):
        """UTCベースで期限チェック"""
        return datetime.utcnow() > self.expires_at
    
    def is_valid(self):
        """UTCベースで有効性チェック"""
        return not self.used and not self.is_expired()

class CsvFileContent(db.Model):
    """CSVファイルの内容をデータベースに保存"""
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), unique=True, nullable=False)
    original_filename = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)  # CSV内容をテキストとして保存
    file_size = db.Column(db.Integer, nullable=False)
    word_count = db.Column(db.Integer, default=0)
    upload_date = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    
    def get_csv_data(self):
        """CSV内容を辞書リストとして返す"""
        try:
            reader = csv.DictReader(StringIO(self.content))
            return list(reader)
        except Exception as e:
            print(f"CSV parsing error: {e}")
            return []

# ====================================================================
# ヘルパー関数
# ====================================================================

# 部屋ごとの単語データを読み込む関数
def load_word_data_for_room(room_number):
    """指定された部屋の単語データを読み込む（完全DB対応版）"""
    try:
        # データベースから部屋設定を取得
        room_setting = RoomSetting.query.filter_by(room_number=room_number).first()
        
        if room_setting and room_setting.csv_filename:
            csv_filename = room_setting.csv_filename
        else:
            csv_filename = "words.csv"
        
        print(f"🔍 部屋{room_number}のCSVファイル: {csv_filename}")
        
        # デフォルトファイルの場合
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
            # ★重要：データベースからカスタムCSVの内容を取得
            csv_file = CsvFileContent.query.filter_by(filename=csv_filename).first()
            if csv_file:
                try:
                    # CSV内容をパース
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
                # フォールバック: デフォルトファイル使用
                print("🔄 デフォルトファイルにフォールバック")
                return load_word_data_for_room("default")
        
        return word_data
        
    except Exception as e:
        print(f"❌ 読み込みエラー: {e}")
        import traceback
        traceback.print_exc()
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

@app.route('/change_username', methods=['GET', 'POST'])
def change_username_page():
    try:
        if 'user_id' not in session:
            flash('ログインが必要です。', 'danger')
            return redirect(url_for('login_page'))
        
        current_user = User.query.get(session['user_id'])
        if not current_user:
            flash('ユーザーが見つかりません。', 'danger')
            return redirect(url_for('logout'))
        
        if request.method == 'POST':
            room_password = request.form.get('room_password')
            individual_password = request.form.get('individual_password')
            new_username = request.form.get('new_username', '').strip()
            
            # パスワード認証
            if not current_user.check_room_password(room_password):
                flash('入室パスワードが間違っています。', 'danger')
                context = get_template_context()
                context['current_user'] = current_user
                return render_template('change_username.html', **context)
            
            if not current_user.check_individual_password(individual_password):
                flash('個別パスワードが間違っています。', 'danger')
                context = get_template_context()
                context['current_user'] = current_user
                return render_template('change_username.html', **context)
            
            # 新しいユーザー名の検証
            if not new_username:
                flash('新しいアカウント名を入力してください。', 'danger')
                context = get_template_context()
                context['current_user'] = current_user
                return render_template('change_username.html', **context)
            
            if len(new_username) > 80:
                flash('アカウント名は80文字以内で入力してください。', 'danger')
                context = get_template_context()
                context['current_user'] = current_user
                return render_template('change_username.html', **context)
            
            # 同じ部屋内での重複チェック
            existing_user = User.query.filter_by(
                room_number=current_user.room_number,
                username=new_username
            ).first()
            
            if existing_user and existing_user.id != current_user.id:
                flash(f'部屋{current_user.room_number}には既に「{new_username}」というアカウント名が存在します。', 'danger')
                context = get_template_context()
                context['current_user'] = current_user
                return render_template('change_username.html', **context)
            
            # アカウント名変更の実行
            old_username = current_user.username
            current_user.change_username(new_username)
            
            try:
                db.session.commit()
                
                # セッションのユーザー名も更新
                session['username'] = new_username
                
                flash(f'アカウント名を「{old_username}」から「{new_username}」に変更しました。', 'success')
                return redirect(url_for('index'))
                
            except Exception as e:
                db.session.rollback()
                flash(f'アカウント名の変更中にエラーが発生しました: {str(e)}', 'danger')
        
        context = get_template_context()
        context['current_user'] = current_user
        return render_template('change_username.html', **context)
        
    except Exception as e:
        print(f"Error in change_username_page: {e}")
        import traceback
        traceback.print_exc()
        flash('システムエラーが発生しました。', 'danger')
        return redirect(url_for('index'))

# データベースマイグレーション関数
# app.py の migrate_database() 関数を以下に置き換えてください

def migrate_database():
    """データベーススキーマの変更を処理する（外部キー制約修正版）"""
    with app.app_context():
        print("🔄 データベースマイグレーションを開始...")
        
        try:
            inspector = inspect(db.engine)
            
            # 1. Userテーブルの確認
            if inspector.has_table('user'):
                columns = [col['name'] for col in inspector.get_columns('user')]
                print(f"📋 既存のUserテーブルカラム: {columns}")
                
                # アカウント名変更機能用のカラムを追加
                if 'original_username' not in columns:
                    print("🔧 original_usernameカラムを追加します...")
                    with db.engine.connect() as conn:
                        # 新しいカラムを追加
                        conn.execute(text('ALTER TABLE "user" ADD COLUMN original_username VARCHAR(80)'))
                        # 既存ユーザーの original_username を現在の username で初期化
                        conn.execute(text('UPDATE "user" SET original_username = username WHERE original_username IS NULL'))
                        # NOT NULL制約を追加
                        conn.execute(text('ALTER TABLE "user" ALTER COLUMN original_username SET NOT NULL'))
                        conn.commit()
                    print("✅ original_usernameカラムを追加しました。")
                
                if 'username_changed_at' not in columns:
                    print("🔧 username_changed_atカラムを追加します...")
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE "user" ADD COLUMN username_changed_at TIMESTAMP'))
                        conn.commit()
                    print("✅ username_changed_atカラムを追加しました。")
                
                # パスワードハッシュフィールドの文字数制限を拡張
                print("🔧 パスワードハッシュフィールドの文字数制限を拡張します...")
                with db.engine.connect() as conn:
                    try:
                        conn.execute(text('ALTER TABLE "user" ALTER COLUMN _room_password_hash TYPE VARCHAR(255)'))
                        conn.execute(text('ALTER TABLE "user" ALTER COLUMN _individual_password_hash TYPE VARCHAR(255)'))
                        conn.commit()
                        print("✅ パスワードハッシュフィールドを255文字に拡張しました。")
                    except Exception as alter_error:
                        print(f"⚠️ カラム変更エラー: {alter_error}")
                
                # last_loginカラムの確認・追加
                if 'last_login' not in columns:
                    print("🔧 last_loginカラムを追加します...")
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE "user" ADD COLUMN last_login TIMESTAMP'))
                        conn.commit()
                    print("✅ last_loginカラムを追加しました。")
            
            # 2. RoomSettingテーブルの確認
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
            
            # 3. App_infoテーブルの確認（★重要な修正箇所）
            if inspector.has_table('app_info'):
                columns = [col['name'] for col in inspector.get_columns('app_info')]
                print(f"📋 既存のAppInfoテーブルカラム: {columns}")
                
                # school_nameカラムの追加
                if 'school_name' not in columns:
                    print("🔧 school_nameカラムを追加します...")
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE app_info ADD COLUMN school_name VARCHAR(100) DEFAULT \'朋優学院\''))
                        conn.commit()
                    print("✅ school_nameカラムを追加しました。")
                
                # 他の不足カラムもチェック
                required_columns = {
                    'app_settings': 'TEXT DEFAULT \'{}\'',
                    'created_at': 'TIMESTAMP',
                    'updated_at': 'TIMESTAMP',
                    'updated_by': 'VARCHAR(80) DEFAULT \'system\''
                }
                
                for col_name, col_definition in required_columns.items():
                    if col_name not in columns:
                        print(f"🔧 {col_name}カラムを追加します...")
                        with db.engine.connect() as conn:
                            conn.execute(text(f'ALTER TABLE app_info ADD COLUMN {col_name} {col_definition}'))
                            conn.commit()
                        print(f"✅ {col_name}カラムを追加しました。")
            
            # 4. その他のテーブル確認（password_reset_token, csv_file_content等）
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
            
            # 5. CsvFileContentテーブルの確認
            if not inspector.has_table('csv_file_content'):
                print("🔧 csv_file_contentテーブルを作成します...")
                db.create_all()
                print("✅ csv_file_contentテーブルを作成しました。")
            else:
                print("✅ csv_file_contentテーブルは既に存在します。")
            
            fix_foreign_key_constraints()
            
            print("✅ データベースマイグレーションが完了しました。")
            
        except Exception as e:
            print(f"⚠️ マイグレーション中にエラーが発生しました: {e}")
            import traceback
            traceback.print_exc()
            
            # エラーが発生した場合のフォールバック処理
            try:
                db.session.rollback()
                print("🔄 トランザクションをロールバックしました")
            except:
                pass

def verify_database_connection():
    """データベース接続確認関数"""
    try:
        with app.app_context():
            # PostgreSQLの場合の接続確認
            if is_postgres:
                db.engine.execute(text('SELECT 1'))
                print("✅ PostgreSQL接続確認: 成功")
            else:
                # SQLiteの場合の接続確認
                db.engine.execute(text('SELECT 1'))
                print("✅ SQLite接続確認: 成功")
            
            return True
            
    except Exception as e:
        print(f"❌ データベース接続エラー: {e}")
        return False

def diagnose_database_environment():
    """データベース環境の詳細診断"""
    print("\n=== データベース環境診断 ===")
    
    # 環境変数の確認
    database_url = os.environ.get('DATABASE_URL', '未設定')
    render_env = os.environ.get('RENDER', 'false') == 'true'
    
    print(f"DATABASE_URL: {'設定済み' if database_url != '未設定' else '未設定'}")
    print(f"RENDER環境: {render_env}")
    print(f"is_postgres: {is_postgres}")
    
    # SQLAlchemyエンジンの状態確認
    try:
        engine_info = str(db.engine.url)
        # パスワード部分をマスク
        if '@' in engine_info:
            parts = engine_info.split('@')
            if ':' in parts[0]:
                user_pass = parts[0].split(':')
                if len(user_pass) > 1:
                    masked = user_pass[0] + ':***@' + '@'.join(parts[1:])
                    engine_info = masked
        
        print(f"SQLAlchemy Engine: {engine_info}")
        
    except Exception as e:
        print(f"SQLAlchemy Engine確認エラー: {e}")
    
    print("========================\n")

# データベース初期化関数（完全リセット対応版）
# app.py の create_tables_and_admin_user() 関数を以下に置き換えてください

def create_tables_and_admin_user():
    """データベース初期化関数（マイグレーション付き）"""
    try:
        with app.app_context():
            logger.info("🔧 データベース初期化を開始...")
            
            # データベース接続確認
            try:
                with db.engine.connect() as conn:
                    conn.execute(text('SELECT 1'))
                logger.info("✅ データベース接続確認")
            except Exception as e:
                logger.error(f"❌ データベース接続失敗: {e}")
                return
            
            # テーブル作成
            db.create_all()
            logger.info("✅ テーブルを確認/作成しました。")
            
            # ★ 重要：マイグレーションを強制実行
            try:
                logger.info("🔄 データベースマイグレーションを実行中...")
                migrate_database()
                logger.info("✅ マイグレーション完了")
            except Exception as migration_error:
                logger.error(f"⚠️ マイグレーションエラー: {migration_error}")
                # マイグレーションが失敗してもアプリは起動を続行
            
            # 管理者ユーザー確認/作成
            try:
                admin_user = User.query.filter_by(username='admin', room_number='ADMIN').first()
                
                if not admin_user:
                    logger.info("👤 管理者ユーザーを作成します...")
                    admin_user = User(
                        username='admin',
                        original_username='admin',  # ★ 追加
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
                    logger.info("✅ 管理者ユーザー 'admin' を作成しました")
                else:
                    logger.info("✅ 管理者ユーザー 'admin' は既に存在します。")
                    
            except Exception as e:
                logger.error(f"⚠️ 管理者ユーザー処理エラー: {e}")
                db.session.rollback()
                
            # アプリ情報確認/作成
            try:
                app_info = AppInfo.get_current_info()
                logger.info("✅ アプリ情報を確認/作成しました")
                
            except Exception as e:
                logger.error(f"⚠️ アプリ情報処理エラー: {e}")
                
            logger.info("🎉 データベース初期化が完了しました！")
                
    except Exception as e:
        logger.error(f"❌ データベース初期化エラー: {e}")
        raise
    
# ===== データ永続化チェック機能 =====
def check_data_persistence():
    """データの永続化状況をチェック"""
    try:
        with app.app_context():  # ★ アプリケーションコンテキストを追加
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

# ヘルパー関数
def generate_reset_token():
    """セキュアなリセットトークンを生成"""
    return secrets.token_urlsafe(32)

def generate_temp_password():
    """一時パスワードを生成"""
    characters = string.ascii_letters + string.digits
    return ''.join(secrets.choice(characters) for _ in range(8))

# app.py のメール送信関数を以下に置き換え

def send_password_reset_email(user, email, token):
    """パスワード再発行メールを送信（エラーハンドリング強化版）"""
    try:
        print(f"🔍 メール送信開始: {email}")
        
        # メール設定の再確認
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
        
        # AppInfo取得
        app_info = AppInfo.get_current_info()
        
        # リセットURL生成
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
        
        # メッセージ作成
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
        
        # メール送信
        print(f"🔍 メール送信実行中...")
        mail.send(msg)
        print(f"✅ パスワード再発行メール送信成功: {email}")
        
        return True
        
    except Exception as e:
        print(f"❌ メール送信エラー: {e}")
        print(f"❌ エラータイプ: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        
        # 具体的なエラー情報
        if 'authentication' in str(e).lower():
            print("❌ Gmail認証エラー: アプリパスワードを確認してください")
        elif 'connection' in str(e).lower():
            print("❌ 接続エラー: SMTPサーバーへの接続に失敗しました")
        elif 'timeout' in str(e).lower():
            print("❌ タイムアウトエラー: ネットワーク接続を確認してください")
        
        raise e

@app.route('/admin/cleanup_orphaned_tokens', methods=['POST'])
def admin_cleanup_orphaned_tokens():
    """存在しないユーザーを参照するトークンを削除"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限がありません。'}), 403
    
    try:
        # 孤立したトークンを検索
        orphaned_tokens = db.session.query(PasswordResetToken).filter(
            ~PasswordResetToken.user_id.in_(
                db.session.query(User.id)
            )
        ).all()
        
        orphaned_count = len(orphaned_tokens)
        
        # 孤立したトークンを削除
        for token in orphaned_tokens:
            db.session.delete(token)
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': f'{orphaned_count}個の孤立したトークンを削除しました。',
            'deleted_count': orphaned_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
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
            flash('学習を始めるにはログインしてください。', 'info')
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
        
        # ★重要な修正：JavaScriptで使う変数名を変更
        return render_template('index.html',
                                app_info_for_js=app_info_for_js,
                                chapter_data=sorted_all_chapter_unit_status)
    
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
        return render_template('login.html')
        
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

# app.py に以下のルートを追加してください

@app.route('/emergency_fix_db')
def emergency_fix_db():
    """緊急データベース修復"""
    try:
        print("🆘 緊急データベース修復開始...")
        
        # 既存のトランザクションをクリア
        try:
            db.session.rollback()
        except:
            pass
        
        # school_nameカラムが存在しないエラーを修正
        with db.engine.connect() as conn:
            # 現在のapp_infoテーブルの構造を確認
            try:
                result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'app_info'"))
                existing_columns = [row[0] for row in result.fetchall()]
                print(f"既存カラム: {existing_columns}")
                
                # school_nameカラムが存在しない場合は追加
                if 'school_name' not in existing_columns:
                    print("🔧 school_nameカラムを追加中...")
                    conn.execute(text("ALTER TABLE app_info ADD COLUMN school_name VARCHAR(100) DEFAULT '朋優学院'"))
                    print("✅ school_nameカラムを追加しました")
                
                # その他の必要なカラムも追加
                missing_columns = {
                    'app_settings': "TEXT DEFAULT '{}'",
                    'created_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                    'updated_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                    'updated_by': "VARCHAR(80) DEFAULT 'system'"
                }
                
                for col_name, col_def in missing_columns.items():
                    if col_name not in existing_columns:
                        print(f"🔧 {col_name}カラムを追加中...")
                        conn.execute(text(f"ALTER TABLE app_info ADD COLUMN {col_name} {col_def}"))
                        print(f"✅ {col_name}カラムを追加しました")
                
                conn.commit()
                
                # 修復後の状態確認
                result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'app_info'"))
                final_columns = [row[0] for row in result.fetchall()]
                print(f"修復後のカラム: {final_columns}")
                
                return f"""
                <h1>✅ 緊急修復完了</h1>
                <p>app_infoテーブルの修復が完了しました。</p>
                <h3>修復前のカラム:</h3>
                <p>{existing_columns}</p>
                <h3>修復後のカラム:</h3>
                <p>{final_columns}</p>
                <p><a href="/admin">管理者ページに戻る</a></p>
                """
                
            except Exception as fix_error:
                print(f"修復エラー: {fix_error}")
                return f"""
                <h1>❌ 修復エラー</h1>
                <p>エラー: {str(fix_error)}</p>
                <p><a href="/admin">管理者ページに戻る</a></p>
                """
                
    except Exception as e:
        print(f"緊急修復失敗: {e}")
        return f"""
        <h1>💥 緊急修復失敗</h1>
        <p>エラー: {str(e)}</p>
        <p>手動でPostgreSQLにアクセスして以下のSQLを実行してください：</p>
        <pre>ALTER TABLE app_info ADD COLUMN school_name VARCHAR(100) DEFAULT '朋優学院';</pre>
        """

# app.py のパスワード再発行リクエストルートを修正

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
                flash('メール送信機能が設定されていないため、パスワード再発行を実行できません。', 'danger')
                context = get_template_context()
                context['mail_configured'] = mail_configured
                return render_template('password_reset_request.html', **context)
            
            user = User.query.filter_by(
                room_number=room_number, 
                student_id=student_id,
                username=username
            ).first()
            
            if not user:
                flash('入力された情報に一致するアカウントが見つかった場合、パスワード再発行のご案内をメールで送信しました。', 'success')
                return redirect(url_for('login_page'))
            
            # 既存の未使用トークンがあれば無効化
            existing_tokens = PasswordResetToken.query.filter_by(user_id=user.id, used=False).all()
            for token in existing_tokens:
                token.used = True
                token.used_at = datetime.utcnow()  # ★ UTCで保存
            
            # ★修正：すべてUTCで統一
            reset_token = generate_reset_token()
            now_utc = datetime.utcnow()
            expires_at_utc = now_utc + timedelta(hours=1)
            
            password_reset_token = PasswordResetToken(
                user_id=user.id,
                token=reset_token,
                expires_at=expires_at_utc  # ★ UTC時刻で保存
            )
            
            db.session.add(password_reset_token)
            db.session.commit()
            
            print(f"🔍 トークン作成時刻（UTC）: {now_utc}")
            print(f"🔍 有効期限（UTC）: {expires_at_utc}")
            
            # メール送信
            try:
                success = send_password_reset_email(user, email, reset_token)
                if success:
                    flash('パスワード再発行のご案内をメールで送信しました。', 'success')
                else:
                    flash('メール送信に失敗しました。', 'danger')
                    password_reset_token.used = True
                    db.session.commit()
            except Exception as email_error:
                print(f"❌ メール送信例外: {email_error}")
                flash('メール送信中にエラーが発生しました。', 'danger')
                password_reset_token.used = True
                db.session.commit()
            
            return redirect(url_for('login_page'))
        
        context = get_template_context()
        context['mail_configured'] = mail_configured
        return render_template('password_reset_request.html', **context)
        
    except Exception as e:
        print(f"Error in password_reset_request: {e}")
        flash('システムエラーが発生しました。', 'danger')
        return redirect(url_for('login_page'))


# 管理者用：期限切れトークンの自動削除（定期実行推奨）
@app.route('/admin/cleanup_expired_tokens', methods=['POST'])
def admin_cleanup_expired_tokens():
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限がありません。'}), 403
    
    try:
        # 期限切れまたは使用済みトークンを削除
        expired_tokens = PasswordResetToken.query.filter(
            (PasswordResetToken.expires_at < datetime.now(JST)) |
            (PasswordResetToken.used == True)
        ).all()
        
        deleted_count = len(expired_tokens)
        
        for token in expired_tokens:
            db.session.delete(token)
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': f'{deleted_count}個の期限切れトークンを削除しました。',
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

# app.py に以下のルートを追加してください

@app.route('/admin/force_migration', methods=['POST'])
def admin_force_migration():
    """手動でデータベースマイグレーションを実行"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
    
    try:
        print("🔧 手動マイグレーション開始...")
        
        # 既存のトランザクションを終了
        try:
            db.session.rollback()
        except:
            pass
        
        # マイグレーション実行
        migrate_database()
        
        # 成功時のレスポンス
        return jsonify({
            'status': 'success',
            'message': 'データベースマイグレーションが完了しました'
        })
        
    except Exception as e:
        print(f"❌ 手動マイグレーションエラー: {e}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'status': 'error',
            'message': f'マイグレーションエラー: {str(e)}'
        }), 500

def fix_foreign_key_constraints():
    """外部キー制約を修正してCASCADEを追加"""
    try:
        with app.app_context():
            print("🔧 外部キー制約の修正を開始...")
            
            # PostgreSQLの場合の制約確認・修正
            if is_postgres:
                with db.engine.connect() as conn:
                    # 既存の外部キー制約を確認
                    result = conn.execute(text("""
                        SELECT constraint_name 
                        FROM information_schema.table_constraints 
                        WHERE table_name = 'password_reset_token' 
                        AND constraint_type = 'FOREIGN KEY'
                    """))
                    
                    existing_constraints = [row[0] for row in result.fetchall()]
                    print(f"📋 既存の外部キー制約: {existing_constraints}")
                    
                    # 既存制約を削除してCASCADE付きで再作成
                    for constraint_name in existing_constraints:
                        try:
                            # 制約削除
                            conn.execute(text(f'ALTER TABLE password_reset_token DROP CONSTRAINT {constraint_name}'))
                            print(f"🗑️ 制約削除: {constraint_name}")
                        except Exception as e:
                            print(f"⚠️ 制約削除エラー ({constraint_name}): {e}")
                    
                    # CASCADE付きの新しい外部キー制約を追加
                    try:
                        conn.execute(text("""
                            ALTER TABLE password_reset_token 
                            ADD CONSTRAINT fk_password_reset_token_user_id 
                            FOREIGN KEY (user_id) REFERENCES "user" (id) ON DELETE CASCADE
                        """))
                        print("✅ CASCADE付き外部キー制約を追加しました")
                    except Exception as e:
                        print(f"⚠️ 新制約追加エラー: {e}")
                    
                    conn.commit()
            
            print("✅ 外部キー制約修正完了")
            
    except Exception as e:
        print(f"❌ 外部キー制約修正エラー: {e}")
        import traceback
        traceback.print_exc()

@app.route('/admin/check_database_status')
def admin_check_database_status():
    """データベースの状態をチェック"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
    
    try:
        inspector = inspect(db.engine)
        
        status = {
            'tables': {},
            'missing_columns': []
        }
        
        # 各テーブルのカラム状況をチェック
        expected_tables = {
            'user': ['original_username', 'username_changed_at', 'last_login'],
            'app_info': ['school_name', 'app_settings', 'created_at', 'updated_at', 'updated_by'],
            'room_setting': ['csv_filename', 'created_at', 'updated_at'],
            'password_reset_token': ['used_at'],
            'csv_file_content': []
        }
        
        for table_name, expected_columns in expected_tables.items():
            if inspector.has_table(table_name):
                existing_columns = [col['name'] for col in inspector.get_columns(table_name)]
                missing = [col for col in expected_columns if col not in existing_columns]
                
                status['tables'][table_name] = {
                    'exists': True,
                    'columns': existing_columns,
                    'missing_columns': missing
                }
                
                if missing:
                    status['missing_columns'].extend([f"{table_name}.{col}" for col in missing])
            else:
                status['tables'][table_name] = {
                    'exists': False,
                    'columns': [],
                    'missing_columns': expected_columns
                }
                status['missing_columns'].extend([f"{table_name}.{col}" for col in expected_columns])
        
        return jsonify({
            'status': 'success',
            'database_status': status,
            'needs_migration': len(status['missing_columns']) > 0
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'データベース状態チェックエラー: {str(e)}'
        }), 500

# パスワードリセット実行
@app.route('/password_reset/<token>', methods=['GET', 'POST'])
def password_reset(token):
    try:
        print(f"🔍 パスワードリセット処理開始: {token}")
        
        reset_token = PasswordResetToken.query.filter_by(token=token).first()
        
        if not reset_token:
            print("❌ トークンがデータベースに見つかりません")
            flash('無効なリンクです。', 'danger')
            return redirect(url_for('password_reset_request'))
        
        # ★修正：すべてUTCで比較
        now_utc = datetime.utcnow()
        expires_at_utc = reset_token.expires_at
        
        print(f"🔍 現在時刻（UTC）: {now_utc}")
        print(f"🔍 有効期限（UTC）: {expires_at_utc}")
        print(f"🔍 使用済みフラグ: {reset_token.used}")
        
        # UTC同士で比較
        is_expired = now_utc > expires_at_utc
        is_used = reset_token.used
        
        print(f"🔍 期限切れ: {is_expired}")
        print(f"🔍 使用済み: {is_used}")
        
        if is_used:
            flash('このリンクは既に使用されています。', 'danger')
            return redirect(url_for('password_reset_request'))
        
        if is_expired:
            flash('リンクの有効期限が切れています。', 'danger')
            return redirect(url_for('password_reset_request'))
        
        if request.method == 'POST':
            new_password = request.form.get('new_password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            
            if not new_password or not confirm_password:
                flash('パスワードを入力してください。', 'danger')
            elif new_password != confirm_password:
                flash('パスワードが一致しません。', 'danger')
            elif len(new_password) < 6:
                flash('パスワードは6文字以上で入力してください。', 'danger')
            else:
                # パスワード更新
                user = reset_token.user
                user.set_individual_password(new_password)
                
                # トークンを使用済みにする
                reset_token.used = True
                reset_token.used_at = datetime.utcnow()  # ★ UTCで保存
                
                db.session.commit()
                
                print(f"✅ パスワード更新完了: ユーザー {user.username}")
                flash('パスワードが正常に更新されました。', 'success')
                return redirect(url_for('login_page'))
        
        # GET リクエスト時 - 残り時間をJST表示用に変換
        time_remaining = expires_at_utc - now_utc
        minutes_remaining = max(0, int(time_remaining.total_seconds() / 60))
        
        print(f"🔍 残り時間: {minutes_remaining}分")
        
        context = get_template_context()
        context.update({
            'token': token,
            'user': reset_token.user,
            'minutes_remaining': minutes_remaining
        })
        
        return render_template('password_reset.html', **context)
        
    except Exception as e:
        print(f"❌ パスワードリセットエラー: {e}")
        flash('システムエラーが発生しました。', 'danger')
        return redirect(url_for('login_page'))

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

@app.route('/debug/app_info_comparison')
def debug_app_info_comparison():
    """デバッグ用: 両方の関数の返り値を比較"""
    if not session.get('admin_logged_in'):
        return "管理者ログインが必要です", 403
    
    try:
        # get_template_context()の結果
        context = get_template_context()
        template_app_info = context.get('app_info')
        
        # get_app_info_dict()の結果
        dict_app_info = get_app_info_dict(
            user_id=session.get('user_id'),
            username=session.get('username'),
            room_number=session.get('room_number')
        )
        
        result = {
            'template_context_app_info': {
                'type': str(type(template_app_info)),
                'app_name': getattr(template_app_info, 'app_name', 'N/A') if template_app_info else None,
                'footer_text': getattr(template_app_info, 'footer_text', 'N/A') if template_app_info else None,
                'is_none': template_app_info is None
            },
            'dict_app_info': dict_app_info,
            'database_direct_query': None
        }
        
        # データベースから直接取得
        try:
            db_app_info = AppInfo.query.first()
            if db_app_info:
                result['database_direct_query'] = {
                    'app_name': db_app_info.app_name,
                    'footer_text': db_app_info.footer_text,
                    'contact_email': db_app_info.contact_email
                }
        except Exception as e:
            result['database_direct_query'] = f"エラー: {str(e)}"
        
        return f"<pre>{json.dumps(result, indent=2, ensure_ascii=False)}</pre>"
        
    except Exception as e:
        return f"エラー: {str(e)}"

@app.route('/api/clear_quiz_progress', methods=['POST'])
def api_clear_quiz_progress():
    return jsonify(status='success', message='一時的なクイズ進捗クリア要求を受信しました（サーバー側は変更なし）。')

@app.route('/debug/check_token/<token>')
def debug_check_token(token):
    """デバッグ用：トークンの状態確認"""
    if not session.get('admin_logged_in'):
        return "管理者権限が必要です", 403
    
    reset_token = PasswordResetToken.query.filter_by(token=token).first()
    if not reset_token:
        return "トークンが見つかりません", 404
    
    now_jst = datetime.now(JST)
    
    return f"""
    <h2>トークン診断結果</h2>
    <p>現在時刻（JST）: {now_jst}</p>
    <p>トークン作成時刻: {reset_token.created_at}</p>
    <p>有効期限: {reset_token.expires_at}</p>
    <p>使用済みフラグ: {reset_token.used}</p>
    <p>使用時刻: {reset_token.used_at}</p>
    <p>有効性: {'有効' if reset_token.is_valid() else '無効'}</p>
    """


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
        
        # 部屋ごとの単語データを取得
        word_data = load_word_data_for_room(current_user.room_number)
        print(f"部屋の単語データ数: {len(word_data)}")
        
        room_setting = RoomSetting.query.filter_by(room_number=current_user.room_number).first()
        max_enabled_unit_num_str = room_setting.max_enabled_unit_number if room_setting else "9999"
        parsed_max_enabled_unit_num = parse_unit_number(max_enabled_unit_num_str)
        print(f"最大単元番号: {max_enabled_unit_num_str}")

        # ★修正：章ごとに進捗をまとめる
        chapter_progress_summary = {}

        # 有効な単語データで単元進捗を初期化
        for word in word_data:
            chapter_num = word['chapter']
            unit_num = word['number']
            category_name = word.get('category', '未分類')
            
            is_word_enabled_in_csv = word['enabled']
            is_unit_enabled_by_room_setting = parse_unit_number(unit_num) <= parsed_max_enabled_unit_num

            if is_word_enabled_in_csv and is_unit_enabled_by_room_setting:
                # 章の初期化
                if chapter_num not in chapter_progress_summary:
                    chapter_progress_summary[chapter_num] = {
                        'chapter_name': f'第{chapter_num}章',
                        'units': {},
                        'total_questions': 0,
                        'total_mastered': 0
                    }
                
                # 単元の初期化
                if unit_num not in chapter_progress_summary[chapter_num]['units']:
                    chapter_progress_summary[chapter_num]['units'][unit_num] = {
                        'categoryName': category_name,
                        'attempted_problems': set(),
                        'mastered_problems': set(),
                        'total_questions_in_unit': 0,
                        'total_attempts': 0
                    }
                
                chapter_progress_summary[chapter_num]['units'][unit_num]['total_questions_in_unit'] += 1
                chapter_progress_summary[chapter_num]['total_questions'] += 1

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
                chapter_number = matched_word['chapter']
                unit_number = matched_word['number']
                
                is_word_enabled_in_csv = matched_word['enabled']
                is_unit_enabled_by_room_setting = parse_unit_number(unit_number) <= parsed_max_enabled_unit_num

                if (is_word_enabled_in_csv and is_unit_enabled_by_room_setting and 
                    chapter_number in chapter_progress_summary and
                    unit_number in chapter_progress_summary[chapter_number]['units']):
                    
                    correct_attempts = history.get('correct_attempts', 0)
                    incorrect_attempts = history.get('incorrect_attempts', 0)
                    total_problem_attempts = correct_attempts + incorrect_attempts
                    
                    unit_data = chapter_progress_summary[chapter_number]['units'][unit_number]
                    unit_data['total_attempts'] += total_problem_attempts
                    
                    if total_problem_attempts > 0:
                        unit_data['attempted_problems'].add(problem_id)
                        
                        # マスター判定：正答率80%以上
                        accuracy_rate = (correct_attempts / total_problem_attempts) * 100
                        if accuracy_rate >= 80.0:
                            unit_data['mastered_problems'].add(problem_id)
                            chapter_progress_summary[chapter_number]['total_mastered'] += 1
            else:
                unmatched_problems += 1

        # データを整理してテンプレートに渡す形式に変換
        sorted_chapter_progress = {}
        for chapter_num in sorted(chapter_progress_summary.keys(), key=lambda x: int(x) if x.isdigit() else float('inf')):
            chapter_data = chapter_progress_summary[chapter_num]
            
            # 単元データをソートして配列に変換
            sorted_units = []
            for unit_num in sorted(chapter_data['units'].keys(), key=lambda x: parse_unit_number(x)):
                unit_data = chapter_data['units'][unit_num]
                sorted_units.append({
                    'unit_num': unit_num,
                    'category_name': unit_data['categoryName'],
                    'attempted_problems': list(unit_data['attempted_problems']),
                    'mastered_problems': list(unit_data['mastered_problems']),
                    'total_questions_in_unit': unit_data['total_questions_in_unit'],
                    'total_attempts': unit_data['total_attempts']
                })
            
            sorted_chapter_progress[chapter_num] = {
                'chapter_name': chapter_data['chapter_name'],
                'units': sorted_units,
                'total_questions': chapter_data['total_questions'],
                'total_mastered': chapter_data['total_mastered']
            }

        print(f"章別進捗: {len(sorted_chapter_progress)}章")

        # ランキング計算（既存のコード）
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
            
            # ベイズ統計による正答率補正の設定値
            EXPECTED_AVG_ACCURACY = 0.7
            CONFIDENCE_ATTEMPTS = 10
            PRIOR_CORRECT = EXPECTED_AVG_ACCURACY * CONFIDENCE_ATTEMPTS
            PRIOR_ATTEMPTS = CONFIDENCE_ATTEMPTS

            # ベイズ統計による総合評価型スコア計算
            if total_attempts == 0:
                comprehensive_score = 0
            else:
                bayesian_accuracy = (PRIOR_CORRECT + total_correct) / (PRIOR_ATTEMPTS + total_attempts)
                
                comprehensive_score = (
                    (user_mastered_count ** 1.3) * 10 +
                    (bayesian_accuracy ** 2) * 500 +
                    math.log(total_attempts + 1) * 20
                ) / 100

            ranking_data.append({
                'username': user_obj.username,
                'total_attempts': total_attempts,
                'total_correct': total_correct,
                'accuracy_rate': (total_correct / total_attempts * 100) if total_attempts > 0 else 0,
                'coverage_rate': coverage_rate,
                'mastered_count': user_mastered_count,
                'total_questions_for_room': total_questions_for_room_ranking,
                'balance_score': comprehensive_score 
            })

        # バランススコアで降順ソート
        ranking_data.sort(key=lambda x: (x['balance_score'], x['total_attempts']), reverse=True)
        top_10_ranking = ranking_data[:10]

        print(f"ランキング対象ユーザー数: {len(ranking_data)}")
        print("=== 進捗ページ処理完了 ===\n")

        context = get_template_context()
        
        return render_template('progress.html',
                               current_user=current_user,
                               user_progress_by_chapter=sorted_chapter_progress,  # ★変更
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
        
        # ユーザー情報を拡張（元のアカウント名と変更履歴を含む）
        user_list_with_details = []
        for user in users:
            if user.username == 'admin':
                continue
                
            user_details = {
                'id': user.id,
                'username': user.username,
                'original_username': user.original_username if user.original_username else user.username,
                'room_number': user.room_number,
                'student_id': user.student_id,
                'last_login': user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else 'なし',
                'username_changed': user.original_username and user.original_username != user.username,
                'username_changed_at': user.username_changed_at.strftime('%Y-%m-%d %H:%M:%S') if user.username_changed_at else None
            }
            user_list_with_details.append(user_details)
        
        # 部屋番号のリストを取得
        unique_room_numbers = set()
        for user in users:
            if user.room_number != 'ADMIN':
                unique_room_numbers.add(user.room_number)
        
        for setting in room_settings:
            if setting.room_number != 'ADMIN':
                unique_room_numbers.add(setting.room_number)
        
        # デフォルト設定の作成処理...
        for room_num in unique_room_numbers:
            if room_num not in room_csv_settings:
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
        except Exception as e:
            print(f"⚠️ デフォルト設定作成エラー: {e}")
            db.session.rollback()
        
        context = get_template_context()
        
        template_context = {
            'users': user_list_with_details,
            'room_max_unit_settings': room_max_unit_settings,
            'room_csv_settings': room_csv_settings
        }
        
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
                app_info.school_name = request.form.get('school_name', '朋優学院').strip()
                
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

        # 部屋番号 + ユーザー名の組み合わせでの重複チェック
        existing_user = User.query.filter_by(
            room_number=room_number, 
            username=username
        ).first()
                    
        if existing_user:
            flash(f'部屋{room_number}にユーザー名{username}は既に存在します。', 'danger')
            return redirect(url_for('admin_page'))

        new_user = User(
        room_number=room_number,
        student_id=student_id,
        username=username,
        original_username=username  # ★ 追加：初回登録時は同じ名前を設定
        )
        new_user.set_room_password(room_password)
        new_user.set_individual_password(individual_password)
        new_user.problem_history = "{}"
        new_user.incorrect_words = "[]"
        new_user.last_login = datetime.now(JST)

        db.session.add(new_user)
        db.session.commit()
        
        # 部屋設定の自動作成（既存のコード）
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

        username = user_to_delete.username
        room_number = user_to_delete.room_number
        student_id = user_to_delete.student_id

        # ★重要：関連するパスワードリセットトークンを先に削除
        try:
            reset_tokens = PasswordResetToken.query.filter_by(user_id=user_id).all()
            token_count = len(reset_tokens)
            
            for token in reset_tokens:
                db.session.delete(token)
            
            print(f"🗑️ 削除されたパスワードリセットトークン: {token_count}個")
            
        except Exception as token_error:
            print(f"⚠️ トークン削除エラー: {token_error}")
            # トークン削除エラーでも処理を続行

        # ★ユーザー本体を削除
        db.session.delete(user_to_delete)
        db.session.commit()
        
        flash(f'✅ ユーザー "{username}" (部屋番号: {room_number}, 出席番号: {student_id}) を削除しました。', 'success')
        
        if token_count > 0:
            flash(f'📧 関連するパスワードリセットトークン {token_count}個も削除されました。', 'info')
        
        return redirect(url_for('admin_page'))
        
    except Exception as e:
        print(f"❌ ユーザー削除エラー: {e}")
        import traceback
        traceback.print_exc()
        
        db.session.rollback()
        flash(f'ユーザー削除中にエラーが発生しました: {str(e)}', 'danger')
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

        # ★重要：ファイル内容を読み取り（ファイルシステムには保存しない）
        content = file.read().decode('utf-8')
        filename = secure_filename(file.filename)
        original_filename = file.filename
        file_size = len(content.encode('utf-8'))
        
        print(f"📁 ファイル情報: {filename}, サイズ: {file_size}bytes")
        
        # CSVファイルの形式を検証
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

# admin_list_room_csv_filesルートもデバッグ版に修正
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

    # ヘッダー行
    cw.writerow(['部屋番号', '入室パスワードハッシュ', '出席番号', 'アカウント名', '個別パスワードハッシュ'])

    for user in users:
        cw.writerow([
            user.room_number,
            user._room_password_hash,
            user.student_id,
            user.username,
            user._individual_password_hash
        ])
    
    # ★ Shift_JISエンコーディングで文字化け対策
    try:
        output = si.getvalue().encode('shift_jis')
        mimetype = "text/csv; charset=shift_jis"
    except UnicodeEncodeError:
        output = '\ufeff' + si.getvalue()
        output = output.encode('utf-8')
        mimetype = "text/csv; charset=utf-8"
    
    response = Response(output, mimetype=mimetype)
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

    # ヘッダー行
    cw.writerow(['部屋番号', '有効な最大単元番号', 'CSVファイル名'])

    for setting in room_settings:
        cw.writerow([setting.room_number, setting.max_enabled_unit_number, setting.csv_filename])
    
    # ★ Shift_JISエンコーディングで文字化け対策
    try:
        output = si.getvalue().encode('shift_jis')
        mimetype = "text/csv; charset=shift_jis"
    except UnicodeEncodeError:
        output = '\ufeff' + si.getvalue()
        output = output.encode('utf-8')
        mimetype = "text/csv; charset=utf-8"
    
    response = Response(output, mimetype=mimetype)
    response.headers["Content-Disposition"] = "attachment; filename=room_settings_data.csv"
    return response

@app.route('/admin/download_users_template_csv')
def download_users_template_csv():
    if not session.get('admin_logged_in'):
        flash('管理者権限がありません。', 'danger')
        return redirect(url_for('login_page'))

    si = StringIO()
    cw = csv.writer(si)
    
    # ヘッダー行
    cw.writerow(['部屋番号', '入室パスワード', '出席番号', '個別パスワード', 'アカウント名'])
    
    # サンプルデータを追加
    cw.writerow(['101', '2024101', '1', 'TemplarsGoldIsMine', 'フィリップ4世'])
    cw.writerow(['101', '2024101', '2', 'RomeIsEternal', 'ボニファティウス8世'])
    cw.writerow(['102', '2024102', '1', 'LetsGoAvignon', 'クレメンス5世'])
    
    # ★ Shift_JISエンコーディングで文字化け対策
    try:
        output = si.getvalue().encode('shift_jis')
        mimetype = "text/csv; charset=shift_jis"
    except UnicodeEncodeError:
        output = '\ufeff' + si.getvalue()
        output = output.encode('utf-8')
        mimetype = "text/csv; charset=utf-8"
    
    response = Response(output, mimetype=mimetype)
    response.headers["Content-Disposition"] = "attachment; filename=users_template.csv"
    return response

@app.route('/admin/download_csv_template')
def download_csv_template():
    """部屋用CSVテンプレートダウンロード"""
    if not session.get('admin_logged_in'):
        flash('管理者権限がありません。', 'danger')
        return redirect(url_for('login_page'))

    si = StringIO()
    cw = csv.writer(si)
    
    # ヘッダー行
    cw.writerow(['chapter', 'number', 'category', 'question', 'answer', 'enabled'])
    
    # サンプルデータを追加
    cw.writerow(['1', '1', '古代エジプト', 'ファラオの墓とされる巨大な建造物は？', 'ピラミッド', '1'])
    cw.writerow(['1', '2', '古代エジプト２', '古代エジプトの象形文字を何という？', 'ヒエログリフ', '1'])
    cw.writerow(['1', '3', '古代メソポタミア', 'シュメール人が発明した文字は？', '楔形文字', '1'])
    cw.writerow(['2', '1', 'فارسی', 'هویو', 'Hōyū', '1'])
    cw.writerow(['2', '2', '古代ローマ', 'ローマ帝国初代皇帝に与えられた称号は？', 'アウグストゥス', '1'])
    
    # ★ Shift_JISエンコーディングで文字化け対策
    try:
        output = si.getvalue().encode('shift_jis')
        mimetype = "text/csv; charset=shift_jis"
    except UnicodeEncodeError:
        output = '\ufeff' + si.getvalue()
        output = output.encode('utf-8')
        mimetype = "text/csv; charset=utf-8"
    
    response = Response(output, mimetype=mimetype)
    response.headers["Content-Disposition"] = "attachment; filename=words_template.csv"
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
@app.context_processor
def inject_app_info():
    """
    全テンプレートでアプリ情報を使用できるようにするcontext processor
    """
    try:
        app_info = AppInfo.get_current_info()
        
        # セッション情報を取得
        user_id = session.get('user_id')
        username = session.get('username')
        room_number = session.get('room_number')
        is_admin = session.get('admin_logged_in', False)
        
        return {
            'app_info': app_info,
            'app_name': app_info.app_name,  # {{ app_name }} で直接使用可能
            'app_version': app_info.version,
            'app_last_updated': app_info.last_updated_date,
            'app_update_content': app_info.update_content,
            'app_footer_text': app_info.footer_text,
            'app_contact_email': app_info.contact_email,
            'app_school_name': app_info.school_name,
            'current_user_id': user_id,
            'current_username': username,
            'current_room_number': room_number,
            'is_logged_in': user_id is not None,
            'is_admin_logged_in': is_admin
        }
    except Exception as e:
        logger.error(f"Context processor error: {e}")
        # エラー時はデフォルト値を返す
        return {
            'app_info': None,
            'app_name': '世界史単語帳',
            'app_version': '1.0.0',
            'app_last_updated': '2025年6月15日',
            'app_update_content': 'アプリケーションが開始されました。',
            'app_footer_text': '',
            'app_contact_email': '',
            'app_school_name': '朋優学院',
            'current_user_id': session.get('user_id'),
            'current_username': session.get('username'),
            'current_room_number': session.get('room_number'),
            'is_logged_in': session.get('user_id') is not None,
            'is_admin_logged_in': session.get('admin_logged_in', False)
        }

def get_template_context():
    """全テンプレートで共通に使用するコンテキストを取得"""
    try:
        app_info = AppInfo.get_current_info()
        return {'app_info': app_info}
    except Exception as e:
        logger.error(f"Error getting app_info: {e}")
        return {'app_info': None}

@app.route('/debug/timezone_check')
def debug_timezone_check():
    if not session.get('admin_logged_in'):
        return "管理者権限が必要です", 403
    
    try:
        # PostgreSQLのタイムゾーン設定を確認（新しいSQLAlchemy形式）
        with db.engine.connect() as conn:
            result = conn.execute(text("SELECT current_setting('TIMEZONE')")).fetchone()
            pg_timezone = result[0] if result else 'Unknown'
            
            # PostgreSQLで現在時刻を取得
            pg_now_result = conn.execute(text("SELECT NOW()")).fetchone()
            pg_now = pg_now_result[0] if pg_now_result else 'Unknown'
            
            pg_now_jst_result = conn.execute(text("SELECT NOW() AT TIME ZONE 'Asia/Tokyo'")).fetchone()
            pg_now_jst = pg_now_jst_result[0] if pg_now_jst_result else 'Unknown'
        
        # 現在時刻の各パターンを確認
        now_python = datetime.now()
        now_python_jst = datetime.now(JST)
        now_utc = datetime.utcnow()
        
        return f"""
        <h2>タイムゾーン診断</h2>
        <p><strong>PostgreSQLタイムゾーン:</strong> {pg_timezone}</p>
        <p><strong>Python datetime.now():</strong> {now_python}</p>
        <p><strong>Python datetime.now(JST):</strong> {now_python_jst}</p>
        <p><strong>Python datetime.utcnow():</strong> {now_utc}</p>
        <p><strong>PostgreSQL NOW():</strong> {pg_now}</p>
        <p><strong>PostgreSQL NOW() AT TIME ZONE 'Asia/Tokyo':</strong> {pg_now_jst}</p>
        <hr>
        <h3>問題の分析</h3>
        <p>PostgreSQLが UTC なら、Pythonの datetime.utcnow() と PostgreSQL NOW() が一致するはずです。</p>
        <p>JST設定なら、Python datetime.now(JST) と PostgreSQL NOW() が一致するはずです。</p>
        """
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        return f"""
        <h2>エラー詳細</h2>
        <p><strong>エラー:</strong> {str(e)}</p>
        <pre>{error_detail}</pre>
        """

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

@app.route('/admin/check_all_users')
def admin_check_all_users():
    """すべてのユーザーデータを詳細確認"""
    if not session.get('admin_logged_in'):
        return jsonify(error='管理者権限が必要です'), 403
    
    try:
        # 全ユーザーを取得
        all_users = User.query.all()
        
        user_details = []
        for user in all_users:
            user_details.append({
                'id': user.id,
                'username': user.username,
                'room_number': user.room_number,
                'student_id': user.student_id,
                'last_login': user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else 'なし',
                'problem_history_count': len(json.loads(user.problem_history or '{}')),
                'incorrect_words_count': len(json.loads(user.incorrect_words or '[]'))
            })
        
        # 部屋別集計
        room_stats = {}
        for user in all_users:
            if user.room_number not in room_stats:
                room_stats[user.room_number] = 0
            room_stats[user.room_number] += 1
        
        return jsonify({
            'total_users': len(all_users),
            'room_stats': room_stats,
            'user_details': user_details
        })
        
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/score_details')
def score_details():
    """スコア算出方法の詳細ページ"""
    context = get_template_context()
    return render_template('score_details.html', **context)

# 起動時ログを改善
def enhanced_startup_check():
    """起動時の詳細チェック（修正版）"""
    try:
        with app.app_context():
            print("\n" + "="*60)
            print("🔍 データ永続化確認")
            print("="*60)
            
            # 環境変数確認
            database_url = os.environ.get('DATABASE_URL', '未設定')
            is_render = os.environ.get('RENDER', 'false') == 'true'
            reset_db = os.environ.get('RESET_DATABASE', 'false') == 'true'
            
            print(f"📊 環境: {'Render' if is_render else 'ローカル'}")
            print(f"📊 DATABASE_URL: {'設定済み' if database_url != '未設定' else '未設定'}")
            print(f"📊 RESET_DATABASE: {reset_db}")
            
            # データベース接続確認をコメントアウト
            # if verify_database_connection():
            #     print("✅ データベース接続: 正常")
            # else:
            #     print("❌ データベース接続: 失敗")
            
            print("✅ データベース接続: スキップ")
                
            # テーブル存在確認
            try:
                tables = db.engine.table_names()
                expected_tables = ['user', 'room_setting', 'csv_file_content', 'app_info']
                
                missing_tables = [t for t in expected_tables if t not in tables]
                if missing_tables:
                    print(f"⚠️ 不足テーブル: {missing_tables}")
                else:
                    print("✅ 全テーブル存在確認")
                    
            except Exception as e:
                print(f"⚠️ テーブル確認エラー: {e}")
            
            print("="*60 + "\n")
            
    except Exception as e:
        print(f"❌ 起動チェックエラー: {e}")

# app.pyに追加する診断関数
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

# ===== メイン起動処理の修正 =====
if __name__ == '__main__':
    try:
        # データベース初期化
        create_tables_and_admin_user()
        
        # サーバー起動
        port = int(os.environ.get('PORT', 5001))
        debug_mode = os.environ.get('RENDER') != 'true'
        
        logger.info(f"🌐 サーバーを起動します: http://0.0.0.0:{port}")
        
        app.run(host='0.0.0.0', port=port, debug=debug_mode)
        
    except Exception as e:
        logger.error(f"💥 起動失敗: {e}")
        import traceback
        traceback.print_exc()