import os
import json
import csv
import re
import hashlib
import logging
import math
import time
import secrets
import string
from io import StringIO
from datetime import datetime, timedelta
# 既存のインポートの後に追加
from sqlalchemy import inspect, text, func, case, cast, Integer

# 外部ライブラリ
import pytz
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import inspect, text, func
from functools import wraps

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash('管理者権限がありません。', 'danger')
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

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
    username = db.Column(db.String(80), nullable=False)
    original_username = db.Column(db.String(80), nullable=False)
    room_number = db.Column(db.String(50), nullable=False)
    _room_password_hash = db.Column(db.String(255))
    student_id = db.Column(db.String(50), nullable=False)
    _individual_password_hash = db.Column(db.String(255))
    problem_history = db.Column(db.Text)
    incorrect_words = db.Column(db.Text)
    last_login = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    username_changed_at = db.Column(db.DateTime)
    is_first_login = db.Column(db.Boolean, default=True, nullable=False)
    password_changed_at = db.Column(db.DateTime)
    restriction_triggered = db.Column(db.Boolean, default=False, nullable=False)  # 制限が発動したことがあるか
    restriction_released = db.Column(db.Boolean, default=False, nullable=False)   # 制限が解除されたか
    
    # 複合ユニーク制約
    __table_args__ = (
        db.UniqueConstraint('room_number', 'student_id', 'username', 
                          name='unique_room_student_username'),
    )

    # 既存のメソッドはそのまま
    def set_room_password(self, password):
        self._room_password_hash = generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)

    def check_room_password(self, password):
        return check_password_hash(self._room_password_hash, password)

    def set_individual_password(self, password):
        self._individual_password_hash = generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)

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

    def change_username(self, new_username):
        """アカウント名を変更する"""
        if not self.original_username:
            self.original_username = self.username
        
        self.username = new_username
        self.username_changed_at = datetime.now(JST)
    
    def mark_first_login_completed(self):
        """初回ログインを完了としてマークする"""
        self.is_first_login = False
    
    def change_password_first_time(self, new_password):
        """初回パスワード変更（個別パスワードのみ）"""
        self.set_individual_password(new_password)
        self.password_changed_at = datetime.now(JST)
        self.mark_first_login_completed()
    
    def set_restriction_state(self, triggered, released):
        """制限状態を設定"""
        self.restriction_triggered = triggered
        self.restriction_released = released
    
    def get_restriction_state(self):
        """制限状態を取得"""
        return {
            'hasBeenRestricted': self.restriction_triggered,
            'restrictionReleased': self.restriction_released
        }

class RoomSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(50), unique=True, nullable=False)
    enabled_units = db.Column(db.Text, default="[]", nullable=False)  # ← JSON形式で単元リストを保存
    csv_filename = db.Column(db.String(100), default="words.csv", nullable=False)
    max_enabled_unit_number = db.Column(db.String(50), default="9999", nullable=False)
    ranking_display_count = db.Column(db.Integer, default=10, nullable=False)

    def get_enabled_units(self):
        """有効な単元のリストを取得"""
        try:
            return json.loads(self.enabled_units)
        except:
            return []
    
    def set_enabled_units(self, units_list):
        """有効な単元のリストを設定"""
        self.enabled_units = json.dumps(units_list)

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

class UserStats(db.Model):
    """ユーザーの学習統計を事前計算して保存するテーブル"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, unique=True)
    room_number = db.Column(db.String(50), nullable=False, index=True)  # 高速検索用インデックス
    
    # 基本統計
    total_attempts = db.Column(db.Integer, default=0, nullable=False)
    total_correct = db.Column(db.Integer, default=0, nullable=False)
    mastered_count = db.Column(db.Integer, default=0, nullable=False)
    incorrect_count = db.Column(db.Integer, default=0, nullable=False)
    
    # 計算済みスコア
    accuracy_rate = db.Column(db.Float, default=0.0, nullable=False)
    coverage_rate = db.Column(db.Float, default=0.0, nullable=False)
    balance_score = db.Column(db.Float, default=0.0, nullable=False)
    mastery_score = db.Column(db.Float, default=0.0, nullable=False)
    reliability_score = db.Column(db.Float, default=0.0, nullable=False)
    activity_score = db.Column(db.Float, default=0.0, nullable=False)
    
    # メタデータ
    last_updated = db.Column(db.DateTime, default=lambda: datetime.now(JST), nullable=False)
    total_questions_in_room = db.Column(db.Integer, default=0, nullable=False)
    
    # リレーション
    user = db.relationship('User', backref=db.backref('stats', uselist=False, passive_deletes=True))
    
    def __repr__(self):
        return f'<UserStats {self.user.username}: {self.balance_score:.1f}>'

    @classmethod
    def get_or_create(cls, user_id):
        """ユーザー統計を取得または作成"""
        stats = cls.query.filter_by(user_id=user_id).first()
        if not stats:
            user = User.query.get(user_id)
            if user:
                stats = cls(
                    user_id=user_id,
                    room_number=user.room_number
                )
                db.session.add(stats)
                db.session.flush()  # IDを取得するため
        return stats

    def update_stats(self, word_data=None):
        """統計を再計算して更新"""
        try:
            user = self.user
            if not user:
                return False
            
            print(f"📊 統計更新開始: {user.username}")
            
            # 部屋の単語データを取得
            if word_data is None:
                word_data = load_word_data_for_room(user.room_number)
            
            # 部屋設定を取得
            room_setting = RoomSetting.query.filter_by(room_number=user.room_number).first()
            max_enabled_unit_num_str = room_setting.max_enabled_unit_number if room_setting else "9999"
            parsed_max_enabled_unit_num = parse_unit_number(max_enabled_unit_num_str)
            
            # 有効な問題数を計算
            total_questions_for_room = 0
            for word in word_data:
                is_word_enabled_in_csv = word['enabled']
                is_unit_enabled_by_room_setting = parse_unit_number(word['number']) <= parsed_max_enabled_unit_num
                if is_word_enabled_in_csv and is_unit_enabled_by_room_setting:
                    total_questions_for_room += 1
            
            # 学習履歴を分析
            user_history = user.get_problem_history()
            user_incorrect = user.get_incorrect_words()
            total_attempts = 0
            total_correct = 0
            mastered_problem_ids = set()
            
            for problem_id, history in user_history.items():
                # 対応する単語を検索
                matched_word = None
                for word in word_data:
                    if get_problem_id(word) == problem_id:
                        matched_word = word
                        break
                
                if matched_word:
                    is_word_enabled_in_csv = matched_word['enabled']
                    is_unit_enabled_by_room_setting = parse_unit_number(matched_word['number']) <= parsed_max_enabled_unit_num
                    
                    if is_word_enabled_in_csv and is_unit_enabled_by_room_setting:
                        correct_attempts = history.get('correct_attempts', 0)
                        incorrect_attempts = history.get('incorrect_attempts', 0)
                        problem_total_attempts = correct_attempts + incorrect_attempts
                        
                        total_attempts += problem_total_attempts
                        total_correct += correct_attempts
                        
                        # マスター判定：正答率80%以上
                        if problem_total_attempts > 0:
                            accuracy_rate = (correct_attempts / problem_total_attempts) * 100
                            if accuracy_rate >= 80.0:
                                mastered_problem_ids.add(problem_id)
            
            # 基本統計を更新
            self.total_attempts = total_attempts
            self.total_correct = total_correct
            self.mastered_count = len(mastered_problem_ids)
            self.total_questions_in_room = total_questions_for_room
            self.incorrect_count = len(user_incorrect)
            
            # 正答率計算
            self.accuracy_rate = (total_correct / total_attempts * 100) if total_attempts > 0 else 0
            
            # 網羅率計算
            self.coverage_rate = (self.mastered_count / total_questions_for_room * 100) if total_questions_for_room > 0 else 0
            
            # ベイズ統計による正答率補正
            EXPECTED_AVG_ACCURACY = 0.7
            CONFIDENCE_ATTEMPTS = 10
            PRIOR_CORRECT = EXPECTED_AVG_ACCURACY * CONFIDENCE_ATTEMPTS
            PRIOR_ATTEMPTS = CONFIDENCE_ATTEMPTS
            
            # 動的スコアシステムによる計算
            if total_attempts == 0:
                self.balance_score = 0
                self.mastery_score = 0
                self.reliability_score = 0
                self.activity_score = 0
            else:
                # 正答率を計算
                accuracy_rate = total_correct / total_attempts
                
                # 1. マスタースコア（段階的 + 連続的）
                mastery_base = (self.mastered_count // 100) * 250
                mastery_progress = ((self.mastered_count % 100) / 100) * 125
                self.mastery_score = mastery_base + mastery_progress
                
                # 2. 正答率スコア（段階的連続計算）
                if accuracy_rate >= 0.9:
                    self.reliability_score = 500 + (accuracy_rate - 0.9) * 800
                elif accuracy_rate >= 0.8:
                    self.reliability_score = 350 + (accuracy_rate - 0.8) * 1500
                elif accuracy_rate >= 0.7:
                    self.reliability_score = 200 + (accuracy_rate - 0.7) * 1500
                elif accuracy_rate >= 0.6:
                    self.reliability_score = 100 + (accuracy_rate - 0.6) * 1000
                else:
                    self.reliability_score = accuracy_rate * 166.67
                
                # 3. 継続性スコア（活動量評価）
                self.activity_score = math.sqrt(total_attempts) * 3
                
                # 4. 精度ボーナス（高正答率への追加評価）
                precision_bonus = 0
                if accuracy_rate >= 0.95:
                    precision_bonus = 150 + (accuracy_rate - 0.95) * 1000
                elif accuracy_rate >= 0.9:
                    precision_bonus = 100 + (accuracy_rate - 0.9) * 1000
                elif accuracy_rate >= 0.85:
                    precision_bonus = 50 + (accuracy_rate - 0.85) * 1000
                elif accuracy_rate >= 0.8:
                    precision_bonus = (accuracy_rate - 0.8) * 1000
                
                # 総合スコア = マスタースコア + 正答率スコア + 継続性スコア + 精度ボーナス
                self.balance_score = self.mastery_score + self.reliability_score + self.activity_score + precision_bonus
            
            # 更新日時
            self.last_updated = datetime.now(JST)
            
            print(f"✅ 統計更新完了: {user.username} (スコア: {self.balance_score:.1f})")
            return True
            
        except Exception as e:
            print(f"❌ 統計更新エラー ({user.username}): {e}")
            return False

# ====================================================================
# ヘルパー関数
# ====================================================================

# 部屋ごとの単語データを読み込む関数
def load_word_data_for_room(room_number):
    try:
        room_setting = RoomSetting.query.filter_by(room_number=room_number).first()
        
        if room_setting and room_setting.csv_filename:
            csv_filename = room_setting.csv_filename
        else:
            csv_filename = "words.csv"
        
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
            except FileNotFoundError:
                print(f"❌ デフォルトファイルが見つかりません: words.csv")
                return []
        else:
            # ★重要：データベースからカスタムCSVの内容を取得
            csv_file = CsvFileContent.query.filter_by(filename=csv_filename).first()  # この行が抜けていました
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
                except Exception as parse_error:
                    print(f"❌ CSVパースエラー: {parse_error}")
                    return []
            else:
                print(f"❌ データベースにCSVが見つかりません: {csv_filename}")
                return load_word_data_for_room("default")
        
        filtered_word_data = filter_special_problems(word_data, room_number)  # 関数名変更
        
        return filtered_word_data
        
    except Exception as e:
        print(f"❌ 読み込みエラー: {e}")
        return []

def filter_special_problems(word_data, room_number):
    """Z問題（特別問題）のフィルタリング処理"""
    chapters = {}
    for word in word_data:
        chapter = word['chapter']
        if chapter not in chapters:
            chapters[chapter] = {'regular': [], 'special': []}
        
        # Z問題の判定
        number_str = str(word['number']).strip().upper()
        if number_str == 'Z':
            chapters[chapter]['special'].append(word)
        else:
            chapters[chapter]['regular'].append(word)
    
    users = User.query.filter_by(room_number=room_number).all()
    filtered_data = []
    
    for chapter, problems in chapters.items():
        filtered_data.extend(problems['regular'])
        
        if problems['special']:
            special_unlocked = check_special_unlock_status(chapter, problems['regular'], users)
            
            if special_unlocked:
                for special_word in problems['special']:
                    special_word['enabled'] = True
                    filtered_data.append(special_word)
                print(f"🔓 第{chapter}章のZ問題を解放しました")
            else:
                print(f"🔒 第{chapter}章のZ問題は条件未達成のため非表示")
    
    return filtered_data

def check_special_unlock_status(chapter, regular_problems, users):
    """特定の章のZ問題が解放されるかチェック"""
    if not regular_problems:
        return False
    
    for word in regular_problems:
        problem_id = get_problem_id(word)
        
        is_mastered_by_anyone = False
        for user in users:
            if user.username == 'admin':
                continue
            
            user_history = user.get_problem_history()
            if problem_id in user_history:
                history = user_history[problem_id]
                correct = history.get('correct_attempts', 0)
                incorrect = history.get('incorrect_attempts', 0)
                total = correct + incorrect
                
                if total > 0 and (correct / total) >= 0.8:
                    is_mastered_by_anyone = True
                    break
        
        if not is_mastered_by_anyone:
            return False
    
    return True

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
    """
    単元文字列を解析して数値に変換するヘルパー関数
    例: "10" -> 10, "2-5" -> 5 (最大値), "all" -> 9999 (大きな数値)
    """
    if isinstance(unit_str, int):
        return unit_str
    if not isinstance(unit_str, str):
        return 9999 # デフォルト値

    unit_str = unit_str.strip().lower()
    if unit_str == 'all':
        return 9999 # 全単元を意味する大きな数値

    if '-' in unit_str:
        try:
            parts = unit_str.split('-')
            if len(parts) == 2:
                return int(parts[1]) # 範囲指定の場合、上限を返す
        except ValueError:
            pass
    
    try:
        return int(unit_str)
    except ValueError:
        return 9999 # 解析できない場合は全単元

def is_unit_enabled_by_room_setting(unit_number, room_setting):
    """部屋設定で単元が有効かチェック（後方互換性対応）"""
    if not room_setting:
        return True
    
    try:
        # 新しい方式：enabled_unitsを使用
        if hasattr(room_setting, 'get_enabled_units'):
            enabled_units = room_setting.get_enabled_units()
            if enabled_units:  # リストが空でない場合
                unit_str = str(unit_number)
                return unit_str in enabled_units
        
        # 従来の方式：max_enabled_unit_numberを使用（フォールバック）
        if hasattr(room_setting, 'max_enabled_unit_number'):
            max_unit_str = room_setting.max_enabled_unit_number
            parsed_max_unit = parse_unit_number(max_unit_str)
            parsed_current_unit = parse_unit_number(str(unit_number))
            return parsed_current_unit <= parsed_max_unit
        
        # どちらもない場合はデフォルトで全て有効
        return True
        
    except Exception as e:
        print(f"⚠️ 単元有効性チェックエラー: {e}")
        return True  # エラー時は安全のため有効とする

# 問題IDを生成するヘルパー関数
def get_problem_id(word):
    try:
        chapter = str(word.get('chapter', '0')).zfill(3)
        number = str(word.get('number', '0')).zfill(3)
        question = str(word.get('question', ''))
        answer = str(word.get('answer', ''))
        
        question_clean = re.sub(r'[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', '', question[:15])
        answer_clean = re.sub(r'[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', '', answer[:10])
        
        problem_id = f"{chapter}-{number}-{question_clean}-{answer_clean}"
        return problem_id
        
    except Exception as e:
        # print(f'ID生成エラー: {e}')  # 削除
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
def migrate_database():
    """データベーススキーマの変更を処理する"""
    with app.app_context():
        print("🔄 データベースマイグレーション開始...")
        
        try:
            inspector = inspect(db.engine)
            
            # 1. Userテーブルの確認
            if inspector.has_table('user'):
                columns = [col['name'] for col in inspector.get_columns('user')]
                print(f"📋 既存のUserテーブルカラム: {columns}")
                
                # 🆕 制限状態管理用カラムを追加
                if 'restriction_triggered' not in columns:
                    print("🔧 restriction_triggeredカラムを追加します...")
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE "user" ADD COLUMN restriction_triggered BOOLEAN DEFAULT FALSE'))
                        conn.commit()
                    print("✅ restriction_triggeredカラムを追加しました。")
                
                if 'restriction_released' not in columns:
                    print("🔧 restriction_releasedカラムを追加します...")
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE "user" ADD COLUMN restriction_released BOOLEAN DEFAULT FALSE'))
                        conn.commit()
                    print("✅ restriction_releasedカラムを追加しました。")
                
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
                
                if 'is_first_login' not in columns:
                    print("🔧 is_first_loginカラムを追加します...")
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE "user" ADD COLUMN is_first_login BOOLEAN DEFAULT TRUE'))
                        # 既存のadminユーザーは初回ログイン完了済みにする
                        conn.execute(text("UPDATE \"user\" SET is_first_login = FALSE WHERE username = 'admin'"))
                        conn.commit()
                    print("✅ is_first_loginカラムを追加しました。")
                
                if 'password_changed_at' not in columns:
                    print("🔧 password_changed_atカラムを追加します...")
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE "user" ADD COLUMN password_changed_at TIMESTAMP'))
                        conn.commit()
                    print("✅ password_changed_atカラムを追加しました。")
            
            # 2. RoomSettingテーブルの確認
            if inspector.has_table('room_setting'):
                columns = [col['name'] for col in inspector.get_columns('room_setting')]
                if 'max_enabled_unit_number' not in columns:
                    print("🔧 room_settingテーブルにmax_enabled_unit_numberカラムを追加します...")
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE room_setting ADD COLUMN max_enabled_unit_number VARCHAR(50) DEFAULT \'9999\''))
                        conn.commit()
                    print("✅ max_enabled_unit_numberカラムを追加しました。")
                
                # enabled_units カラムが存在しない場合は追加
                if 'enabled_units' not in columns:
                    print("🔧 enabled_unitsカラムを追加します...")
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE room_setting ADD COLUMN enabled_units TEXT DEFAULT \'[]\''))
                        
                        # 既存のmax_enabled_unit_numberからenabled_unitsに移行
                        conn.execute(text("""
                            UPDATE room_setting 
                            SET enabled_units = CASE 
                                WHEN max_enabled_unit_number = '9999' THEN '[]'
                                ELSE '["' || max_enabled_unit_number || '"]'
                            END
                        """))
                        conn.commit()
                    print("✅ enabled_unitsカラムを追加し、既存データを移行しました。")
            
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
            
            if not inspector.has_table('user_stats'):
                    print("🔧 user_statsテーブルを作成します...")
                    db.create_all()
                    print("✅ user_statsテーブルを作成しました。")
            else:
                print("✅ user_statsテーブルは既に存在します。")
                    
                # 既存テーブルのカラム確認
                columns = [col['name'] for col in inspector.get_columns('user_stats')]
                required_columns = [
                    'id', 'user_id', 'room_number', 'total_attempts', 'total_correct', 
                    'mastered_count', 'accuracy_rate', 'coverage_rate', 'balance_score',
                    'mastery_score', 'reliability_score', 'activity_score', 'last_updated',
                    'total_questions_in_room'
                ]
                    
                missing_columns = [col for col in required_columns if col not in columns]
                if missing_columns:
                    print(f"⚠️ user_statsテーブルに不足カラム: {missing_columns}")
                    # 必要に応じてカラム追加処理
                    with db.engine.connect() as conn:
                        for col_name in missing_columns:
                            if col_name == 'room_number':
                                conn.execute(text('ALTER TABLE user_stats ADD COLUMN room_number VARCHAR(50) NOT NULL DEFAULT ""'))
                            elif col_name in ['total_attempts', 'total_correct', 'mastered_count', 'total_questions_in_room']:
                                conn.execute(text(f'ALTER TABLE user_stats ADD COLUMN {col_name} INTEGER DEFAULT 0'))
                            elif col_name in ['accuracy_rate', 'coverage_rate', 'balance_score', 'mastery_score', 'reliability_score', 'activity_score']:
                                conn.execute(text(f'ALTER TABLE user_stats ADD COLUMN {col_name} FLOAT DEFAULT 0.0'))
                            elif col_name == 'last_updated':
                                conn.execute(text('ALTER TABLE user_stats ADD COLUMN last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP'))
                            print(f"✅ {col_name}カラムを追加しました。")
                        conn.commit()
            
            # 5. UserStatsテーブルのincorrect_countカラム追加  👈 この部分を追加
            if inspector.has_table('user_stats'):
                columns = [col['name'] for col in inspector.get_columns('user_stats')]
                if 'incorrect_count' not in columns:
                    print("🔧 user_statsテーブルにincorrect_countカラムを追加します...")
                    try:
                        with db.engine.connect() as conn:
                            conn.execute(text('ALTER TABLE user_stats ADD COLUMN incorrect_count INTEGER DEFAULT 0'))
                            conn.commit()
                        print("✅ incorrect_countカラムを追加しました")
                    except Exception as e:
                        print(f"⚠️ カラム追加エラー: {e}")
                else:
                    print("✅ incorrect_countカラムは既に存在します")
            
            fix_foreign_key_constraints()
                
            print("✅ UserStats関連のマイグレーション完了")
                
        except Exception as e:
            print(f"⚠️ マイグレーション中にエラーが発生しました: {e}")
            import traceback
            traceback.print_exc()

def initialize_user_stats():
    """全ユーザーの統計を初期化"""
    try:
        print("📊 ユーザー統計初期化開始...")
        
        users = User.query.filter(User.username != 'admin').all()
        initialized_count = 0
        
        for user in users:
            try:
                # 既存の統計があるかチェック
                existing_stats = UserStats.query.filter_by(user_id=user.id).first()
                if existing_stats:
                    print(f"📋 既存統計更新: {user.username}")
                    existing_stats.update_stats()
                else:
                    print(f"➕ 新規統計作成: {user.username}")
                    stats = UserStats.get_or_create(user.id)
                    stats.update_stats()
                
                initialized_count += 1
                
                # 10件ごとにコミット
                if initialized_count % 10 == 0:
                    db.session.commit()
                    print(f"💾 中間コミット: {initialized_count}件完了")
                    
            except Exception as user_error:
                print(f"❌ {user.username}の統計初期化エラー: {user_error}")
                db.session.rollback()
                continue
        
        # 最終コミット
        db.session.commit()
        print(f"✅ ユーザー統計初期化完了: {initialized_count}人")
        return True
        
    except Exception as e:
        print(f"❌ 統計初期化エラー: {e}")
        db.session.rollback()
        return False

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

def create_user_stats_table_simple():
    """シンプルなuser_statsテーブル作成"""
    try:
        print("🔧 user_statsテーブル作成開始...")
        
        # SQLAlchemyを使用してテーブル作成
        db.create_all()
        
        # 手動でテーブル作成も試行
        with db.engine.connect() as conn:
            # テーブル存在確認
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'user_stats'
                )
            """))
            table_exists = result.fetchone()[0]
            
            if not table_exists:
                print("🔧 SQLで直接テーブル作成...")
                conn.execute(text("""
                    CREATE TABLE user_stats (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL UNIQUE,
                        room_number VARCHAR(50) NOT NULL,
                        total_attempts INTEGER DEFAULT 0,
                        total_correct INTEGER DEFAULT 0,
                        mastered_count INTEGER DEFAULT 0,
                        accuracy_rate FLOAT DEFAULT 0.0,
                        coverage_rate FLOAT DEFAULT 0.0,
                        balance_score FLOAT DEFAULT 0.0,
                        mastery_score FLOAT DEFAULT 0.0,
                        reliability_score FLOAT DEFAULT 0.0,
                        activity_score FLOAT DEFAULT 0.0,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        total_questions_in_room INTEGER DEFAULT 0,
                        FOREIGN KEY (user_id) REFERENCES "user"(id) ON DELETE CASCADE
                    )
                """))
                
                conn.execute(text("""
                    CREATE INDEX idx_user_stats_room_number ON user_stats(room_number)
                """))
                
                conn.commit()
                print("✅ user_statsテーブル作成完了")
                return True
            else:
                print("✅ user_statsテーブルは既に存在します")
                return True
                
    except Exception as e:
        print(f"❌ テーブル作成エラー: {e}")
        return False

def create_tables_and_admin_user():
    """データベース初期化関数（UserStats対応版）"""
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
            
            # ★重要：user_statsテーブルを確実に作成
            try:
                create_user_stats_table_simple()
            except Exception as stats_error:
                logger.error(f"⚠️ user_statsテーブル作成エラー: {stats_error}")
            
            # マイグレーション実行
            try:
                logger.info("🔄 データベースマイグレーションを実行中...")
                migrate_database()
                logger.info("✅ マイグレーション完了")
            except Exception as migration_error:
                logger.error(f"⚠️ マイグレーションエラー: {migration_error}")
            
            # 管理者ユーザー確認/作成
            try:
                admin_user = User.query.filter_by(username='admin', room_number='ADMIN').first()
                
                if not admin_user:
                    logger.info("👤 管理者ユーザーを作成します...")
                    admin_user = User(
                        username='admin',
                        original_username='admin',
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

@app.route('/create_missing_tables')
def create_missing_tables():
    """不足しているテーブルを作成"""
    try:
        print("🔧 不足テーブル作成開始...")
        
        # user_statsテーブル作成
        success = create_user_stats_table_simple()
        
        if success:
            # 作成後の確認
            with db.engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM user_stats"))
                count = result.fetchone()[0]
                
                return f"""
                <h1>✅ テーブル作成完了</h1>
                <p>user_statsテーブルが正常に作成されました。</p>
                <p>現在のレコード数: {count}件</p>
                
                <h3>次の手順:</h3>
                <ol>
                    <li><a href="/admin">管理者ページに移動</a></li>
                    <li>「📊 ユーザー統計管理」で「🔄 全統計を強制再初期化」実行</li>
                    <li><a href="/progress">進捗ページで動作確認</a></li>
                </ol>
                
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 40px; }}
                    h1 {{ color: #28a745; }}
                    h3 {{ color: #495057; }}
                    ol {{ background: #f8f9fa; padding: 20px; border-radius: 5px; }}
                    a {{ color: #007bff; text-decoration: none; }}
                    a:hover {{ text-decoration: underline; }}
                </style>
                """
        else:
            return """
            <h1>❌ テーブル作成失敗</h1>
            <p>user_statsテーブルの作成に失敗しました。</p>
            <p><a href="/admin">管理者ページに戻る</a></p>
            """
            
    except Exception as e:
        return f"""
        <h1>💥 エラー発生</h1>
        <p>エラー: {str(e)}</p>
        <p><a href="/admin">管理者ページに戻る</a></p>
        """


@app.route('/admin/manual_create_stats_table', methods=['POST'])
def admin_manual_create_stats_table():
    """管理者用：統計テーブル手動作成"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
    
    try:
        success = create_user_stats_table_simple()
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'user_statsテーブルを作成しました。統計の初期化を実行してください。'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'テーブル作成に失敗しました'
            })
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'テーブル作成エラー: {str(e)}'
        }), 500
    
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

@app.route('/admin/initialize_user_stats', methods=['POST'])
def admin_initialize_user_stats():
    """管理者用：ユーザー統計の強制初期化"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
    
    try:
        success = initialize_user_stats()
        if success:
            return jsonify({
                'status': 'success',
                'message': 'ユーザー統計の初期化が完了しました'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': '統計初期化中にエラーが発生しました'
            })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'初期化エラー: {str(e)}'
        }), 500

@app.route('/admin/add_first_login_columns', methods=['POST'])
def admin_add_first_login_columns():
    """初回ログイン用カラムを手動で追加"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
    
    try:
        print("🔧 初回ログイン用カラムの追加を開始...")
        
        with db.engine.connect() as conn:
            # 現在のカラムを確認
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'user'
            """))
            existing_columns = [row[0] for row in result.fetchall()]
            print(f"📋 既存カラム: {existing_columns}")
            
            added_columns = []
            
            # is_first_loginカラムを追加
            if 'is_first_login' not in existing_columns:
                print("🔧 is_first_loginカラムを追加中...")
                conn.execute(text('ALTER TABLE "user" ADD COLUMN is_first_login BOOLEAN DEFAULT TRUE'))
                # 既存のadminユーザーは初回ログイン完了済みにする
                conn.execute(text("UPDATE \"user\" SET is_first_login = FALSE WHERE username = 'admin'"))
                added_columns.append('is_first_login')
                print("✅ is_first_loginカラムを追加しました")
            else:
                print("✅ is_first_loginカラムは既に存在します")
            
            # password_changed_atカラムを追加
            if 'password_changed_at' not in existing_columns:
                print("🔧 password_changed_atカラムを追加中...")
                conn.execute(text('ALTER TABLE "user" ADD COLUMN password_changed_at TIMESTAMP'))
                added_columns.append('password_changed_at')
                print("✅ password_changed_atカラムを追加しました")
            else:
                print("✅ password_changed_atカラムは既に存在します")
            
            conn.commit()
            
            return jsonify({
                'status': 'success',
                'message': f'初回ログイン用カラムの追加が完了しました',
                'added_columns': added_columns
            })
        
    except Exception as e:
        print(f"❌ カラム追加エラー: {e}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'status': 'error',
            'message': f'カラム追加エラー: {str(e)}'
        }), 500

# app.py に緊急修復用のルートを追加

@app.route('/emergency_add_first_login_columns')
def emergency_add_first_login_columns():
    """緊急修復：初回ログイン用カラムを追加"""
    try:
        print("🆘 緊急カラム追加開始...")
        
        # 既存のトランザクションをクリア
        try:
            db.session.rollback()
        except:
            pass
        
        with db.engine.connect() as conn:
            # 現在のuserテーブルの構造を確認
            try:
                result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'user'"))
                existing_columns = [row[0] for row in result.fetchall()]
                print(f"既存カラム: {existing_columns}")
                
                messages = []
                
                # is_first_loginカラムが存在しない場合は追加
                if 'is_first_login' not in existing_columns:
                    print("🔧 is_first_loginカラムを追加中...")
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN is_first_login BOOLEAN DEFAULT TRUE'))
                    # 既存のadminユーザーは初回ログイン完了済みにする
                    conn.execute(text("UPDATE \"user\" SET is_first_login = FALSE WHERE username = 'admin'"))
                    messages.append("✅ is_first_loginカラムを追加しました")
                else:
                    messages.append("✅ is_first_loginカラムは既に存在します")
                
                # password_changed_atカラムが存在しない場合は追加
                if 'password_changed_at' not in existing_columns:
                    print("🔧 password_changed_atカラムを追加中...")
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN password_changed_at TIMESTAMP'))
                    messages.append("✅ password_changed_atカラムを追加しました")
                else:
                    messages.append("✅ password_changed_atカラムは既に存在します")
                
                conn.commit()
                
                # 修復後の状態確認
                result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'user'"))
                final_columns = [row[0] for row in result.fetchall()]
                print(f"修復後のカラム: {final_columns}")
                
                return f"""
                <h1>✅ 緊急修復完了</h1>
                <p>初回ログイン用カラムの追加が完了しました。</p>
                <h3>実行結果:</h3>
                <ul>
                    {''.join(f'<li>{msg}</li>' for msg in messages)}
                </ul>
                <h3>修復前のカラム:</h3>
                <p>{existing_columns}</p>
                <h3>修復後のカラム:</h3>
                <p>{final_columns}</p>
                <p><a href="/admin">管理者ページに戻る</a></p>
                <p><a href="/login">ログインページに戻る</a></p>
                """
                
            except Exception as fix_error:
                print(f"修復エラー: {fix_error}")
                return f"""
                <h1>❌ 修復エラー</h1>
                <p>エラー: {str(fix_error)}</p>
                <p><a href="/login">ログインページに戻る</a></p>
                """
                
    except Exception as e:
        print(f"緊急修復失敗: {e}")
        return f"""
        <h1>💥 緊急修復失敗</h1>
        <p>エラー: {str(e)}</p>
        <p>手動でPostgreSQLにアクセスして以下のSQLを実行してください：</p>
        <pre>
ALTER TABLE "user" ADD COLUMN is_first_login BOOLEAN DEFAULT TRUE;
ALTER TABLE "user" ADD COLUMN password_changed_at TIMESTAMP;
UPDATE "user" SET is_first_login = FALSE WHERE username = 'admin';
        </pre>
        """

@app.route('/admin/fix_progress_issue', methods=['POST'])
def admin_fix_progress_issue():
    """進捗ページの問題を修正"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
    
    try:
        print("🔧 進捗ページ問題の修正を開始...")
        
        # 1. ranking_display_count カラムを追加
        with db.engine.connect() as conn:
            # カラムの存在を確認
            try:
                result = conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'room_setting' AND column_name = 'ranking_display_count'
                """))
                
                if not result.fetchone():
                    print("🔧 ranking_display_count カラムを追加中...")
                    conn.execute(text('ALTER TABLE room_setting ADD COLUMN ranking_display_count INTEGER DEFAULT 10'))
                    conn.commit()
                    print("✅ ranking_display_count カラムを追加しました")
                else:
                    print("✅ ranking_display_count カラムは既に存在します")
                    
            except Exception as e:
                print(f"⚠️ カラム追加エラー: {e}")
        
        # 2. 全ての部屋設定にデフォルト値を設定
        room_settings = RoomSetting.query.all()
        updated_count = 0
        
        for setting in room_settings:
            if not hasattr(setting, 'ranking_display_count') or setting.ranking_display_count is None:
                setting.ranking_display_count = 10
                updated_count += 1
        
        if updated_count > 0:
            db.session.commit()
            print(f"✅ {updated_count}個の部屋設定を更新しました")
        
        return jsonify({
            'status': 'success',
            'message': '進捗ページの問題を修正しました',
            'updated_settings': updated_count
        })
        
    except Exception as e:
        print(f"❌ 修正エラー: {e}")
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': f'修正エラー: {str(e)}'
        }), 500

@app.route('/admin/test_progress_data')
def admin_test_progress_data():
    """進捗データをテスト"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
    
    try:
        # テストユーザーを取得
        test_user = User.query.filter(User.username != 'admin').first()
        if not test_user:
            return jsonify({'status': 'error', 'message': 'テスト用ユーザーが見つかりません'}), 404
        
        # 単語データを取得
        word_data = load_word_data_for_room(test_user.room_number)
        user_history = test_user.get_problem_history()
        
        # 部屋設定を取得
        room_setting = RoomSetting.query.filter_by(room_number=test_user.room_number).first()
        
        result = {
            'test_user': test_user.username,
            'room_number': test_user.room_number,
            'word_data_count': len(word_data),
            'user_history_count': len(user_history),
            'room_setting_exists': room_setting is not None,
            'ranking_display_count': getattr(room_setting, 'ranking_display_count', 'カラムなし') if room_setting else '設定なし',
            'sample_history': dict(list(user_history.items())[:3]) if user_history else {}
        }
        
        return jsonify({
            'status': 'success',
            'test_data': result
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'テストエラー: {str(e)}'
        }), 500

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
            is_unit_enabled_by_room = is_unit_enabled_by_room_setting(unit_num, room_setting)
            is_unit_globally_enabled = is_word_enabled_in_csv and is_unit_enabled_by_room 

            # 利用可能な単元のみを章データに追加
            if is_unit_globally_enabled:
                if chapter_num not in all_chapter_unit_status:
                    all_chapter_unit_status[chapter_num] = {'units': {}, 'name': f'第{chapter_num}章'}
                
                if unit_num not in all_chapter_unit_status[chapter_num]['units']:
                    all_chapter_unit_status[chapter_num]['units'][unit_num] = {
                        'categoryName': category_name,
                        'enabled': True  # 利用可能な単元のみ追加するのでenabled=True
                    }

        # ★新機能：空の章（利用可能な単元がない章）を除外
        filtered_chapter_unit_status = {}
        for chapter_num, chapter_data in all_chapter_unit_status.items():
            if chapter_data['units']:  # 章に利用可能な単元がある場合のみ含める
                filtered_chapter_unit_status[chapter_num] = chapter_data

        sorted_all_chapter_unit_status = dict(sorted(filtered_chapter_unit_status.items(), 
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

# app.py の login_page ルートを修正

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    try:
        if request.method == 'POST':
            login_type = request.form.get('login_type', 'user')
            
            if login_type == 'admin':
                # 管理者ログイン処理（変更なし）
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
                # 一般ユーザーログイン処理
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

                    # 🆕 初回ログインチェック
                    if hasattr(user, 'is_first_login') and user.is_first_login:
                        flash('初回ログインです。セキュリティのためパスワードを変更してください。', 'info')
                        return redirect(url_for('first_time_password_change'))
                    
                    flash('ログインしました。', 'success')
                    return redirect(url_for('index'))
                else:
                    flash('部屋番号、出席番号、またはパスワードが間違っています。', 'danger')
        
        # GET リクエスト時
        context = get_template_context()
        return render_template('login.html', **context)
        
    except Exception as e:
        print(f"Error in login route: {e}")
        import traceback
        traceback.print_exc()
        return f"Login Error: {e}", 500

@app.route('/first_time_password_change', methods=['GET', 'POST'])
def first_time_password_change():
    """初回ログイン時の必須パスワード変更"""
    try:
        if 'user_id' not in session:
            flash('ログインが必要です。', 'danger')
            return redirect(url_for('login_page'))
        
        current_user = User.query.get(session['user_id'])
        if not current_user:
            flash('ユーザーが見つかりません。', 'danger')
            return redirect(url_for('logout'))
        
        # 既に初回ログインが完了している場合は通常ページにリダイレクト
        if hasattr(current_user, 'is_first_login') and not current_user.is_first_login:
            return redirect(url_for('index'))
        
        if request.method == 'POST':
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            # バリデーション
            if not all([current_password, new_password, confirm_password]):
                flash('すべての項目を入力してください。', 'danger')
                context = get_template_context()
                context['current_user'] = current_user
                return render_template('first_time_password_change.html', **context)
            
            # 現在のパスワード確認
            if not current_user.check_individual_password(current_password):
                flash('現在のパスワードが間違っています。', 'danger')
                context = get_template_context()
                context['current_user'] = current_user
                return render_template('first_time_password_change.html', **context)
            
            # 新しいパスワードの確認
            if new_password != confirm_password:
                flash('新しいパスワードが一致しません。', 'danger')
                context = get_template_context()
                context['current_user'] = current_user
                return render_template('first_time_password_change.html', **context)
            
            # パスワードの強度チェック
            if len(new_password) < 6:
                flash('新しいパスワードは6文字以上で入力してください。', 'danger')
                context = get_template_context()
                context['current_user'] = current_user
                return render_template('first_time_password_change.html', **context)
            
            # 現在のパスワードと同じかチェック
            if current_user.check_individual_password(new_password):
                flash('新しいパスワードは現在のパスワードと異なるものにしてください。', 'danger')
                context = get_template_context()
                context['current_user'] = current_user
                return render_template('first_time_password_change.html', **context)
            
            # パスワード変更実行
            try:
                if hasattr(current_user, 'change_password_first_time'):
                    current_user.change_password_first_time(new_password)
                else:
                    # フォールバック: 古いバージョン対応
                    current_user.set_individual_password(new_password)
                    if hasattr(current_user, 'is_first_login'):
                        current_user.is_first_login = False
                    if hasattr(current_user, 'password_changed_at'):
                        current_user.password_changed_at = datetime.now(JST)
                
                db.session.commit()
                
                flash('パスワードが正常に変更されました。学習を開始できます。', 'success')
                return redirect(url_for('index'))
                
            except Exception as e:
                db.session.rollback()
                flash(f'パスワード変更中にエラーが発生しました: {str(e)}', 'danger')
        
        # GET リクエスト時
        context = get_template_context()
        context['current_user'] = current_user
        return render_template('first_time_password_change.html', **context)
        
    except Exception as e:
        print(f"Error in first_time_password_change: {e}")
        import traceback
        traceback.print_exc()
        flash('システムエラーが発生しました。', 'danger')
        return redirect(url_for('index'))

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

# app.py の admin_force_migration ルートを修正（約1750行目付近）
@app.route('/admin/force_migration', methods=['GET', 'POST'])
def admin_force_migration():
    """手動でデータベースマイグレーションを実行"""
    if not session.get('admin_logged_in'):
        if request.method == 'GET':
            flash('管理者権限が必要です。', 'danger')
            return redirect(url_for('login_page'))
        return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
    
    if request.method == 'GET':
        # GET リクエストの場合は確認ページを表示
        return """
        <html>
        <head>
            <title>データベースマイグレーション</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; }
                .container { max-width: 600px; margin: 0 auto; }
                .warning { background: #fff3cd; border: 1px solid #ffeaa7; padding: 20px; border-radius: 5px; margin: 20px 0; }
                .btn { padding: 12px 20px; margin: 10px; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; display: inline-block; }
                .btn-primary { background: #007bff; color: white; }
                .btn-secondary { background: #6c757d; color: white; }
                .btn:hover { opacity: 0.8; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🔧 データベースマイグレーション</h1>
                <div class="warning">
                    <h3>⚠️ 注意事項</h3>
                    <p>この操作は以下を実行します：</p>
                    <ul>
                        <li>Userテーブルに制限状態管理用カラムを追加</li>
                        <li>その他の不足カラムを追加</li>
                        <li>外部キー制約を修正</li>
                    </ul>
                    <p><strong>本番環境での実行のため、慎重に行ってください。</strong></p>
                </div>
                
                <form method="POST" onsubmit="return confirm('本当にマイグレーションを実行しますか？');">
                    <button type="submit" class="btn btn-primary">🚀 マイグレーションを実行</button>
                </form>
                
                <a href="/admin" class="btn btn-secondary">← 管理者ページに戻る</a>
            </div>
        </body>
        </html>
        """
    
    # POST リクエストの場合は実際にマイグレーションを実行
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
        return """
        <html>
        <head>
            <title>マイグレーション完了</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; }
                .container { max-width: 600px; margin: 0 auto; }
                .success { background: #d4edda; border: 1px solid #c3e6cb; padding: 20px; border-radius: 5px; margin: 20px 0; }
                .btn { padding: 12px 20px; margin: 10px; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; display: inline-block; }
                .btn-success { background: #28a745; color: white; }
                .btn:hover { opacity: 0.8; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>✅ マイグレーション完了</h1>
                <div class="success">
                    <h3>成功！</h3>
                    <p>データベースマイグレーションが正常に完了しました。</p>
                    <p>制限状態管理用のカラムが追加され、アプリケーションが正常に動作するはずです。</p>
                </div>
                
                <a href="/admin" class="btn btn-success">← 管理者ページに戻る</a>
                <a href="/" class="btn btn-success">🏠 メインページに移動</a>
            </div>
        </body>
        </html>
        """
        
    except Exception as e:
        print(f"❌ 手動マイグレーションエラー: {e}")
        import traceback
        traceback.print_exc()
        
        return f"""
        <html>
        <head>
            <title>マイグレーションエラー</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .container {{ max-width: 600px; margin: 0 auto; }}
                .error {{ background: #f8d7da; border: 1px solid #f5c6cb; padding: 20px; border-radius: 5px; margin: 20px 0; }}
                .btn {{ padding: 12px 20px; margin: 10px; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; display: inline-block; }}
                .btn-danger {{ background: #dc3545; color: white; }}
                .btn:hover {{ opacity: 0.8; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>❌ マイグレーションエラー</h1>
                <div class="error">
                    <h3>エラーが発生しました</h3>
                    <p><strong>エラー内容:</strong> {str(e)}</p>
                    <p>管理者に連絡するか、緊急修復ページを試してください。</p>
                </div>
                
                <a href="/emergency_add_restriction_columns" class="btn btn-danger">🆘 緊急修復を試す</a>
                <a href="/admin" class="btn btn-danger">← 管理者ページに戻る</a>
            </div>
        </body>
        </html>
        """

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

@app.route('/emergency_add_restriction_columns')
def emergency_add_restriction_columns():
    """緊急修復：制限状態用カラムを追加"""
    try:
        print("🆘 緊急制限状態カラム追加開始...")
        
        # 既存のトランザクションをクリア
        try:
            db.session.rollback()
        except:
            pass
        
        with db.engine.connect() as conn:
            # 現在のuserテーブルの構造を確認
            try:
                result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'user'"))
                existing_columns = [row[0] for row in result.fetchall()]
                print(f"既存カラム: {existing_columns}")
                
                messages = []
                
                # restriction_triggeredカラムが存在しない場合は追加
                if 'restriction_triggered' not in existing_columns:
                    print("🔧 restriction_triggeredカラムを追加中...")
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN restriction_triggered BOOLEAN DEFAULT FALSE'))
                    messages.append("✅ restriction_triggeredカラムを追加しました")
                else:
                    messages.append("✅ restriction_triggeredカラムは既に存在します")
                
                # restriction_releasedカラムが存在しない場合は追加
                if 'restriction_released' not in existing_columns:
                    print("🔧 restriction_releasedカラムを追加中...")
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN restriction_released BOOLEAN DEFAULT FALSE'))
                    messages.append("✅ restriction_releasedカラムを追加しました")
                else:
                    messages.append("✅ restriction_releasedカラムは既に存在します")
                
                conn.commit()
                
                # 修復後の状態確認
                result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'user'"))
                final_columns = [row[0] for row in result.fetchall()]
                print(f"修復後のカラム: {final_columns}")
                
                return f"""
                <html>
                <head>
                    <title>緊急修復完了</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; margin: 40px; }}
                        .container {{ max-width: 600px; margin: 0 auto; }}
                        .success {{ background: #d4edda; border: 1px solid #c3e6cb; padding: 20px; border-radius: 5px; margin: 20px 0; }}
                        .btn {{ padding: 12px 20px; margin: 10px; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; display: inline-block; }}
                        .btn-success {{ background: #28a745; color: white; }}
                        .btn:hover {{ opacity: 0.8; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>✅ 緊急修復完了</h1>
                        <div class="success">
                            <h3>制限状態カラムの追加が完了しました</h3>
                            <ul>
                                {''.join(f'<li>{msg}</li>' for msg in messages)}
                            </ul>
                            <p><strong>修復前のカラム:</strong> {len(existing_columns)}個</p>
                            <p><strong>修復後のカラム:</strong> {len(final_columns)}個</p>
                        </div>
                        
                        <a href="/admin" class="btn btn-success">← 管理者ページに戻る</a>
                        <a href="/" class="btn btn-success">🏠 メインページに移動</a>
                    </div>
                </body>
                </html>
                """
                
            except Exception as fix_error:
                print(f"修復エラー: {fix_error}")
                return f"""
                <html>
                <head><title>修復エラー</title></head>
                <body>
                    <h1>❌ 修復エラー</h1>
                    <p>エラー: {str(fix_error)}</p>
                    <p><a href="/admin">管理者ページに戻る</a></p>
                </body>
                </html>
                """
                
    except Exception as e:
        print(f"緊急修復失敗: {e}")
        return f"""
        <html>
        <head><title>緊急修復失敗</title></head>
        <body>
            <h1>💥 緊急修復失敗</h1>
            <p>エラー: {str(e)}</p>
            <p>手動でPostgreSQLにアクセスして以下のSQLを実行してください：</p>
            <pre>
ALTER TABLE "user" ADD COLUMN restriction_triggered BOOLEAN DEFAULT FALSE;
ALTER TABLE "user" ADD COLUMN restriction_released BOOLEAN DEFAULT FALSE;
            </pre>
        </body>
        </html>
        """

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
# 管理者用全員ランキングページ
# ====================================================================

@app.route('/admin/ranking')
def admin_ranking_page():
    """管理者用全員ランキング表示ページ"""
    try:
        if not session.get('admin_logged_in'):
            flash('管理者権限がありません。', 'danger')
            return redirect(url_for('login_page'))

        print("🏆 管理者用ランキングページ表示開始...")

        # テンプレートに必要な基本情報のみ渡す
        # 実際のデータは Ajax で後から取得
        context = get_template_context()
        
        return render_template('admin_ranking.html', **context)
        
    except Exception as e:
        print(f"❌ 管理者ランキングページエラー: {e}")
        import traceback
        traceback.print_exc()
        flash('ランキングページの読み込み中にエラーが発生しました。', 'danger')
        return redirect(url_for('admin_page'))

# ====================================================================
# 管理者用ランキング API エンドポイント
# ====================================================================
@app.route('/admin/get_available_units/<room_number>')
def admin_get_available_units(room_number):
    """指定部屋で利用可能な単元一覧を取得（管理者用・フィルタリングなし）"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify(status='error', message='管理者権限がありません。'), 403

        # 管理者用：フィルタリングなしで部屋の単語データを取得
        word_data = load_raw_word_data_for_room(room_number)
        
        # 単元一覧を抽出
        units = set()
        for word in word_data:
            if word['enabled']:
                units.add(str(word['number']))
        
        # ソートして返す（Z問題を最後に）
        sorted_units = sorted(list(units), key=lambda x: (x.upper() == 'Z', parse_unit_number(x)))
        
        return jsonify({
            'status': 'success',
            'available_units': sorted_units,
            'total_problems': len(word_data),
            'enabled_problems': len([w for w in word_data if w['enabled']])
        })
        
    except Exception as e:
        return jsonify(status='error', message=str(e)), 500
    
@app.route('/api/admin/rooms')
def api_admin_rooms():
    """管理者用：全部屋の一覧を取得"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify(status='error', message='管理者権限が必要です'), 403
        
        print("🔍 管理者用部屋一覧取得開始...")
        
        # 部屋別のユーザー数を集計
        rooms_query = db.session.query(
            User.room_number,
            func.count(User.id).label('user_count')
        ).filter(
            User.room_number != 'ADMIN'
        ).group_by(User.room_number).all()
        
        rooms = []
        for room_data in rooms_query:
            rooms.append({
                'room_number': room_data.room_number,
                'user_count': room_data.user_count
            })
        
        # 部屋番号でソート
        rooms.sort(key=lambda x: int(x['room_number']) if x['room_number'].isdigit() else float('inf'))
        
        print(f"✅ 部屋一覧取得完了: {len(rooms)}個の部屋")
        
        return jsonify({
            'status': 'success',
            'rooms': rooms
        })
        
    except Exception as e:
        print(f"❌ 部屋一覧取得エラー: {e}")
        import traceback
        traceback.print_exc()
        return jsonify(status='error', message=str(e)), 500

@app.route('/api/admin/room_ranking/<room_number>')
def api_admin_room_ranking(room_number):
    """管理者用：指定した部屋の全ユーザーランキングを取得"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify(status='error', message='管理者権限が必要です'), 403
        
        print(f"\n=== 管理者用ランキング取得開始 (部屋: {room_number}) ===")
        start_time = time.time()
        
        # user_statsテーブルの存在確認
        try:
            inspector = inspect(db.engine)
            user_stats_exists = inspector.has_table('user_stats')
            
            if not user_stats_exists:
                print("⚠️ user_statsテーブルが存在しません。従来方式で計算します...")
                return admin_fallback_ranking_calculation(room_number, start_time)
            
            # 事前計算された統計データを高速取得
            room_stats = UserStats.query.filter_by(room_number=room_number)\
                                        .join(User)\
                                        .filter(User.username != 'admin')\
                                        .order_by(UserStats.balance_score.desc(), UserStats.total_attempts.desc())\
                                        .all()
            
            print(f"📊 事前計算データ取得: {len(room_stats)}人分")
            
            # データが空の場合はフォールバック
            if not room_stats:
                print("⚠️ 統計データが空です。従来方式で計算します...")
                return admin_fallback_ranking_calculation(room_number, start_time)
            
        except Exception as stats_error:
            print(f"⚠️ 統計テーブルアクセスエラー: {stats_error}")
            print("従来方式で計算します...")
            return admin_fallback_ranking_calculation(room_number, start_time)
        
        # ランキングデータを構築（全員取得）
        ranking_data = []
        total_attempts = 0
        total_correct = 0
        total_scores = []
        active_users = 0
        
        # ランキングデータを構築（全員取得）
        for stats in room_stats:
            user_data = {
                'username': stats.user.username,
                'total_attempts': stats.total_attempts,
                'total_correct': stats.total_correct,
                'accuracy_rate': round(stats.accuracy_rate, 1),
                'coverage_rate': round(stats.coverage_rate, 1),
                'mastered_count': stats.mastered_count,
                'total_questions_for_room': stats.total_questions_in_room,
                'balance_score': round(stats.balance_score, 1),
                'mastery_score': round(stats.mastery_score, 1),
                'reliability_score': round(stats.reliability_score, 1),
                'activity_score': round(stats.activity_score, 1),
                'last_login': stats.user.last_login.isoformat() if stats.user.last_login else None,
                'incorrect_count': len(stats.user.get_incorrect_words()) if stats.user else 0
            }
            
            ranking_data.append(user_data)
            
            # 統計データ集計
            total_attempts += stats.total_attempts
            total_correct += stats.total_correct
            total_scores.append(stats.balance_score)
            
            # アクティブユーザー判定（何らかの学習履歴がある）
            if stats.total_attempts > 0:
                active_users += 1
        
        # 統計情報を計算
        statistics = {
            'total_users': len(ranking_data),
            'active_users': active_users,
            'average_score': round(sum(total_scores) / len(total_scores), 1) if total_scores else 0,
            'max_score': round(max(total_scores), 1) if total_scores else 0,
            'total_attempts': total_attempts,
            'total_correct': total_correct,
            'room_accuracy': round((total_correct / total_attempts * 100), 1) if total_attempts > 0 else 0
        }
        
        elapsed_time = time.time() - start_time
        print(f"=== 管理者用ランキング取得完了: {elapsed_time:.3f}秒 ===\n")
        
        return jsonify({
            'status': 'success',
            'room_number': room_number,
            'ranking_data': ranking_data,
            'statistics': statistics,
            'calculation_time': round(elapsed_time, 3),
            'using_precalculated': True,
            'data_source': 'user_stats_table'
        })
        
    except Exception as e:
        print(f"❌ 管理者ランキング取得エラー: {e}")
        import traceback
        traceback.print_exc()
        # 最終フォールバック：エラー時は従来方式
        try:
            return admin_fallback_ranking_calculation(room_number, time.time())
        except:
            return jsonify(status='error', message=f'ランキング取得エラー: {str(e)}'), 500

def admin_fallback_ranking_calculation(room_number, start_time):
    """管理者用フォールバック：従来方式でランキング計算"""
    try:
        print("🔄 管理者用従来方式でランキング計算中...")
        
        # 部屋の単語データと設定を取得
        word_data = load_word_data_for_room(room_number)
        room_setting = RoomSetting.query.filter_by(room_number=room_number).first()
        max_enabled_unit_num_str = room_setting.max_enabled_unit_number if room_setting else "9999"
        parsed_max_enabled_unit_num = parse_unit_number(max_enabled_unit_num_str)
        
        # 部屋の総問題数を計算
        total_questions_for_room_ranking = 0
        for word in word_data:
            is_word_enabled_in_csv = word['enabled']
            is_unit_enabled_by_room_setting = parse_unit_number(word['number']) <= parsed_max_enabled_unit_num
            if is_word_enabled_in_csv and is_unit_enabled_by_room_setting:
                total_questions_for_room_ranking += 1
        
        # 部屋内の全ユーザーを取得
        all_users_for_ranking = User.query.filter_by(room_number=room_number).all()
        ranking_data = []
        total_attempts = 0
        total_correct = 0
        total_scores = []
        active_users = 0

        # ベイズ統計による正答率補正の設定値
        EXPECTED_AVG_ACCURACY = 0.7
        CONFIDENCE_ATTEMPTS = 10
        PRIOR_CORRECT = EXPECTED_AVG_ACCURACY * CONFIDENCE_ATTEMPTS
        PRIOR_ATTEMPTS = CONFIDENCE_ATTEMPTS

        # 全ユーザーのスコアを計算
        for user_obj in all_users_for_ranking:
            if user_obj.username == 'admin':
                continue
                
            user_total_attempts = 0
            user_total_correct = 0
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
                        is_unit_enabled_by_room_setting = parse_unit_number(matched_word['number']) <= parsed_max_enabled_unit_num

                        if is_word_enabled_in_csv and is_unit_enabled_by_room_setting:
                            correct_attempts = history.get('correct_attempts', 0)
                            incorrect_attempts = history.get('incorrect_attempts', 0)
                            problem_total_attempts = correct_attempts + incorrect_attempts
                            
                            user_total_attempts += problem_total_attempts
                            user_total_correct += correct_attempts
                            
                            if problem_total_attempts > 0:
                                accuracy_rate = (correct_attempts / problem_total_attempts) * 100
                                if accuracy_rate >= 80.0:
                                    mastered_problem_ids.add(problem_id)
            
            user_mastered_count = len(mastered_problem_ids)
            coverage_rate = (user_mastered_count / total_questions_for_room_ranking * 100) if total_questions_for_room_ranking > 0 else 0

            # 動的スコアシステムによる計算
            if total_attempts == 0:
                comprehensive_score = 0
                mastery_score = 0
                reliability_score = 0
                activity_score = 0
            else:
                # 正答率を計算
                accuracy_rate = total_correct / total_attempts
                
                # 1. マスタースコア（段階的 + 連続的）
                mastery_base = (user_mastered_count // 100) * 250
                mastery_progress = ((user_mastered_count % 100) / 100) * 125
                mastery_score = mastery_base + mastery_progress
                
                # 2. 正答率スコア（段階的連続計算）
                if accuracy_rate >= 0.9:
                    reliability_score = 500 + (accuracy_rate - 0.9) * 800
                elif accuracy_rate >= 0.8:
                    reliability_score = 350 + (accuracy_rate - 0.8) * 1500
                elif accuracy_rate >= 0.7:
                    reliability_score = 200 + (accuracy_rate - 0.7) * 1500
                elif accuracy_rate >= 0.6:
                    reliability_score = 100 + (accuracy_rate - 0.6) * 1000
                else:
                    reliability_score = accuracy_rate * 166.67
                
                # 3. 継続性スコア（活動量評価）
                activity_score = math.sqrt(total_attempts) * 3
                
                # 4. 精度ボーナス（高正答率への追加評価）
                precision_bonus = 0
                if accuracy_rate >= 0.95:
                    precision_bonus = 150 + (accuracy_rate - 0.95) * 1000
                elif accuracy_rate >= 0.9:
                    precision_bonus = 100 + (accuracy_rate - 0.9) * 1000
                elif accuracy_rate >= 0.85:
                    precision_bonus = 50 + (accuracy_rate - 0.85) * 1000
                elif accuracy_rate >= 0.8:
                    precision_bonus = (accuracy_rate - 0.8) * 1000
                
                # 総合スコア
                comprehensive_score = mastery_score + reliability_score + activity_score + precision_bonus

            user_data = {
                'username': user_obj.username,
                'total_attempts': user_total_attempts,
                'total_correct': user_total_correct,
                'accuracy_rate': round((user_total_correct / user_total_attempts * 100), 1) if user_total_attempts > 0 else 0,
                'coverage_rate': round(coverage_rate, 1),
                'mastered_count': user_mastered_count,
                'total_questions_for_room': total_questions_for_room_ranking,
                'balance_score': round(comprehensive_score, 1),
                'mastery_score': round(mastery_score, 1),
                'reliability_score': round(reliability_score, 1),
                'activity_score': round(activity_score, 1),
                'last_login': user_obj.last_login.isoformat() if user_obj.last_login else None
            }

            ranking_data.append(user_data)
            
            # 統計データ集計
            total_attempts += user_total_attempts
            total_correct += user_total_correct
            total_scores.append(comprehensive_score)

        # バランススコアで降順ソート
        ranking_data.sort(key=lambda x: (x['balance_score'], x['total_attempts']), reverse=True)

        # 統計情報を計算
        statistics = {
            'total_users': len(ranking_data),
            'active_users': active_users,
            'average_score': round(sum(total_scores) / len(total_scores), 1) if total_scores else 0,
            'max_score': round(max(total_scores), 1) if total_scores else 0,
            'total_attempts': total_attempts,
            'total_correct': total_correct,
            'room_accuracy': round((total_correct / total_attempts * 100), 1) if total_attempts > 0 else 0
        }

        elapsed_time = time.time() - start_time
        print(f"=== 管理者用従来方式ランキング計算完了: {elapsed_time:.2f}秒 ===\n")

        return jsonify({
            'status': 'success',
            'room_number': room_number,
            'ranking_data': ranking_data,
            'statistics': statistics,
            'calculation_time': round(elapsed_time, 2),
            'using_precalculated': False,  # 従来方式使用
            'data_source': 'realtime_calculation'
        })
        
    except Exception as e:
        print(f"❌ 管理者用従来方式計算エラー: {e}")
        import traceback
        traceback.print_exc()
        return jsonify(status='error', message=f'ランキング計算エラー: {str(e)}'), 500

# ====================================================================
# 管理者用ランキング操作 API
# ====================================================================

@app.route('/api/admin/export_ranking/<room_number>')
def api_admin_export_ranking(room_number):
    """管理者用：指定部屋のランキングをCSVエクスポート"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify(status='error', message='管理者権限が必要です'), 403
        
        print(f"📥 CSV エクスポート開始: 部屋{room_number}")
        
        # ランキングデータを取得（既存のAPIを再利用）
        ranking_response = api_admin_room_ranking(room_number)
        ranking_json = ranking_response.get_json()
        
        if ranking_json.get('status') != 'success':
            return jsonify(status='error', message='ランキングデータの取得に失敗しました'), 500
        
        ranking_data = ranking_json.get('ranking_data', [])
        
        if not ranking_data:
            return jsonify(status='error', message='エクスポートするデータがありません'), 404
        
        # CSVデータを作成
        si = StringIO()
        cw = csv.writer(si)
        
        # ヘッダー行（BOM付きでUTF-8エンコード）
        headers = [
            '順位', '名前', '最終ログイン', '回答数', '正解数', '正答率(%)', 
            'マスター数', '総合スコア', '網羅率(%)', 'マスタリー', '信頼性', 'アクティビティ'
        ]
        cw.writerow(headers)
        
        # データ行
        for index, user in enumerate(ranking_data, 1):
            # 最終ログイン時刻のフォーマット
            last_login = 'なし'
            if user.get('last_login'):
                try:
                    login_time = datetime.fromisoformat(user['last_login'].replace('Z', '+00:00'))
                    # JSTに変換
                    login_time_jst = login_time + timedelta(hours=9)
                    last_login = login_time_jst.strftime('%Y-%m-%d %H:%M')
                except:
                    last_login = 'なし'
            
            row = [
                index,  # 順位
                user.get('username', 'Unknown'),
                last_login,
                user.get('total_attempts', 0),
                user.get('total_correct', 0),
                user.get('accuracy_rate', 0),
                user.get('mastered_count', 0),
                user.get('balance_score', 0),
                user.get('coverage_rate', 0),
                user.get('mastery_score', 0),
                user.get('reliability_score', 0),
                user.get('activity_score', 0)
            ]
            cw.writerow(row)
        
        # UTF-8 BOM付きでエンコード
        csv_content = '\ufeff' + si.getvalue()
        csv_bytes = csv_content.encode('utf-8')
        
        # ファイル名を作成
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'ranking_room_{room_number}_{timestamp}.csv'
        
        response = Response(
            csv_bytes,
            mimetype='text/csv; charset=utf-8',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': 'text/csv; charset=utf-8'
            }
        )
        
        print(f"✅ CSV エクスポート完了: {filename} ({len(ranking_data)}人)")
        return response
        
    except Exception as e:
        print(f"❌ CSV エクスポートエラー: {e}")
        import traceback
        traceback.print_exc()
        return jsonify(status='error', message=f'CSVエクスポートエラー: {str(e)}'), 500

@app.route('/api/admin/update_ranking_display_count', methods=['POST'])
def api_admin_update_ranking_display_count():
    """管理者用：ランキング表示人数設定を更新"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify(status='error', message='管理者権限が必要です'), 403
        
        data = request.get_json()
        room_number = data.get('room_number')
        display_count = data.get('ranking_display_count', 10)
        
        if not room_number:
            return jsonify(status='error', message='部屋番号が指定されていません'), 400
        
        # 表示人数の範囲チェック
        try:
            display_count = int(display_count)
            if display_count < 5 or display_count > 100:
                return jsonify(status='error', message='表示人数は5〜100の範囲で設定してください'), 400
        except (ValueError, TypeError):
            return jsonify(status='error', message='表示人数は数値で入力してください'), 400
        
        print(f"🔧 ランキング表示人数更新: 部屋{room_number} -> {display_count}人")
        
        # 部屋設定を取得または作成
        room_setting = RoomSetting.query.filter_by(room_number=room_number).first()
        
        if room_setting:
            room_setting.ranking_display_count = display_count
            room_setting.updated_at = datetime.now(JST)
        else:
            # 新規作成
            room_setting = RoomSetting(
                room_number=room_number,
                max_enabled_unit_number="9999",
                csv_filename="words.csv",
                ranking_display_count=display_count
            )
            db.session.add(room_setting)
        
        db.session.commit()
        
        print(f"✅ ランキング表示人数更新完了: 部屋{room_number} = {display_count}人")
        
        return jsonify({
            'status': 'success',
            'message': f'部屋{room_number}のランキング表示人数を{display_count}人に設定しました',
            'room_number': room_number,
            'ranking_display_count': display_count
        })
        
    except Exception as e:
        print(f"❌ ランキング表示人数更新エラー: {e}")
        db.session.rollback()
        return jsonify(status='error', message=f'設定更新エラー: {str(e)}'), 500
# ====================================================================
# APIエンドポイント
# ====================================================================
@app.route('/api/update_user_stats', methods=['POST'])
def update_user_stats():
    """ユーザー統計を非同期更新"""
    try:
        if 'user_id' not in session:
            return jsonify(status='error', message='ログインしていません。'), 401
        
        current_user = User.query.get(session['user_id'])
        if not current_user:
            return jsonify(status='error', message='ユーザーが見つかりません。'), 404

        # 統計更新
        try:
            user_stats = UserStats.get_or_create(current_user.id)
            if user_stats:
                word_data = load_word_data_for_room(current_user.room_number)
                user_stats.update_stats(word_data)
                db.session.commit()
        except Exception as stats_error:
            db.session.rollback()
            return jsonify(status='error', message=f'統計更新エラー: {str(stats_error)}'), 500
        
        return jsonify(status='success', message='統計を更新しました。')
        
    except Exception as e:
        return jsonify(status='error', message=str(e)), 500
    
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

        filtered_word_data = []
        for word in word_data:
            unit_num = word['number']
            is_word_enabled_in_csv = word['enabled']
            # 修正：新しい関数を使用
            is_unit_enabled_by_room = is_unit_enabled_by_room_setting(unit_num, room_setting)

            if is_word_enabled_in_csv and is_unit_enabled_by_room:
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

        # 🆕 制限状態も含めて返す
        restriction_state = current_user.get_restriction_state()
        
        return jsonify(
            status='success', 
            problemHistory=current_user.get_problem_history(),
            incorrectWords=current_user.get_incorrect_words(),
            quizProgress={},
            restrictionState=restriction_state  # 🆕 制限状態を追加
        )
    except Exception as e:
        print(f"Error in api_load_quiz_progress: {e}")
        return jsonify(status='error', message=str(e)), 500

@app.route('/api/save_progress', methods=['POST'])
def save_quiz_progress():
    """学習進捗保存（軽量版 - 統計更新なし）"""
    try:
        if 'user_id' not in session:
            return jsonify(status='error', message='ログインしていません。'), 401
        
        data = request.get_json()
        received_problem_history = data.get('problemHistory', {})
        received_incorrect_words = data.get('incorrectWords', [])

        current_user = User.query.get(session['user_id'])
        if not current_user:
            return jsonify(status='error', message='ユーザーが見つかりません。'), 404

        # 学習履歴を保存（統計更新なし）
        current_user.set_problem_history(received_problem_history)
        current_user.set_incorrect_words(received_incorrect_words)
        
        # 一括コミット
        db.session.commit()
        
        return jsonify(status='success', message='進捗を保存しました。')
        
    except Exception as e:
        db.session.rollback()
        return jsonify(status='error', message=f'進捗の保存中にエラーが発生しました: {str(e)}'), 500

@app.route('/api/update_restriction_state', methods=['POST'])
def update_restriction_state():
    """制限状態を更新"""
    try:
        if 'user_id' not in session:
            return jsonify(status='error', message='ログインしていません。'), 401
        
        data = request.get_json()
        has_been_restricted = data.get('hasBeenRestricted', False)
        restriction_released = data.get('restrictionReleased', False)

        current_user = User.query.get(session['user_id'])
        if not current_user:
            return jsonify(status='error', message='ユーザーが見つかりません。'), 404

        print(f"🔄 制限状態更新: {current_user.username} - triggered={has_been_restricted}, released={restriction_released}")

        # 制限状態を保存
        current_user.set_restriction_state(has_been_restricted, restriction_released)
        db.session.commit()

        return jsonify(status='success', message='制限状態を更新しました。')
        
    except Exception as e:
        print(f"❌ 制限状態更新エラー: {e}")
        db.session.rollback()
        return jsonify(status='error', message=f'制限状態更新エラー: {str(e)}'), 500

@app.route('/api/save_progress_debug', methods=['POST'])
def save_quiz_progress_debug():
    """デバッグ情報付きの進捗保存 + 統計自動更新"""
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
        
        # ★統計を自動更新
        stats_update_success = False
        old_balance_score = 0
        new_balance_score = 0
        
        try:
            user_stats = UserStats.get_or_create(current_user.id)
            if user_stats:
                old_balance_score = user_stats.balance_score
                word_data = load_word_data_for_room(current_user.room_number)
                user_stats.update_stats(word_data)
                new_balance_score = user_stats.balance_score
                stats_update_success = True
                print(f"📊 統計更新: {old_balance_score:.1f} → {new_balance_score:.1f}")
                
        except Exception as stats_error:
            print(f"⚠️ 統計更新エラー: {stats_error}")

        db.session.commit()

        # 保存後の確認
        saved_history = current_user.get_problem_history()
        saved_incorrect = current_user.get_incorrect_words()
        
        print(f"保存後の履歴数: {len(saved_history)}")
        print(f"保存後の苦手問題数: {len(saved_incorrect)}")
        print("=== 進捗保存デバッグ終了 ===\n")

        return jsonify(
            status='success', 
            message='進捗が保存され、統計が更新されました。',
            debug_info={
                'old_history_count': len(old_history),
                'new_history_count': len(received_problem_history),
                'saved_history_count': len(saved_history),
                'new_entries_count': len(new_entries),
                'old_incorrect_count': len(old_incorrect),
                'new_incorrect_count': len(received_incorrect_words),
                'saved_incorrect_count': len(saved_incorrect),
                'stats_updated': stats_update_success,
                'old_balance_score': old_balance_score,
                'new_balance_score': new_balance_score
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

# app.py に以下の関数を追加してください

def analyze_unmatched_problems():
    """ID不一致問題を分析する（修正前の状態確認）"""
    
    # デフォルトの単語データを取得
    default_word_data = load_default_word_data()
    if not default_word_data:
        return {
            'status': 'error',
            'message': '単語データが見つかりません'
        }
    
    # 新しいID生成方式でマッピングを作成
    word_mapping = {}
    for word in default_word_data:
        new_id = get_problem_id(word)
        word_mapping[new_id] = word
    
    print(f"📋 問題データ: {len(word_mapping)}個")
    
    users = User.query.all()
    analysis_results = {
        'total_users': 0,
        'users_with_unmatched': 0,
        'total_unmatched_entries': 0,
        'fixable_entries': 0,
        'user_details': []
    }
    
    for user in users:
        if user.username == 'admin':
            continue
            
        analysis_results['total_users'] += 1
        
        user_history = user.get_problem_history()
        user_incorrect = user.get_incorrect_words()
        
        matched_ids = []
        unmatched_ids = []
        fixable_ids = []
        
        # 履歴の各IDをチェック
        for problem_id in user_history.keys():
            if problem_id in word_mapping:
                matched_ids.append(problem_id)
            else:
                unmatched_ids.append(problem_id)
                
                # 修正可能かチェック
                if can_fix_problem_id(problem_id, default_word_data):
                    fixable_ids.append(problem_id)
        
        user_unmatched_count = len(unmatched_ids)
        user_fixable_count = len(fixable_ids)
        
        if user_unmatched_count > 0:
            analysis_results['users_with_unmatched'] += 1
            analysis_results['total_unmatched_entries'] += user_unmatched_count
            analysis_results['fixable_entries'] += user_fixable_count
            
            analysis_results['user_details'].append({
                'username': user.username,
                'room_number': user.room_number,
                'total_history': len(user_history),
                'matched_count': len(matched_ids),
                'unmatched_count': user_unmatched_count,
                'fixable_count': user_fixable_count,
                'unmatched_ids': unmatched_ids[:5],  # 最初の5件のみ
                'fixable_ids': fixable_ids[:5]
            })
    
    return analysis_results

def can_fix_problem_id(old_id, word_data):
    """問題IDが修正可能かチェック"""
    try:
        parts = old_id.split('-')
        if len(parts) >= 2:
            old_chapter = int(parts[0].lstrip('0') or '0')
            old_number = int(parts[1].lstrip('0') or '0')
            
            # 章と単元が一致する問題があるかチェック
            for word in word_data:
                word_chapter = int(str(word['chapter']))
                word_number = int(str(word['number']))
                
                if word_chapter == old_chapter and word_number == old_number:
                    return True
        return False
    except (ValueError, IndexError):
        return False

def fix_unmatched_problems_only():
    """ID不一致問題のみを修正"""
    
    # デフォルトの単語データを取得
    default_word_data = load_default_word_data()
    if not default_word_data:
        print("❌ 単語データが見つかりません")
        return False
    
    users = User.query.all()
    fixed_users = 0
    total_fixed_entries = 0
    total_unfixable_entries = 0
    
    for user in users:
        if user.username == 'admin':
            continue
            
        print(f"\n🔧 ID修正開始: {user.username}")
        
        old_history = user.get_problem_history()
        old_incorrect = user.get_incorrect_words()
        
        new_history = {}
        new_incorrect = []
        user_fixed_count = 0
        user_unfixable_count = 0
        
        # 各履歴エントリをチェック
        for old_id, history_data in old_history.items():
            
            # まず新しいID形式かチェック（既に正しい場合はそのまま保持）
            is_valid_new_id = any(get_problem_id(word) == old_id for word in default_word_data)
            
            if is_valid_new_id:
                # 既に正しいIDの場合はそのまま保持
                new_history[old_id] = history_data
                continue
            
            # 修正が必要な場合
            best_match_word = None
            best_score = 0
            
            # 古いIDからの情報抽出を試行
            parts = old_id.split('-')
            if len(parts) >= 2:
                try:
                    old_chapter = int(parts[0].lstrip('0') or '0')
                    old_number = int(parts[1].lstrip('0') or '0')
                    
                    # 対応する問題を探す
                    for word in default_word_data:
                        score = 0
                        word_chapter = int(str(word['chapter']))
                        word_number = int(str(word['number']))
                        
                        # 章と単元が完全一致するか
                        if word_chapter == old_chapter and word_number == old_number:
                            score = 100  # 完全一致は高スコア
                            
                            # 問題文の類似性もチェック
                            if len(parts) > 2:
                                old_text = ''.join(parts[2:]).lower()
                                question_clean = str(word['question']).lower()
                                question_clean = ''.join(c for c in question_clean if c.isalnum())
                                
                                if old_text and question_clean and old_text[:10] in question_clean:
                                    score += 20
                            
                            if score > best_score:
                                best_score = score
                                best_match_word = word
                                break  # 章・単元一致なら即採用
                            
                except ValueError:
                    continue
            
            # マッチした場合は新しいIDで保存
            if best_match_word and best_score >= 100:  # 章・単元一致が必須
                new_id = get_problem_id(best_match_word)
                new_history[new_id] = history_data
                user_fixed_count += 1
                
                # 苦手問題の判定
                incorrect_attempts = history_data.get('incorrect_attempts', 0)
                correct_streak = history_data.get('correct_streak', 0)
                
                if incorrect_attempts > 0 and correct_streak < 2:
                    if new_id not in new_incorrect:
                        new_incorrect.append(new_id)
                        
                print(f"  ✓ 修正: {old_id[:40]}... -> 第{best_match_word['chapter']}章単元{best_match_word['number']}")
            else:
                # 修正できない場合は削除（ログに記録）
                user_unfixable_count += 1
                print(f"  ❌ 修正不可: {old_id[:40]}... (一致する問題なし)")
        
        # 変更があった場合のみ保存
        if user_fixed_count > 0 or user_unfixable_count > 0:
            user.set_problem_history(new_history)
            user.set_incorrect_words(new_incorrect)
            fixed_users += 1
            total_fixed_entries += user_fixed_count
            total_unfixable_entries += user_unfixable_count
            
            print(f"  📊 結果: {user_fixed_count}個修正, {user_unfixable_count}個削除, {len(new_incorrect)}個苦手問題")
    
    try:
        db.session.commit()
        print(f"\n✅ ID修正完了")
        print(f"   修正対象ユーザー数: {fixed_users}")
        print(f"   修正されたエントリ数: {total_fixed_entries}")
        print(f"   削除されたエントリ数: {total_unfixable_entries}")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"❌ 修正エラー: {e}")
        return False

@app.route('/admin/analyze_unmatched_data', methods=['POST'])
def admin_analyze_unmatched_data():
    """ID不一致問題の分析"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限がありません。'}), 403
    
    try:
        analysis = analyze_unmatched_problems()
        return jsonify({
            'status': 'success',
            'analysis': analysis
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/fix_unmatched_data', methods=['POST'])
def admin_fix_unmatched_data():
    """ID不一致問題のみを修正"""
    if not session.get('admin_logged_in'):
        flash('管理者権限がありません。', 'danger')
        return redirect(url_for('login_page'))
    
    try:
        success = fix_unmatched_problems_only()
        if success:
            flash('ID不一致問題の修正が完了しました。', 'success')
        else:
            flash('ID不一致問題の修正中にエラーが発生しました。', 'danger')
    except Exception as e:
        flash(f'修正エラー: {str(e)}', 'danger')
    
    return redirect(url_for('admin_page'))

# 既存の fix_all_user_data 関数はバックアップとして残す
@app.route('/admin/fix_all_data_legacy', methods=['POST'])
def admin_fix_all_data_legacy():
    """従来の全データ修正（バックアップ用）"""
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

# app.py に以下の関数を追加してください

def clean_unmatched_history():
    """ID不一致の学習履歴を削除する"""
    
    # デフォルトの単語データを取得
    default_word_data = load_default_word_data()
    if not default_word_data:
        print("❌ 単語データが見つかりません")
        return False
    
    # 新しいID生成方式で有効なIDのセットを作成
    valid_ids = set()
    for word in default_word_data:
        new_id = get_problem_id(word)
        valid_ids.add(new_id)
    
    print(f"📋 有効な問題ID数: {len(valid_ids)}個")
    
    users = User.query.all()
    cleaned_users = 0
    total_removed_entries = 0
    total_removed_incorrect = 0
    
    for user in users:
        if user.username == 'admin':
            continue
            
        print(f"\n🧹 履歴クリーニング: {user.username}")
        
        old_history = user.get_problem_history()
        old_incorrect = user.get_incorrect_words()
        
        # 有効なIDのみを保持
        new_history = {}
        removed_count = 0
        
        for problem_id, history_data in old_history.items():
            if problem_id in valid_ids:
                # 有効なIDは保持
                new_history[problem_id] = history_data
            else:
                # 無効なIDは削除
                removed_count += 1
                print(f"  🗑️ 削除: {problem_id}")
        
        # 苦手問題リストも有効なIDのみ保持
        new_incorrect = []
        removed_incorrect_count = 0
        
        for problem_id in old_incorrect:
            if problem_id in valid_ids:
                new_incorrect.append(problem_id)
            else:
                removed_incorrect_count += 1
                print(f"  🗑️ 苦手問題から削除: {problem_id}")
        
        # 変更があった場合のみ保存
        if removed_count > 0 or removed_incorrect_count > 0:
            user.set_problem_history(new_history)
            user.set_incorrect_words(new_incorrect)
            cleaned_users += 1
            total_removed_entries += removed_count
            total_removed_incorrect += removed_incorrect_count
            
            print(f"  📊 結果: {removed_count}個の履歴を削除, {removed_incorrect_count}個の苦手問題を削除")
            print(f"  ✅ 残存: {len(new_history)}個の履歴, {len(new_incorrect)}個の苦手問題")
    
    try:
        db.session.commit()
        print(f"\n✅ 履歴クリーニング完了")
        print(f"   対象ユーザー数: {cleaned_users}")
        print(f"   削除された学習履歴: {total_removed_entries}個")
        print(f"   削除された苦手問題: {total_removed_incorrect}個")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"❌ クリーニングエラー: {e}")
        return False

def analyze_unmatched_history():
    """ID不一致の学習履歴を分析（削除前の確認用）"""
    
    # デフォルトの単語データを取得
    default_word_data = load_default_word_data()
    if not default_word_data:
        return {
            'status': 'error',
            'message': '単語データが見つかりません'
        }
    
    # 有効なIDのセットを作成
    valid_ids = set()
    for word in default_word_data:
        new_id = get_problem_id(word)
        valid_ids.add(new_id)
    
    users = User.query.all()
    analysis_results = {
        'total_users': 0,
        'users_with_invalid': 0,
        'total_invalid_entries': 0,
        'total_invalid_incorrect': 0,
        'user_details': []
    }
    
    for user in users:
        if user.username == 'admin':
            continue
            
        analysis_results['total_users'] += 1
        
        user_history = user.get_problem_history()
        user_incorrect = user.get_incorrect_words()
        
        invalid_history_ids = []
        invalid_incorrect_ids = []
        
        # 履歴の各IDをチェック
        for problem_id in user_history.keys():
            if problem_id not in valid_ids:
                invalid_history_ids.append(problem_id)
        
        # 苦手問題の各IDをチェック
        for problem_id in user_incorrect:
            if problem_id not in valid_ids:
                invalid_incorrect_ids.append(problem_id)
        
        user_invalid_count = len(invalid_history_ids)
        user_invalid_incorrect_count = len(invalid_incorrect_ids)
        
        if user_invalid_count > 0 or user_invalid_incorrect_count > 0:
            analysis_results['users_with_invalid'] += 1
            analysis_results['total_invalid_entries'] += user_invalid_count
            analysis_results['total_invalid_incorrect'] += user_invalid_incorrect_count
            
            analysis_results['user_details'].append({
                'username': user.username,
                'room_number': user.room_number,
                'total_history': len(user_history),
                'valid_history': len(user_history) - user_invalid_count,
                'invalid_history': user_invalid_count,
                'invalid_incorrect': user_invalid_incorrect_count,
                'invalid_history_ids': invalid_history_ids[:3],  # 最初の3件のみ
                'invalid_incorrect_ids': invalid_incorrect_ids[:3]
            })
    
    return analysis_results

@app.route('/admin/analyze_invalid_history', methods=['POST'])
def admin_analyze_invalid_history():
    """ID不一致履歴の分析"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限がありません。'}), 403
    
    try:
        analysis = analyze_unmatched_history()
        return jsonify({
            'status': 'success',
            'analysis': analysis
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/clean_invalid_history', methods=['POST'])
def admin_clean_invalid_history():
    """ID不一致履歴の削除"""
    if not session.get('admin_logged_in'):
        flash('管理者権限がありません。', 'danger')
        return redirect(url_for('login_page'))
    
    try:
        success = clean_unmatched_history()
        if success:
            flash('ID不一致の学習履歴を削除しました。', 'success')
        else:
            flash('履歴削除中にエラーが発生しました。', 'danger')
    except Exception as e:
        flash(f'削除エラー: {str(e)}', 'danger')
    
    return redirect(url_for('admin_page'))

# app.py に以下のデバッグ機能を追加してください

def debug_specific_user_data(username):
    """特定ユーザーのデータを詳細デバッグ"""
    
    user = User.query.filter_by(username=username).first()
    if not user:
        print(f"❌ ユーザー '{username}' が見つかりません")
        return
    
    print(f"\n🔍 ユーザー詳細デバッグ: {username}")
    print(f"部屋番号: {user.room_number}")
    
    # 部屋ごとの単語データを取得
    word_data = load_word_data_for_room(user.room_number)
    print(f"部屋の単語データ数: {len(word_data)}")
    
    # ユーザーの学習履歴を取得
    user_history = user.get_problem_history()
    user_incorrect = user.get_incorrect_words()
    
    print(f"学習履歴数: {len(user_history)}")
    print(f"苦手問題数: {len(user_incorrect)}")
    
    # 新しいID生成方式で有効なIDのセットを作成
    valid_ids = set()
    for word in word_data:
        new_id = get_problem_id(word)
        valid_ids.add(new_id)
    
    print(f"有効ID数: {len(valid_ids)}")
    
    # 各履歴IDを詳細チェック
    matched_count = 0
    unmatched_count = 0
    unmatched_details = []
    
    for problem_id, history_data in user_history.items():
        if problem_id in valid_ids:
            matched_count += 1
        else:
            unmatched_count += 1
            unmatched_details.append({
                'id': problem_id,
                'correct_attempts': history_data.get('correct_attempts', 0),
                'incorrect_attempts': history_data.get('incorrect_attempts', 0),
                'last_answered': history_data.get('last_answered', '')
            })
            print(f"❌ 不一致ID: {problem_id}")
            print(f"   履歴: 正解{history_data.get('correct_attempts', 0)}回, 不正解{history_data.get('incorrect_attempts', 0)}回")
    
    print(f"\n📊 集計結果:")
    print(f"一致する履歴: {matched_count}個")
    print(f"不一致な履歴: {unmatched_count}個")
    
    # 苦手問題もチェック
    unmatched_incorrect = []
    for problem_id in user_incorrect:
        if problem_id not in valid_ids:
            unmatched_incorrect.append(problem_id)
            print(f"❌ 不一致苦手問題: {problem_id}")
    
    print(f"不一致苦手問題: {len(unmatched_incorrect)}個")
    
    return {
        'user': username,
        'room_number': user.room_number,
        'total_history': len(user_history),
        'matched_history': matched_count,
        'unmatched_history': unmatched_count,
        'unmatched_details': unmatched_details,
        'unmatched_incorrect': unmatched_incorrect,
        'valid_ids_count': len(valid_ids)
    }

def force_clean_specific_user(username):
    """特定ユーザーの不一致IDを強制削除"""
    
    user = User.query.filter_by(username=username).first()
    if not user:
        print(f"❌ ユーザー '{username}' が見つかりません")
        return False
    
    # 部屋ごとの単語データを取得
    word_data = load_word_data_for_room(user.room_number)
    
    # 有効なIDのセットを作成
    valid_ids = set()
    for word in word_data:
        new_id = get_problem_id(word)
        valid_ids.add(new_id)
    
    print(f"\n🧹 {username} の不一致履歴強制削除開始")
    
    old_history = user.get_problem_history()
    old_incorrect = user.get_incorrect_words()
    
    # 有効なIDのみを保持
    new_history = {}
    removed_count = 0
    
    for problem_id, history_data in old_history.items():
        if problem_id in valid_ids:
            new_history[problem_id] = history_data
        else:
            removed_count += 1
            print(f"🗑️ 削除: {problem_id}")
    
    # 苦手問題も有効なIDのみ保持
    new_incorrect = []
    removed_incorrect_count = 0
    
    for problem_id in old_incorrect:
        if problem_id in valid_ids:
            new_incorrect.append(problem_id)
        else:
            removed_incorrect_count += 1
            print(f"🗑️ 苦手問題から削除: {problem_id}")
    
    # 保存
    user.set_problem_history(new_history)
    user.set_incorrect_words(new_incorrect)
    
    try:
        db.session.commit()
        print(f"✅ {username} のクリーニング完了")
        print(f"   削除された履歴: {removed_count}個")
        print(f"   削除された苦手問題: {removed_incorrect_count}個")
        print(f"   残存履歴: {len(new_history)}個")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"❌ 保存エラー: {e}")
        return False

@app.route('/admin/debug_user/<username>')
def admin_debug_user(username):
    """特定ユーザーのデバッグ情報を表示"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限がありません。'}), 403
    
    try:
        debug_result = debug_specific_user_data(username)
        if debug_result:
            return jsonify({
                'status': 'success',
                'debug_data': debug_result
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'ユーザー {username} が見つかりません'
            })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/force_clean_user/<username>', methods=['POST'])
def admin_force_clean_user(username):
    """特定ユーザーの不一致データを強制削除"""
    if not session.get('admin_logged_in'):
        flash('管理者権限がありません。', 'danger')
        return redirect(url_for('admin_page'))
    
    try:
        success = force_clean_specific_user(username)
        if success:
            flash(f'ユーザー {username} の不一致データを削除しました。', 'success')
        else:
            flash(f'ユーザー {username} のデータ削除に失敗しました。', 'danger')
    except Exception as e:
        flash(f'削除エラー: {str(e)}', 'danger')
    
    return redirect(url_for('admin_page'))

# 修正版：analyze_unmatched_history関数（より詳細な分析）
def analyze_unmatched_history_detailed():
    """ID不一致の学習履歴を詳細分析"""
    
    users = User.query.all()
    analysis_results = {
        'total_users': 0,
        'users_with_invalid': 0,
        'total_invalid_entries': 0,
        'total_invalid_incorrect': 0,
        'user_details': [],
        'debug_info': []
    }
    
    for user in users:
        if user.username == 'admin':
            continue
            
        analysis_results['total_users'] += 1
        
        # 部屋ごとの単語データを取得
        word_data = load_word_data_for_room(user.room_number)
        
        # 有効なIDのセットを作成
        valid_ids = set()
        for word in word_data:
            new_id = get_problem_id(word)
            valid_ids.add(new_id)
        
        user_history = user.get_problem_history()
        user_incorrect = user.get_incorrect_words()
        
        invalid_history_ids = []
        invalid_incorrect_ids = []
        
        # 履歴の各IDをチェック
        for problem_id in user_history.keys():
            if problem_id not in valid_ids:
                invalid_history_ids.append(problem_id)
        
        # 苦手問題の各IDをチェック
        for problem_id in user_incorrect:
            if problem_id not in valid_ids:
                invalid_incorrect_ids.append(problem_id)
        
        user_invalid_count = len(invalid_history_ids)
        user_invalid_incorrect_count = len(invalid_incorrect_ids)
        
        # デバッグ情報を追加
        analysis_results['debug_info'].append({
            'username': user.username,
            'room_number': user.room_number,
            'word_data_count': len(word_data),
            'valid_ids_count': len(valid_ids),
            'total_history': len(user_history),
            'invalid_history_ids': invalid_history_ids,
            'invalid_incorrect_ids': invalid_incorrect_ids
        })
        
        if user_invalid_count > 0 or user_invalid_incorrect_count > 0:
            analysis_results['users_with_invalid'] += 1
            analysis_results['total_invalid_entries'] += user_invalid_count
            analysis_results['total_invalid_incorrect'] += user_invalid_incorrect_count
            
            analysis_results['user_details'].append({
                'username': user.username,
                'room_number': user.room_number,
                'total_history': len(user_history),
                'valid_history': len(user_history) - user_invalid_count,
                'invalid_history': user_invalid_count,
                'invalid_incorrect': user_invalid_incorrect_count,
                'invalid_history_ids': invalid_history_ids[:5],  # 最初の5件のみ
                'invalid_incorrect_ids': invalid_incorrect_ids[:5]
            })
    
    return analysis_results

@app.route('/admin/analyze_invalid_history_detailed', methods=['POST'])
def admin_analyze_invalid_history_detailed():
    """詳細な無効履歴分析"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限がありません。'}), 403
    
    try:
        analysis = analyze_unmatched_history_detailed()
        return jsonify({
            'status': 'success',
            'analysis': analysis
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ====================================================================
# 進捗ページ
# ====================================================================
@app.route('/progress')
def progress_page():
    """個人進捗のみを高速表示（ランキングは非同期）"""
    try:
        if 'user_id' not in session:
            flash('進捗を確認するにはログインしてください。', 'info')
            return redirect(url_for('login_page'))

        current_user = User.query.get(session['user_id'])
        if not current_user:
            flash('ユーザーが見つかりません。', 'danger')
            return redirect(url_for('logout'))

        print(f"\n=== 進捗ページ（高速版）処理開始 ===")
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

        # 章ごとに進捗をまとめる（個人のみ、高速化）
        chapter_progress_summary = {}

        # 有効な単語データで単元進捗を初期化
        for word in word_data:
            chapter_num = word['chapter']
            unit_num = word['number']
            category_name = word.get('category', '未分類')
            
            is_word_enabled_in_csv = word['enabled']
            is_unit_enabled_by_room = is_unit_enabled_by_room_setting(unit_num, room_setting)  # ←変数名を変更

            if is_word_enabled_in_csv and is_unit_enabled_by_room:
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

        # 学習履歴を処理（個人のみ）
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
                is_unit_enabled_by_room = parse_unit_number(unit_number) <= parsed_max_enabled_unit_num

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
        print("=== 進捗ページ（高速版）処理完了 ===\n")

        context = get_template_context()
        
        # ★重要：ランキングデータは空で渡す（Ajax で後から取得）
        return render_template('progress.html',
                               current_user=current_user,
                               user_progress_by_chapter=sorted_chapter_progress,
                               # ランキング関連は空・None で初期化
                               top_10_ranking=[],  
                               current_user_stats=None,
                               current_user_rank=None,
                               total_users_in_room=0,
                               ranking_display_count=5,
                               # 非同期ローディング用フラグ
                               async_loading=True,
                               **context)
    
    except Exception as e:
        print(f"Error in progress_page: {e}")
        import traceback
        traceback.print_exc()
        return f"Progress Error: {e}", 500

@app.route('/api/ranking_data')
def api_ranking_data():
    """ランキングデータを取得（フォールバック対応版）"""
    try:
        if 'user_id' not in session:
            return jsonify(status='error', message='認証されていません。'), 401

        current_user = User.query.get(session['user_id'])
        if not current_user:
            return jsonify(status='error', message='ユーザーが見つかりません。'), 404

        print(f"\n=== ランキング取得開始 ({current_user.username}) ===")
        start_time = time.time()

        current_room_number = current_user.room_number
        
        # ★重要：user_statsテーブルの存在確認
        try:
            # user_statsテーブルが存在するかチェック
            with db.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'user_stats'
                    )
                """))
                user_stats_exists = result.fetchone()[0]
            
            if not user_stats_exists:
                print("⚠️ user_statsテーブルが存在しません。従来方式で計算します...")
                return fallback_ranking_calculation(current_user, start_time)
            
            # 事前計算された統計データを高速取得
            room_stats = UserStats.query.filter_by(room_number=current_room_number)\
                                        .join(User)\
                                        .filter(User.username != 'admin')\
                                        .order_by(UserStats.balance_score.desc(), UserStats.total_attempts.desc())\
                                        .all()
            
            print(f"📊 事前計算データ取得: {len(room_stats)}人分")
            
            # データが空の場合はフォールバック
            if not room_stats:
                print("⚠️ 統計データが空です。従来方式で計算します...")
                return fallback_ranking_calculation(current_user, start_time)
            
        except Exception as stats_error:
            print(f"⚠️ 統計テーブルアクセスエラー: {stats_error}")
            print("従来方式で計算します...")
            return fallback_ranking_calculation(current_user, start_time)
        
        # ランキング表示人数を取得
        ranking_display_count = 5
        try:
            room_setting = RoomSetting.query.filter_by(room_number=current_room_number).first()
            if room_setting and hasattr(room_setting, 'ranking_display_count'):
                ranking_display_count = room_setting.ranking_display_count or 5
        except Exception as e:
            print(f"⚠️ ranking_display_count 取得エラー: {e}")
        
        # ランキングデータを構築（計算済みデータを使用）
        ranking_data = []
        current_user_stats = None
        current_user_rank = None
        
        for index, stats in enumerate(room_stats, 1):
            user_data = {
                'username': stats.user.username,
                'total_attempts': stats.total_attempts,
                'total_correct': stats.total_correct,
                'accuracy_rate': stats.accuracy_rate,
                'coverage_rate': stats.coverage_rate,
                'mastered_count': stats.mastered_count,
                'total_questions_for_room': stats.total_questions_in_room,
                'balance_score': stats.balance_score,
                'mastery_score': stats.mastery_score,
                'reliability_score': stats.reliability_score,
                'activity_score': stats.activity_score
            }
            
            ranking_data.append(user_data)
            
            # 現在のユーザーの統計を記録
            if stats.user_id == current_user.id:
                current_user_stats = user_data
                current_user_rank = index

        # 上位ランキングを取得
        top_ranking = ranking_data[:ranking_display_count]

        elapsed_time = time.time() - start_time
        print(f"=== 高速ランキング取得完了: {elapsed_time:.3f}秒 ===\n")
        
        # フォールバック：統計が見つからない場合
        if not current_user_stats:
            print(f"⚠️ {current_user.username}の統計が見つかりません。")
            current_user_stats = {
                'username': current_user.username,
                'total_attempts': 0,
                'total_correct': 0,
                'accuracy_rate': 0,
                'coverage_rate': 0,
                'mastered_count': 0,
                'total_questions_for_room': 0,
                'balance_score': 0,
                'mastery_score': 0,
                'reliability_score': 0,
                'activity_score': 0
            }
            current_user_rank = len(ranking_data) + 1

        return jsonify({
            'status': 'success',
            'ranking_data': top_ranking,
            'current_user_stats': current_user_stats,
            'current_user_rank': current_user_rank,
            'total_users_in_room': len(ranking_data),
            'ranking_display_count': ranking_display_count,
            'calculation_time': round(elapsed_time, 3),
            'using_precalculated': True,
            'data_source': 'user_stats_table'
        })
        
    except Exception as e:
        print(f"❌ ランキング取得エラー: {e}")
        # 最終フォールバック：エラー時は従来方式
        try:
            return fallback_ranking_calculation(current_user, time.time())
        except:
            return jsonify(status='error', message=f'ランキング取得エラー: {str(e)}'), 500


def fallback_ranking_calculation(current_user, start_time):
    """フォールバック：従来方式でランキング計算"""
    try:
        print("🔄 従来方式でランキング計算中...")
        
        current_room_number = current_user.room_number
        
        # 部屋の単語データと設定を取得
        word_data = load_word_data_for_room(current_room_number)
        room_setting = RoomSetting.query.filter_by(room_number=current_room_number).first()
        max_enabled_unit_num_str = room_setting.max_enabled_unit_number if room_setting else "9999"
        parsed_max_enabled_unit_num = parse_unit_number(max_enabled_unit_num_str)
        
        # ランキング表示人数を取得
        ranking_display_count = 5
        try:
            if room_setting and hasattr(room_setting, 'ranking_display_count'):
                ranking_display_count = room_setting.ranking_display_count or 5
        except Exception as e:
            print(f"⚠️ ranking_display_count 取得エラー: {e}")
        
        # 部屋の総問題数を計算
        total_questions_for_room_ranking = 0
        for word in word_data:
            is_word_enabled_in_csv = word['enabled']
            is_unit_enabled_by_room_setting = parse_unit_number(word['number']) <= parsed_max_enabled_unit_num
            if is_word_enabled_in_csv and is_unit_enabled_by_room_setting:
                total_questions_for_room_ranking += 1
        
        # 部屋内の全ユーザーを取得
        all_users_for_ranking = User.query.filter_by(room_number=current_room_number).all()
        ranking_data = []
        current_user_stats = None

        # ベイズ統計による正答率補正の設定値
        EXPECTED_AVG_ACCURACY = 0.7
        CONFIDENCE_ATTEMPTS = 10
        PRIOR_CORRECT = EXPECTED_AVG_ACCURACY * CONFIDENCE_ATTEMPTS
        PRIOR_ATTEMPTS = CONFIDENCE_ATTEMPTS

        # 全ユーザーのスコアを計算
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
                        is_unit_enabled_by_room_setting = parse_unit_number(matched_word['number']) <= parsed_max_enabled_unit_num

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

            # 動的スコアシステムによる計算
            if total_attempts == 0:
                comprehensive_score = 0
                mastery_score = 0
                reliability_score = 0
                activity_score = 0
            else:
                # 正答率を計算
                accuracy_rate = total_correct / total_attempts
                
                # 1. マスタースコア（段階的 + 連続的）
                mastery_base = (user_mastered_count // 100) * 250
                mastery_progress = ((user_mastered_count % 100) / 100) * 125
                mastery_score = mastery_base + mastery_progress
                
                # 2. 正答率スコア（段階的連続計算）
                if accuracy_rate >= 0.9:
                    reliability_score = 500 + (accuracy_rate - 0.9) * 800
                elif accuracy_rate >= 0.8:
                    reliability_score = 350 + (accuracy_rate - 0.8) * 1500
                elif accuracy_rate >= 0.7:
                    reliability_score = 200 + (accuracy_rate - 0.7) * 1500
                elif accuracy_rate >= 0.6:
                    reliability_score = 100 + (accuracy_rate - 0.6) * 1000
                else:
                    reliability_score = accuracy_rate * 166.67
                
                # 3. 継続性スコア（活動量評価）
                activity_score = math.sqrt(total_attempts) * 3
                
                # 4. 精度ボーナス（高正答率への追加評価）
                precision_bonus = 0
                if accuracy_rate >= 0.95:
                    precision_bonus = 150 + (accuracy_rate - 0.95) * 1000
                elif accuracy_rate >= 0.9:
                    precision_bonus = 100 + (accuracy_rate - 0.9) * 1000
                elif accuracy_rate >= 0.85:
                    precision_bonus = 50 + (accuracy_rate - 0.85) * 1000
                elif accuracy_rate >= 0.8:
                    precision_bonus = (accuracy_rate - 0.8) * 1000
                
                # 総合スコア
                comprehensive_score = mastery_score + reliability_score + activity_score + precision_bonus

            user_data = {
                'username': user_obj.username,
                'total_attempts': total_attempts,
                'total_correct': total_correct,
                'accuracy_rate': (total_correct / total_attempts * 100) if total_attempts > 0 else 0,
                'coverage_rate': coverage_rate,
                'mastered_count': user_mastered_count,
                'total_questions_for_room': total_questions_for_room_ranking,
                'balance_score': comprehensive_score,
                'mastery_score': mastery_score,
                'reliability_score': reliability_score,
                'activity_score': activity_score
            }

            ranking_data.append(user_data)
            
            # 現在のユーザーのスコアを記録
            if user_obj.id == current_user.id:
                current_user_stats = user_data

        # バランススコアで降順ソート
        ranking_data.sort(key=lambda x: (x['balance_score'], x['total_attempts']), reverse=True)

        # 現在のユーザーの順位を特定
        current_user_rank = None
        if current_user_stats:
            for index, user_data in enumerate(ranking_data, 1):
                if user_data['username'] == current_user.username:
                    current_user_rank = index
                    break
        
        # 上位ランキングを取得
        top_ranking = ranking_data[:ranking_display_count]

        elapsed_time = time.time() - start_time
        print(f"=== 従来方式ランキング計算完了: {elapsed_time:.2f}秒 ===\n")

        return jsonify({
            'status': 'success',
            'ranking_data': top_ranking,
            'current_user_stats': current_user_stats,
            'current_user_rank': current_user_rank,
            'total_users_in_room': len(ranking_data),
            'ranking_display_count': ranking_display_count,
            'calculation_time': round(elapsed_time, 2),
            'using_precalculated': False,  # 従来方式使用
            'data_source': 'realtime_calculation'
        })
        
    except Exception as e:
        print(f"❌ 従来方式計算エラー: {e}")
        return jsonify(status='error', message=f'ランキング計算エラー: {str(e)}'), 500

# 管理者用：統計の確認・修復
@app.route('/admin/check_user_stats')
def admin_check_user_stats():
    """管理者用：ユーザー統計の状態確認"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
    
    try:
        total_users = User.query.filter(User.username != 'admin').count()
        total_stats = UserStats.query.count()
        
        # 統計が古いユーザーを検索（1日以上更新されていない）
        one_day_ago = datetime.now(JST) - timedelta(days=1)
        outdated_stats = UserStats.query.filter(UserStats.last_updated < one_day_ago).count()
        
        # 統計がないユーザーを検索
        users_without_stats = db.session.query(User).outerjoin(UserStats).filter(
            User.username != 'admin',
            UserStats.id.is_(None)
        ).count()
        
        # 部屋別統計
        room_stats = db.session.query(
            UserStats.room_number,
            db.func.count(UserStats.id).label('count'),
            db.func.avg(UserStats.balance_score).label('avg_score'),
            db.func.max(UserStats.balance_score).label('max_score')
        ).group_by(UserStats.room_number).all()
        
        room_summary = []
        for room_stat in room_stats:
            room_summary.append({
                'room_number': room_stat.room_number,
                'user_count': room_stat.count,
                'avg_score': round(room_stat.avg_score, 1) if room_stat.avg_score else 0,
                'max_score': round(room_stat.max_score, 1) if room_stat.max_score else 0
            })
        
        return jsonify({
            'status': 'success',
            'summary': {
                'total_users': total_users,
                'total_stats': total_stats,
                'users_without_stats': users_without_stats,
                'outdated_stats': outdated_stats,
                'coverage_rate': round((total_stats / total_users * 100), 1) if total_users > 0 else 0
            },
            'room_stats': room_summary
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'統計確認エラー: {str(e)}'
        }), 500

@app.route('/admin/repair_user_stats', methods=['POST'])
def admin_repair_user_stats():
    """管理者用：不足している統計データを修復"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
    
    try:
        print("🔧 ユーザー統計修復開始...")
        
        # 統計がないユーザーを検索
        users_without_stats = db.session.query(User).outerjoin(UserStats).filter(
            User.username != 'admin',
            UserStats.id.is_(None)
        ).all()
        
        # 古い統計を更新
        one_day_ago = datetime.now(JST) - timedelta(days=1)
        outdated_stats = UserStats.query.filter(UserStats.last_updated < one_day_ago).all()
        
        repaired_count = 0
        updated_count = 0
        
        # 統計がないユーザーに新規作成
        for user in users_without_stats:
            try:
                stats = UserStats.get_or_create(user.id)
                if stats:
                    stats.update_stats()
                    repaired_count += 1
                    print(f"🔧 新規統計作成: {user.username}")
                    
            except Exception as user_error:
                print(f"❌ {user.username}の統計作成エラー: {user_error}")
                continue
        
        # 古い統計を更新
        for stats in outdated_stats:
            try:
                stats.update_stats()
                updated_count += 1
                print(f"🔄 統計更新: {stats.user.username}")
                
            except Exception as update_error:
                print(f"❌ {stats.user.username}の統計更新エラー: {update_error}")
                continue
        
        db.session.commit()
        
        message = f'修復完了: {repaired_count}件の統計を新規作成, {updated_count}件の統計を更新しました'
        print(f"✅ {message}")
        
        return jsonify({
            'status': 'success',
            'message': message,
            'repaired_count': repaired_count,
            'updated_count': updated_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': f'修復エラー: {str(e)}'
        }), 500

# app.py に以下の緊急修復用ルートを追加してください

@app.route('/emergency_create_user_stats')
def emergency_create_user_stats():
    """緊急修復：user_statsテーブルを作成"""
    try:
        print("🆘 緊急user_statsテーブル作成開始...")
        
        # 既存のトランザクションをクリア
        try:
            db.session.rollback()
        except:
            pass
        
        with db.engine.connect() as conn:
            # user_statsテーブルが存在するかチェック
            try:
                result = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'user_stats'
                    )
                """))
                table_exists = result.fetchone()[0]
                
                if table_exists:
                    return """
                    <h1>✅ user_statsテーブルは既に存在します</h1>
                    <p><a href="/admin">管理者ページに戻る</a></p>
                    <p><a href="/progress">進捗ページを確認</a></p>
                    """
                
                print("🔧 user_statsテーブルを作成中...")
                
                # user_statsテーブルを作成
                conn.execute(text("""
                    CREATE TABLE user_stats (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL UNIQUE REFERENCES "user"(id) ON DELETE CASCADE,
                        room_number VARCHAR(50) NOT NULL,
                        total_attempts INTEGER DEFAULT 0 NOT NULL,
                        total_correct INTEGER DEFAULT 0 NOT NULL,
                        mastered_count INTEGER DEFAULT 0 NOT NULL,
                        accuracy_rate FLOAT DEFAULT 0.0 NOT NULL,
                        coverage_rate FLOAT DEFAULT 0.0 NOT NULL,
                        balance_score FLOAT DEFAULT 0.0 NOT NULL,
                        mastery_score FLOAT DEFAULT 0.0 NOT NULL,
                        reliability_score FLOAT DEFAULT 0.0 NOT NULL,
                        activity_score FLOAT DEFAULT 0.0 NOT NULL,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        total_questions_in_room INTEGER DEFAULT 0 NOT NULL
                        incorrect_count INTEGER DEFAULT 0 NOT NULL,
                    )
                """))
                
                # インデックスを作成
                conn.execute(text("""
                    CREATE INDEX idx_user_stats_room_number ON user_stats(room_number)
                """))
                
                conn.commit()
                print("✅ user_statsテーブル作成完了")
                
                # テーブル作成後の確認
                result = conn.execute(text("SELECT COUNT(*) FROM user_stats"))
                count = result.fetchone()[0]
                
                return f"""
                <h1>✅ 緊急修復完了</h1>
                <p>user_statsテーブルの作成が完了しました。</p>
                <p>現在のレコード数: {count}件</p>
                <h3>次の手順:</h3>
                <ol>
                    <li><a href="/admin">管理者ページに移動</a></li>
                    <li>「📊 ユーザー統計管理」セクションで「🔄 全統計を強制再初期化」を実行</li>
                    <li><a href="/progress">進捗ページを確認</a></li>
                </ol>
                """
                
            except Exception as create_error:
                print(f"テーブル作成エラー: {create_error}")
                return f"""
                <h1>❌ テーブル作成エラー</h1>
                <p>エラー: {str(create_error)}</p>
                <p><a href="/admin">管理者ページに戻る</a></p>
                """
                
    except Exception as e:
        print(f"緊急修復失敗: {e}")
        return f"""
        <h1>💥 緊急修復失敗</h1>
        <p>エラー: {str(e)}</p>
        <p>手動でPostgreSQLにアクセスして以下のSQLを実行してください：</p>
        <pre>
CREATE TABLE user_stats (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES "user"(id) ON DELETE CASCADE,
    room_number VARCHAR(50) NOT NULL,
    total_attempts INTEGER DEFAULT 0 NOT NULL,
    total_correct INTEGER DEFAULT 0 NOT NULL,
    mastered_count INTEGER DEFAULT 0 NOT NULL,
    accuracy_rate FLOAT DEFAULT 0.0 NOT NULL,
    coverage_rate FLOAT DEFAULT 0.0 NOT NULL,
    balance_score FLOAT DEFAULT 0.0 NOT NULL,
    mastery_score FLOAT DEFAULT 0.0 NOT NULL,
    reliability_score FLOAT DEFAULT 0.0 NOT NULL,
    activity_score FLOAT DEFAULT 0.0 NOT NULL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    total_questions_in_room INTEGER DEFAULT 0 NOT NULL
);

CREATE INDEX idx_user_stats_room_number ON user_stats(room_number);
        </pre>
        """


@app.route('/admin/force_create_user_stats', methods=['POST'])
def admin_force_create_user_stats():
    """管理者用：user_statsテーブル強制作成"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
    
    try:
        print("🔧 管理者による強制テーブル作成...")
        
        with db.engine.connect() as conn:
            # テーブル存在確認
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'user_stats'
                )
            """))
            table_exists = result.fetchone()[0]
            
            if table_exists:
                return jsonify({
                    'status': 'info',
                    'message': 'user_statsテーブルは既に存在します'
                })
            
            # テーブル作成
            conn.execute(text("""
                CREATE TABLE user_stats (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE REFERENCES "user"(id) ON DELETE CASCADE,
                    room_number VARCHAR(50) NOT NULL,
                    total_attempts INTEGER DEFAULT 0 NOT NULL,
                    total_correct INTEGER DEFAULT 0 NOT NULL,
                    mastered_count INTEGER DEFAULT 0 NOT NULL,
                    accuracy_rate FLOAT DEFAULT 0.0 NOT NULL,
                    coverage_rate FLOAT DEFAULT 0.0 NOT NULL,
                    balance_score FLOAT DEFAULT 0.0 NOT NULL,
                    mastery_score FLOAT DEFAULT 0.0 NOT NULL,
                    reliability_score FLOAT DEFAULT 0.0 NOT NULL,
                    activity_score FLOAT DEFAULT 0.0 NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    total_questions_in_room INTEGER DEFAULT 0 NOT NULL
                )
            """))
            
            # インデックス作成
            conn.execute(text("""
                CREATE INDEX idx_user_stats_room_number ON user_stats(room_number)
            """))
            
            conn.commit()
            
            return jsonify({
                'status': 'success',
                'message': 'user_statsテーブルを作成しました'
            })
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'テーブル作成エラー: {str(e)}'
        }), 500

# ====================================================================
# 管理者ページ
# ====================================================================
# app.py の admin_page ルートを以下に置き換えてください

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
        room_max_unit_settings = {}
        for rs in room_settings:
            if hasattr(rs, 'max_enabled_unit_number'):
                room_max_unit_settings[rs.room_number] = rs.max_enabled_unit_number
            else:
                room_max_unit_settings[rs.room_number] = "9999"  # デフォルト値
        room_csv_settings = {rs.room_number: rs.csv_filename for rs in room_settings}
        room_ranking_settings = {rs.room_number: getattr(rs, 'ranking_display_count', 10) for rs in room_settings}
        
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
        
        # デフォルト設定の作成処理
        for room_num in unique_room_numbers:
            if room_num not in room_csv_settings:
                default_room_setting = RoomSetting(
                    room_number=room_num,
                    max_enabled_unit_number="9999",
                    csv_filename="words.csv",
                    ranking_display_count=10  # ★ランキング表示人数のデフォルト値
                )
                db.session.add(default_room_setting)
                room_max_unit_settings[room_num] = "9999"
                room_csv_settings[room_num] = "words.csv"
                room_ranking_settings[room_num] = 10
        
        try:
            db.session.commit()
        except Exception as e:
            print(f"⚠️ デフォルト設定作成エラー: {e}")
            db.session.rollback()
        
        # 統計情報を取得
        total_users = len(user_list_with_details)
        total_rooms = len(unique_room_numbers)
        
        # 最近のログイン状況
        recent_logins = 0
        for user in user_list_with_details:
            if user['last_login'] != 'なし':
                try:
                    login_time = datetime.strptime(user['last_login'], '%Y-%m-%d %H:%M:%S')
                    days_ago = (datetime.now() - login_time).days
                    if days_ago <= 7:  # 1週間以内
                        recent_logins += 1
                except:
                    pass
        
        context = get_template_context()
        
        template_context = {
            'users': user_list_with_details,
            'room_max_unit_settings': room_max_unit_settings,
            'room_csv_settings': room_csv_settings,
            'room_ranking_settings': room_ranking_settings,  # ★ランキング設定を追加
            'admin_stats': {  # ★管理者ダッシュボード用統計
                'total_users': total_users,
                'total_rooms': total_rooms,
                'recent_logins': recent_logins,
                'unique_room_numbers': sorted(list(unique_room_numbers), key=lambda x: int(x) if x.isdigit() else float('inf'))
            },
            **context
        }
        
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

# app.py の admin_add_user ルートを修正

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

        # 重複チェック
        existing_user = User.query.filter_by(
            room_number=room_number, 
            username=username
        ).first()
                    
        if existing_user:
            flash(f'部屋{room_number}にユーザー名{username}は既に存在します。', 'danger')
            return redirect(url_for('admin_page'))

        # 🆕 新規ユーザー作成（初回ログインフラグ付き）
        new_user = User(
            room_number=room_number,
            student_id=student_id,
            username=username,
            original_username=username,
            is_first_login=True  # 🆕 初回ログインフラグを設定
        )
        new_user.set_room_password(room_password)
        new_user.set_individual_password(individual_password)
        new_user.problem_history = "{}"
        new_user.incorrect_words = "[]"
        new_user.last_login = datetime.now(JST)

        db.session.add(new_user)
        db.session.commit()
        
        # 部屋設定の自動作成
        if not RoomSetting.query.filter_by(room_number=room_number).first():
            default_room_setting = RoomSetting(room_number=room_number, max_enabled_unit_number="9999", csv_filename="words.csv")
            db.session.add(default_room_setting)
            db.session.commit()
            flash(f'部屋 {room_number} の設定をデフォルトで作成しました。', 'info')

        flash(f'ユーザー {username} (部屋: {room_number}, 出席番号: {student_id}) を登録しました。初回ログイン時にパスワード変更が必要です。', 'success')
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
@admin_required # <- 追加
def get_room_setting():
    room_number = request.json.get('room_number')
    if not room_number:
        return jsonify(status='error', message='部屋番号が必要です'), 400
    
    room_setting = RoomSetting.query.filter_by(room_number=room_number).first()
    if not room_setting:
        return jsonify(status='success', csv_filename='words.csv', enabled_units=[], max_enabled_unit_number="9999")
    
    return jsonify({
        'status': 'success',
        'csv_filename': room_setting.csv_filename,
        'enabled_units': room_setting.get_enabled_units(),
        'max_enabled_unit_number': room_setting.max_enabled_unit_number # 追加
    })

def admin_get_room_setting():
    """部屋設定を取得するAPI（ランキング表示人数を含む）"""
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
            # 安全に属性にアクセス
            max_unit = getattr(room_setting, 'max_enabled_unit_number', '9999')
            csv_filename = getattr(room_setting, 'csv_filename', 'words.csv')
            ranking_count = getattr(room_setting, 'ranking_display_count', 10)
            enabled_units = room_setting.get_enabled_units() if hasattr(room_setting, 'get_enabled_units') else []
            
            result = {
                'status': 'success',
                'room_number': room_setting.room_number,
                'max_enabled_unit_number': max_unit,
                'enabled_units': enabled_units,
                'csv_filename': csv_filename,
                'ranking_display_count': ranking_count
            }
            print(f"✅ 部屋設定取得成功: ランキング表示{ranking_count}人")
        else:
            # デフォルト設定を返す
            result = {
                'status': 'success',
                'room_number': room_number,
                'max_enabled_unit_number': '9999',
                'enabled_units': [],
                'csv_filename': 'words.csv',
                'ranking_display_count': 10
            }
            print(f"📄 デフォルト設定を返却: {room_number}")

        return jsonify(result)
        
    except Exception as e:
        print(f"❌ 部屋設定取得エラー: {e}")
        return jsonify(status='error', message=str(e)), 500

# app.py

@app.route('/admin/update_room_setting', methods=['POST'])
@admin_required
def update_room_setting():
    data = request.get_json()
    room_number = data.get('room_number')
    csv_filename = data.get('csv_filename')
    max_enabled_unit_number = data.get('max_enabled_unit_number')

    if not room_number:
        return jsonify(status='error', message='部屋番号が必要です'), 400

    room_setting = RoomSetting.query.filter_by(room_number=room_number).first()
    if not room_setting:
        room_setting = RoomSetting(room_number=room_number)
        db.session.add(room_setting)

    if csv_filename is not None:
        room_setting.csv_filename = secure_filename(csv_filename)
    
    if max_enabled_unit_number is not None:
        room_setting.max_enabled_unit_number = max_enabled_unit_number

    try:
        db.session.commit()
        # 統計を更新
        users_in_room = User.query.filter_by(room_number=room_number).all()
        for user in users_in_room:
            if user.stats:
                user.stats.update_stats()
        db.session.commit()
        
        return jsonify(status='success', message=f'部屋 {room_number} の設定を更新しました')
    except Exception as e:
        db.session.rollback()
        print(f"❌ 部屋設定更新エラー: {e}")
        return jsonify(status='error', message=str(e)), 500

@app.route('/admin/get_csv_files')
@admin_required
def get_csv_files():
    try:
        csv_files = RoomCsvFile.query.all()
        file_list = [{
            'filename': f.filename,
            'original_filename': f.original_filename,
            'word_count': f.word_count
        } for f in csv_files]
        return jsonify(status='success', csv_files=file_list)
    except Exception as e:
        return jsonify(status='error', message=str(e)), 500

@app.route('/admin/update_room_units_setting', methods=['POST'])
def admin_update_room_units_setting():
    """部屋の有効単元設定を更新"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify(status='error', message='管理者権限がありません。'), 403

        data = request.get_json()
        room_number = data.get('room_number')
        enabled_units = data.get('enabled_units', [])

        if not room_number:
            return jsonify(status='error', message='部屋番号が指定されていません。'), 400

        room_setting = RoomSetting.query.filter_by(room_number=room_number).first()

        if room_setting:
            room_setting.set_enabled_units(enabled_units)
        else:
            new_room_setting = RoomSetting(
                room_number=room_number, 
                enabled_units=json.dumps(enabled_units), 
                csv_filename="words.csv"
            )
            db.session.add(new_room_setting)
        
        db.session.commit()
        return jsonify(
            status='success', 
            message=f'部屋 {room_number} の単元設定を更新しました。',
            enabled_units=enabled_units
        )
    except Exception as e:
        print(f"Error in admin_update_room_units_setting: {e}")
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

@app.route('/admin/update_all_rankings_to_5', methods=['POST'])
def admin_update_all_rankings_to_5():
    """全ての部屋のランキング表示人数を5に変更"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
    
    try:
        print("🔧 全部屋のランキング表示人数を5に変更中...")
        
        # 全ての部屋設定を取得
        room_settings = RoomSetting.query.all()
        updated_count = 0
        
        for setting in room_settings:
            if hasattr(setting, 'ranking_display_count'):
                setting.ranking_display_count = 5
                updated_count += 1
            else:
                print(f"⚠️ 部屋{setting.room_number}にranking_display_countカラムがありません")
        
        db.session.commit()
        
        print(f"✅ {updated_count}個の部屋設定を更新しました")
        
        return jsonify({
            'status': 'success',
            'message': f'全{updated_count}部屋のランキング表示人数を5に変更しました',
            'updated_count': updated_count
        })
        
    except Exception as e:
        print(f"❌ 更新エラー: {e}")
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': f'更新エラー: {str(e)}'
        }), 500

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
        print("🔍 全ユーザーCSV処理開始...")
        start_time = time.time()
        
        # ファイル読み込み
        content = file.read()
        
        # ファイルサイズチェック
        if len(content) > 10240:  # 10KB制限
            flash('CSVファイルが大きすぎます（10KB以下にしてください）。', 'danger')
            return redirect(url_for('admin_page'))
        
        content_str = content.decode('utf-8')
        lines = content_str.strip().split('\n')
        
        # 行数制限
        if len(lines) > 50:  # 50行制限
            flash('CSVファイルの行数が多すぎます（50行以下にしてください）。', 'danger')
            return redirect(url_for('admin_page'))
        
        print(f"📊 ファイルサイズ: {len(content)}bytes, 行数: {len(lines)}")
        
        if len(lines) < 2:
            flash('CSVファイルにデータがありません。', 'danger')
            return redirect(url_for('admin_page'))
        
        # ヘッダー行をスキップして、すべてのデータ行を処理
        header_line = lines[0]
        data_lines = lines[1:]  # 2行目以降すべて
        
        print(f"📋 ヘッダー: {header_line}")
        print(f"📋 処理対象データ行数: {len(data_lines)}")
        
        users_added_count = 0
        errors = []
        skipped_count = 0
        
        # ★修正: すべてのデータ行を処理
        for line_num, data_line in enumerate(data_lines, start=2):
            try:
                if not data_line.strip():
                    continue
                    
                values = [v.strip() for v in data_line.split(',')]
                if len(values) < 5:
                    errors.append(f"行{line_num}: データが不完全です")
                    continue
                
                room_number, room_password, student_id, individual_password, username = values[:5]
                
                # 必須項目チェック
                if not all([room_number, room_password, student_id, individual_password, username]):
                    errors.append(f"行{line_num}: 必須項目が不足しています")
                    continue

                # 重複チェック
                existing_user = User.query.filter_by(room_number=room_number, username=username).first()
                if existing_user:
                    errors.append(f"行{line_num}: ユーザー {username} は既に存在します")
                    skipped_count += 1
                    continue

                # 新規ユーザー作成（軽量パスワードハッシュ化）
                new_user = User(
                    room_number=room_number,
                    student_id=student_id,
                    username=username,
                    original_username=username,
                    is_first_login=True  # 🆕 CSV一括追加でも初回ログインフラグを設定
                )
                
                # ★修正: 軽量パスワードハッシュ化
                new_user._room_password_hash = generate_password_hash(room_password, method='pbkdf2:sha256', salt_length=8)
                new_user._individual_password_hash = generate_password_hash(individual_password, method='pbkdf2:sha256', salt_length=8)

                new_user.problem_history = "{}"
                new_user.incorrect_words = "[]"
                new_user.last_login = datetime.now(JST)

                db.session.add(new_user)
                users_added_count += 1
                print(f"✅ ユーザー準備: {username} ({users_added_count}/{len(data_lines)})")
                
                # 5件ごとにコミット（効率化）
                if users_added_count % 5 == 0:
                    db.session.commit()
                    print(f"💾 バッチコミット: {users_added_count}件完了")
                    
                    # メモリ解放
                    import gc
                    gc.collect()

            except Exception as e:
                db.session.rollback()
                errors.append(f"行{line_num}: エラー - {str(e)[:50]}")
                print(f"❌ 行{line_num}エラー: {e}")
                continue

        # 最終コミット（余りがある場合）
        if users_added_count % 5 != 0:
            db.session.commit()
            print(f"💾 最終コミット: {users_added_count}件完了")

        total_time = time.time() - start_time
        print(f"🏁 全体処理完了: {users_added_count}ユーザー追加, 処理時間: {total_time:.2f}秒")

        # 結果メッセージ
        if users_added_count > 0:
            flash(f'✅ {users_added_count}人のユーザーを追加しました（処理時間: {total_time:.1f}秒）', 'success')
        
        if skipped_count > 0:
            flash(f'⚠️ {skipped_count}人のユーザーは重複のためスキップしました', 'warning')
            
        if errors:
            error_count = len(errors)
            if error_count <= 3:
                flash(f'❌ エラー: {", ".join(errors)}', 'danger')
            else:
                flash(f'❌ {error_count}件のエラーが発生しました。最初の3件: {", ".join(errors[:3])}', 'danger')
                
    except Exception as e:
        error_time = time.time() - start_time if 'start_time' in locals() else 0
        print(f"❌ 致命的エラー: {e} (処理時間: {error_time:.2f}秒)")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        flash(f'CSV処理エラー: {str(e)} (処理時間: {error_time:.1f}秒)', 'danger')

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

@app.route('/api/check_special_status/<chapter_num>')
def api_check_special_status(chapter_num):
    """特定の章のZ問題解放状態をチェック"""
    try:
        if 'user_id' not in session:
            return jsonify(status='error', message='認証が必要です'), 401
        
        current_user = User.query.get(session['user_id'])
        if not current_user:
            return jsonify(status='error', message='ユーザーが見つかりません'), 404
        
        users = User.query.filter_by(room_number=current_user.room_number).all()
        word_data = load_word_data_for_room(current_user.room_number)
        regular_problems = [w for w in word_data if w['chapter'] == chapter_num and str(w['number']).upper() != 'Z']
        
        is_unlocked = check_special_unlock_status(chapter_num, regular_problems, users)
        
        return jsonify({
            'status': 'success',
            'chapter': chapter_num,
            'special_unlocked': is_unlocked,
            'regular_problems_count': len(regular_problems)
        })
        
    except Exception as e:
        return jsonify(status='error', message=str(e)), 500

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
        return {
            'app_info': app_info,
            'app_name': app_info.app_name
        }
    except Exception as e:
        logger.error(f"Error getting app_info: {e}")
        return {
            'app_info': None,
            'app_name': 'アプリ'  # エラー時のデフォルト値
        }

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

def load_raw_word_data_for_room(room_number):
    """管理者用：フィルタリングなしで部屋の単語データを読み込む"""
    try:
        room_setting = RoomSetting.query.filter_by(room_number=room_number).first()
        
        if room_setting and room_setting.csv_filename:
            csv_filename = room_setting.csv_filename
        else:
            csv_filename = "words.csv"
        
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
                except Exception as parse_error:
                    print(f"❌ CSVパースエラー: {parse_error}")
                    return []
            else:
                print(f"❌ データベースにCSVが見つかりません: {csv_filename}")
                return []
        
        return word_data  # フィルタリングなしで返す
        
    except Exception as e:
        print(f"❌ 読み込みエラー: {e}")
        return []

@app.route('/emergency_add_ranking_column')
def emergency_add_ranking_column():
    """緊急修復：ranking_display_countカラムを追加（GET版）"""
    try:
        print("🆘 緊急ranking_display_countカラム追加開始...")
        
        with db.engine.connect() as conn:
            # カラム存在確認
            try:
                result = conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'room_setting' AND column_name = 'ranking_display_count'
                """))
                
                if not result.fetchone():
                    print("🔧 ranking_display_countカラムを追加中...")
                    conn.execute(text('ALTER TABLE room_setting ADD COLUMN ranking_display_count INTEGER DEFAULT 10'))
                    conn.commit()
                    print("✅ ranking_display_countカラムを追加しました")
                    
                    return """
                    <h1>✅ 緊急修復完了</h1>
                    <p>ranking_display_countカラムを追加しました。</p>
                    <p><a href="/admin">管理者ページに戻る</a></p>
                    <p><a href="/admin/upload_room_csv">CSVアップロードを再試行</a></p>
                    """
                else:
                    return """
                    <h1>✅ カラムは既に存在します</h1>
                    <p>ranking_display_countカラムは既に存在します。</p>
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
        """

@app.route('/debug_room_setting_model')
def debug_room_setting_model():
    """RoomSettingモデルの状態をデバッグ"""
    if not session.get('admin_logged_in'):
        return "管理者権限が必要です", 403
    
    try:
        # モデルの属性を確認
        model_attributes = [attr for attr in dir(RoomSetting) if not attr.startswith('_')]
        
        # データベースのカラムを確認
        with db.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'room_setting'
                ORDER BY column_name
            """))
            db_columns = [row[0] for row in result.fetchall()]
        
        # テスト用のRoomSettingインスタンスを作成してみる
        test_instance_error = None
        try:
            test_room = RoomSetting(
                room_number="TEST",
                ranking_display_count=5  # この行でエラーが出るかテスト
            )
            test_success = True
        except Exception as e:
            test_success = False
            test_instance_error = str(e)
        
        return f"""
        <h1>RoomSetting モデル診断</h1>
        <h3>モデルの属性:</h3>
        <p>{model_attributes}</p>
        
        <h3>データベースのカラム:</h3>
        <p>{db_columns}</p>
        
        <h3>ranking_display_count の状態:</h3>
        <p>モデルにranking_display_countがあるか: {'ranking_display_count' in model_attributes}</p>
        <p>DBにranking_display_countがあるか: {'ranking_display_count' in db_columns}</p>
        
        <h3>テストインスタンス作成:</h3>
        <p>成功: {test_success}</p>
        <p>エラー: {test_instance_error}</p>
        
        <p><a href="/admin">管理者ページに戻る</a></p>
        """
        
    except Exception as e:
        return f"<h1>診断エラー: {str(e)}</h1>"
    
# app.py に追加する論述問題集用ルート

# ========================================
# 論述問題集用データベースモデル
# ========================================

class EssayProblem(db.Model):
    __tablename__ = 'essay_problems'
    
    id = db.Column(db.Integer, primary_key=True)
    chapter = db.Column(db.String(10), nullable=False)
    type = db.Column(db.String(1), nullable=False)  # A, B, C, D
    university = db.Column(db.String(100), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    answer_length = db.Column(db.Integer, nullable=False)
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    
    def to_dict(self):
        return {
            'id': self.id,
            'chapter': self.chapter,
            'type': self.type,
            'university': self.university,
            'year': self.year,
            'question': self.question,
            'answer': self.answer,
            'answer_length': self.answer_length,
            'enabled': self.enabled
        }

class EssayProgress(db.Model):
    __tablename__ = 'essay_progress'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    problem_id = db.Column(db.Integer, db.ForeignKey('essay_problems.id', ondelete='CASCADE'), nullable=False)
    viewed_answer = db.Column(db.Boolean, default=False, nullable=False)
    understood = db.Column(db.Boolean, default=False, nullable=False)
    difficulty_rating = db.Column(db.Integer)  # 1-5
    memo = db.Column(db.Text)
    review_flag = db.Column(db.Boolean, default=False, nullable=False)
    viewed_at = db.Column(db.DateTime)
    understood_at = db.Column(db.DateTime)
    last_updated = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'problem_id', name='unique_user_problem'),
    )
    
    user = db.relationship('User', backref='essay_progress')
    problem = db.relationship('EssayProblem', backref='progress_records')

class EssayCsvFile(db.Model):
    __tablename__ = 'essay_csv_files'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), unique=True, nullable=False)
    original_filename = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    problem_count = db.Column(db.Integer, default=0, nullable=False)
    upload_date = db.Column(db.DateTime, default=lambda: datetime.now(JST))

# ========================================
# 論述問題集用ルート
# ========================================

@app.route('/essay')
def essay_index():
    """論述問題集のメインページ"""
    try:
        if 'user_id' not in session:
            flash('論述問題集を利用するにはログインしてください。', 'info')
            return redirect(url_for('login_page'))
        
        current_user = User.query.get(session['user_id'])
        if not current_user:
            flash('ユーザーが見つかりません。', 'danger')
            return redirect(url_for('logout'))
        
        # 章別の問題数と進捗を取得
        chapter_stats = get_essay_chapter_stats(current_user.id)
        
        context = get_template_context()
        context.update({
            'chapter_stats': chapter_stats,
            'current_user': current_user
        })
        
        return render_template('essay_index.html', **context)
        
    except Exception as e:
        logger.error(f"Error in essay_index: {e}")
        flash('論述問題集の読み込み中にエラーが発生しました。', 'danger')
        return redirect(url_for('index'))

@app.route('/essay/chapter/<chapter>')
def essay_chapter(chapter):
    """章別問題一覧"""
    try:
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        
        current_user = User.query.get(session['user_id'])
        if not current_user:
            return redirect(url_for('logout'))
        
        # フィルタリングパラメータ
        type_filter = request.args.get('type', '')
        university_filter = request.args.get('university', '')
        year_from = request.args.get('year_from', type=int)
        year_to = request.args.get('year_to', type=int)
        keyword = request.args.get('keyword', '')
        
        # 問題一覧を取得
        problems = get_filtered_essay_problems(
            chapter=chapter,
            type_filter=type_filter,
            university_filter=university_filter,
            year_from=year_from,
            year_to=year_to,
            keyword=keyword,
            user_id=current_user.id
        )
        
        # フィルター用データ
        filter_data = get_essay_filter_data(chapter)
        
        context = get_template_context()
        context.update({
            'chapter': chapter,
            'chapter_name': f'第{chapter}章' if chapter != 'com' else '総合問題',
            'problems': problems,
            'filter_data': filter_data,
            'current_filters': {
                'type': type_filter,
                'university': university_filter,
                'year_from': year_from,
                'year_to': year_to,
                'keyword': keyword
            }
        })
        
        return render_template('essay_chapter.html', **context)
        
    except Exception as e:
        logger.error(f"Error in essay_chapter: {e}")
        flash('問題一覧の読み込み中にエラーが発生しました。', 'danger')
        return redirect(url_for('essay_index'))

@app.route('/essay/problem/<int:problem_id>')
def essay_problem(problem_id):
    """個別問題表示"""
    try:
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        
        current_user = User.query.get(session['user_id'])
        if not current_user:
            return redirect(url_for('logout'))
        
        # 問題を取得
        problem = EssayProblem.query.get_or_404(problem_id)
        
        # 進捗を取得または作成
        progress = EssayProgress.query.filter_by(
            user_id=current_user.id,
            problem_id=problem_id
        ).first()
        
        if not progress:
            progress = EssayProgress(
                user_id=current_user.id,
                problem_id=problem_id
            )
            db.session.add(progress)
            db.session.commit()
        
        # 同じ章の前後の問題を取得
        prev_problem, next_problem = get_adjacent_problems(problem)
        
        context = get_template_context()
        context.update({
            'problem': problem,
            'progress': progress,
            'prev_problem': prev_problem,
            'next_problem': next_problem
        })
        
        return render_template('essay_problem.html', **context)
        
    except Exception as e:
        logger.error(f"Error in essay_problem: {e}")
        flash('問題の読み込み中にエラーが発生しました。', 'danger')
        return redirect(url_for('essay_index'))

# ========================================
# API エンドポイント
# ========================================

@app.route('/api/essay/progress/update', methods=['POST'])
def update_essay_progress():
    """論述問題の進捗更新"""
    try:
        if 'user_id' not in session:
            return jsonify({'status': 'error', 'message': 'ログインが必要です'}), 401
        
        data = request.get_json()
        problem_id = data.get('problem_id')
        updates = data.get('updates', {})
        
        if not problem_id:
            return jsonify({'status': 'error', 'message': '問題IDが必要です'}), 400
        
        current_user = User.query.get(session['user_id'])
        if not current_user:
            return jsonify({'status': 'error', 'message': 'ユーザーが見つかりません'}), 404
        
        # 進捗を取得または作成
        progress = EssayProgress.query.filter_by(
            user_id=current_user.id,
            problem_id=problem_id
        ).first()
        
        if not progress:
            progress = EssayProgress(
                user_id=current_user.id,
                problem_id=problem_id
            )
            db.session.add(progress)
        
        # 更新処理
        now = datetime.now(JST)
        
        if 'viewed_answer' in updates and updates['viewed_answer']:
            progress.viewed_answer = True
            if not progress.viewed_at:
                progress.viewed_at = now
        
        if 'understood' in updates:
            progress.understood = updates['understood']
            if updates['understood']:
                progress.understood_at = now
        
        if 'difficulty_rating' in updates:
            progress.difficulty_rating = updates['difficulty_rating']
        
        if 'memo' in updates:
            progress.memo = updates['memo']
        
        if 'review_flag' in updates:
            progress.review_flag = updates['review_flag']
        
        progress.last_updated = now
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': '進捗を更新しました',
            'progress': {
                'viewed_answer': progress.viewed_answer,
                'understood': progress.understood,
                'difficulty_rating': progress.difficulty_rating,
                'memo': progress.memo,
                'review_flag': progress.review_flag
            }
        })
        
    except Exception as e:
        logger.error(f"Error updating essay progress: {e}")
        db.session.rollback()
        return jsonify({'status': 'error', 'message': '進捗の更新中にエラーが発生しました'}), 500

# ========================================
# ヘルパー関数
# ========================================
def get_essay_chapter_stats(user_id):
    """章別の統計情報を取得"""
    try:
        # 章別の問題数と進捗を集計
        stats_query = db.session.query(
            EssayProblem.chapter,
            func.count(EssayProblem.id).label('total_problems'),
            func.count(EssayProgress.id).label('viewed_problems'),
            func.sum(
                db.case(
                    (EssayProgress.understood == True, 1),
                    else_=0
                )
            ).label('understood_problems')
        ).outerjoin(
            EssayProgress,
            db.and_(
                EssayProblem.id == EssayProgress.problem_id,
                EssayProgress.user_id == user_id
            )
        ).filter(
            EssayProblem.enabled == True
        ).group_by(
            EssayProblem.chapter
        ).order_by(
            db.case(
                (EssayProblem.chapter == 'com', 999),
                else_=db.cast(EssayProblem.chapter, db.Integer)
            )
        ).all()
        
        chapter_stats = []
        for stat in stats_query:
            chapter_stats.append({
                'chapter': stat.chapter,
                'chapter_name': f'第{stat.chapter}章' if stat.chapter != 'com' else '総合問題',
                'total_problems': stat.total_problems,
                'viewed_problems': stat.viewed_problems or 0,
                'understood_problems': stat.understood_problems or 0,
                'progress_rate': round((stat.understood_problems or 0) / stat.total_problems * 100, 1) if stat.total_problems > 0 else 0
            })
        
        return chapter_stats
        
    except Exception as e:
        logger.error(f"Error getting essay chapter stats: {e}")
        return []

def get_filtered_essay_problems(chapter, type_filter='', university_filter='', 
                               year_from=None, year_to=None, keyword='', user_id=None):
    """フィルタリングされた問題一覧を取得"""
    try:
        query = db.session.query(EssayProblem, EssayProgress).outerjoin(
            EssayProgress,
            (EssayProblem.id == EssayProgress.problem_id) & 
            (EssayProgress.user_id == user_id)
        ).filter(
            EssayProblem.chapter == chapter,
            EssayProblem.enabled == True
        )
        
        # フィルタリング
        if type_filter:
            query = query.filter(EssayProblem.type == type_filter)
        
        if university_filter:
            query = query.filter(EssayProblem.university.ilike(f'%{university_filter}%'))
        
        if year_from:
            query = query.filter(EssayProblem.year >= year_from)
        
        if year_to:
            query = query.filter(EssayProblem.year <= year_to)
        
        if keyword:
            keyword_filter = f'%{keyword}%'
            query = query.filter(
                db.or_(
                    EssayProblem.question.ilike(keyword_filter),
                    EssayProblem.answer.ilike(keyword_filter)
                )
            )
        
        # ソート: type → year → university
        query = query.order_by(
            EssayProblem.type,
            EssayProblem.year.desc(),
            EssayProblem.university
        )
        
        results = query.all()
        
        problems = []
        for problem, progress in results:
            problem_data = problem.to_dict()
            problem_data['preview'] = problem.question[:20] + '...' if len(problem.question) > 20 else problem.question
            problem_data['progress'] = {
                'viewed_answer': progress.viewed_answer if progress else False,
                'understood': progress.understood if progress else False,
                'difficulty_rating': progress.difficulty_rating if progress else None,
                'review_flag': progress.review_flag if progress else False
            }
            problems.append(problem_data)
        
        return problems
        
    except Exception as e:
        logger.error(f"Error getting filtered essay problems: {e}")
        return []

def get_essay_filter_data(chapter):
    """フィルター用のデータを取得"""
    try:
        # 大学一覧
        universities = db.session.query(EssayProblem.university).filter(
            EssayProblem.chapter == chapter,
            EssayProblem.enabled == True
        ).distinct().order_by(EssayProblem.university).all()
        
        # 年度範囲
        year_range = db.session.query(
            func.min(EssayProblem.year).label('min_year'),
            func.max(EssayProblem.year).label('max_year')
        ).filter(
            EssayProblem.chapter == chapter,
            EssayProblem.enabled == True
        ).first()
        
        return {
            'universities': [u[0] for u in universities],
            'year_range': {
                'min': year_range.min_year or 2020,
                'max': year_range.max_year or 2025
            },
            'types': ['A', 'B', 'C', 'D']
        }
        
    except Exception as e:
        logger.error(f"Error getting essay filter data: {e}")
        return {
            'universities': [],
            'year_range': {'min': 2020, 'max': 2025},
            'types': ['A', 'B', 'C', 'D']
        }

def get_adjacent_problems(problem):
    """前後の問題を取得"""
    try:
        # 同じ章の問題を type → year → university の順でソート
        ordered_problems = EssayProblem.query.filter(
            EssayProblem.chapter == problem.chapter,
            EssayProblem.enabled == True
        ).order_by(
            EssayProblem.type,
            EssayProblem.year.desc(),
            EssayProblem.university
        ).all()
        
        current_index = None
        for i, p in enumerate(ordered_problems):
            if p.id == problem.id:
                current_index = i
                break
        
        if current_index is None:
            return None, None
        
        prev_problem = ordered_problems[current_index - 1] if current_index > 0 else None
        next_problem = ordered_problems[current_index + 1] if current_index < len(ordered_problems) - 1 else None
        
        return prev_problem, next_problem
        
    except Exception as e:
        logger.error(f"Error getting adjacent problems: {e}")
        return None, None

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

@app.route('/emergency_fix_room_setting')
def emergency_fix_room_setting():
    """緊急修復：room_settingテーブルのカラムを修正"""
    try:
        print("🆘 緊急room_setting修復開始...")
        
        # 既存のトランザクションをクリア
        try:
            db.session.rollback()
        except:
            pass
        
        with db.engine.connect() as conn:
            # 現在のroom_settingテーブルの構造を確認
            try:
                result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'room_setting'"))
                existing_columns = [row[0] for row in result.fetchall()]
                print(f"既存カラム: {existing_columns}")
                
                messages = []
                
                # max_enabled_unit_numberカラムが存在しない場合は追加
                if 'max_enabled_unit_number' not in existing_columns:
                    print("🔧 max_enabled_unit_numberカラムを追加中...")
                    conn.execute(text('ALTER TABLE room_setting ADD COLUMN max_enabled_unit_number VARCHAR(50) DEFAULT \'9999\''))
                    messages.append("✅ max_enabled_unit_numberカラムを追加しました")
                else:
                    messages.append("✅ max_enabled_unit_numberカラムは既に存在します")
                
                # enabled_unitsカラムが存在しない場合は追加
                if 'enabled_units' not in existing_columns:
                    print("🔧 enabled_unitsカラムを追加中...")
                    conn.execute(text('ALTER TABLE room_setting ADD COLUMN enabled_units TEXT DEFAULT \'[]\''))
                    messages.append("✅ enabled_unitsカラムを追加しました")
                else:
                    messages.append("✅ enabled_unitsカラムは既に存在します")
                
                conn.commit()
                
                # 修復後の状態確認
                result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'room_setting'"))
                final_columns = [row[0] for row in result.fetchall()]
                print(f"修復後のカラム: {final_columns}")
                
                return f"""
                <h1>✅ 緊急修復完了</h1>
                <p>room_settingテーブルの修復が完了しました。</p>
                <h3>実行結果:</h3>
                <ul>
                    {''.join(f'<li>{msg}</li>' for msg in messages)}
                </ul>
                <h3>修復前のカラム:</h3>
                <p>{existing_columns}</p>
                <h3>修復後のカラム:</h3>
                <p>{final_columns}</p>
                <p><a href="/admin">管理者ページに戻る</a></p>
                <p><a href="/login">ログインページに戻る</a></p>
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
        <pre>
ALTER TABLE room_setting ADD COLUMN max_enabled_unit_number VARCHAR(50) DEFAULT '9999';
ALTER TABLE room_setting ADD COLUMN enabled_units TEXT DEFAULT '[]';
        </pre>
        """

@app.route('/admin/fix_room_settings_attributes', methods=['POST'])
def admin_fix_room_settings_attributes():
    """部屋設定の属性不整合を修復"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
    
    try:
        print("🔧 部屋設定属性修復開始...")
        
        # 全ての部屋設定を取得
        room_settings = RoomSetting.query.all()
        fixed_count = 0
        
        with db.engine.connect() as conn:
            for setting in room_settings:
                try:
                    # 必要な属性が存在するかチェック
                    if not hasattr(setting, 'max_enabled_unit_number'):
                        # SQLで直接更新
                        conn.execute(text(f"""
                            UPDATE room_setting 
                            SET max_enabled_unit_number = '9999' 
                            WHERE room_number = '{setting.room_number}'
                        """))
                        fixed_count += 1
                        
                    if not hasattr(setting, 'enabled_units'):
                        # SQLで直接更新
                        conn.execute(text(f"""
                            UPDATE room_setting 
                            SET enabled_units = '[]' 
                            WHERE room_number = '{setting.room_number}'
                        """))
                        
                except Exception as setting_error:
                    print(f"⚠️ 設定修復エラー ({setting.room_number}): {setting_error}")
                    continue
            
            conn.commit()
        
        # SQLAlchemyのセッションをリフレッシュ
        db.session.expire_all()
        
        return jsonify({
            'status': 'success',
            'message': f'{fixed_count}個の部屋設定を修復しました',
            'fixed_count': fixed_count
        })
        
    except Exception as e:
        print(f"❌ 属性修復エラー: {e}")
        return jsonify({
            'status': 'error',
            'message': f'修復エラー: {str(e)}'
        }), 500

# app.py に追加する管理者用全員ランキング機能
@app.route('/api/rooms')
def api_rooms():
    """管理者用：全部屋の一覧を取得"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify(status='error', message='管理者権限が必要です'), 403
        
        # 部屋別のユーザー数を集計
        rooms_data = db.session.query(
            User.room_number,
            db.func.count(User.id).label('user_count')
        ).filter(
            User.room_number != 'ADMIN'
        ).group_by(User.room_number).all()
        
        rooms = []
        for room_data in rooms_data:
            rooms.append({
                'room_number': room_data.room_number,
                'user_count': room_data.user_count
            })
        
        # 部屋番号でソート
        rooms.sort(key=lambda x: int(x['room_number']) if x['room_number'].isdigit() else float('inf'))
        
        return jsonify({
            'status': 'success',
            'rooms': rooms
        })
        
    except Exception as e:
        print(f"❌ 部屋一覧取得エラー: {e}")
        return jsonify(status='error', message=str(e)), 500

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

@app.route('/admin/comprehensive_storage_analysis')
def admin_comprehensive_storage_analysis():
    """包括的ストレージ分析（データベース全体を調査）"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('login_page'))
    
    try:
        analysis = {}
        
        # 1. 各テーブルのレコード数とサイズ推定
        table_analysis = {}
        
        # Userテーブル
        users = User.query.all()
        user_data_size = 0
        user_count = 0
        max_user_size = 0
        max_user_name = ""
        
        for user in users:
            if user.username == 'admin':
                continue
            user_count += 1
            
            # 各フィールドのサイズを計算
            user_size = 0
            user_size += len(str(user.username).encode('utf-8'))
            user_size += len(str(user.room_number).encode('utf-8'))
            user_size += len(str(user.student_id).encode('utf-8'))
            
            if user.problem_history:
                user_size += len(user.problem_history.encode('utf-8'))
            if user.incorrect_words:
                user_size += len(user.incorrect_words.encode('utf-8'))
            
            # パスワードハッシュのサイズ
            if hasattr(user, '_room_password_hash') and user._room_password_hash:
                user_size += len(user._room_password_hash.encode('utf-8'))
            if hasattr(user, '_individual_password_hash') and user._individual_password_hash:
                user_size += len(user._individual_password_hash.encode('utf-8'))
            
            user_data_size += user_size
            
            if user_size > max_user_size:
                max_user_size = user_size
                max_user_name = user.username
        
        table_analysis['users'] = {
            'count': user_count,
            'total_size_mb': round(user_data_size / (1024 * 1024), 3),
            'avg_size_kb': round(user_data_size / user_count / 1024, 2) if user_count > 0 else 0,
            'max_user': max_user_name,
            'max_size_kb': round(max_user_size / 1024, 2)
        }
        
        # CSVファイルテーブル
        csv_files = CsvFileContent.query.all()
        csv_total_size = sum(len(f.content.encode('utf-8')) for f in csv_files)
        
        table_analysis['csv_files'] = {
            'count': len(csv_files),
            'total_size_mb': round(csv_total_size / (1024 * 1024), 3),
            'files': [
                {
                    'filename': f.filename,
                    'size_kb': round(len(f.content.encode('utf-8')) / 1024, 2),
                    'word_count': f.word_count
                }
                for f in csv_files
            ]
        }
        
        # その他のテーブル
        room_settings = RoomSetting.query.all()
        settings_size = sum(
            len(str(rs.room_number).encode('utf-8')) +
            len(str(rs.csv_filename).encode('utf-8')) +
            len(str(rs.max_enabled_unit_number).encode('utf-8')) +
            len(str(getattr(rs, 'enabled_units', '')).encode('utf-8'))
            for rs in room_settings
        )
        
        table_analysis['room_settings'] = {
            'count': len(room_settings),
            'total_size_kb': round(settings_size / 1024, 2)
        }
        
        # パスワードリセットトークン
        tokens = PasswordResetToken.query.all()
        tokens_size = sum(
            len(str(t.token).encode('utf-8')) +
            len(str(t.user_id).encode('utf-8')) +
            32  # 日時フィールドの推定サイズ
            for t in tokens
        )
        
        table_analysis['password_tokens'] = {
            'count': len(tokens),
            'total_size_kb': round(tokens_size / 1024, 2)
        }
        
        # AppInfoテーブル
        app_infos = AppInfo.query.all()
        app_info_size = 0
        for info in app_infos:
            app_info_size += len(str(info.app_name).encode('utf-8'))
            app_info_size += len(str(info.update_content).encode('utf-8'))
            app_info_size += len(str(getattr(info, 'footer_text', '')).encode('utf-8'))
            # その他のフィールド
        
        table_analysis['app_info'] = {
            'count': len(app_infos),
            'total_size_kb': round(app_info_size / 1024, 2)
        }
        
        # UserStatsテーブル（存在する場合）
        try:
            user_stats = UserStats.query.all()
            stats_size = len(user_stats) * 200  # 1レコードあたり約200バイトと推定
            table_analysis['user_stats'] = {
                'count': len(user_stats),
                'total_size_kb': round(stats_size / 1024, 2)
            }
        except:
            table_analysis['user_stats'] = {
                'count': 0,
                'total_size_kb': 0
            }
        
        # 総計算
        total_estimated_mb = sum([
            table_analysis['users']['total_size_mb'],
            table_analysis['csv_files']['total_size_mb'],
            table_analysis['room_settings']['total_size_kb'] / 1024,
            table_analysis['password_tokens']['total_size_kb'] / 1024,
            table_analysis['app_info']['total_size_kb'] / 1024,
            table_analysis['user_stats']['total_size_kb'] / 1024
        ])
        
        # データベースメタデータの推定
        metadata_overhead_mb = total_estimated_mb * 0.3  # インデックスなどで30%のオーバーヘッド
        
        analysis = {
            'table_analysis': table_analysis,
            'data_total_mb': round(total_estimated_mb, 3),
            'metadata_overhead_mb': round(metadata_overhead_mb, 3),
            'estimated_db_total_mb': round(total_estimated_mb + metadata_overhead_mb, 3),
            'render_usage_mb': 84,  # Renderでの実際の使用量
            'difference_mb': round(84 - (total_estimated_mb + metadata_overhead_mb), 3)
        }
        
        return render_template('admin_comprehensive_analysis.html', analysis=analysis)
        
    except Exception as e:
        print(f"包括的ストレージ分析エラー: {e}")
        import traceback
        traceback.print_exc()
        flash(f'包括的ストレージ分析エラー: {str(e)}', 'danger')
        return redirect(url_for('admin_page'))
    
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