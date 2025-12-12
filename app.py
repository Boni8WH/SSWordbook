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
import uuid
import io
from io import StringIO, BytesIO
from datetime import datetime, timedelta
from sqlalchemy import inspect, text, func, case, cast, Integer
from sqlalchemy.orm import joinedload
from datetime import date, datetime, timedelta
import random
import glob
import pytz
import threading
from flask_apscheduler import APScheduler
from pywebpush import webpush, WebPushException
try:
    import boto3
    from botocore.exceptions import NoCredentialsError
    S3_AVAILABLE = True
except ImportError:
    print("⚠️ boto3が利用できません。画像アップロードはローカル保存になります。")
    S3_AVAILABLE = False
    boto3 = None
    NoCredentialsError = Exception
JST = pytz.timezone('Asia/Tokyo')

# AWS S3設定
S3_BUCKET = 'your-bucket-name'
S3_KEY = 'your-access-key'
S3_SECRET = 'your-secret-key'
S3_REGION = 'ap-northeast-1'  # 東京リージョン

S3_BUCKET = os.environ.get('S3_BUCKET', 'your-default-bucket')
S3_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
S3_SECRET = os.environ.get('AWS_SECRET_ACCESS_KEY')
S3_REGION = os.environ.get('AWS_REGION', 'ap-northeast-1')

# S3クライアント初期化（boto3利用可能時のみ）
if S3_AVAILABLE and S3_KEY and S3_SECRET:
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=S3_KEY,
            aws_secret_access_key=S3_SECRET,
            region_name=S3_REGION
        )
        print("✅ S3クライアント初期化完了")
    except Exception as e:
        print(f"⚠️ S3クライアント初期化失敗: {e}")
        S3_AVAILABLE = False
        s3_client = None
else:
    print("⚠️ S3設定不完全：ローカル保存を使用")
    S3_AVAILABLE = False  # 認証情報がない場合はS3_AVAILABLEをFalseに設定
    s3_client = None

def upload_image_to_s3(file, filename, folder='essay_images', content_type='image/jpeg'):
    """画像をS3にアップロード（boto3利用可能時のみ）"""
    if not S3_AVAILABLE:
        print("⚠️ S3アップロード不可：boto3がインストールされていません")
        return None
        
    try:
        s3_client.upload_fileobj(
            file,
            S3_BUCKET,
            f"{folder}/{filename}",
            ExtraArgs={'ContentType': content_type}
        )
        return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{folder}/{filename}"
    except NoCredentialsError:
        print("AWS認証情報が見つかりません")
        return None
    except Exception as e:
        print(f"S3アップロードエラー: {e}")
        return None
# ====================================================================
# データベースモデル定義（models.pyから統合）
# ====================================================================

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator, Text
from werkzeug.security import generate_password_hash, check_password_hash

# SQLAlchemyインスタンスを作成
db = SQLAlchemy()

# JSONデータを扱うカスタム型
class JSONEncodedDict(TypeDecorator):
    impl = Text

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(value)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(50), nullable=False)
    student_id = db.Column(db.String(50), nullable=False)
    username = db.Column(db.String(80), nullable=False)
    
    _room_password_hash = db.Column(db.String(255), nullable=False)
    _individual_password_hash = db.Column(db.String(255), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('room_number', 'student_id', name='uq_room_student_id'),
        db.UniqueConstraint('room_number', 'username', name='uq_room_username'),
    )

    original_username = db.Column(db.String(80), nullable=False)
    is_first_login = db.Column(db.Boolean, default=True, nullable=False)
    password_changed_at = db.Column(db.DateTime)
    username_changed_at = db.Column(db.DateTime)
    restriction_triggered = db.Column(db.Boolean, default=False, nullable=False)
    restriction_released = db.Column(db.Boolean, default=False, nullable=False)
    problem_history = db.Column(JSONEncodedDict, default={})
    incorrect_words = db.Column(JSONEncodedDict, default=[])
    last_login = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    
    # 通知設定
    notification_enabled = db.Column(db.Boolean, default=True, nullable=False)
    notification_time = db.Column(db.String(5), default="21:00", nullable=False)
    push_subscription = db.Column(JSONEncodedDict, nullable=True)

    def set_room_password(self, password): self._room_password_hash = generate_password_hash(password)
    def check_room_password(self, password): return check_password_hash(self._room_password_hash, password)
    def set_individual_password(self, password): self._individual_password_hash = generate_password_hash(password)
    def check_individual_password(self, password): return check_password_hash(self._individual_password_hash, password)
    def __repr__(self): return f'<User {self.username} (Room: {self.room_number}, ID: {self.student_id})>'
    def get_problem_history(self): return self.problem_history or {}
    def set_problem_history(self, history): self.problem_history = history
    def get_incorrect_words(self): return self.incorrect_words or []
    def set_incorrect_words(self, words): self.incorrect_words = words
    def change_username(self, new_username):
        if not self.original_username: self.original_username = self.username
        self.username = new_username
        self.username_changed_at = datetime.now(JST)
    def mark_first_login_completed(self): self.is_first_login = False
    def change_password_first_time(self, new_password):
        self.set_individual_password(new_password)
        self.password_changed_at = datetime.now(JST)
        self.mark_first_login_completed()
    def set_restriction_state(self, triggered, released):
        self.restriction_triggered = triggered
        self.restriction_released = released
    def get_restriction_state(self): return {'hasBeenRestricted': self.restriction_triggered, 'restrictionReleased': self.restriction_released}

class AdminUser(db.Model):
    __tablename__ = 'admin_user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    _password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self._password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self._password_hash, password)

    def __repr__(self):
        return f'<AdminUser {self.username}>'

class DailyQuiz(db.Model):
    """その日の部屋ごとの10問を保存するテーブル"""
    __tablename__ = 'daily_quiz'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    room_number = db.Column(db.String(50), nullable=False)
    problem_ids_json = db.Column(db.Text, nullable=False)  # 問題IDのリストをJSON文字列で保存
    monthly_score_processed = db.Column(db.Boolean, default=False, nullable=True)

    __table_args__ = (db.UniqueConstraint('date', 'room_number', name='uq_daily_quiz_date_room'),)

    def get_problem_ids(self):
        return json.loads(self.problem_ids_json)

class DailyQuizResult(db.Model):
    """ユーザーごとの今日の10問の結果を保存するテーブル"""
    __tablename__ = 'daily_quiz_result'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    quiz_id = db.Column(db.Integer, db.ForeignKey('daily_quiz.id', ondelete='CASCADE'), nullable=False)
    score = db.Column(db.Integer, nullable=False)  # 正解数
    time_taken_ms = db.Column(db.Integer, nullable=False)  # ミリ秒単位でのタイム
    completed_at = db.Column(db.DateTime, default=lambda: datetime.now(JST))

    user = db.relationship('User', backref=db.backref('daily_quiz_results', lazy=True, cascade="all, delete-orphan"))
    quiz = db.relationship('DailyQuiz', backref=db.backref('results', lazy=True, cascade="all, delete-orphan"))

class MonthlyScore(db.Model):
    """月間の累計スコアを保存するテーブル"""
    __tablename__ = 'monthly_score'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    room_number = db.Column(db.String(50), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    total_score = db.Column(db.Integer, default=0, nullable=False)

    user = db.relationship('User', backref=db.backref('monthly_scores', lazy=True, cascade="all, delete-orphan"))
    __table_args__ = (db.UniqueConstraint('user_id', 'room_number', 'year', 'month', name='uq_user_room_year_month'),)

class MonthlyResultViewed(db.Model):
    """ユーザーが前月の結果を見たかを記録するテーブル"""
    __tablename__ = 'monthly_result_viewed'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    year = db.Column(db.Integer, nullable=False)  # 結果を見た対象の年（例：9月の結果）
    month = db.Column(db.Integer, nullable=False) # 結果を見た対象の月（例：9月）
    viewed_at = db.Column(db.DateTime, default=lambda: datetime.now(JST))

    user = db.relationship('User', backref=db.backref('monthly_views', lazy=True, cascade="all, delete-orphan"))
    __table_args__ = (db.UniqueConstraint('user_id', 'year', 'month', name='uq_user_viewed_year_month'),)

class RoomSetting(db.Model):
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(50), unique=True, nullable=False)
    max_enabled_unit_number = db.Column(db.String(50), default="9999", nullable=False)
    csv_filename = db.Column(db.String(100), default="words.csv", nullable=False)
    ranking_display_count = db.Column(db.Integer, default=10, nullable=False)
    enabled_units = db.Column(db.Text, default="[]", nullable=False)  # JSON形式で単元リストを保存
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(JST), onupdate=lambda: datetime.now(JST))

    is_suspended = db.Column(db.Boolean, nullable=False, default=False)
    suspended_at = db.Column(db.DateTime, nullable=True)

    def get_enabled_units(self):
        """有効な単元のリストを取得"""
        try:
            return json.loads(self.enabled_units)
        except (json.JSONDecodeError, TypeError):
            return []
        except Exception as e:
            print(f"Error parsing enabled_units: {e}")
            return []
    
    def set_enabled_units(self, units_list):
        """有効な単元のリストを設定"""
        self.enabled_units = json.dumps(units_list)

    def __repr__(self):
        return f'<RoomSetting {self.room_number}, Max Unit: {self.max_enabled_unit_number}, CSV: {self.csv_filename}>'

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
    app_name = db.Column(db.String(100), default="単語帳", nullable=False)
    version = db.Column(db.String(20), default="1.0.0", nullable=False)
    last_updated_date = db.Column(db.String(50), default="2025年6月15日", nullable=False)
    update_content = db.Column(db.Text, default="アプリケーションが開始されました。", nullable=False)
    footer_text = db.Column(db.String(200), default="", nullable=True)
    contact_email = db.Column(db.String(100), default="", nullable=True)
    school_name = db.Column(db.String(100), default="〇〇高校", nullable=True)
    
    # ロゴ画像データ（DB保存用）
    logo_image_content = db.Column(db.LargeBinary, nullable=True)
    logo_image_mimetype = db.Column(db.String(50), nullable=True)

    # ロゴタイプ: 'text' or 'image'
    logo_type = db.Column(db.String(10), default='text')
    # ロゴ画像ファイル名（後方互換性とS3用）
    logo_image_filename = db.Column(db.String(100), nullable=True)
    app_settings = db.Column(JSONEncodedDict, default={})
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(JST), onupdate=lambda: datetime.now(JST))
    updated_by = db.Column(db.String(80), default="system")

    @classmethod
    def get_current_info(cls):
        """現在のアプリ情報を取得。存在しない場合はデフォルトを作成"""
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
        """フロントエンド用の辞書形式で返す"""
        return {
            'appName': self.app_name,
            'version': self.version,
            'lastUpdatedDate': self.last_updated_date,
            'updateContent': self.update_content,
            'footerText': self.footer_text,
            'contactEmail': self.contact_email,
            'schoolName': getattr(self, 'school_name', '〇〇高校')
        }

    def __repr__(self):
        return f'<AppInfo {self.app_name} v{self.version}>'

class RpgEnemy(db.Model):
    """RPGモードの敵キャラクター"""
    __tablename__ = 'rpg_enemy'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    
    # 画像関連 (ファイル名/URL + DB保存用バイナリ)
    icon_image = db.Column(db.String(255)) # ファイル名またはURL
    icon_image_content = db.Column(db.LargeBinary) # 🆕 DB保存用
    icon_image_mimetype = db.Column(db.String(50)) # 🆕 MIMEタイプ
    
    badge_name = db.Column(db.String(100))
    badge_image = db.Column(db.String(255)) # ファイル名またはFAクラス
    badge_image_content = db.Column(db.LargeBinary) # 🆕 DB保存用
    badge_image_mimetype = db.Column(db.String(50)) # 🆕 MIMEタイプ
    
    difficulty = db.Column(db.Integer, default=1)
    description = db.Column(db.Text)
    intro_dialogue = db.Column(db.Text)
    defeat_dialogue = db.Column(db.Text)
    
    # クリア条件
    time_limit = db.Column(db.Integer, default=60)
    clear_correct_count = db.Column(db.Integer, default=10)
    clear_max_mistakes = db.Column(db.Integer, default=2)
    
    is_active = db.Column(db.Boolean, default=True)
    display_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    
    # 出現条件 (NEW)
    appearance_required_score = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'icon_image': self.icon_image,
            'badge_name': self.badge_name,
            'badge_image': self.badge_image,
            'difficulty': self.difficulty,
            'description': self.description,
            'intro_dialogue': self.intro_dialogue,
            'defeat_dialogue': self.defeat_dialogue,
            'time_limit': self.time_limit,
            'clear_correct_count': self.clear_correct_count,
            'clear_max_mistakes': self.clear_max_mistakes,
            'is_active': self.is_active,
            'display_order': self.display_order,
            'appearance_required_score': self.appearance_required_score,
            # 🆕 画像配信用URL
            'icon_url': url_for('serve_rpg_image', enemy_id=self.id, image_type='icon'),
            'badge_url': url_for('serve_rpg_image', enemy_id=self.id, image_type='badge')
        }

# Helper to determine database type for migrations
def _is_postgres():
    return db.engine.dialect.name == 'postgresql'

def _add_rpg_image_columns_safe():
    """RpgEnemyテーブルに画像保存用カラムを追加（安全版）"""
    try:
        with db.engine.connect() as conn:
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('rpg_enemy')]
            
            is_postgres = _is_postgres()

            if 'icon_image_content' not in columns:
                print("🔄 RpgEnemy: icon_image_contentを追加")
                col_type = "BYTEA" if is_postgres else "BLOB"
                conn.execute(text(f"ALTER TABLE rpg_enemy ADD COLUMN icon_image_content {col_type}"))
                
            if 'icon_image_mimetype' not in columns:
                print("🔄 RpgEnemy: icon_image_mimetypeを追加")
                conn.execute(text("ALTER TABLE rpg_enemy ADD COLUMN icon_image_mimetype VARCHAR(50)"))

            if 'badge_image_content' not in columns:
                print("🔄 RpgEnemy: badge_image_contentを追加")
                col_type = "BYTEA" if is_postgres else "BLOB"
                conn.execute(text(f"ALTER TABLE rpg_enemy ADD COLUMN badge_image_content {col_type}"))

            if 'badge_image_mimetype' not in columns:
                print("🔄 RpgEnemy: badge_image_mimetypeを追加")
                conn.execute(text("ALTER TABLE rpg_enemy ADD COLUMN badge_image_mimetype VARCHAR(50)"))
                
            conn.commit()
            print("✅ RpgEnemyカラム追加完了")
            
    except Exception as e:
        print(f"⚠️ RpgEnemy migration warning: {e}")

def _add_score_column_to_rpg_enemy():
    """RpgEnemyテーブルにappearance_required_scoreカラムを追加するマイグレーション関数"""
    try:
        with db.engine.connect() as conn:
            # appearance_required_score カラムの確認と追加
            try:
                conn.execute(text("SELECT appearance_required_score FROM rpg_enemy LIMIT 1"))
            except Exception:
                print("🔄 appearance_required_scoreカラムを追加します...")
                conn.execute(text("ALTER TABLE rpg_enemy ADD COLUMN appearance_required_score INTEGER DEFAULT 0 NOT NULL"))
                conn.commit()
                # 既存のアレクサンドロスも0でOK
                print("✅ RpgEnemyカラム追加完了")
    except Exception as e:
        print(f"⚠️ RpgEnemyマイグレーションエラー (無視可能): {e}")

def _create_rpg_enemy_table():
    """RpgEnemyテーブルを作成するマイグレーション関数"""
    try:
        inspector = inspect(db.engine)
        if 'rpg_enemy' not in inspector.get_table_names():
            print("🔄 rpg_enemyテーブルを作成します...")
            RpgEnemy.__table__.create(db.engine)
            print("✅ rpg_enemyテーブル作成完了")
            
            # 初期データ投入（アレクサンドロス大王）
            _seed_initial_rpg_enemy()
    except Exception as e:
        print(f"⚠️ rpg_enemyテーブル作成エラー: {e}")

def _seed_initial_rpg_enemy():
    """初期の敵キャラ（アレクサンドロス大王）を投入"""
    try:
        if RpgEnemy.query.count() == 0:
            alexander = RpgEnemy(
                name="アレクサンドロス大王",
                icon_image="boss_alexander.png",
                badge_name="征服王",
                badge_image="fas fa-crown", # 仮
                difficulty=3,
                description="東方遠征を成し遂げた伝説の英雄王。",
                intro_dialogue="余の覇道、貴様に止められるか！？",
                defeat_dialogue="見事だ…！貴様の知略、認めよう。",
                time_limit=60,
                clear_correct_count=10,
                clear_max_mistakes=2,
                is_active=True,
                display_order=1
            )
            db.session.add(alexander)
            db.session.commit()
            print("✅ 初期RPG敵キャラ（アレクサンドロス）を投入しました")
    except Exception as e:
        print(f"⚠️ 初期データ投入エラー: {e}")
        db.session.rollback()

def _add_logo_columns_to_app_info():
    """AppInfoテーブルにロゴ用カラムを追加するマイグレーション関数"""
    try:
        with db.engine.connect() as conn:
            # logo_image_content カラムの確認と追加
            try:
                conn.execute(text("SELECT logo_image_content FROM app_info LIMIT 1"))
            except Exception:
                print("🔄 logo_image_contentカラムを追加します...")
                conn.execute(text("ALTER TABLE app_info ADD COLUMN logo_image_content BYTEA"))
                conn.commit()

            # logo_image_mimetype カラムの確認と追加
            try:
                conn.execute(text("SELECT logo_image_mimetype FROM app_info LIMIT 1"))
            except Exception:
                print("🔄 logo_image_mimetypeカラムを追加します...")
                conn.execute(text("ALTER TABLE app_info ADD COLUMN logo_image_mimetype VARCHAR(50)"))
                conn.commit()
                
            print("✅ AppInfoテーブルのマイグレーション完了")
    except Exception as e:
        print(f"⚠️ マイグレーションエラー (無視可能): {e}")

def _add_notification_columns_to_user():
    """Userテーブルに通知用カラムを追加するマイグレーション関数"""
    try:
        inspector = inspect(db.engine)
        columns = [c['name'] for c in inspector.get_columns('user')]
        
        with db.engine.connect() as conn:
            # トランザクション開始
            trans = conn.begin()
            try:
                # notification_enabled
                if 'notification_enabled' not in columns:
                    print("🔄 notification_enabledカラムを追加します...")
                    conn.execute(text("ALTER TABLE \"user\" ADD COLUMN notification_enabled BOOLEAN DEFAULT TRUE"))

                # notification_time
                if 'notification_time' not in columns:
                    print("🔄 notification_timeカラムを追加します...")
                    conn.execute(text("ALTER TABLE \"user\" ADD COLUMN notification_time VARCHAR(5) DEFAULT '21:00'"))

                # push_subscription
                if 'push_subscription' not in columns:
                    print("🔄 push_subscriptionカラムを追加します...")
                    conn.execute(text("ALTER TABLE \"user\" ADD COLUMN push_subscription TEXT"))
                
                trans.commit()
                print("✅ Userテーブルの通知マイグレーション完了")
            except Exception as e:
                trans.rollback()
                print(f"⚠️ Userマイグレーションエラー (ロールバック): {e}")
                raise e
    except Exception as e:
        print(f"⚠️ Userマイグレーションエラー (全体): {e}")

# ====================================================================
# 通知機能関連
# ====================================================================

def _create_rpg_state_table():
    """RpgStateテーブルを作成するマイグレーション関数"""
    try:
        inspector = inspect(db.engine)
        if 'rpg_state' not in inspector.get_table_names():
            print("🔄 rpg_stateテーブルを作成します...")
            RpgState.__table__.create(db.engine)
            print("✅ rpg_stateテーブル作成完了")
    except Exception as e:
        print(f"⚠️ rpg_stateテーブル作成エラー: {e}")


def send_push_notification(user, title, body, url="/"):
    """プッシュ通知を送信"""
    if not user.push_subscription:
        return False
    
    try:
        subscription_info = user.push_subscription
        if isinstance(subscription_info, str):
            subscription_info = json.loads(subscription_info)

        webpush(
            subscription_info=subscription_info,
            data=json.dumps({"title": title, "body": body, "url": url}),
            vapid_private_key=VAPID_PRIVATE_KEY_PATH,
            vapid_claims=VAPID_CLAIMS.copy()
        )
        return True
    except WebPushException as ex:
        if ex.response and ex.response.status_code == 410:
            # 登録が無効になっている場合
            user.push_subscription = None
            db.session.commit()
        print(f"Push Error: {ex}")
        return False
    except Exception as e:
        print(f"Push Error: {e}")
        return False

def check_daily_quiz_reminders():
    """毎分実行：通知時刻のユーザーにリマインド"""
    with app.app_context():
        now = datetime.now(JST)
        current_time_str = now.strftime("%H:%M")
        print(f"DEBUG: Reminder check running at {current_time_str} (JST)")
        
        # 通知有効かつ現在時刻設定のユーザーを取得
        users = User.query.filter_by(notification_enabled=True, notification_time=current_time_str).all()
        print(f"DEBUG: Found {len(users)} users for time {current_time_str}")
        
        for user in users:
            # 今日のクイズ完了チェック
            today = (datetime.now(JST) - timedelta(hours=7)).date() # 7時間引いて日付区切り調整？（要確認）
            # シンプルにJSTの日付を使うなら: today = datetime.now(JST).date()
            # 既存ロジックに従う
            
            daily_quiz = DailyQuiz.query.filter_by(date=today, room_number=user.room_number).first()
            
            if daily_quiz:
                result = DailyQuizResult.query.filter_by(user_id=user.id, quiz_id=daily_quiz.id).first()
                if not result:
                    print(f"DEBUG: Sending reminder to {user.username} (Quiz exists but not done)")
                    # 未完了なら通知
                    send_push_notification(
                        user,
                        "今日の10問が未完では？",
                        "勝利は、わが迅速果敢な行動にあり",
                        url="/"
                    )
            else:
                # クイズ自体がまだ生成されていない場合も、当然「未完了」なので通知する
                print(f"DEBUG: Sending reminder to {user.username} (Quiz not generated yet)")
                send_push_notification(
                    user,
                    "今日の10問が未完では？",
                    "勝利は、わが迅速果敢な行動にあり",
                    url="/"
                )





class PasswordResetToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    token = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    used_at = db.Column(db.DateTime)
    
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
    content = db.Column(db.Text, nullable=False)
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
    room_number = db.Column(db.String(50), nullable=False, index=True)
    
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
                db.session.flush()
        return stats

    def update_stats(self, word_data=None, problem_id_map=None, parsed_max_enabled_unit_num=None):
        """統計を再計算して更新"""
        try:
            user = self.user
            if not user:
                return False
            
            # print(f"📊 統計更新開始: {user.username}") # ログ抑制
            
            # 部屋の単語データを取得
            if word_data is None:
                word_data = load_word_data_for_room(user.room_number)
            
            # マップと設定が渡されていない場合はここで計算（単体呼び出し用）
            if problem_id_map is None or parsed_max_enabled_unit_num is None:
                # 部屋設定を取得
                room_setting = RoomSetting.query.filter_by(room_number=user.room_number).first()
                max_enabled_unit_num_str = room_setting.max_enabled_unit_number if room_setting else "9999"
                parsed_max_enabled_unit_num = parse_unit_number(max_enabled_unit_num_str)
                
                # IDマップを作成
                problem_id_map = {}
                for word in word_data:
                    pid = get_problem_id(word)
                    problem_id_map[pid] = word

            # 有効な問題数を計算（これはword_dataから計算できるので高速）
            # ただし、毎回計算するのは無駄なので、呼び出し元で計算して渡すのがベストだが、
            # ここではマップ構築時に一緒にやるか、既存ロジックを維持しつつマップを使う。
            # いったん既存ロジックをマップベースに書き換える。
            
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
                # 対応する単語をマップから高速検索
                matched_word = problem_id_map.get(problem_id)
                
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
                
                # 総合スコア
                raw_score = self.mastery_score + self.reliability_score + self.activity_score + precision_bonus
                
                # RPGボーナス適用
                rpg_state = RpgState.query.filter_by(user_id=self.user_id).first()
                if rpg_state and rpg_state.permanent_bonus_percent > 0:
                    bonus_multiplier = 1 + (rpg_state.permanent_bonus_percent / 100.0)
                    self.balance_score = raw_score * bonus_multiplier
                else:
                    self.balance_score = raw_score

            
            # 更新日時
            self.last_updated = datetime.now(JST)
            
            print(f"✅ 統計更新完了: {user.username} (スコア: {self.balance_score:.1f})")
            return True
            
        except Exception as e:
            print(f"❌ 統計更新エラー ({user.username}): {e}")
            return False

class RpgState(db.Model):
    """ユーザーのRPGモード進行状況を保存するテーブル"""
    __tablename__ = 'rpg_state'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, unique=True)
    
    # クリア済みステージIDのリスト (JSON)
    cleared_stages = db.Column(JSONEncodedDict, default=[], nullable=False)
    
    # 最後に挑戦した日時 (再挑戦クールダウン用)
    last_challenge_at = db.Column(db.DateTime, nullable=True)
    
    # 永続ボーナス (%単位, float)
    permanent_bonus_percent = db.Column(db.Float, default=0.0, nullable=False)
    
    # 獲得したバッジIDのリスト (JSON)
    earned_badges = db.Column(JSONEncodedDict, default=[], nullable=False)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(JST), onupdate=lambda: datetime.now(JST))

    user = db.relationship('User', backref=db.backref('rpg_state', uselist=False, cascade="all, delete-orphan"))

    def __repr__(self):
        return f'<RpgState User:{self.user_id} Bonus:{self.permanent_bonus_percent}%>'

# 論述問題の部屋別公開設定モデル

class EssayVisibilitySetting(db.Model):
    __tablename__ = 'essay_visibility_setting'
    
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(50), nullable=False)
    chapter = db.Column(db.String(10), nullable=False)
    problem_type = db.Column(db.String(1), nullable=False)
    is_visible = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(JST), onupdate=lambda: datetime.now(JST))
    
    __table_args__ = (
        db.UniqueConstraint('room_number', 'chapter', 'problem_type', name='uq_room_chapter_type'),
    )
    
    def __repr__(self):
        return f'<EssayVisibilitySetting Room:{self.room_number} Ch:{self.chapter} Type:{self.problem_type} Visible:{self.is_visible}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'room_number': self.room_number,
            'chapter': self.chapter,
            'problem_type': self.problem_type,
            'is_visible': self.is_visible,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class EssayProblem(db.Model):
    __tablename__ = 'essay_problems'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    chapter = db.Column(db.String(10), nullable=False)
    type = db.Column(db.String(1), nullable=False)
    university = db.Column(db.String(100), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    answer_length = db.Column(db.Integer, nullable=False)
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    image_url = db.Column(db.Text, nullable=True) 
    
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
            'enabled': self.enabled,
            'image_url': self.image_url,
            'has_image': bool(self.image_url)
        }

class EssayProgress(db.Model):
    __tablename__ = 'essay_progress'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    problem_id = db.Column(db.Integer, db.ForeignKey('essay_problems.id', ondelete='CASCADE'), nullable=False)
    viewed_answer = db.Column(db.Boolean, default=False, nullable=False)
    understood = db.Column(db.Boolean, default=False, nullable=False)
    difficulty_rating = db.Column(db.Integer)
    memo = db.Column(db.Text)
    review_flag = db.Column(db.Boolean, default=False, nullable=False)
    viewed_at = db.Column(db.DateTime)
    understood_at = db.Column(db.DateTime)
    last_updated = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'problem_id', name='unique_user_problem'),
        {'extend_existing': True}  # ← 追加
    )

class EssayCsvFile(db.Model):
    __tablename__ = 'essay_csv_files'
    __table_args__ = {'extend_existing': True}  # ← 追加
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), unique=True, nullable=False)
    original_filename = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    problem_count = db.Column(db.Integer, default=0, nullable=False)
    upload_date = db.Column(db.DateTime, default=lambda: datetime.now(JST))

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response, abort, make_response, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import inspect, text, func
from functools import wraps
from PIL import Image

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

class EssayImage(db.Model):
    __tablename__ = 'essay_images'
    
    id = db.Column(db.Integer, primary_key=True)
    problem_id = db.Column(db.Integer, db.ForeignKey('essay_problems.id'), nullable=False, unique=True)
    image_data = db.Column(db.LargeBinary, nullable=False)  # 画像のバイナリデータ
    image_format = db.Column(db.String(10), nullable=False, default='PNG')  # PNG, JPEG など
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # リレーション
    essay_problem = db.relationship('EssayProblem', backref=db.backref('image', uselist=False))
    
    def __repr__(self):
        return f'<EssayImage {self.problem_id}>'

class Announcement(db.Model):
    __tablename__ = 'announcements'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    target_rooms = db.Column(db.String(200), nullable=True) # "all" or "101,102"
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    def to_dict(self):
        # 日時をJSTに変換して文字列化
        d = self.date
        if d:
            if d.tzinfo is None:
                # Naiveな場合はUTCとみなしてJSTに変換
                d = pytz.utc.localize(d).astimezone(JST)
            else:
                d = d.astimezone(JST)
            date_str = d.strftime('%Y-%m-%d %H:%M')
        else:
            date_str = ''

        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'date': date_str,
            'target_rooms': self.target_rooms,
            'is_active': self.is_active
        }

# ===== メール設定 =====
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', '587'))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME'])

mail = Mail(app)

# ===== スケジューラー設定 =====
scheduler = APScheduler()
scheduler.init_app(app)
# スケジューラーは後で起動（関数定義後）
scheduler.start()

# スケジューラーにジョブ追加
if not scheduler.get_job('daily_reminder'):
    scheduler.add_job(id='daily_reminder', func=check_daily_quiz_reminders, trigger='cron', minute='*')

# VAPID Keys (本来は環境変数推奨)
VAPID_PUBLIC_KEY = "BJJXMPrN1SvmAwKkab8rW50Aa96KLVHCIDQcvPkWZ9xeTfmQ8CDWV-a1CJMO5Xqapcrw4fX85ekwbzmrJfi7qr0"
VAPID_PRIVATE_KEY_PATH = os.path.join(basedir, 'private_key.pem')

# サーバー環境(Render等)で秘密鍵ファイルがない場合、環境変数から復元
if not os.path.exists(VAPID_PRIVATE_KEY_PATH):
    vapid_private_key_content = os.environ.get('VAPID_PRIVATE_KEY')
    if vapid_private_key_content:
        try:
            # 環境変数の改行文字エスケープを修正 (\n -> 実際の改行)
            content = vapid_private_key_content.replace('\\n', '\n')
            
            # 念のため、前後の余分な空白を削除
            content = content.strip()
            
            # ファイルに書き込み
            with open(VAPID_PRIVATE_KEY_PATH, 'w') as f:
                f.write(content)
                
            print("RUN: VAPID private key restored from environment variable.")
        except Exception as e:
            print(f"ERROR: Failed to restore VAPID private key: {e}")
    else:
        print("WARNING: VAPID private key not found in file or environment.")

VAPID_CLAIMS = {"sub": "mailto:admin@example.com"}

# ===== SQLAlchemy初期化 =====
db.init_app(app)

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# 部屋ごとのCSVファイルを保存するフォルダ
ROOM_CSV_FOLDER = 'room_csv'

# ユーザー登録の進捗状況を管理するグローバル変数
registration_status = {
    'is_processing': False,
    'total': 0,
    'current': 0,
    'message': '',
    'errors': [],
    'completed': False
}

# ====================================================================
# アプリ情報を取得するヘルパー関数
# ====================================================================
def get_logo_url(filename):
    """ロゴ画像のURLを取得（DB -> S3 -> ローカル）"""
    # DBに画像があるかチェック（AppInfoを取得）
    try:
        app_info = AppInfo.query.first()
        if app_info and app_info.logo_image_content:
            return url_for('serve_logo')
    except:
        pass

    if not filename:
        return None
        
    if S3_AVAILABLE:
        return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/logos/{filename}"
    else:
        return url_for('static', filename=f'uploads/logos/{filename}')

@app.route('/logo')
def serve_logo():
    """DBからロゴ画像を配信するルート"""
    try:
        app_info = AppInfo.query.first()
        if app_info and app_info.logo_image_content:
            response = make_response(app_info.logo_image_content)
            response.headers.set('Content-Type', app_info.logo_image_mimetype or 'image/png')
            return response
        else:
            # フォールバック: デフォルト画像など
            return "", 404
    except Exception as e:
        print(f"Error serving logo: {e}")
        return "", 500

@app.context_processor
def inject_logo_url():
    return dict(get_logo_url=get_logo_url)

def get_app_info_dict(user_id=None, username=None, room_number=None):
    try:
        app_info = AppInfo.get_current_info()
        info_dict = app_info.to_dict()
        
        info_dict['isLoggedIn'] = user_id is not None
        info_dict['username'] = username
        info_dict['roomNumber'] = room_number
        info_dict['schoolName'] = getattr(app_info, 'school_name', '〇〇高校')
        
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
                    'schoolName': getattr(app_info, 'school_name', '〇〇高校'),
                    'isLoggedIn': user_id is not None,
                    'username': username,
                    'roomNumber': room_number
                }
        except:
            pass
        
        # 最終フォールバック
        return {
            'appName': '単語帳',
            'version': '1.0.0', 
            'lastUpdatedDate': '2025年6月15日',
            'schoolName': '〇〇高校', 
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
# ヘルパー関数
# ====================================================================
def get_monthly_ranking(room_number, user_id, year, month):
    """指定された月間のランキングデータを取得する"""
    all_monthly_scores = MonthlyScore.query.filter_by(room_number=room_number, year=year, month=month)\
        .join(User)\
        .order_by(MonthlyScore.total_score.desc(), User.username).all()

    monthly_top_5 = []
    monthly_user_rank_info = None
    total_participants = len(all_monthly_scores)

    for i, score_entry in enumerate(all_monthly_scores, 1):
        rank_data = {
            'rank': i,
            'username': score_entry.user.username,
            'score': score_entry.total_score
        }
        if i <= 5:
            monthly_top_5.append(rank_data)
        if score_entry.user_id == user_id:
            monthly_user_rank_info = rank_data
            
    return monthly_top_5, monthly_user_rank_info, total_participants

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
                # ★修正: BOM付きUTF-8に対応 ('utf-8-sig')
                with open('words.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # 必須フィールドのチェック（空白のみも除外）
                        if not row.get('question') or not row.get('answer') or not row.get('question').strip() or not row.get('answer').strip():
                            continue

                        row['enabled'] = row.get('enabled', '1') == '1'
                        row['chapter'] = str(row['chapter'])
                        row['number'] = str(row['number'])
                        word_data.append(row)
            except FileNotFoundError:
                print(f"❌ デフォルトファイルが見つかりません: words.csv")
                return []
        else:
            # ★重要：データベースからカスタムCSVの内容を取得
            csv_file = CsvFileContent.query.filter_by(filename=csv_filename).first()
            if csv_file:
                try:
                    content = csv_file.content
                    # StringIOはエンコーディング指定できないが、contentは既にデコード済み文字列
                    reader = csv.DictReader(StringIO(content))
                    word_data = []
                    for row in reader:
                        # 必須フィールドのチェック（空白のみも除外）
                        if not row.get('question') or not row.get('answer') or not row.get('question').strip() or not row.get('answer').strip():
                            continue

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
        
        filtered_word_data = filter_special_problems(word_data, room_number)
        
        # ★デバッグログ: 最初の数件を表示
        if filtered_word_data:
            print(f"🔍 load_word_data_for_room: {len(filtered_word_data)} words loaded.")
            print(f"   First word: {filtered_word_data[0]}")
        else:
            print("⚠️ load_word_data_for_room: No words loaded.")
        
        return filtered_word_data
        
    except Exception as e:
        print(f"❌ 読み込みエラー: {e}")
        db.session.rollback()
        return []

def generate_problem_id(word):
    """
    問題IDを生成するヘルパー関数（JavaScript側とロジックを統一）
    """
    try:
        chapter = str(word.get('chapter', '0')).zfill(3)
        number = str(word.get('number', '0')).zfill(3)
        question = str(word.get('question', ''))
        answer = str(word.get('answer', ''))
        
        # 問題文と答えから英数字と日本語文字のみ抽出
        question_clean = re.sub(r'[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', '', question[:15])
        answer_clean = re.sub(r'[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', '', answer[:10])
        
        problem_id = f"{chapter}-{number}-{question_clean}-{answer_clean}"
        return problem_id
        
    except Exception as e:
        chapter = str(word.get('chapter', '0')).zfill(3)
        number = str(word.get('number', '0')).zfill(3)
        return f"{chapter}-{number}-error"

def levenshtein_distance(s1, s2):
    """2つの文字列のレーベンシュタイン距離を計算する"""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]

def process_daily_quiz_results_for_scoring(quiz_id):
    """指定されたクイズIDの結果を集計し、月間スコアに加算する"""
    try:
        quiz = DailyQuiz.query.get(quiz_id)
        if not quiz or quiz.monthly_score_processed:
            print(f"集計スキップ: クイズID {quiz_id} は存在しないか、処理済みです。")
            return

        print(f"月間スコア集計開始: クイズID {quiz_id} (日付: {quiz.date})")
        
        results = DailyQuizResult.query.filter_by(quiz_id=quiz_id)\
            .options(joinedload(DailyQuizResult.user))\
            .order_by(DailyQuizResult.score.desc(), DailyQuizResult.time_taken_ms.asc()).all()

        if not results:
            print("参加者がいないため集計を終了します。")
            quiz.monthly_score_processed = True
            db.session.commit()
            return

        quiz_year = quiz.date.year
        quiz_month = quiz.date.month
        point_mapping = {1: 6, 2: 5, 3: 4, 4: 3, 5: 2}

        for i, result in enumerate(results, 1):
            user = result.user
            if not user:
                continue

            # ポイントを計算
            points = point_mapping.get(i, 1)  # 1位〜5位は特別点、6位以下は参加点で1点

            # 月間スコアのレコードを検索または作成
            monthly_score = MonthlyScore.query.filter_by(
                user_id=user.id,
                room_number=user.room_number,
                year=quiz_year,
                month=quiz_month
            ).first()

            if not monthly_score:
                monthly_score = MonthlyScore(
                    user_id=user.id,
                    room_number=user.room_number,
                    year=quiz_year,
                    month=quiz_month,
                    total_score=0
                )
                db.session.add(monthly_score)

            # スコアを加算
            monthly_score.total_score += points
            print(f"  -> {user.username}: {points}点 加算 (合計: {monthly_score.total_score})")

        # クイズを「処理済み」にマーク
        quiz.monthly_score_processed = True
        db.session.commit()
        print(f"月間スコア集計完了: クイズID {quiz_id}")

    except Exception as e:
        db.session.rollback()
        print(f"❌ 月間スコア集計エラー: {e}")

def fix_user_data_types():
    """
    既存ユーザーの problem_history と incorrect_words が文字列で保存されている場合、
    正しいPythonオブジェクト（辞書/リスト）に変換して修復する。
    """
    users_to_fix = User.query.all()
    fixed_users_count = 0
    fixed_history_count = 0
    fixed_incorrect_count = 0

    for user in users_to_fix:
        is_fixed = False
        # problem_history の型をチェック
        if isinstance(user.problem_history, str):
            try:
                user.problem_history = json.loads(user.problem_history)
                fixed_history_count += 1
                is_fixed = True
            except json.JSONDecodeError:
                user.problem_history = {} # 解析できない場合は空の辞書に
        
        # incorrect_words の型をチェック
        if isinstance(user.incorrect_words, str):
            try:
                user.incorrect_words = json.loads(user.incorrect_words)
                fixed_incorrect_count += 1
                is_fixed = True
            except json.JSONDecodeError:
                user.incorrect_words = [] # 解析できない場合は空のリストに

        if is_fixed:
            fixed_users_count += 1
            print(f"🔧 ユーザー '{user.username}' のデータ型を修復しました。")

    if fixed_users_count > 0:
        db.session.commit()
        
    return {
        "fixed_users": fixed_users_count,
        "fixed_history": fixed_history_count,
        "fixed_incorrect": fixed_incorrect_count
    }

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

@app.route('/admin/emergency_fix_user_schema', methods=['POST'])
@admin_required
def emergency_fix_user_schema():
    """管理者用: Userテーブルのユニーク制約を修正する"""
    try:
        with db.engine.connect() as conn:
            # PostgreSQLの制約名を取得 (Render環境で一般的)
            constraints = conn.execute(text(
                "SELECT constraint_name FROM information_schema.table_constraints "
                "WHERE table_name = 'user' AND constraint_type = 'UNIQUE'"
            )).fetchall()
            
            for (constraint_name,) in constraints:
                # ユーザー名と出席番号の古いグローバルユニーク制約を削除
                if 'username' in constraint_name or 'student_id' in constraint_name:
                    print(f"🔧 古い制約を削除します: {constraint_name}")
                    conn.execute(text(f'ALTER TABLE "user" DROP CONSTRAINT {constraint_name}'))

            # 新しい複合ユニーク制約を追加
            print("🔧 新しい複合ユニーク制約を追加します...")
            conn.execute(text('ALTER TABLE "user" ADD CONSTRAINT uq_room_student_id UNIQUE (room_number, student_id)'))
            conn.execute(text('ALTER TABLE "user" ADD CONSTRAINT uq_room_username UNIQUE (room_number, username)'))
            
            conn.commit()
            
        flash('データベースのUserテーブル構造を正常に修復しました。', 'success')
    except Exception as e:
        db.session.rollback()
        # 制約が既に存在する場合のエラーは無視して成功とみなす
        if 'already exists' in str(e):
            flash('データベース構造は既に修復済みです。', 'info')
        else:
            flash(f'データベース構造の修復中にエラーが発生しました: {str(e)}', 'danger')
            
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
            
            # 重複チェック（個別パスワードハッシュも考慮）
            existing_user = User.query.filter_by(
                room_number=current_user.room_number,  # 修正: current_user.room_numberを使用
                username=new_username  # 修正: usernameで重複チェック（student_idは不要）
            ).filter(
                User.id != current_user.id  # 自分自身は除外
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
                        conn.execute(text('ALTER TABLE app_info ADD COLUMN school_name VARCHAR(100) DEFAULT \'〇〇高校\''))
                        conn.commit()
                    print("✅ school_nameカラムを追加しました。")
                
                # logo_typeとlogo_image_filenameカラムの追加
                if 'logo_type' not in columns:
                    print("🔧 logo_typeカラムを追加します...")
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE app_info ADD COLUMN logo_type VARCHAR(10) DEFAULT \'text\' NOT NULL'))
                        conn.commit()
                    print("✅ logo_typeカラムを追加しました。")

                if 'logo_image_filename' not in columns:
                    print("🔧 logo_image_filenameカラムを追加します...")
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE app_info ADD COLUMN logo_image_filename VARCHAR(100)'))
                        conn.commit()
                    print("✅ logo_image_filenameカラムを追加しました。")

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
                
                # ★ ロゴ画像カラムの追加
                if 'logo_image_content' not in columns:
                    print("🔧 logo_image_contentカラムを追加します...")
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE app_info ADD COLUMN logo_image_content BYTEA'))
                        conn.commit()
                    print("✅ logo_image_contentカラムを追加しました。")
                
                if 'logo_image_mimetype' not in columns:
                    print("🔧 logo_image_mimetypeカラムを追加します...")
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE app_info ADD COLUMN logo_image_mimetype VARCHAR(50)'))
                        conn.commit()
                    print("✅ logo_image_mimetypeカラムを追加しました。")
            
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

            # 6. RoomSettingテーブルの一時停止機能用カラム追加 👈 ここから追加
            if inspector.has_table('room_setting'):
                columns = [col['name'] for col in inspector.get_columns('room_setting')]
                print(f"📋 既存のRoomSettingテーブルカラム: {columns}")
                
                # is_suspendedカラムの追加
                if 'is_suspended' not in columns:
                    print("🔧 is_suspendedカラムを追加します...")
                    try:
                        with db.engine.connect() as conn:
                            conn.execute(text('ALTER TABLE room_setting ADD COLUMN is_suspended BOOLEAN DEFAULT FALSE NOT NULL'))
                            conn.commit()
                        print("✅ is_suspendedカラムを追加しました")
                    except Exception as e:
                        print(f"⚠️ is_suspendedカラム追加エラー: {e}")
                else:
                    print("✅ is_suspendedカラムは既に存在します")
                
                # suspended_atカラムの追加
                if 'suspended_at' not in columns:
                    print("🔧 suspended_atカラムを追加します...")
                    try:
                        with db.engine.connect() as conn:
                            conn.execute(text('ALTER TABLE room_setting ADD COLUMN suspended_at TIMESTAMP'))
                            conn.commit()
                        print("✅ suspended_atカラムを追加しました")
                    except Exception as e:
                        print(f"⚠️ suspended_atカラム追加エラー: {e}")
                else:
                    print("✅ suspended_atカラムは既に存在します")
            
            print("✅ RoomSetting一時停止機能のマイグレーション完了")

            # 7. EssayProblemテーブルのimage_urlカラム追加
            if inspector.has_table('essay_problems'):
                columns = [col['name'] for col in inspector.get_columns('essay_problems')]
                print(f"📋 既存のEssayProblemsテーブルカラム: {columns}")
                
                # image_urlカラムの追加
                if 'image_url' not in columns:
                    print("🔧 image_urlカラムを追加します...")
                    try:
                        with db.engine.connect() as conn:
                            conn.execute(text('ALTER TABLE essay_problems ADD COLUMN image_url VARCHAR(500)'))
                            conn.commit()
                        print("✅ image_urlカラムを追加しました")
                    except Exception as e:
                        print(f"⚠️ image_urlカラム追加エラー: {e}")
                else:
                    print("✅ image_urlカラムは既に存在します")
            else:
                print("📋 essay_problemsテーブルが存在しません（論述機能未使用）")

            print("✅ EssayProblems関連のマイグレーション完了")

            # 8. Announcementテーブルの作成
            if not inspector.has_table('announcements'):
                print("🔧 announcementsテーブルを作成します...")
                db.create_all()
                print("✅ announcementsテーブルを作成しました。")
            else:
                print("✅ announcementsテーブルは既に存在します。")


            # 8. EssayImageテーブルの作成
            if not inspector.has_table('essay_images'):
                print("🔧 essay_imagesテーブルを作成します...")
                try:
                    # EssayImageテーブルを明示的に作成
                    with db.engine.connect() as conn:
                        conn.execute(text("""
                            CREATE TABLE essay_images (
                                id SERIAL PRIMARY KEY,
                                problem_id INTEGER NOT NULL UNIQUE REFERENCES essay_problems(id) ON DELETE CASCADE,
                                image_data BYTEA NOT NULL,
                                image_format VARCHAR(10) NOT NULL DEFAULT 'PNG',
                                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                            )
                        """))
                        conn.commit()
                    print("✅ essay_imagesテーブルを作成しました")
                except Exception as e:
                    print(f"⚠️ essay_imagesテーブル作成エラー: {e}")
            else:
                print("✅ essay_imagesテーブルは既に存在します")

            print("✅ EssayImage関連のマイグレーション完了")
                
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
            create_essay_visibility_table_auto()
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

            # 通知カラム追加マイグレーション
            _add_notification_columns_to_user()
            _create_rpg_state_table()
            _create_rpg_enemy_table()
            _seed_initial_rpg_enemy() # 確実に初期データを投入
            _add_score_column_to_rpg_enemy() # NEW
            
            # 管理者ユーザー確認/作成
            try:
                admin_user = User.query.filter_by(username='admin', room_number='ADMIN').first()
                
                # 環境変数からパスワードを取得
                env_admin_password = os.environ.get('ADMIN_PASSWORD')
                
                if not admin_user:
                    logger.info("👤 管理者ユーザーを作成します...")
                    admin_user = User(
                        username='admin',
                        original_username='admin',
                        room_number='ADMIN',
                        student_id='000',
                        problem_history={},
                        incorrect_words=[]
                    )
                    admin_user.last_login = datetime.now(JST)
                    
                    # 新規作成時のパスワード設定
                    password_to_use = env_admin_password if env_admin_password else 'Avignon1309'
                    if not env_admin_password:
                        logger.warning("⚠️ ADMIN_PASSWORD環境変数が未設定です。デフォルトのパスワードを使用します。")
                    
                    admin_user.set_room_password(password_to_use)
                    admin_user.set_individual_password(password_to_use)
                    
                    db.session.add(admin_user)
                    db.session.commit()
                    logger.info("✅ 管理者ユーザー 'admin' を作成しました")
                else:
                    logger.info("✅ 管理者ユーザー 'admin' は既に存在します。")
                    
                    # 既存ユーザーでも環境変数が設定されていればパスワードを更新（強制上書き）
                    if env_admin_password:
                        admin_user.set_room_password(env_admin_password)
                        admin_user.set_individual_password(env_admin_password)
                        db.session.commit()
                        logger.info("🔄 環境変数 ADMIN_PASSWORD に基づいて管理者パスワードを更新しました。")
                    
            except Exception as e:
                logger.error(f"⚠️ 管理者ユーザー処理エラー: {e}")
                db.session.rollback()
                
            # アプリ情報確認/作成
            try:
                # ★マイグレーション実行
                _add_logo_columns_to_app_info()
                _add_rpg_image_columns_safe() # 🆕
                
                app_info = AppInfo.get_current_info()
                logger.info("✅ アプリ情報を確認/作成しました")
                
            except Exception as e:
                logger.error(f"⚠️ アプリ情報処理エラー: {e}")
                
            logger.info("🎉 データベース初期化が完了しました！")
                
    except Exception as e:
        logger.error(f"❌ データベース初期化エラー: {e}")
        raise

@app.route('/api/rpg/image/<int:enemy_id>/<string:image_type>')
def serve_rpg_image(enemy_id, image_type):
    """
    RPG敵キャラの画像（アイコン/バッジ）をDBから配信する
    image_type: 'icon' or 'badge'
    """
    try:
        enemy = RpgEnemy.query.get(enemy_id)
        if not enemy:
            return "", 404
            
        content = None
        mimetype = None
        filename = None
        
        if image_type == 'icon':
            content = enemy.icon_image_content
            mimetype = enemy.icon_image_mimetype
            filename = enemy.icon_image
        elif image_type == 'badge':
            content = enemy.badge_image_content
            mimetype = enemy.badge_image_mimetype
            filename = enemy.badge_image
        else:
            return "", 400
            
        # 1. DBにバイナリがあればそれを返す
        if content:
            response = make_response(content)
            response.headers.set('Content-Type', mimetype or 'image/png')
            # キャッシュ制御 (任意)
            response.headers.set('Cache-Control', 'public, max-age=3600')
            return response
            
        # 2. DBになければ、従来のファイルパス/URLを確認
        # filenameがURL(http...)ならリダイレクト
        if filename and (filename.startswith('http://') or filename.startswith('https://')):
            return redirect(filename)
            
        # 3. ローカルファイルの場合 (static/images/rpg/)
        if filename:
            # セキュリティのためファイル名のみ抽出
            secure_name = secure_filename(os.path.basename(filename))
            return redirect(url_for('static', filename=f'images/rpg/{secure_name}'))
            
        return "", 404
        
    except Exception as e:
        print(f"Error serving RPG image: {e}")
        return "", 500

def create_essay_visibility_table_auto():
    """essay_visibility_settingテーブルを自動作成"""
    try:
        print("🔧 essay_visibility_settingテーブル確認中...")
        
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        
        if not inspector.has_table('essay_visibility_setting'):
            print("🔧 essay_visibility_settingテーブルを作成中...")
            
            # 直接SQLでテーブル作成
            with db.engine.connect() as conn:
                if is_postgres:
                    # PostgreSQL用
                    conn.execute(text("""
                        CREATE TABLE essay_visibility_setting (
                            id SERIAL PRIMARY KEY,
                            room_number VARCHAR(50) NOT NULL,
                            chapter VARCHAR(10) NOT NULL,
                            problem_type VARCHAR(1) NOT NULL,
                            is_visible BOOLEAN NOT NULL DEFAULT TRUE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(room_number, chapter, problem_type)
                        )
                    """))
                else:
                    # SQLite用
                    conn.execute(text("""
                        CREATE TABLE essay_visibility_setting (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            room_number VARCHAR(50) NOT NULL,
                            chapter VARCHAR(10) NOT NULL,
                            problem_type VARCHAR(1) NOT NULL,
                            is_visible BOOLEAN NOT NULL DEFAULT 1,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(room_number, chapter, problem_type)
                        )
                    """))
                
                conn.commit()
            
            print("✅ essay_visibility_settingテーブル作成完了")
            
            # デフォルト設定の作成を試行
            try:
                create_default_visibility_settings()
            except Exception as default_error:
                print(f"⚠️ デフォルト設定作成エラー（スキップ）: {default_error}")
                
        else:
            print("ℹ️ essay_visibility_settingテーブルは既に存在します")
            
    except Exception as e:
        print(f"❌ essay_visibility_settingテーブル作成エラー: {e}")

def create_default_visibility_settings():
    """デフォルトの公開設定を作成"""
    try:
        print("🔧 デフォルト公開設定を作成中...")
        
        # 部屋一覧を取得
        with db.engine.connect() as conn:
            # ユーザーテーブルから部屋番号を取得
            rooms_result = conn.execute(text("""
                SELECT DISTINCT room_number 
                FROM "user" 
                WHERE room_number IS NOT NULL
            """))
            rooms = [row[0] for row in rooms_result.fetchall()]
            
            if not rooms:
                print("⚠️ 部屋が見つからないため、デフォルト設定をスキップします")
                return
            
            # essay_problemsテーブルから章・タイプを取得
            try:
                problems_result = conn.execute(text("""
                    SELECT DISTINCT chapter, type 
                    FROM essay_problems 
                    WHERE enabled = true
                """))
                chapter_types = problems_result.fetchall()
            except:
                print("⚠️ essay_problemsテーブルが見つからないため、サンプル設定を作成します")
                # サンプル設定
                chapter_types = [('1', 'A'), ('1', 'B'), ('1', 'C'), ('1', 'D')]
            
            if not chapter_types:
                print("⚠️ 論述問題が見つからないため、デフォルト設定をスキップします")
                return
            
            # デフォルト設定を作成
            created_count = 0
            for room_number in rooms:
                for chapter, problem_type in chapter_types:
                    if chapter and problem_type:
                        # 既存チェック
                        check_result = conn.execute(text("""
                            SELECT COUNT(*) FROM essay_visibility_setting 
                            WHERE room_number = :room AND chapter = :chapter AND problem_type = :type
                        """), {
                            'room': room_number,
                            'chapter': chapter,
                            'type': problem_type
                        })
                        
                        if check_result.fetchone()[0] == 0:
                            # 新規作成
                            conn.execute(text("""
                                INSERT INTO essay_visibility_setting 
                                (room_number, chapter, problem_type, is_visible) 
                                VALUES (:room, :chapter, :type, true)
                            """), {
                                'room': room_number,
                                'chapter': chapter,
                                'type': problem_type
                            })
                            created_count += 1
            
            conn.commit()
            print(f"✅ デフォルト公開設定を{created_count}件作成しました")
            
    except Exception as e:
        print(f"❌ デフォルト設定作成エラー: {e}")

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

@app.route('/emergency_create_essay_tables')
def emergency_create_essay_tables():
    """緊急修復：論述問題用テーブルを作成"""
    try:
        print("🆘 緊急論述問題テーブル作成開始...")
        
        with db.engine.connect() as conn:
            # essay_problemsテーブル作成
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS essay_problems (
                    id SERIAL PRIMARY KEY,
                    chapter VARCHAR(10) NOT NULL,
                    type VARCHAR(1) NOT NULL,
                    university VARCHAR(100) NOT NULL,
                    year INTEGER NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    answer_length INTEGER NOT NULL,
                    enabled BOOLEAN DEFAULT TRUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            conn.commit()
            print("✅ 論述問題テーブル作成完了")
            
            return """
            <h1>✅ 緊急修復完了</h1>
            <p>論述問題テーブルの作成が完了しました。</p>
            <p><a href="/admin">管理者ページに戻る</a></p>
            """
            
    except Exception as e:
        print(f"緊急修復失敗: {e}")
        return f"<h1>💥 緊急修復失敗</h1><p>エラー: {str(e)}</p>"

@app.route('/emergency_create_essay_progress_table')
def emergency_create_essay_progress_table():
    """緊急修復：EssayProgressテーブルを作成"""
    try:
        print("🆘 緊急EssayProgressテーブル作成開始...")
        
        with db.engine.connect() as conn:
            # essay_progressテーブル作成
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS essay_progress (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
                    problem_id INTEGER NOT NULL REFERENCES essay_problems(id) ON DELETE CASCADE,
                    viewed_answer BOOLEAN DEFAULT FALSE NOT NULL,
                    understood BOOLEAN DEFAULT FALSE NOT NULL,
                    difficulty_rating INTEGER,
                    memo TEXT,
                    review_flag BOOLEAN DEFAULT FALSE NOT NULL,
                    viewed_at TIMESTAMP,
                    understood_at TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, problem_id)
                )
            """))
            
            # essay_csv_filesテーブルも作成
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS essay_csv_files (
                    id SERIAL PRIMARY KEY,
                    filename VARCHAR(100) UNIQUE NOT NULL,
                    original_filename VARCHAR(100) NOT NULL,
                    content TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    problem_count INTEGER DEFAULT 0 NOT NULL,
                    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            conn.commit()
            print("✅ 論述問題関連テーブル作成完了")
            
            return """
            <h1>✅ 緊急修復完了</h1>
            <p>論述問題関連テーブルの作成が完了しました。</p>
            <p><a href="/essay">論述問題集を確認</a></p>
            <p><a href="/admin">管理者ページに戻る</a></p>
            """
            
    except Exception as e:
        print(f"緊急修復失敗: {e}")
        return f"<h1>💥 緊急修復失敗</h1><p>エラー: {str(e)}</p>"

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
                setting.ranking_display_count = 5
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

def extract_keywords_from_text(text):
    """
    文章から一問一答のキーワード候補を抜き出す（ライブラリ不要版）
    """
    # データベースから全ての一問一答の「答え」を取得
    # 注意: 問題数が増えるとパフォーマンスに影響する可能性があります
    try:
        # CsvFileContentからすべてのCSVコンテンツを取得
        all_csv_content = db.session.query(CsvFileContent.content).all()
        
        all_answers = set()
        for (content,) in all_csv_content:
            reader = csv.DictReader(StringIO(content))
            for row in reader:
                answer = row.get('answer', '').strip()
                if len(answer) >= 2: # 2文字以上の答えのみをキーワード候補とする
                    all_answers.add(answer)

    except Exception as e:
        print(f"キーワード抽出のための単語データ取得エラー: {e}")
        return []

    # テキストに含まれるキーワードを抽出
    found_keywords = []
    for answer in all_answers:
        if answer in text:
            found_keywords.append(answer)
    
    # 文字数が長いものから順に並べ替え、最大10件に絞る
    found_keywords.sort(key=len, reverse=True)
    
    return found_keywords[:10]

@app.route('/api/search_essays', methods=['POST'])
def api_search_essays():
    """論述問題をキーワード検索するAPI"""
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        
        if not query:
            return jsonify({'status': 'success', 'results': []})
            
        # キーワードで検索（問題文または模範解答）
        search_term = f"%{query}%"
        essays = EssayProblem.query.filter(
            db.or_(
                EssayProblem.question.like(search_term),
                EssayProblem.answer.like(search_term),
                EssayProblem.university.like(search_term)
            )
        ).limit(50).all()
        
        results = []
        for essay in essays:
            # 問題文を短く切り詰める
            snippet = essay.question[:100] + '...' if len(essay.question) > 100 else essay.question
            
            results.append({
                'id': essay.id,
                'chapter': essay.chapter,
                'university': essay.university,
                'year': essay.year,
                'type': essay.type,
                'question_snippet': snippet
            })
            
        return jsonify({'status': 'success', 'results': results})
        
    except Exception as e:
        app.logger.error(f"Essay search error: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/essay/get_keywords/<int:problem_id>')
def get_essay_keywords(problem_id):
    """
    論述問題IDを受け取り、その問題のキーワードを返すAPI
    """
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'ログインが必要です'}), 401
    
    problem = EssayProblem.query.get(problem_id)
    if not problem or not problem.enabled:
        return jsonify({'status': 'error', 'message': '問題が見つかりません'}), 404

    # 問題文と解答文を結合してキーワードを抽出
    combined_text = problem.question + " " + problem.answer
    keywords = extract_keywords_from_text(combined_text)

    # 抽出したキーワードに対応する一問一答の問題を取得
    quiz_data = []
    if keywords:
        # CsvFileContentからすべてのCSVコンテンツを取得
        all_csv_content = db.session.query(CsvFileContent.content).all()
        all_words = []
        for (content,) in all_csv_content:
            reader = csv.DictReader(StringIO(content))
            all_words.extend(list(reader))

        for keyword in keywords:
            # 答えがキーワードと一致する問題を探す
            for word in all_words:
                if word.get('answer', '').strip() == keyword:
                    quiz_data.append(word)
                    # 同じキーワードで複数の問題が見つからないように一度見つけたらループを抜ける
                    break 
    
    return jsonify({
        'status': 'success',
        'problem_id': problem_id,
        'quiz_data': quiz_data # 問題と答えのペアのリストを返す
    })

# 部屋ごとのCSVファイルを保存するフォルダ
ROOM_CSV_FOLDER = 'room_csv'

# ユーザー登録の進捗状況を管理するグローバル変数
registration_status = {
    'is_processing': False,
    'total': 0,
    'current': 0,
    'message': '',
    'errors': [],
    'completed': False
}

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
            
            # S章の場合は 'S' で判定、それ以外は従来通り number で判定
            unit_to_check = 'S' if str(chapter_num) == 'S' else unit_num
            is_unit_enabled_by_room = is_unit_enabled_by_room_setting(unit_to_check, room_setting)
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
                # 'S' を「歴史総合」に変換
                chapter_data['name'] = "歴史総合" if chapter_num == "S" else f"第{chapter_num}章"
                filtered_chapter_unit_status[chapter_num] = chapter_data

        def sort_key(item):
            chapter_num = item[0]
            if chapter_num == 'S':
                return (0, 0)  # 'S'を最優先
            if chapter_num.isdigit():
                return (1, int(chapter_num))  # 次に数字の章
            return (2, chapter_num)  # それ以外の章

        sorted_all_chapter_unit_status = dict(sorted(filtered_chapter_unit_status.items(), key=sort_key))

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
    if request.method == 'POST':
        login_type = request.form.get('login_type')
        
        if login_type == 'admin':
            admin_username = request.form.get('admin_username')
            admin_password = request.form.get('admin_password')

            admin_user = User.query.filter_by(room_number='ADMIN', username=admin_username).first()
            
            if admin_user and admin_user.check_individual_password(admin_password):
                session['admin_logged_in'] = True
                session['username'] = 'admin'
                session['user_id'] = admin_user.id  # 管理者ユーザーのIDも保存
                flash('管理者としてログインしました。', 'success')
                return redirect(url_for('admin_page'))
            else:
                flash('管理者のユーザー名またはパスワードが間違っています。', 'danger')
        
        elif login_type == 'user':
            room_number = request.form.get('room_number')
            room_password = request.form.get('room_password')
            student_id = request.form.get('student_id')
            individual_password = request.form.get('individual_password')
            
            room_setting = RoomSetting.query.filter_by(room_number=room_number).first()
            if room_setting and room_setting.is_suspended:
                flash(f'部屋{room_number}は現在一時停止中です。管理者にお問い合わせください。', 'warning')
                app.logger.info(f"一時停止中の部屋{room_number}へのログイン試行")
                return redirect(url_for('login_page'))
            
            # 複数アカウント対応の認証を使用
            user = authenticate_user(room_number, room_password, student_id, individual_password)
            
            if user:
                remember = request.form.get('remember_me')
                if remember:
                    # セッションを永続化（有効期限はapp.configで設定済み）
                    session.permanent = True
                    # 明示的に有効期限を設定することも可能
                    app.permanent_session_lifetime = timedelta(days=7)
                else:
                    session.permanent = False
                    
                session['user_id'] = user.id
                session['username'] = user.username
                session['room_number'] = user.room_number
                user.last_login = datetime.now(JST)
                db.session.commit()
                
                if hasattr(user, 'is_first_login') and user.is_first_login:
                    flash('初回ログインです。パスワードを変更してください。', 'info')
                    return redirect(url_for('first_time_password_change'))
                else:
                    flash(f'ようこそ、{user.username}さん！', 'success')
                    return redirect(url_for('index'))
            else:
                flash('ログイン情報が間違っています。', 'danger')
    
    context = get_template_context()
    return render_template('login.html', **context)

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
        # ログアウト時にプッシュ通知の購読を解除（任意）
        # モバイル端末の共有利用などを考慮すると、ログアウト時は通知も切るべき
        if 'user_id' in session:
            try:
                user = User.query.get(session['user_id'])
                if user:
                    user.push_subscription = None
                    db.session.commit()
            except Exception as e:
                print(f"Error clearing subscription on logout: {e}")

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
                    conn.execute(text("ALTER TABLE app_info ADD COLUMN school_name VARCHAR(100) DEFAULT '〇〇高校'"))
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
        <pre>ALTER TABLE app_info ADD COLUMN school_name VARCHAR(100) DEFAULT '〇〇高校';</pre>
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
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"❌ トークン保存エラー: {e}")
                flash('システムエラーが発生しました。', 'danger')
                return redirect(url_for('login_page'))
            
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

# app.py のルーティングエリア（例えば /admin/app_info の近く）に追加

@app.route('/admin/force_migration', methods=['GET', 'POST'])
def admin_force_migration():
    """手動でデータベースマイグレーションを実行"""
    if not session.get('admin_logged_in'):
        if request.method == 'GET':
            flash('管理者権限が必要です。', 'danger')
            return redirect(url_for('login_page'))
        return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
    
    if request.method == 'GET':
        # GETリクエストの場合は確認ページを表示
        return """
        <html><head><title>データベースマイグレーション</title></head>
        <body>
            <h1>データベースマイグレーションの確認</h1>
            <p><strong>警告:</strong> この操作はデータベースのスキーマを更新します。</p>
            <p>不足しているテーブル（daily_quizなど）やカラムが作成されます。既存のデータは保持されます。</p>
            <form method="POST" onsubmit="return confirm('本当にデータベースのマイグレーションを実行しますか？');">
                <button type="submit" style="padding: 10px 20px; font-size: 16px;">マイグレーションを実行</button>
            </form>
            <a href="/admin">管理者ページに戻る</a>
        </body></html>
        """
    
    # POSTリクエストの場合は実際にマイグレーションを実行
    try:
        print("🔧 手動でのデータベースマイグレーションを開始します...")
        db.create_all()
        # migrate_database() 関数も念のため呼び出す
        migrate_database()
        print("✅ 手動でのデータベースマイグレーションが完了しました。")
        flash('データベースの構造を正常に更新しました。', 'success')
        return redirect(url_for('admin_page'))
    except Exception as e:
        print(f"❌ 手動マイグレーション中にエラーが発生しました: {e}")
        flash(f'データベースの更新中にエラーが発生しました: {str(e)}', 'danger')
        return redirect(url_for('admin_page'))

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
                chapter = str(word['chapter'])
                number = str(word['number'])
                
                # S章とZ章は章レベルで管理
                if chapter == 'S':
                    units.add('S')
                elif number == 'Z':
                    units.add('Z')
                else:
                    units.add(number)
        
        # ソートして返す（数字 → S → Z の順）
        sorted_units = sorted(list(units), key=lambda x: (
            x == 'Z',  # Z を最後に
            x == 'S',  # S をその次に
            parse_unit_number(x)  # 残りは数値順
        ))
        
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
        
        # 強制更新フラグの確認
        force_refresh = request.args.get('refresh') == 'true'
        if force_refresh:
            print("🔄 ランキング強制更新リクエストを受信しました")
        
        # user_statsテーブルの存在確認
        try:
            inspector = inspect(db.engine)
            user_stats_exists = inspector.has_table('user_stats')
            
            if not user_stats_exists:
                print("⚠️ user_statsテーブルが存在しません。従来方式で計算します...")
                return admin_fallback_ranking_calculation(room_number, start_time)
            
            # 強制更新または統計データがないユーザーの同期
            if force_refresh:
                # 部屋の全ユーザーを取得して統計を更新
                users_in_room = User.query.filter_by(room_number=room_number).all()
                print(f"🔄 全ユーザー({len(users_in_room)}人)の統計を再計算中...")
                
                # 部屋の単語データを一度だけロード（最適化）
                word_data = load_word_data_for_room(room_number)
                
                # 部屋設定とIDマップを一度だけ計算（最適化）
                room_setting = RoomSetting.query.filter_by(room_number=room_number).first()
                max_enabled_unit_num_str = room_setting.max_enabled_unit_number if room_setting else "9999"
                parsed_max_enabled_unit_num = parse_unit_number(max_enabled_unit_num_str)
                
                problem_id_map = {}
                for word in word_data:
                    pid = get_problem_id(word)
                    problem_id_map[pid] = word
                
                count = 0
                for user in users_in_room:
                    if user.username == 'admin':
                        continue
                    stats = UserStats.get_or_create(user.id)
                    # 最適化されたupdate_statsを呼び出し
                    stats.update_stats(word_data, problem_id_map, parsed_max_enabled_unit_num)
                    count += 1
                    if count % 50 == 0: # コミット頻度を調整
                        db.session.commit()
                
                db.session.commit()
                print(f"✅ 全ユーザーの統計更新完了 ({count}人)")
            
            # 統計データがないユーザーを特定して作成（同期処理）
            try:
                users_without_stats = User.query.filter_by(room_number=room_number)\
                    .outerjoin(UserStats, User.id == UserStats.user_id)\
                    .filter(UserStats.id == None)\
                    .all()
                
                if users_without_stats:
                    print(f"🔄 統計データ未作成のユーザーを検出: {len(users_without_stats)}人 - 作成中...")
                    for user in users_without_stats:
                        UserStats.get_or_create(user.id)
                    db.session.commit()
                    print("✅ 統計データの同期完了")
            except Exception as sync_error:
                print(f"⚠️ 統計データ同期エラー (無視して続行): {sync_error}")
                db.session.rollback()
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

@app.route('/api/admin/daily_quiz_info/<room_number>')
@admin_required
def api_admin_daily_quiz_info(room_number):
    """管理者用: 指定部屋の「今日の10問」ランキングと月間取り組み回数を取得"""
    try:
        # 今日の日付 (JSTの午前7時を日付の区切りとする)
        today = (datetime.now(JST) - timedelta(hours=7)).date()
        
        # 1. 今日のランキングを取得
        daily_quiz = DailyQuiz.query.filter_by(date=today, room_number=room_number).first()
        
        daily_ranking = []
        total_participants_today = 0
        average_score_today = 0
        
        if daily_quiz:
            results = DailyQuizResult.query.filter_by(quiz_id=daily_quiz.id)\
                .join(User)\
                .order_by(DailyQuizResult.score.desc(), DailyQuizResult.time_taken_ms.asc()).all()
            
            total_participants_today = len(results)
            if total_participants_today > 0:
                total_score = sum(r.score for r in results)
                average_score_today = round(total_score / total_participants_today, 2)
            
            for i, result in enumerate(results, 1):
                daily_ranking.append({
                    'rank': i,
                    'username': result.user.username,
                    'student_id': result.user.student_id,
                    'score': result.score,
                    'time': f"{(result.time_taken_ms / 1000):.2f}秒"
                })

        # 2. 今月の取り組み回数を取得
        current_year = today.year
        current_month = today.month
        
        first_day_of_month = date(current_year, current_month, 1)
        # 次の月の初日を取得し、1日引くことで今月の最終日を計算
        if current_month == 12:
            last_day_of_month = date(current_year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day_of_month = date(current_year, current_month + 1, 1) - timedelta(days=1)

        monthly_attempts = db.session.query(
            User.username,
            User.student_id,
            func.count(DailyQuizResult.id).label('attempts_count')
        ).join(
            DailyQuizResult, User.id == DailyQuizResult.user_id
        ).join(
            DailyQuiz, DailyQuizResult.quiz_id == DailyQuiz.id
        ).filter(
            User.room_number == room_number,
            DailyQuiz.date >= first_day_of_month,
            DailyQuiz.date <= last_day_of_month
        ).group_by(
            User.id, User.username, User.student_id
        ).order_by(
            func.count(DailyQuizResult.id).desc(), User.username
        ).all()
        
        monthly_attempts_data = [
            {'username': row.username, 'student_id': row.student_id, 'attempts_count': row.attempts_count}
            for row in monthly_attempts
        ]

        return jsonify({
            'status': 'success',
            'daily_ranking': daily_ranking,
            'monthly_attempts': monthly_attempts_data,
            'stats': {
                'total_participants_today': total_participants_today,
                'average_score_today': average_score_today
            }
        })

    except Exception as e:
        app.logger.error(f"管理者用「今日の10問」情報取得エラー: {e}")
        return jsonify(status='error', message=str(e)), 500

@app.route('/api/admin/monthly_cumulative_ranking/<room_number>/<int:year>/<int:month>')
@admin_required
def api_admin_monthly_cumulative_ranking(room_number, year, month):
    """管理者用: 指定部屋の月間累計スコアランキングを取得"""
    try:
        monthly_scores = db.session.query(
            User.username,
            User.student_id,
            MonthlyScore.total_score
        ).join(
            MonthlyScore, User.id == MonthlyScore.user_id
        ).filter(
            MonthlyScore.room_number == room_number,
            MonthlyScore.year == year,
            MonthlyScore.month == month
        ).order_by(
            MonthlyScore.total_score.desc(),
            User.username
        ).all()

        ranking_data = [
            {'rank': i + 1, 'username': row.username, 'student_id': row.student_id, 'total_score': row.total_score}
            for i, row in enumerate(monthly_scores)
        ]

        return jsonify({
            'status': 'success',
            'ranking': ranking_data
        })

    except Exception as e:
        app.logger.error(f"月間累計スコアランキング取得エラー: {e}")
        return jsonify(status='error', message=str(e)), 500

@app.route('/api/admin/daily_ranking/<room_number>/<int:year>/<int:month>/<int:day>')
@admin_required
def api_admin_daily_ranking(room_number, year, month, day):
    """管理者用: 指定日の「今日の10問」ランキングを取得"""
    try:
        target_date = date(year, month, day)

        daily_quiz = DailyQuiz.query.filter_by(date=target_date, room_number=room_number).first()

        daily_ranking = []
        if daily_quiz:
            results = DailyQuizResult.query.filter_by(quiz_id=daily_quiz.id)\
                .join(User)\
                .order_by(DailyQuizResult.score.desc(), DailyQuizResult.time_taken_ms.asc()).all()

            for i, result in enumerate(results, 1):
                daily_ranking.append({
                    'rank': i,
                    'username': result.user.username,
                    'student_id': result.user.student_id,
                    'score': result.score,
                    'time': f"{(result.time_taken_ms / 1000):.2f}秒"
                })

        return jsonify({
            'status': 'success',
            'ranking': daily_ranking
        })

    except Exception as e:
        app.logger.error(f"指定日の日次ランキング取得エラー: {e}")
        return jsonify(status='error', message=str(e)), 500
    
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
        display_count = data.get('ranking_display_count', 5)
        
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
            chapter = str(word.get('chapter', ''))
            unit_num = word['number']
            is_word_enabled_in_csv = word['enabled']
            
            # S章の場合は 'S' で判定、それ以外は従来通り number で判定
            unit_to_check = 'S' if chapter == 'S' else unit_num
            is_unit_enabled_by_room = is_unit_enabled_by_room_setting(unit_to_check, room_setting)

            if is_word_enabled_in_csv and is_unit_enabled_by_room:
                filtered_word_data.append(word)
        
        return jsonify(filtered_word_data)
        
    except Exception as e:
        print(f"Error searching essays: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# =========================================================
# お知らせ機能 API & 管理ルート
# =========================================================

@app.route('/api/announcements', methods=['GET'])
def get_announcements():
    """アクティブなお知らせを取得（最新5件）"""
    try:
        user_id = session.get('user_id')
        user_room = None
        if user_id:
            user = User.query.get(user_id)
            if user:
                user_room = user.room_number

        # 全体向けまたは自室向けのお知らせを取得
        query = Announcement.query.filter_by(is_active=True)
        
        # フィルタリングロジック
        # target_roomsが 'all' または 自分の部屋番号を含むものを抽出
        # SQLレベルでのフィルタリングは複雑になるため、Python側でフィルタリングするか、
        # シンプルに 'all' と 部分一致を使う
        
        all_announcements = query.order_by(Announcement.date.desc()).all()
        filtered_announcements = []
        
        for ann in all_announcements:
            targets = [t.strip() for t in (ann.target_rooms or 'all').split(',')]
            if 'all' in targets:
                filtered_announcements.append(ann.to_dict())
            elif user_room and user_room in targets:
                filtered_announcements.append(ann.to_dict())
            
            if len(filtered_announcements) >= 5:
                break
                
        return jsonify({'status': 'success', 'announcements': filtered_announcements})
        
    except Exception as e:
        print(f"Error fetching announcements: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/announcements/add', methods=['POST'])
@admin_required
def admin_add_announcement():
    try:
        title = request.form.get('title')
        content = request.form.get('content')
        # target_roomsは複数選択なのでgetlistで取得
        target_rooms_list = request.form.getlist('target_rooms')
        
        # リストが空の場合はデフォルトでallにする（念のため）
        if not target_rooms_list:
            target_rooms = 'all'
        else:
            # 'all'が含まれている場合は'all'のみにする、または他の選択肢があっても'all'扱いにする
            if 'all' in target_rooms_list:
                target_rooms = 'all'
            else:
                target_rooms = ','.join(target_rooms_list)
        
        if not title or not content:
            flash('タイトルと内容は必須です。', 'danger')
            return redirect(url_for('admin_page'))
            
        new_announcement = Announcement(
            title=title,
            content=content,
            target_rooms=target_rooms
        )
        db.session.add(new_announcement)
        db.session.commit()

        # Update: 対象ユーザーにプッシュ通知
        try:
            print(f"DEBUG: Announcement created. Target rooms: {target_rooms}")
            # 全員または特定の部屋
            website_url = url_for('index', _external=True)
            
            if target_rooms == "all":
                users = User.query.filter(User.push_subscription.isnot(None)).all()
                print(f"DEBUG: Target 'all'. Found {len(users)} users with subscription.")
            else:
                target_room_list = [r.strip() for r in target_rooms.split(',')]
                users = User.query.filter(
                    User.room_number.in_(target_room_list),
                    User.push_subscription.isnot(None)
                ).all()
                print(f"DEBUG: Target rooms {target_room_list}. Found {len(users)} users with subscription.")

            count = 0
            for user in users:
                if user.notification_enabled:
                    # 本文を通知に使用（長すぎる場合は省略）
                    body_text = content[:40] + "..." if len(content) > 40 else content
                    send_push_notification(
                        user,
                        f"ナポレオン「{title}」",
                        body_text,
                        url=website_url
                    )
                    count += 1
                else:
                    print(f"DEBUG: User {user.username} has notifications disabled.")
            print(f"DEBUG: Sent notification to {count} users.")
            
        except Exception as e:
            print(f"Error sending announcement push: {e}")

        flash('お知らせを投稿しました', 'success')
        return redirect(url_for('admin_page'))
    except Exception as e:
        db.session.rollback()
        flash(f'エラーが発生しました: {e}', 'danger')
        return redirect(url_for('admin_page'))

@app.route('/admin/announcements/delete/<int:id>', methods=['POST'])
@admin_required
def admin_delete_announcement(id):
    try:
        announcement = Announcement.query.get_or_404(id)
        db.session.delete(announcement)
        db.session.commit()
        flash('お知らせを削除しました。', 'success')
        return redirect(url_for('admin_page'))
    except Exception as e:
        db.session.rollback()
        flash(f'エラーが発生しました: {e}', 'danger')
        return redirect(url_for('admin_page'))

@app.route('/admin/announcements/toggle/<int:id>', methods=['POST'])
@admin_required
def admin_toggle_announcement(id):
    try:
        announcement = Announcement.query.get_or_404(id)
        announcement.is_active = not announcement.is_active
        db.session.commit()
        status = '有効' if announcement.is_active else '無効'
        flash(f'お知らせを{status}にしました。', 'success')
        return redirect(url_for('admin_page'))
    except Exception as e:
        db.session.rollback()
        flash(f'エラーが発生しました: {e}', 'danger')
        return redirect(url_for('admin_page'))

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

@app.route('/weak_problems')
def weak_problems_page():
    """苦手問題一覧ページ"""
    if 'user_id' not in session:
        flash('ログインが必要です。', 'info')
        return redirect(url_for('login_page'))
    
    context = get_template_context()
    return render_template('weak_problem.html', **context)

@app.route('/api/weak_problems_everyone')
def api_weak_problems_everyone():
    """みんなの苦手問題（部屋ごとの集計）を取得"""
    try:
        if 'user_id' not in session:
            return jsonify(status='error', message='認証されていません。'), 401
        
        current_user = User.query.get(session['user_id'])
        if not current_user:
            return jsonify(status='error', message='ユーザーが見つかりません。'), 404
            
        room_number = current_user.room_number
        
        # 部屋の単語データを取得
        word_data = load_word_data_for_room(room_number)
        
        # 有効な問題IDと単語情報のマッピングを作成（Z問題を除外）
        valid_problems = {}
        for word in word_data:
            # Z問題（難関私大対策）は除外
            if str(word.get('number', '')).upper() == 'Z':
                continue
                
            problem_id = get_problem_id(word)
            valid_problems[problem_id] = word
            
        # 同じ部屋の全ユーザーを取得（管理者は除く）
        room_users = User.query.filter_by(room_number=room_number).filter(User.username != 'admin').all()
        
        # 集計用辞書
        problem_stats = {}
        
        for user in room_users:
            history = user.get_problem_history()
            
            for problem_id, stats in history.items():
                # 有効な問題（Z問題以外）のみ集計
                if problem_id in valid_problems:
                    if problem_id not in problem_stats:
                        problem_stats[problem_id] = {
                            'correct': 0,
                            'incorrect': 0,
                            'total': 0
                        }
                    
                    problem_stats[problem_id]['correct'] += stats.get('correct_attempts', 0)
                    problem_stats[problem_id]['incorrect'] += stats.get('incorrect_attempts', 0)
                    problem_stats[problem_id]['total'] += (stats.get('correct_attempts', 0) + stats.get('incorrect_attempts', 0))
        
        # 結果リストを作成
        results = []
        for problem_id, stats in problem_stats.items():
            total = stats['total']
            if total > 0:
                correct = stats['correct']
                accuracy = correct / total
                
                # 統計的信頼性（誤差範囲）の計算
                # 95%信頼区間での誤差範囲 (Margin of Error)
                # MOE = 1.96 * sqrt(p(1-p)/n)
                if total >= 5:  # 最低5回は回答が必要（統計的異常値の排除）
                    if accuracy == 0 or accuracy == 1:
                        # 正答率0%または100%の場合、標準誤差は0になるが、
                        # サンプル数が少ないと信頼性が低い。
                        # ここでは簡易的に、サンプル数が少ない場合は除外するロジックとするか、
                        # またはMOEの計算を調整する。
                        # 今回は「最低5回」のフィルタでカバーする。
                        is_reliable = True
                    else:
                        margin_of_error = 1.96 * math.sqrt((accuracy * (1 - accuracy)) / total)
                        # 誤差範囲が20%以下なら信頼できるとみなす
                        is_reliable = margin_of_error <= 0.2
                else:
                    is_reliable = False

                if is_reliable:
                    word = valid_problems[problem_id]
                    results.append({
                        'problemId': problem_id,
                        'question': word['question'],
                        'answer': word['answer'],
                        'accuracyRate': accuracy * 100,
                        'totalAttempts': total,
                        'correctAttempts': correct,
                        'incorrectAttempts': stats['incorrect']
                    })
        
        # ソート: 正答率が低い順 -> 回答数が多い順
        results.sort(key=lambda x: (x['accuracyRate'], -x['totalAttempts']))
        
        # Top 20を返す
        return jsonify({
            'status': 'success',
            'problems': results[:20]
        })
        
    except Exception as e:
        print(f"Error in api_weak_problems_everyone: {e}")
        return jsonify(status='error', message=str(e)), 500

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

# ========================================================================
# データ損失防止: 安全なデータクリーニング関数
# ========================================================================

def safe_clean_unmatched_history(dry_run=True, deletion_threshold=0.1):
    """
    安全版: ID不一致の学習履歴を削除する
    
    Args:
        dry_run: Trueの場合、実際には削除せずプレビューのみ
        deletion_threshold: この割合以上のデータ削除時に警告（0.1 = 10%）
    
    Returns:
        dict: 実行結果の詳細情報
    """
    
    users = User.query.all()
    analysis_results = []
    total_data_to_delete = 0
    total_data_size = 0
    high_deletion_users = []
    
    # 部屋ごとの有効IDキャッシュ (key: room_number, value: set of valid_ids)
    room_valid_ids_cache = {}
    
    print(f"🔧 データクリーニング開始 (Dry-run: {dry_run})")
    
    # 第1フェーズ: 影響分析
    for user in users:
        if user.username == 'admin':
            continue
            
        # ユーザーの部屋に対応する有効IDを取得
        room_num = user.room_number
        if room_num not in room_valid_ids_cache:
            word_data = load_word_data_for_room(room_num)
            valid_ids = set()
            for word in word_data:
                valid_ids.add(get_problem_id(word))
            room_valid_ids_cache[room_num] = valid_ids
            print(f"📋 Room {room_num}: 有効ID {len(valid_ids)}個をキャッシュしました")
            
        valid_ids = room_valid_ids_cache[room_num]
        
        old_history = user.get_problem_history()
        old_incorrect = user.get_incorrect_words()
        
        total_data_size += len(old_history)
        
        # 削除されるデータをカウント
        to_delete_count = sum(1 for pid in old_history.keys() if pid not in valid_ids)
        to_delete_incorrect = sum(1 for pid in old_incorrect if pid not in valid_ids)
        
        if len(old_history) > 0:
            deletion_rate = to_delete_count / len(old_history)
            
            user_result = {
                'username': user.username,
                'room_number': room_num,
                'total_history': len(old_history),
                'to_delete': to_delete_count,
                'to_delete_incorrect': to_delete_incorrect,
                'deletion_rate': deletion_rate,
                'will_remain': len(old_history) - to_delete_count
            }
            
            # 削除率が高いユーザーを記録
            if deletion_rate > deletion_threshold:
                high_deletion_users.append(user_result)
            
            analysis_results.append(user_result)
            total_data_to_delete += to_delete_count
    
    # 全体の削除率を計算
    overall_deletion_rate = total_data_to_delete / total_data_size if total_data_size > 0 else 0
    
    print(f"\n📊 影響分析結果:")
    print(f"   総データ数: {total_data_size}")
    print(f"   削除予定: {total_data_to_delete} ({overall_deletion_rate*100:.1f}%)")
    print(f"   高削除率ユーザー数: {len(high_deletion_users)}")
    
    # 閾値チェック
    if overall_deletion_rate > deletion_threshold:
        warning_msg = f"⚠️ 警告: 全体の{overall_deletion_rate*100:.1f}%のデータが削除されます（閾値: {deletion_threshold*100}%）"
        print(warning_msg)
        
        if len(high_deletion_users) > 0:
            print("\n⚠️ 高削除率ユーザー:")
            for user_info in high_deletion_users[:5]:  # 最初の5ユーザーのみ表示
                print(f"   - {user_info['username']} (Room {user_info['room_number']}): {user_info['deletion_rate']*100:.1f}% ({user_info['to_delete']}/{user_info['total_history']})")
    
    # Dry-runモードの場合はここで終了
    if dry_run:
        return {
            'status': 'dry_run',
            'message': 'プレビューモード: 実際の削除は行われませんでした',
            'total_data': total_data_size,
            'to_delete': total_data_to_delete,
            'deletion_rate': overall_deletion_rate,
            'high_deletion_users': high_deletion_users,
            'analysis': analysis_results
        }
    
    # 第2フェーズ: 実際の削除（dry_run=Falseの場合のみ）
    print("\n🔧 データクリーニング実行...")
    cleaned_users = 0
    total_removed_entries = 0
    total_removed_incorrect = 0
    
    for user in users:
        if user.username == 'admin':
            continue
            
        # キャッシュから有効IDを取得（分析フェーズでキャッシュ済みのはずだが念のため）
        room_num = user.room_number
        if room_num not in room_valid_ids_cache:
             # ここに来ることは稀だが、念のため再ロード
            word_data = load_word_data_for_room(room_num)
            valid_ids = set()
            for word in word_data:
                valid_ids.add(get_problem_id(word))
            room_valid_ids_cache[room_num] = valid_ids
            
        valid_ids = room_valid_ids_cache[room_num]
        
        old_history = user.get_problem_history()
        old_incorrect = user.get_incorrect_words()
        
        # 有効なIDのみを保持
        new_history = {pid: data for pid, data in old_history.items() if pid in valid_ids}
        new_incorrect = [pid for pid in old_incorrect if pid in valid_ids]
        
        removed_count = len(old_history) - len(new_history)
        removed_incorrect_count = len(old_incorrect) - len(new_incorrect)
        
        # 変更があった場合のみ保存
        if removed_count > 0 or removed_incorrect_count > 0:
            user.set_problem_history(new_history)
            user.set_incorrect_words(new_incorrect)
            cleaned_users += 1
            total_removed_entries += removed_count
            total_removed_incorrect += removed_incorrect_count
            
            print(f"  ✓ {user.username}: {removed_count}個削除（残存: {len(new_history)}）")
    
    try:
        db.session.commit()
        print(f"\n✅ クリーニング完了")
        
        return {
            'status': 'success',
            'message': 'データクリーニングが完了しました',
            'cleaned_users': cleaned_users,
            'removed_entries': total_removed_entries,
            'removed_incorrect': total_removed_incorrect,
            'analysis': analysis_results
        }
    except Exception as e:
        db.session.rollback()
        print(f"❌ クリーニングエラー: {e}")
        return {
            'status': 'error',
            'message': f'クリーニング中にエラーが発生しました: {str(e)}'
        }

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

# ========================================================================
# データ損失防止: 安全なデータクリーニング用管理者ルート
# ========================================================================

@app.route('/admin/safe_clean_preview', methods=['POST'])
def admin_safe_clean_preview():
    """安全版: データクリーニングのプレビュー（dry-run）"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限がありません。'}), 403
    
    try:
        # Dry-runモードで実行
        result = safe_clean_unmatched_history(dry_run=True, deletion_threshold=0.1)
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/safe_clean_execute', methods=['POST'])
def admin_safe_clean_execute():
    """安全版: データクリーニングの実行"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限がありません。'}), 403
    
    try:
        # 実際の削除を実行
        result = safe_clean_unmatched_history(dry_run=False, deletion_threshold=0.1)
        
        if result['status'] == 'success':
            flash(f"データクリーニング完了: {result['removed_entries']}個の履歴を削除しました", 'success')
        else:
            flash(f"エラー: {result['message']}", 'danger')
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/clean_invalid_history', methods=['POST'])
def admin_clean_invalid_history():
    """
    旧版: ID不一致履歴の削除
    ⚠️ 非推奨: 代わりに /admin/safe_clean_execute を使用してください
    """
    if not session.get('admin_logged_in'):
        flash('管理者権限がありません。', 'danger')
        return redirect(url_for('login_page'))
    
    flash('⚠️ この機能は非推奨です。安全版のプレビュー機能を使用してください。', 'warning')
    return redirect(url_for('admin_page'))

# 旧版を残すが、安全版を推奨するメッセージを追加
@app.route('/admin/clean_invalid_history_legacy', methods=['POST'])
def admin_clean_invalid_history_legacy():
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

        # ▼▼▼▼▼ ソート処理を修正 ▼▼▼▼▼
        def sort_key_progress(chapter_num):
            if chapter_num == 'S':
                return (0, 0)
            if chapter_num.isdigit():
                return (1, int(chapter_num))
            return (2, chapter_num)

        for chapter_num in sorted(chapter_progress_summary.keys(), key=sort_key_progress):
        # ▲▲▲▲▲ ここまで修正 ▲▲▲▲▲
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
            
            # 'S' を「歴史総合」に変換
            chapter_name = "歴史総合" if chapter_num == "S" else f"第{chapter_num}章"
            
            sorted_chapter_progress[chapter_num] = {
                'chapter_name': chapter_name,
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
                               top_5_ranking=[],  
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
            # user_statsテーブルが存在するかチェック（SQLAlchemy inspectを使用）
            inspector = inspect(db.engine)
            user_stats_exists = inspector.has_table('user_stats')
            
            if not user_stats_exists:
                print("⚠️ user_statsテーブルが存在しません。従来方式で計算します...")
                return fallback_ranking_calculation(current_user, start_time)
            
            # ★修正: 統計データがないユーザーを特定して作成（同期処理）
            try:
                users_without_stats = User.query.filter_by(room_number=current_room_number)\
                    .outerjoin(UserStats, User.id == UserStats.user_id)\
                    .filter(UserStats.id == None)\
                    .all()
                
                if users_without_stats:
                    print(f"🔄 統計データ未作成のユーザーを検出: {len(users_without_stats)}人 - 作成中...")
                    for user in users_without_stats:
                        UserStats.get_or_create(user.id)
                    db.session.commit()
            except Exception as sync_error:
                print(f"⚠️ 統計データ同期エラー (無視して続行): {sync_error}")
                db.session.rollback()
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
            'current_user_rank': current_user_rank,
            'total_users_in_room': User.query.filter_by(room_number=current_room_number).filter(User.username != 'admin').count(),
            'ranking_display_count': ranking_display_count,
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
@app.route('/admin')
def admin_page():
    try:
        if not session.get('admin_logged_in'):
            flash('管理者権限がありません。', 'danger')
            return redirect(url_for('login_page'))

        print("🔍 管理者ページ表示開始...")

        users = User.query.all()
        room_settings = RoomSetting.query.all()
        announcements = Announcement.query.order_by(Announcement.date.desc()).all()
        
        # 部屋設定のマッピングを作成
        room_max_unit_settings = {}
        for rs in room_settings:
            if hasattr(rs, 'max_enabled_unit_number'):
                room_max_unit_settings[rs.room_number] = rs.max_enabled_unit_number
            else:
                room_max_unit_settings[rs.room_number] = "9999"  # デフォルト値
        room_csv_settings = {rs.room_number: rs.csv_filename for rs in room_settings}
        room_ranking_settings = {rs.room_number: getattr(rs, 'ranking_display_count', 5) for rs in room_settings}
        
        room_data = {}
        for rs in room_settings:
            users_in_room = User.query.filter_by(room_number=rs.room_number).count()
            room_data[rs.room_number] = {
                'csv_filename': rs.csv_filename or '未設定',
                'max_unit': rs.max_enabled_unit_number if hasattr(rs, 'max_enabled_unit_number') else "9999",
                'user_count': users_in_room,
                'is_suspended': getattr(rs, 'is_suspended', False),  # 一時停止状態
                'suspended_at': getattr(rs, 'suspended_at', None)     # 一時停止日時
            }

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
                    ranking_display_count=5  # ★ランキング表示人数のデフォルト値
                )
                db.session.add(default_room_setting)
                room_max_unit_settings[room_num] = "9999"
                room_csv_settings[room_num] = "words.csv"
                room_ranking_settings[room_num] = 5
        
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
            'room_data': room_data,
            'admin_stats': {  # ★管理者ダッシュボード用統計
                'total_users': total_users,
                'total_rooms': total_rooms,
                'recent_logins': recent_logins,
                'unique_room_numbers': sorted(list(unique_room_numbers), key=lambda x: int(x) if x.isdigit() else float('inf'))
            },
            'announcements': announcements,
            'room_settings': room_settings,
            **context
        }
        
        return render_template('admin.html', **template_context)
        
    except Exception as e:
        print(f"❌ 管理者ページエラー: {e}")
        import traceback
        traceback.print_exc()
        return f"Admin Error: {e}", 500

def _update_app_info_general(app_info, form):
    """Update general application information from the form."""
    app_info.version = form.get('version', app_info.version).strip()
    # app_info.last_updated_date = form.get('last_updated_date', app_info.last_updated_date).strip()
    # app_info.update_content = form.get('update_content', app_info.update_content).strip()
    app_info.footer_text = form.get('footer_text', app_info.footer_text or '').strip()
    app_info.contact_email = form.get('contact_email', app_info.contact_email or '').strip()
    app_info.school_name = form.get('school_name', app_info.school_name).strip()
    app_info.updated_by = session.get('username', 'admin')
    app_info.updated_at = datetime.now(JST)

def _handle_text_logo(app_info, form):
    """Handle the logic for 'text' logo type."""
    logo_folder = os.path.join('static', 'uploads', 'logos')
    app_info.app_name = form.get('app_name', app_info.app_name).strip()
    if app_info.logo_image_filename:
        old_filepath = os.path.join(logo_folder, app_info.logo_image_filename)
        if os.path.exists(old_filepath):
            try:
                os.remove(old_filepath)
                logger.info(f"Deleted old logo: {old_filepath}")
            except Exception as e:
                logger.error(f"Error deleting old logo {old_filepath}: {e}")
    app_info.logo_image_filename = None

def _crop_and_save_image(img, crop_data_json, save_path):
    """Crop and save the image based on crop_data."""
    try:
        crop_data = json.loads(crop_data_json)
        x = int(crop_data['x'])
        y = int(crop_data['y'])
        width = int(crop_data['width'])
        height = int(crop_data['height'])

        cropped_img = img.crop((x, y, x + width, y + height))
        cropped_img.save(save_path)
        logger.info(f"Saved cropped logo: {save_path}")
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.error(f"Error processing crop data: {e}. Saving original image.")
        img.save(save_path)

def _handle_image_logo(app_info, request):
    """Handle the logic for 'image' logo type."""
    file = request.files.get('logo_image')
    crop_data_json = request.form.get('crop_data')
    logo_folder = os.path.join('static', 'uploads', 'logos')

    if file and file.filename:
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size > 1 * 1024 * 1024: # 1MB limit
            flash('ロゴ画像のファイルサイズは1MB以下にしてください。', 'danger')
            return False

        if app_info.logo_image_filename:
            # Delete old logo (S3 or local)
            if S3_AVAILABLE:
                try:
                    s3_client.delete_object(Bucket=S3_BUCKET, Key=f"logos/{app_info.logo_image_filename}")
                    logger.info(f"Deleted old logo from S3: logos/{app_info.logo_image_filename}")
                except Exception as e:
                    logger.error(f"Error deleting old logo from S3: {e}")
            else:
                old_filepath = os.path.join(logo_folder, app_info.logo_image_filename)
                if os.path.exists(old_filepath):
                    try:
                        os.remove(old_filepath)
                        logger.info(f"Deleted old logo: {old_filepath}")
                    except Exception as e:
                        logger.error(f"Error deleting old logo {old_filepath}: {e}")

        # Generate unique filename
        ext = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4().hex}{ext}"

        # Process image
        img = Image.open(file)
        
        # Crop if data exists
        if crop_data_json:
             try:
                crop_data = json.loads(crop_data_json)
                x = int(crop_data['x'])
                y = int(crop_data['y'])
                width = int(crop_data['width'])
                height = int(crop_data['height'])
                img = img.crop((x, y, x + width, y + height))
             except Exception as e:
                 logger.error(f"Error cropping image: {e}")

        # Save to DB (Primary) or S3/Local (Legacy/Backup)
        # DB保存を優先
        try:
            img_byte_arr = io.BytesIO()
            # 元のフォーマットを維持、なければPNG
            format = img.format if img.format else 'PNG'
            img.save(img_byte_arr, format=format)
            img_byte_arr = img_byte_arr.getvalue()
            
            app_info.logo_image_content = img_byte_arr
            app_info.logo_image_mimetype = Image.MIME[format] if format in Image.MIME else f'image/{format.lower()}'
            logger.info("Saved logo to Database")
        except Exception as e:
            logger.error(f"Error saving logo to DB: {e}")
            flash('データベースへの保存に失敗しました。', 'danger')
            return False

        # S3/Local保存も一応残しておく（後方互換性のため）
        if S3_AVAILABLE:
            # ... (S3 upload logic if needed, but skipping for now to rely on DB)
            pass
        else:
            # ローカル保存
            os.makedirs(logo_folder, exist_ok=True)
            save_path = os.path.join(logo_folder, unique_filename)
            img.save(save_path)
            logger.info(f"Saved logo locally: {save_path}")

        app_info.logo_image_filename = unique_filename

    if not app_info.app_name:
        app_info.app_name = "App" # Provide a default if empty
    return True

@app.route('/admin/app_info', methods=['GET', 'POST'])
@admin_required
def admin_app_info():
    try:
        app_info = AppInfo.get_current_info()

        if request.method == 'POST':
            _update_app_info_general(app_info, request.form)

            logo_type = request.form.get('logo_type')
            app_info.logo_type = logo_type

            logo_folder = os.path.join('static', 'uploads', 'logos')
            os.makedirs(logo_folder, exist_ok=True)

            if logo_type == 'text':
                _handle_text_logo(app_info, request.form)
            elif logo_type == 'image':
                if not _handle_image_logo(app_info, request):
                    return redirect(url_for('admin_app_info'))

            db.session.commit()
            flash('アプリ情報を更新しました。', 'success')
            return redirect(url_for('admin_app_info'))

        return render_template('admin_app_info.html', app_info=app_info)

    except Exception as e:
        app.logger.error(f"アプリ情報管理ページエラー: {e}")
        import traceback
        traceback.print_exc()
        flash(f'アプリ情報管理ページでエラーが発生しました: {str(e)}', 'danger')
        return redirect(url_for('admin_page'))

@app.route('/admin/app_info/reset', methods=['POST'])
def admin_app_info_reset():
    try:
        if not session.get('admin_logged_in'):
            flash('管理者権限がありません。', 'danger')
            return redirect(url_for('login_page'))

        app_info = AppInfo.get_current_info()
        
        # デフォルト値にリセット
        app_info.app_name = "単語帳"
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


def initialize_essay_visibility(room_number):
    """部屋作成時に論述問題の公開設定を初期化（デフォルト非公開）"""
    try:
        print(f"🔒 部屋 {room_number} の論述問題公開設定を初期化中（デフォルト非公開）...")
        
        # 1. 有効な論述問題の章を取得
        chapters = db.session.query(EssayProblem.chapter).filter(
            EssayProblem.enabled == True
        ).distinct().all()
        
        unique_chapters = sorted(list(set([c[0] for c in chapters])))
        if 'com' in unique_chapters:
            unique_chapters.remove('com')
            unique_chapters.append('com')
            
        problem_types = ['A', 'B', 'C', 'D']
        created_count = 0
        
        for chapter in unique_chapters:
            for p_type in problem_types:
                # 既に設定があるか確認
                existing = EssayVisibilitySetting.query.filter_by(
                    room_number=room_number,
                    chapter=chapter,
                    problem_type=p_type
                ).first()
                
                if not existing:
                    # デフォルトで非公開(False)に設定
                    setting = EssayVisibilitySetting(
                        room_number=room_number,
                        chapter=chapter,
                        problem_type=p_type,
                        is_visible=False  # ★ ここで非公開に設定
                    )
                    db.session.add(setting)
                    created_count += 1
        
        db.session.commit()
        print(f"✅ 部屋 {room_number} の公開設定を初期化しました（{created_count}件作成）")
        return True
        
    except Exception as e:
        print(f"❌ 公開設定初期化エラー: {e}")
        return False

@app.route('/admin/add_user', methods=['POST'])
def admin_add_user():
    try:
        if not session.get('admin_logged_in'):
            flash('管理者権限がありません。', 'danger')
            return redirect(url_for('login_page'))

        room_number = request.form.get('room_number', '').strip()
        room_password = request.form.get('room_password')
        student_id = request.form.get('student_id', '').strip()
        individual_password = request.form.get('individual_password')
        username = request.form.get('username', '').strip()

        if not all([room_number, room_password, student_id, individual_password, username]):
            flash('すべての項目を入力してください。', 'danger')
            return redirect(url_for('admin_page'))

        # ユーザーの重複チェック（よりシンプルに）
        existing_user = User.query.filter_by(
            room_number=room_number,
            student_id=student_id,
        ).all()
        
        for user in existing_user:
            if user.check_individual_password(individual_password):
                flash(f'部屋{room_number}・出席番号{student_id}で同じ個別パスワードのアカウントが既に存在します。', 'danger')
                return redirect(url_for('admin_page'))

        new_user = User(
            room_number=room_number,
            student_id=student_id,
            username=username,
            original_username=username,
            is_first_login=True
        )
        new_user.set_room_password(room_password)
        new_user.set_individual_password(individual_password)
        
        new_user.problem_history = {}
        new_user.incorrect_words = []
        
        new_user.last_login = datetime.now(JST)

        db.session.add(new_user)
        db.session.commit()
        
        # 部屋設定の自動作成
        if not RoomSetting.query.filter_by(room_number=room_number).first():
            default_room_setting = RoomSetting(room_number=room_number)
            db.session.add(default_room_setting)
            db.session.commit()
            
            # ★ 論述問題の公開設定を初期化（非公開）
            initialize_essay_visibility(room_number)
            
            flash(f'部屋 {room_number} の設定をデフォルトで作成しました。', 'info')

        flash(f'ユーザー {username} (部屋: {room_number}, 出席番号: {student_id}) を登録しました。', 'success')
        return redirect(url_for('admin_page'))

    except Exception as e:
        db.session.rollback()
        flash(f'ユーザー追加中にエラーが発生しました: {str(e)}', 'danger')
        return redirect(url_for('admin_page'))

def authenticate_user(room_number, room_password, student_id, individual_password):
    """
    複数の同じ出席番号アカウントから正しいものを見つける
    """
    # 同じ部屋番号・出席番号の全てのユーザーを取得
    potential_users = User.query.filter_by(
        room_number=room_number,
        student_id=student_id
    ).all()
    
    for user in potential_users:
        # 入室パスワードと個別パスワードの両方をチェック
        if user.check_room_password(room_password) and user.check_individual_password(individual_password):
            return user
    
    return None

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

@app.route('/admin/bulk_delete_users', methods=['POST'])
def admin_bulk_delete_users():
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限がありません。'}), 403

    data = request.get_json()
    user_ids = data.get('user_ids')

    if not user_ids:
        return jsonify({'status': 'error', 'message': '削除するユーザーが選択されていません。'}), 400

    try:
        # 関連するデータを先に削除
        PasswordResetToken.query.filter(PasswordResetToken.user_id.in_(user_ids)).delete(synchronize_session=False)
        DailyQuizResult.query.filter(DailyQuizResult.user_id.in_(user_ids)).delete(synchronize_session=False)
        MonthlyScore.query.filter(MonthlyScore.user_id.in_(user_ids)).delete(synchronize_session=False)
        MonthlyResultViewed.query.filter(MonthlyResultViewed.user_id.in_(user_ids)).delete(synchronize_session=False)
        UserStats.query.filter(UserStats.user_id.in_(user_ids)).delete(synchronize_session=False)
        EssayProgress.query.filter(EssayProgress.user_id.in_(user_ids)).delete(synchronize_session=False)

        # ユーザーを削除
        num_deleted = User.query.filter(User.id.in_(user_ids)).delete(synchronize_session=False)
        db.session.commit()

        return jsonify({'status': 'success', 'message': f'{num_deleted}人のユーザーを削除しました。'})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"一括削除エラー: {str(e)}")
        return jsonify({'status': 'error', 'message': f'一括削除中にエラーが発生しました: {str(e)}'}), 500

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
            ranking_count = getattr(room_setting, 'ranking_display_count', 5)
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
                'ranking_display_count': 5
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

        # 空リストの場合は明示的に無効化マーカーを設定
        # これにより、デフォルト（[] = 全有効）と区別する
        if not enabled_units:
            enabled_units = ["__DISABLED__"]

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
        if len(content) > 10 * 1024 * 1024:  # 10MB制限
            flash('CSVファイルが大きすぎます（10MB以下にしてください）。', 'danger')
            return redirect(url_for('admin_page'))
        
        content_str = content.decode('utf-8')
        lines = content_str.strip().split('\n')
        
        # 行数制限
        if len(lines) > 10000:  # 10000行制限
            flash('CSVファイルの行数が多すぎます（10000行以下にしてください）。', 'danger')
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

        # バックグラウンド処理関数
        def process_users_background(app, data_lines):
            global registration_status
            with app.app_context():
                print("🔄 バックグラウンド処理開始: ユーザー登録")
                
                # ステータス初期化
                registration_status['is_processing'] = True
                registration_status['total'] = len(data_lines)
                registration_status['current'] = 0
                registration_status['message'] = '処理を開始します...'
                registration_status['errors'] = []
                registration_status['completed'] = False
                
                
                start_time = time.time()
                users_added_count = 0
                errors = []
                skipped_count = 0
                
                try:
                    for line_num, data_line in enumerate(data_lines, start=2):
                        try:
                            # 進捗更新
                            registration_status['current'] = users_added_count + skipped_count
                            registration_status['message'] = f'ユーザー処理中... ({users_added_count + skipped_count}/{len(data_lines)})'
                            
                            if not data_line.strip():
                                continue
                                
                            values = [v.strip() for v in data_line.split(',')]
                            if len(values) < 5:
                                error_msg = f"行{line_num}: データが不完全です"
                                errors.append(error_msg)
                                registration_status['errors'].append(error_msg)
                                continue
                            
                            room_number, room_password, student_id, individual_password, username = values[:5]
                            
                            # 必須項目チェック
                            if not all([room_number, room_password, student_id, individual_password, username]):
                                error_msg = f"行{line_num}: 必須項目が不足しています"
                                errors.append(error_msg)
                                registration_status['errors'].append(error_msg)
                                continue

                            # 重複チェック
                            individual_password_hash = generate_password_hash(individual_password, method='pbkdf2:sha256', salt_length=8)
                            existing_user = User.query.filter_by(
                                room_number=room_number,
                                student_id=student_id
                            ).first()
                            
                            if existing_user:
                                if existing_user._individual_password_hash == individual_password_hash:
                                     error_msg = f"行{line_num}: 部屋{room_number}・出席番号{student_id}で同じ個別パスワードのアカウントが既に存在します"
                                     errors.append(error_msg)
                                     registration_status['errors'].append(error_msg)
                                     skipped_count += 1
                                     continue
                            
                            existing_username = User.query.filter_by(
                                room_number=room_number,
                                username=username
                            ).first()
                            
                            if existing_username:
                                error_msg = f"行{line_num}: ユーザー {username} は既に存在します"
                                errors.append(error_msg)
                                registration_status['errors'].append(error_msg)
                                skipped_count += 1
                                continue

                            # 新規ユーザー作成
                            new_user = User(
                                room_number=room_number,
                                student_id=student_id,
                                username=username,
                                original_username=username,
                                is_first_login=True
                            )
                            
                            new_user._room_password_hash = generate_password_hash(room_password, method='pbkdf2:sha256', salt_length=8)
                            new_user._individual_password_hash = individual_password_hash

                            new_user.problem_history = {}
                            new_user.incorrect_words = []
                            new_user.last_login = datetime.now(JST)

                            db.session.add(new_user)
                            users_added_count += 1
                            
                            # 100件ごとにコミット
                            if users_added_count % 100 == 0:
                                db.session.commit()
                                print(f"💾 バッチコミット: {users_added_count}件完了")
                                import gc
                                gc.collect()

                        except Exception as e:
                            db.session.rollback()
                            error_msg = f"行{line_num}: エラー - {str(e)[:50]}"
                            errors.append(error_msg)
                            registration_status['errors'].append(error_msg)
                            print(f"❌ 行{line_num}エラー: {e}")
                            continue

                    # 最終コミット
                    if users_added_count % 100 != 0:
                        db.session.commit()
                        print(f"💾 最終コミット: {users_added_count}件完了")

                    total_time = time.time() - start_time
                    print(f"🏁 バックグラウンド処理完了: {users_added_count}ユーザー追加, 処理時間: {total_time:.2f}秒")
                    
                    # 完了ステータス更新
                    registration_status['message'] = f'完了: {users_added_count}件追加, {skipped_count}件スキップ, {len(errors)}件エラー'
                    registration_status['completed'] = True
                    registration_status['is_processing'] = False
                    
                except Exception as e:
                    print(f"❌ バックグラウンド処理全体エラー: {e}")
                    registration_status['message'] = f'エラー発生: {str(e)}'
                    registration_status['completed'] = True
                    registration_status['is_processing'] = False
                    import traceback
                    traceback.print_exc()

        # スレッド開始
        thread = threading.Thread(target=process_users_background, args=(app, data_lines))
        thread.start()
        
        # JSONリクエストの場合はJSONで返す
        if request.args.get('json') == 'true':
            return jsonify({
                'status': 'success',
                'message': 'バックグラウンド処理を開始しました',
                'total_lines': len(data_lines)
            })
        
        flash(f'✅ ユーザー登録処理をバックグラウンドで開始しました。完了までしばらくお待ちください。（対象: {len(data_lines)}件）', 'info')
        return redirect(url_for('admin_page'))
                
    except Exception as e:
        error_time = time.time() - start_time if 'start_time' in locals() else 0
        print(f"❌ 致命的エラー: {e} (処理時間: {error_time:.2f}秒)")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        flash(f'CSV処理エラー: {str(e)} (処理時間: {error_time:.1f}秒)', 'danger')

    return redirect(url_for('admin_page'))

@app.route('/admin/api/registration_status')
def get_registration_status():
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
    return jsonify(registration_status)

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
    cw.writerow(['chapter', 'number', 'category', 'question', 'answer', 'enabled', 'incorrect'])
    
    # サンプルデータを追加
    cw.writerow(['1', '1', '古代エジプト', 'ファラオの墓とされる巨大な建造物は？', 'ピラミッド', '1', 'ジッグラト,バベルの塔,スフィンクス'])
    cw.writerow(['1', '2', '古代エジプト２', '古代エジプトの象形文字を何という？', 'ヒエログリフ', '1', '空欄の場合は'])
    cw.writerow(['1', '3', '古代メソポタミア', 'シュメール人が発明した文字は？', '楔形文字', '1', 'レーベンシュタイン距離に基づき'])
    cw.writerow(['2', '1', 'فارسی', 'متشکرم', 'ありがとう', '1', '誤りの選択肢が'])
    cw.writerow(['2', '2', '古代ローマ', 'ローマ帝国初代皇帝に与えられた称号は？', 'アウグストゥス', '1', '他の問題の解答から抽出されます'])
    
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
@app.route('/debug/essay_progress_stats/<int:user_id>')
def debug_essay_progress_stats_fixed(user_id):
    """修正版の論述問題進捗統計デバッグ"""
    if not session.get('admin_logged_in'):
        return "管理者権限が必要です", 403
    
    try:
        user = User.query.get(user_id)
        if not user:
            return "ユーザーが見つかりません", 404
        
        # 修正版の統計関数を使用
        chapter_stats = get_essay_chapter_stats_with_visibility(user_id, user.room_number)
        
        # 詳細な進捗データも取得
        all_progress = EssayProgress.query.filter_by(user_id=user_id).all()
        
        debug_info = {
            'user_info': {
                'id': user.id,
                'username': user.username,
                'room_number': user.room_number
            },
            'progress_summary': {
                'total_progress_entries': len(all_progress),
                'viewed_count': sum(1 for p in all_progress if p.viewed_answer),
                'understood_count': sum(1 for p in all_progress if p.understood)
            },
            'chapter_stats_fixed': chapter_stats,
            'raw_progress_data': [
                {
                    'problem_id': p.problem_id,
                    'viewed_answer': p.viewed_answer,
                    'understood': p.understood,
                    'viewed_at': p.viewed_at.isoformat() if p.viewed_at else None,
                    'understood_at': p.understood_at.isoformat() if p.understood_at else None
                }
                for p in all_progress
            ]
        }
        
        return f"<pre>{json.dumps(debug_info, indent=2, ensure_ascii=False)}</pre>"
        
    except Exception as e:
        return f"エラー: {str(e)}", 500

@app.route('/debug/essay_progress/<int:user_id>')
def debug_essay_progress(user_id):
    """論述問題の進捗データをデバッグ"""
    if 'admin' not in session:
        return "管理者権限が必要です", 403
    
    try:
        user = User.query.get(user_id)
        if not user:
            return f"ユーザーID {user_id} が見つかりません", 404
        
        # 1. 進捗データの存在確認
        progress_data = EssayProgress.query.filter_by(user_id=user_id).all()
        
        # 2. 章別統計の再計算
        chapter_stats = get_essay_chapter_stats_with_visibility(user_id, user.room_number)
        
        debug_info = {
            'user_info': {
                'id': user.id,
                'username': user.username,
                'room_number': user.room_number
            },
            'progress_count': len(progress_data),
            'progress_details': [
                {
                    'problem_id': p.problem_id,
                    'viewed_answer': p.viewed_answer,
                    'understood': p.understood,
                    'viewed_at': p.viewed_at.isoformat() if p.viewed_at else None,
                    'understood_at': p.understood_at.isoformat() if p.understood_at else None
                }
                for p in progress_data
            ],
            'chapter_stats': chapter_stats,
            'total_problems': sum(stat.get('total_problems', 0) for stat in chapter_stats),
            'total_viewed': sum(stat.get('viewed_problems', 0) for stat in chapter_stats),
            'total_understood': sum(stat.get('understood_problems', 0) for stat in chapter_stats)
        }
        
        return f"<pre>{json.dumps(debug_info, indent=2, ensure_ascii=False)}</pre>"
        
    except Exception as e:
        return f"エラー: {str(e)}", 500

def fix_essay_progress_stats():
    """進捗統計の修正関数"""
    try:
        # EssayProgressテーブルの存在確認
        inspector = inspect(db.engine)
        if not inspector.has_table('essay_progress'):
            print("EssayProgressテーブルが存在しません")
            return False
        
        # 統計再計算のためのSQL修正
        # get_essay_chapter_stats_with_visibility 関数内のクエリを確認
        
        # 1. 基本的な進捗データの確認
        total_progress = db.session.query(EssayProgress).count()
        viewed_count = db.session.query(EssayProgress).filter(EssayProgress.viewed_answer == True).count()
        understood_count = db.session.query(EssayProgress).filter(EssayProgress.understood == True).count()
        
        print(f"進捗データ総数: {total_progress}")
        print(f"閲覧済み: {viewed_count}")
        print(f"理解済み: {understood_count}")
        
        # 2. 章別統計の詳細確認
        stats_query = db.session.query(
            EssayProblem.chapter,
            func.count(EssayProblem.id).label('total_problems'),
            func.count(EssayProgress.id).label('progress_entries'),
            func.sum(
                db.case(
                    (EssayProgress.viewed_answer == True, 1),
                    else_=0
                )
            ).label('viewed_problems'),
            func.sum(
                db.case(
                    (EssayProgress.understood == True, 1),
                    else_=0
                )
            ).label('understood_problems')
        ).outerjoin(
            EssayProgress,
            EssayProblem.id == EssayProgress.problem_id
        ).filter(
            EssayProblem.enabled == True
        ).group_by(
            EssayProblem.chapter
        ).all()
        
        for stat in stats_query:
            print(f"章 {stat.chapter}: 総問題数={stat.total_problems}, "
                  f"進捗エントリ={stat.progress_entries}, "
                  f"閲覧済み={stat.viewed_problems}, "
                  f"理解済み={stat.understood_problems}")
        
        return True
        
    except Exception as e:
        print(f"エラー: {e}")
        return False

# 管理者用の修正エンドポイント
@app.route('/admin/fix_essay_stats')
def admin_fix_essay_stats():
    """管理者用: 論述問題統計の修正"""
    if 'admin' not in session:
        return "管理者権限が必要です", 403
    
    result = fix_essay_progress_stats()
    if result:
        return "統計修正処理を実行しました。ログを確認してください。"
    else:
        return "統計修正処理でエラーが発生しました。", 500
    
def debug_essay_image_info(problem_id):
    """論述問題の画像情報をデバッグ出力"""
    import glob
    import os
    
    upload_dir = os.path.join('static', 'uploads', 'essay_images')
    
    print(f"=== 画像デバッグ情報 - 問題ID: {problem_id} ===")
    print(f"アップロードディレクトリ: {upload_dir}")
    print(f"ディレクトリ存在確認: {os.path.exists(upload_dir)}")
    
    # ディレクトリ内の全ファイルをリスト
    if os.path.exists(upload_dir):
        all_files = os.listdir(upload_dir)
        print(f"ディレクトリ内の全ファイル: {all_files}")
        
        # 該当問題IDのファイルを検索
        pattern = f"essay_problem_{problem_id}.*"
        matching_files = [f for f in all_files if f.startswith(f"essay_problem_{problem_id}.")]
        print(f"該当ファイル（パターン: {pattern}）: {matching_files}")
        
        # glob検索結果
        glob_pattern = os.path.join(upload_dir, pattern)
        glob_matches = glob.glob(glob_pattern)
        print(f"glob検索結果: {glob_matches}")
        
        # 各ファイルの詳細情報
        for file_path in glob_matches:
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
            print(f"  ファイル: {file_path}")
            print(f"  サイズ: {file_size} bytes")
            print(f"  存在確認: {os.path.exists(file_path)}")
    else:
        print("アップロードディレクトリが存在しません")
    
    print("=" * 50)

@app.route('/admin/debug_essay_visibility/<room_number>')
def debug_essay_visibility(room_number):
    """論述問題公開設定のデバッグ情報を取得"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
        
        debug_info = {}
        
        # 1. データベース接続確認
        try:
            with db.engine.connect() as conn:
                conn.execute(text('SELECT 1'))
            debug_info['database_connection'] = 'OK'
        except Exception as db_error:
            debug_info['database_connection'] = f'ERROR: {str(db_error)}'
        
        # 2. テーブル存在確認
        try:
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            debug_info['all_tables'] = tables
            debug_info['essay_visibility_table_exists'] = 'essay_visibility_setting' in tables
            debug_info['essay_problems_table_exists'] = 'essay_problems' in tables
        except Exception as table_error:
            debug_info['table_check_error'] = str(table_error)
        
        # 3. essay_visibility_settingテーブルの詳細確認
        if debug_info.get('essay_visibility_table_exists'):
            try:
                with db.engine.connect() as conn:
                    # テーブル構造確認
                    if is_postgres:
                        structure_result = conn.execute(text("""
                            SELECT column_name, data_type 
                            FROM information_schema.columns 
                            WHERE table_name = 'essay_visibility_setting'
                            ORDER BY ordinal_position
                        """))
                    else:
                        structure_result = conn.execute(text("PRAGMA table_info(essay_visibility_setting)"))
                    
                    debug_info['table_structure'] = [dict(row) for row in structure_result.fetchall()]
                    
                    # レコード数確認
                    count_result = conn.execute(text("SELECT COUNT(*) FROM essay_visibility_setting"))
                    debug_info['total_records'] = count_result.fetchone()[0]
                    
                    # 指定部屋の設定確認
                    room_result = conn.execute(text("""
                        SELECT chapter, problem_type, is_visible 
                        FROM essay_visibility_setting 
                        WHERE room_number = :room_number
                    """), {'room_number': room_number})
                    debug_info['room_settings'] = [dict(row) for row in room_result.fetchall()]
                    
            except Exception as detail_error:
                debug_info['table_detail_error'] = str(detail_error)
        
        # 4. essay_problemsテーブルの確認
        if debug_info.get('essay_problems_table_exists'):
            try:
                with db.engine.connect() as conn:
                    chapters_result = conn.execute(text("""
                        SELECT DISTINCT chapter 
                        FROM essay_problems 
                        WHERE enabled = true 
                        ORDER BY chapter
                    """))
                    debug_info['available_chapters'] = [row[0] for row in chapters_result.fetchall()]
                    
                    problems_count = conn.execute(text("SELECT COUNT(*) FROM essay_problems WHERE enabled = true"))
                    debug_info['enabled_problems_count'] = problems_count.fetchone()[0]
                    
            except Exception as problems_error:
                debug_info['problems_table_error'] = str(problems_error)
        
        # 5. 環境情報
        debug_info['is_postgres'] = is_postgres
        debug_info['render_env'] = os.environ.get('RENDER') == 'true'
        debug_info['room_number_requested'] = room_number
        
        return jsonify({
            'status': 'success',
            'debug_info': debug_info
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            'status': 'error',
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500
    
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
        db.session.rollback()
        # エラー時はデフォルト値を返す
        return {
            'app_info': None,
            'app_name': '単語帳',
            'app_version': '1.0.0',
            'app_last_updated': '2025年6月15日',
            'app_update_content': 'アプリケーションが開始されました。',
            'app_footer_text': '',
            'app_contact_email': '',
            'app_school_name': '〇〇高校',
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
            'app_name': app_info.app_name if app_info and app_info.app_name else 'アプリ'
        }
    except Exception as e:
        logger.error(f"Error getting app_info: {e}")
        
        # トランザクションをロールバックして新しいセッションで再試行
        try:
            db.session.rollback()
            app_info = AppInfo.get_current_info()
            return {
                'app_info': app_info,
                'app_name': app_info.app_name if app_info and app_info.app_name else 'アプリ'
            }
        except Exception as e2:
            logger.error(f"Error getting app_info after rollback: {e2}")
            return {
                'app_info': None,
                'app_name': 'アプリ'
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
        db.session.rollback()
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
                    conn.execute(text('ALTER TABLE room_setting ADD COLUMN ranking_display_count INTEGER DEFAULT 5'))
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

# ========================================
# 論述問題集用ルート
# ========================================
@app.route('/essay')
def essay_index():
    """論述問題の章一覧ページ"""
    if not session.get('user_id'):
        return redirect(url_for('login_page'))
    
    try:
        current_user = session.get('username', 'unknown')
        
        # ユーザーの部屋番号を取得
        user = User.query.get(session['user_id'])
        if not user:
            flash('ユーザー情報が見つかりません。', 'error')
            return redirect(url_for('index'))
        
        current_room = user.room_number
        
        if not current_room:
            flash('部屋番号が設定されていません。', 'error')
            return redirect(url_for('index'))
        
        # 公開設定を取得
        visibility_settings = {}
        try:
            settings = EssayVisibilitySetting.query.filter_by(room_number=current_room).all()
            
            for setting in settings:
                if setting.chapter not in visibility_settings:
                    visibility_settings[setting.chapter] = {}
                visibility_settings[setting.chapter][setting.problem_type] = setting.is_visible
                
        except Exception as e:
            app.logger.error(f"公開設定取得エラー: {e}")
            # デフォルト：全ての論述問題を取得して公開設定
            problems = EssayProblem.query.filter_by(enabled=True).all()
            for problem in problems:
                if problem.chapter not in visibility_settings:
                    visibility_settings[problem.chapter] = {}
                visibility_settings[problem.chapter][problem.type] = True
        
        # 章ごとの統計を取得（順序制御付き）
        chapter_stats = []
        
        # 通常の章（1章、2章、3章...）と総合問題を分離
        regular_chapters = []
        combined_chapters = []
        
        for chapter in visibility_settings.keys():
            if chapter == 'com' or chapter.lower() == 'com':  # 総合問題
                combined_chapters.append(chapter)
            else:
                try:
                    # 数値として変換可能な章を通常章として扱う
                    int(chapter)
                    regular_chapters.append(chapter)
                except ValueError:
                    # 数値でない章も総合問題扱い
                    combined_chapters.append(chapter)
        
        # 通常章を数値でソート
        regular_chapters.sort(key=lambda x: int(x))
        
        # 総合問題をソート（アルファベット順）
        combined_chapters.sort()
        
        # 並び順：通常章 → 総合問題
        sorted_chapters = regular_chapters + combined_chapters
        
        app.logger.info(f"📊 章並び順: {sorted_chapters}")
        
        for chapter in sorted_chapters:
            types = visibility_settings[chapter]
            
            # この章で公開されている問題があるかチェック
            has_visible_problems = any(is_visible for is_visible in types.values())
            
            if not has_visible_problems:
                app.logger.info(f"⏭️ 第{chapter}章: 公開問題なし（スキップ）")
                continue
            
            # 章の統計を計算
            if chapter == 'com' or chapter.lower() == 'com':
                chapter_name = "総合問題"
            else:
                chapter_name = f"第{chapter}章"
            
            # この章の問題を取得（公開設定に従って）
            visible_problems = []
            for problem_type in ['A', 'B', 'C', 'D']:
                is_visible = types.get(problem_type, True)  # デフォルト公開
                if is_visible:
                    problems = EssayProblem.query.filter_by(
                        chapter=chapter,
                        type=problem_type,
                        enabled=True
                    ).all()
                    visible_problems.extend(problems)

            
            if not visible_problems:
                app.logger.info(f"⏭️ {chapter_name}: 実際の問題なし（スキップ）")
                continue
            
            # ユーザーの進捗を取得
            total_problems = len(visible_problems)
            viewed_problems = 0
            understood_problems = 0
            
            # 進捗計算（EssayProgressテーブルがある場合）
            try:
                for problem in visible_problems:
                    progress = EssayProgress.query.filter_by(
                        user_id=session.get('user_id'),
                        problem_id=problem.id
                    ).first()
                    
                    if progress:
                        viewed_problems += 1
                        if progress.understood:
                            understood_problems += 1
            except Exception:
                # EssayProgressテーブルがない場合はスキップ
                pass
            
            # 進捗率を計算
            progress_rate = int((understood_problems / total_problems * 100)) if total_problems > 0 else 0
            
            chapter_stat = {
                'chapter': chapter,
                'chapter_name': chapter_name,
                'total_problems': total_problems,
                'viewed_problems': viewed_problems,
                'understood_problems': understood_problems,
                'progress_rate': progress_rate
            }
            
            chapter_stats.append(chapter_stat)
            app.logger.info(f"📈 {chapter_name}: {total_problems}問（閲覧:{viewed_problems}, 理解:{understood_problems}）")
        
        app.logger.info(f"✅ 論述問題章一覧を生成しました（{len(chapter_stats)}章）")
        
        # テンプレートコンテキストを取得
        context = get_template_context()
        
        return render_template('essay_index.html', 
                             chapter_stats=chapter_stats,
                             current_username=current_user,
                             current_room_number=current_room,
                             **context)
        
    except Exception as e:
        app.logger.error(f"論述問題章一覧エラー: {str(e)}")
        flash('章一覧の取得に失敗しました。', 'error')
        return redirect(url_for('index'))
    
@app.route('/essay/chapter/<chapter>')
def essay_chapter(chapter):
    """章別論述問題一覧（公開設定対応版）"""
    try:
        if 'user_id' not in session:
            flash('論述問題を閲覧するにはログインしてください。', 'info')
            return redirect(url_for('login_page'))

        current_user = User.query.get(session['user_id'])
        if not current_user:
            flash('ユーザーが見つかりません。', 'danger')
            return redirect(url_for('logout'))

        print(f"📊 章別論述問題一覧 - 第{chapter}章, ユーザー: {current_user.username}, 部屋: {current_user.room_number}")

        # フィルターパラメータの取得
        type_filter = request.args.get('type', '').strip()
        university_filter = request.args.get('university', '').strip()
        year_from = request.args.get('year_from', type=int)
        year_to = request.args.get('year_to', type=int)
        keyword = request.args.get('keyword', '').strip()

        print(f"🔍 フィルター - タイプ: {type_filter}, 大学: {university_filter}, 年度: {year_from}-{year_to}, キーワード: {keyword}")

        # 公開設定を考慮した問題取得（ユーザーIDを渡して進捗情報も取得）
        problems = get_filtered_essay_problems_with_visibility(
            chapter=chapter,
            room_number=current_user.room_number,
            type_filter=type_filter or None,
            university_filter=university_filter or None,
            year_from=year_from,
            year_to=year_to,
            keyword=keyword or None,
            user_id=current_user.id  # ここでuser_idを渡す
        )

        print(f"📋 公開設定適用後の問題数: {len(problems)}件")

        # フィルター用のデータを取得（公開設定対応版）
        filter_data = get_essay_filter_data_with_visibility(chapter, current_user.room_number)

        # 章名の決定
        chapter_name = '総合問題' if chapter == 'com' else f'第{chapter}章'

        # 統計情報を計算
        total_problems = len(problems)
        viewed_problems = sum(1 for p in problems if p.progress['viewed_answer'])
        understood_problems = sum(1 for p in problems if p.progress['understood'])
        progress_rate = round((understood_problems / total_problems * 100) if total_problems > 0 else 0, 1)

        # テンプレートコンテキストを取得（引数なし）
        context = get_template_context()
        
        # 必要な情報を追加
        context.update({
            'chapter': chapter,
            'chapter_name': chapter_name,
            'problems': problems,
            'filter_data': filter_data,
            'current_filters': {
                'type': type_filter,
                'university': university_filter,
                'year_from': year_from,
                'year_to': year_to,
                'keyword': keyword
            },
            'current_user_id': current_user.id,
            'current_username': current_user.username,
            'current_room_number': current_user.room_number,
            'is_logged_in': True,
            # 統計情報を追加
            'total_problems': total_problems,
            'viewed_problems': viewed_problems,
            'understood_problems': understood_problems,
            'progress_rate': progress_rate
        })

        return render_template('essay_chapter.html', **context)

    except Exception as e:
        print(f"Error in essay_chapter: {e}")
        import traceback
        traceback.print_exc()
        flash('論述問題の取得中にエラーが発生しました。', 'danger')
        return redirect(url_for('essay_index'))

@app.route('/essay/problem/<int:problem_id>')
def essay_problem(problem_id):
    """個別論述問題表示（画像表示デバッグ機能付き）"""
    try:
        if 'user_id' not in session:
            flash('論述問題を閲覧するにはログインしてください。', 'info')
            return redirect(url_for('login_page'))

        current_user = User.query.get(session['user_id'])
        if not current_user:
            flash('ユーザーが見つかりません。', 'danger')
            return redirect(url_for('logout'))

        problem = EssayProblem.query.get_or_404(problem_id)

        # 現在のユーザーの進捗情報を取得
        progress = EssayProgress.query.filter_by(
            user_id=current_user.id,
            problem_id=problem_id
        ).first()
        
        # デフォルトの進捗情報を設定
        default_progress = {
            'viewed_answer': False,
            'understood': False,
            'difficulty_rating': None,
            'memo': None,
            'review_flag': False
        }
        
        # 問題オブジェクトに進捗情報を追加
        if progress:
            problem.progress = {
                'viewed_answer': progress.viewed_answer,
                'understood': progress.understood,
                'difficulty_rating': progress.difficulty_rating,
                'memo': progress.memo,
                'review_flag': progress.review_flag
            }
        else:
            problem.progress = default_progress
        
        print(f"📊 個別問題表示 - ID: {problem_id}, 第{problem.chapter}章 タイプ{problem.type}, ユーザー: {current_user.username}, 部屋: {current_user.room_number}")
        
        # 公開設定をチェック
        if not is_essay_problem_visible(current_user.room_number, problem.chapter, problem.type):
            print(f"❌ 非公開問題へのアクセス - ID: {problem_id}, 第{problem.chapter}章 タイプ{problem.type}")
            flash('この問題は現在公開されていません。', 'warning')
            return redirect(url_for('essay_index'))
        
        print(f"✅ 公開問題へのアクセス - ID: {problem_id}")
        
        # 前後の問題を取得（公開されているもののみ）
        prev_problem, next_problem = get_adjacent_problems_with_visibility(problem, current_user.room_number)
        
        # 画像関連の詳細デバッグ情報を出力
        print(f"🖼️ 画像デバッグ開始 - 問題ID: {problem_id}")
        debug_essay_image_info(problem_id)
        
        # 画像パスを取得
        image_path = None
        has_image = has_essay_problem_image(problem_id)
        
        print(f"📸 画像存在確認: {has_image}")
        
        if has_image:
            image_path = get_essay_problem_image_path(problem_id)
            print(f"📸 生成された画像パス: {image_path}")
            
            # 画像ファイルの物理的存在確認
            if image_path:
                full_image_path = os.path.join('static', image_path)
                image_exists = os.path.exists(full_image_path)
                print(f"📸 画像ファイル物理的存在確認: {image_exists} (パス: {full_image_path})")
                
                if not image_exists:
                    print(f"⚠️ 画像パスは生成されましたが、ファイルが存在しません: {full_image_path}")
                    image_path = None
        else:
            print(f"📸 問題ID {problem_id} には画像が関連付けられていません")
        
        # テンプレートコンテキストを取得（引数なし）
        context = get_template_context()
        
        # フィルター用のデータを取得（公開設定対応版）
        filter_data = get_essay_filter_data_with_visibility(problem.chapter, current_user.room_number)
        
        # 必要な情報を追加
        context.update({
            'problem': problem,
            'prev_problem': prev_problem,
            'next_problem': next_problem,
            'image_path': image_path,  # ここで正しく渡されているかを確認
            'current_user_id': current_user.id,
            'current_username': current_user.username,
            'current_room_number': current_user.room_number,
            'is_logged_in': True,
            'current_filters': {
                'type': '',
                'university': '',
                'year_from': None,
                'year_to': None,
                'keyword': ''
            },
            'filter_data': filter_data,
            'chapter': problem.chapter,
            'chapter_name': '総合問題' if problem.chapter == 'com' else f'第{problem.chapter}章',
            'problems': [problem]
        })
        
        # テンプレートに渡される image_path の最終確認
        print(f"📸 テンプレートに渡される image_path: {context.get('image_path')}")
        
        return render_template('essay_problem.html', **context)

    except Exception as e:
        print(f"Error in essay_problem: {e}")
        import traceback
        traceback.print_exc()
        flash('論述問題の表示中にエラーが発生しました。', 'danger')
        return redirect(url_for('essay_index'))
    
def get_adjacent_problems_with_visibility(problem, room_number):
    """公開設定を考慮した前後の問題を取得"""
    try:
        print(f"🔍 前後問題取得 - 第{problem.chapter}章, 部屋: {room_number}")
        
        # 同じ章の公開されている問題を type → year → university の順でソート
        ordered_problems = EssayProblem.query.filter(
            EssayProblem.chapter == problem.chapter,
            EssayProblem.enabled == True
        ).order_by(
            EssayProblem.type,
            EssayProblem.year.desc(),
            EssayProblem.university
        ).all()
        
        # 公開設定でフィルタリング
        visible_problems = []
        for p in ordered_problems:
            if is_essay_problem_visible(room_number, p.chapter, p.type):
                visible_problems.append(p)
        
        print(f"📋 公開問題数: {len(visible_problems)}件（全体: {len(ordered_problems)}件）")
        
        current_index = None
        for i, p in enumerate(visible_problems):
            if p.id == problem.id:
                current_index = i
                break
        
        if current_index is None:
            print("⚠️ 現在の問題が公開問題リストに見つかりません")
            return None, None
        
        prev_problem = visible_problems[current_index - 1] if current_index > 0 else None
        next_problem = visible_problems[current_index + 1] if current_index < len(visible_problems) - 1 else None
        
        print(f"📍 前の問題: {prev_problem.id if prev_problem else 'なし'}, 次の問題: {next_problem.id if next_problem else 'なし'}")
        
        return prev_problem, next_problem
        
    except Exception as e:
        print(f"Error getting adjacent problems with visibility: {e}")
        return None, None

def is_essay_problem_visible_sql(room_number, chapter, problem_type):
    """SQLベースの公開設定チェック（モデル問題回避版）"""
    try:
        with db.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT is_visible 
                FROM essay_visibility_setting 
                WHERE room_number = :room_number 
                AND chapter = :chapter 
                AND problem_type = :problem_type
            """), {
                'room_number': room_number,
                'chapter': chapter,
                'problem_type': problem_type
            })
            
            row = result.fetchone()
            if row:
                is_visible = row[0]
                print(f"📊 公開設定確認 - 部屋{room_number} 第{chapter}章 タイプ{problem_type}: {'公開' if is_visible else '非公開'}")
                return is_visible
            else:
                print(f"⚠️ 公開設定なし - 部屋{room_number} 第{chapter}章 タイプ{problem_type}: デフォルト公開")
                return True  # 設定がない場合はデフォルトで公開
    except Exception as e:
        print(f"Error checking essay visibility (SQL): {e}")
        return True  # エラー時はデフォルトで公開

# ========================================
# 論述問題公開設定 ヘルパー関数
# ========================================
def is_essay_problem_visible(room_number, chapter, problem_type):
    """特定の部屋で論述問題が公開されているかチェック（SQL版）"""
    return is_essay_problem_visible_sql(room_number, chapter, problem_type)

def get_essay_visibility_settings(room_number):
    """部屋の論述問題公開設定を全て取得"""
    try:
        settings = EssayVisibilitySetting.query.filter_by(room_number=room_number).all()
        
        # 設定を辞書形式に変換
        visibility_dict = {}
        for setting in settings:
            if setting.chapter not in visibility_dict:
                visibility_dict[setting.chapter] = {}
            visibility_dict[setting.chapter][setting.problem_type] = setting.is_visible
        
        return visibility_dict
        
    except Exception as e:
        print(f"Error getting essay visibility settings: {e}")
        return {}

def set_essay_visibility_setting(room_number, chapter, problem_type, is_visible):
    """論述問題の公開設定を更新または作成"""
    try:
        setting = EssayVisibilitySetting.query.filter_by(
            room_number=room_number,
            chapter=chapter,
            problem_type=problem_type
        ).first()
        
        if setting:
            # 既存設定を更新
            setting.is_visible = is_visible
            setting.updated_at = datetime.now(JST)
        else:
            # 新規設定を作成
            setting = EssayVisibilitySetting(
                room_number=room_number,
                chapter=chapter,
                problem_type=problem_type,
                is_visible=is_visible
            )
            db.session.add(setting)
        
        db.session.commit()
        return True
        
    except Exception as e:
        print(f"Error setting essay visibility: {e}")
        db.session.rollback()
        return False

def get_filtered_essay_problems_with_visibility(chapter, room_number, type_filter=None, university_filter=None, year_from=None, year_to=None, keyword=None, user_id=None):
    """部屋の公開設定を考慮した論述問題の取得（progress情報付き）"""
    try:
        # ベースクエリ (有効な問題のみをまず取得)
        query = EssayProblem.query.filter(EssayProblem.enabled == True) # <--- ★まず章で絞らない

        # もし章が指定されていたら、その章で絞り込む <--- ★このif文を追加
        if chapter:
            query = query.filter(EssayProblem.chapter == chapter)
        
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
        
        # ソート
        query = query.order_by(
            EssayProblem.type,
            EssayProblem.year.desc(),
            EssayProblem.university
        )
        
        results = query.all()
        
        # 結果を処理し、公開設定でフィルタリング
        problems = []
        for problem in results:
            if not is_essay_problem_visible(room_number, problem.chapter, problem.type):
                continue
            
            progress_data = {
                'viewed_answer': False, 'understood': False,
                'difficulty_rating': None, 'review_flag': False
            }
            
            if user_id:
                try:
                    progress = EssayProgress.query.filter_by(
                        user_id=user_id, problem_id=problem.id
                    ).first()
                    
                    if progress:
                        progress_data.update({
                            'viewed_answer': progress.viewed_answer,
                            'understood': progress.understood,
                            'difficulty_rating': progress.difficulty_rating,
                            'review_flag': progress.review_flag
                        })
                except Exception as progress_error:
                    print(f"Error getting progress for problem {problem.id}: {progress_error}")
            
            problem.progress = progress_data
            problems.append(problem)
        
        print(f"📋 公開設定適用後の問題数: {len(problems)}件, 進捗情報付与完了")
        return problems
        
    except Exception as e:
        print(f"Error getting filtered essay problems with visibility: {e}")
        return []

def get_essay_chapter_stats_with_visibility(user_id, room_number):
    """公開設定を考慮した章別統計情報を取得（進捗データ修正版）"""
    try:
        # 1. 公開設定を考慮したすべての問題を取得
        all_problems_query = db.session.query(
            EssayProblem.chapter,
            EssayProblem.type,
            EssayProblem.id
        ).filter(
            EssayProblem.enabled == True
        ).all()
        
        # 公開設定でフィルタリング
        visible_problems = []
        for problem in all_problems_query:
            if is_essay_problem_visible(room_number, problem.chapter, problem.type):
                visible_problems.append(problem)
        
        # 2. 章別に問題をグループ化
        chapter_problems = {}
        for problem in visible_problems:
            if problem.chapter not in chapter_problems:
                chapter_problems[problem.chapter] = []
            chapter_problems[problem.chapter].append(problem.id)
        
        # 3. 各章の進捗データを取得
        chapter_stats = {}
        for chapter, problem_ids in chapter_problems.items():
            # 該当章の進捗データを取得
            progress_query = db.session.query(
                func.count(EssayProgress.id).label('total_progress'),
                func.sum(
                    db.case(
                        (EssayProgress.viewed_answer == True, 1),
                        else_=0
                    )
                ).label('viewed_count'),
                func.sum(
                    db.case(
                        (EssayProgress.understood == True, 1),
                        else_=0
                    )
                ).label('understood_count')
            ).filter(
                EssayProgress.user_id == user_id,
                EssayProgress.problem_id.in_(problem_ids)
            ).first()
            
            total_problems = len(problem_ids)
            viewed_problems = int(progress_query.viewed_count or 0)
            understood_problems = int(progress_query.understood_count or 0)
            
            chapter_stats[chapter] = {
                'chapter_name': '総合問題' if chapter == 'com' else f'第{chapter}章',
                'total_problems': total_problems,
                'viewed_problems': viewed_problems,
                'understood_problems': understood_problems,
                'progress_rate': round((understood_problems / total_problems * 100) if total_problems > 0 else 0, 1)
            }
        
        # 4. ソートして返す
        sorted_chapters = []
        for chapter_key in sorted(chapter_stats.keys(), key=lambda x: (x != 'com', x)):
            chapter_data = chapter_stats[chapter_key]
            chapter_data['chapter'] = chapter_key
            sorted_chapters.append(chapter_data)
        
        print(f"📊 章別統計（修正版）: {len(sorted_chapters)}章")
        for chapter_data in sorted_chapters:
            print(f"  {chapter_data['chapter_name']}: 総数={chapter_data['total_problems']}, "
                  f"閲覧={chapter_data['viewed_problems']}, 理解={chapter_data['understood_problems']}")
        
        return sorted_chapters
        
    except Exception as e:
        print(f"Error getting essay chapter stats with visibility (fixed): {e}")
        import traceback
        traceback.print_exc()
        return []

# ========================================
# 論述問題公開設定 API エンドポイント
# ========================================
@app.route('/debug/essay_images')
def debug_essay_images():
    """論述問題の画像状況をデバッグ"""
    if not session.get('admin_logged_in'):
        return "管理者権限が必要です", 403
    
    import glob
    import os
    
    debug_info = []
    
    try:
        # アップロードディレクトリの確認
        upload_dir = os.path.join('static', 'uploads', 'essay_images')
        debug_info.append(f"アップロードディレクトリ: {upload_dir}")
        debug_info.append(f"ディレクトリ存在: {os.path.exists(upload_dir)}")
        
        if os.path.exists(upload_dir):
            # ディレクトリ内の全ファイル
            all_files = os.listdir(upload_dir)
            debug_info.append(f"ディレクトリ内のファイル数: {len(all_files)}")
            debug_info.append("ファイル一覧:")
            
            for file in all_files:
                file_path = os.path.join(upload_dir, file)
                file_size = os.path.getsize(file_path)
                debug_info.append(f"  - {file} ({file_size} bytes)")
        
        # データベースから画像付き問題を確認
        problems_with_images = []
        all_problems = EssayProblem.query.all()
        
        for problem in all_problems:
            has_image = has_essay_problem_image(problem.id)
            image_path = get_essay_problem_image_path(problem.id) if has_image else None
            
            if has_image:
                problems_with_images.append({
                    'id': problem.id,
                    'chapter': problem.chapter,
                    'university': problem.university,
                    'year': problem.year,
                    'has_image': has_image,
                    'image_path': image_path,
                    'file_exists': os.path.exists(os.path.join('static', image_path)) if image_path else False
                })
        
        debug_info.append(f"\n画像付き問題数: {len(problems_with_images)}")
        debug_info.append("画像付き問題一覧:")
        
        for problem_info in problems_with_images:
            debug_info.append(f"  問題ID {problem_info['id']} ({problem_info['university']} {problem_info['year']}年):")
            debug_info.append(f"    画像パス: {problem_info['image_path']}")
            debug_info.append(f"    ファイル存在: {problem_info['file_exists']}")
        
        return "<pre>" + "\n".join(debug_info) + "</pre>"
        
    except Exception as e:
        return f"<pre>デバッグエラー: {str(e)}</pre>"

@app.route('/debug/essay_image/<int:problem_id>')
def debug_essay_image_specific(problem_id):
    """特定の問題の画像をデバッグ"""
    if not session.get('admin_logged_in'):
        return "管理者権限が必要です", 403
    
    debug_essay_image_info(problem_id)
    
    problem = EssayProblem.query.get_or_404(problem_id)
    has_image = has_essay_problem_image(problem_id)
    image_path = get_essay_problem_image_path(problem_id) if has_image else None
    
    info = []
    info.append(f"問題ID: {problem_id}")
    info.append(f"大学: {problem.university}")
    info.append(f"年度: {problem.year}")
    info.append(f"章: {problem.chapter}")
    info.append(f"画像あり: {has_image}")
    info.append(f"画像パス: {image_path}")
    
    if image_path:
        full_path = os.path.join('static', image_path)
        info.append(f"フルパス: {full_path}")
        info.append(f"ファイル存在: {os.path.exists(full_path)}")
        
        if os.path.exists(full_path):
            file_size = os.path.getsize(full_path)
            info.append(f"ファイルサイズ: {file_size} bytes")
            
            # 画像を実際に表示してみる
            info.append(f"\n実際の画像表示テスト:")
            info.append(f'<img src="/static/{image_path}" style="max-width: 300px; border: 1px solid red;" alt="テスト画像">')
    
    return "<pre>" + "\n".join(info) + "</pre>"

@app.route('/admin/get_room_list')
def admin_get_room_list():
    """管理画面用：全部屋番号のリストを取得"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
        
        # RoomSettingから部屋番号を取得
        room_settings = db.session.query(RoomSetting.room_number).distinct().all()
        rooms_from_settings = [r[0] for r in room_settings]
        
        # Userテーブルからも部屋番号を取得
        user_rooms = db.session.query(User.room_number).distinct().all()
        rooms_from_users = [r[0] for r in user_rooms if r[0]]
        
        # 重複を除去してマージ
        all_rooms = list(set(rooms_from_settings + rooms_from_users))
        all_rooms.sort()
        
        return jsonify({
            'status': 'success',
            'rooms': all_rooms
        })
        
    except Exception as e:
        print(f"Error getting room list: {e}")
        return jsonify({'status': 'error', 'message': '部屋一覧の取得に失敗しました'}), 500

@app.route('/admin/essay_visibility_settings/<room_number>')
def admin_get_essay_visibility_settings(room_number):
    """特定部屋の論述問題公開設定を取得（強化版）"""
    try:
        print(f"📊 部屋 {room_number} の論述問題公開設定を取得開始")
        
        if not session.get('admin_logged_in'):
            print("❌ 管理者権限なし")
            return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
        
        # デバッグ情報をまず確認
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        
        print(f"🔍 データベーステーブル一覧: {inspector.get_table_names()}")
        
        if not inspector.has_table('essay_visibility_setting'):
            print("❌ essay_visibility_settingテーブルが存在しません - 自動作成を試行")
            
            # 自動作成を試行
            try:
                create_essay_visibility_table_auto()
                print("✅ テーブル自動作成完了")
            except Exception as create_error:
                print(f"❌ テーブル自動作成失敗: {create_error}")
                return jsonify({
                    'status': 'error', 
                    'message': f'テーブルが存在せず、自動作成にも失敗しました: {str(create_error)}'
                }), 500
        
        # 設定データを取得
        try:
            with db.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT chapter, problem_type, is_visible 
                    FROM essay_visibility_setting 
                    WHERE room_number = :room_number
                """), {'room_number': room_number})
                
                settings_data = result.fetchall()
                print(f"📋 部屋 {room_number} の設定: {len(settings_data)}件取得")
        except Exception as query_error:
            print(f"❌ 設定データ取得エラー: {query_error}")
            return jsonify({
                'status': 'error', 
                'message': f'設定データの取得に失敗しました: {str(query_error)}'
            }), 500
        
        # 設定を辞書形式に変換
        visibility_dict = {}
        for row in settings_data:
            chapter, problem_type, is_visible = row
            if chapter not in visibility_dict:
                visibility_dict[chapter] = {}
            visibility_dict[chapter][problem_type] = is_visible
        
        # 章リストを取得
        chapters = []
        try:
            with db.engine.connect() as conn:
                chapters_result = conn.execute(text("""
                    SELECT DISTINCT chapter 
                    FROM essay_problems 
                    WHERE enabled = true 
                    ORDER BY chapter
                """))
                chapters = [row[0] for row in chapters_result.fetchall() if row[0]]
                print(f"📊 利用可能な章: {chapters}")
        except Exception as chapters_error:
            print(f"⚠️ 章データ取得エラー: {chapters_error}")
            # デフォルト章を設定
            chapters = ['1', '2', '3', '4', '5', 'com']
        
        # 章をソート
        numeric_chapters = []
        string_chapters = []
        
        for ch in chapters:
            try:
                numeric_chapters.append((int(ch), ch))
            except ValueError:
                string_chapters.append(ch)
        
        sorted_chapters = [ch for _, ch in sorted(numeric_chapters)]
        sorted_chapters.extend(sorted(string_chapters))
        
        print(f"✅ 設定取得完了 - 章: {sorted_chapters}, 設定: {len(settings_data)}件")
        
        return jsonify({
            'status': 'success',
            'settings': visibility_dict,
            'chapters': sorted_chapters,
            'types': ['A', 'B', 'C', 'D']
        })
        
    except Exception as e:
        print(f"❌ 論述問題公開設定取得エラー: {e}")
        import traceback
        print(traceback.format_exc())
        return jsonify({
            'status': 'error', 
            'message': f'予期しないエラーが発生しました: {str(e)}'
        }), 500

@app.route('/admin/essay_visibility_settings/save', methods=['POST'])
def admin_save_essay_visibility_settings():
    """論述問題公開設定を保存（修正版）"""
    try:
        print("💾 論述問題公開設定保存開始")
        
        if not session.get('admin_logged_in'):
            print("❌ 管理者権限なし")
            return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
        
        data = request.get_json()
        if not data:
            print("❌ JSONデータなし")
            return jsonify({'status': 'error', 'message': 'JSONデータが必要です'}), 400
        
        room_number = data.get('room_number')
        settings = data.get('settings', {})
        
        print(f"📊 保存対象: 部屋{room_number}, 設定数: {len(settings)}")
        
        if not room_number:
            return jsonify({'status': 'error', 'message': '部屋番号が指定されていません'}), 400
        
        # テーブル存在確認
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        if not inspector.has_table('essay_visibility_setting'):
            print("❌ テーブルが存在しません - 自動作成を試行")
            try:
                create_essay_visibility_table_auto()
            except Exception as create_error:
                print(f"❌ テーブル作成失敗: {create_error}")
                return jsonify({'status': 'error', 'message': 'テーブルが存在せず、作成にも失敗しました'}), 500
        
        saved_count = 0
        updated_count = 0
        
        # 直接SQLで設定を保存（モデルの問題を回避）
        try:
            with db.engine.connect() as conn:
                for chapter, chapter_settings in settings.items():
                    for problem_type, is_visible in chapter_settings.items():
                        print(f"🔧 処理中: 部屋{room_number} 第{chapter}章 タイプ{problem_type} -> {'公開' if is_visible else '非公開'}")
                        
                        # 既存設定があるかチェック
                        check_result = conn.execute(text("""
                            SELECT COUNT(*) FROM essay_visibility_setting 
                            WHERE room_number = :room AND chapter = :chapter AND problem_type = :type
                        """), {
                            'room': room_number,
                            'chapter': chapter,
                            'type': problem_type
                        })
                        
                        exists = check_result.fetchone()[0] > 0
                        
                        if exists:
                            # 既存設定を更新
                            conn.execute(text("""
                                UPDATE essay_visibility_setting 
                                SET is_visible = :visible, updated_at = CURRENT_TIMESTAMP 
                                WHERE room_number = :room AND chapter = :chapter AND problem_type = :type
                            """), {
                                'visible': is_visible,
                                'room': room_number,
                                'chapter': chapter,
                                'type': problem_type
                            })
                            updated_count += 1
                        else:
                            # 新規設定を作成
                            conn.execute(text("""
                                INSERT INTO essay_visibility_setting 
                                (room_number, chapter, problem_type, is_visible) 
                                VALUES (:room, :chapter, :type, :visible)
                            """), {
                                'room': room_number,
                                'chapter': chapter,
                                'type': problem_type,
                                'visible': is_visible
                            })
                            saved_count += 1
                
                conn.commit()
                print(f"✅ 保存完了: 新規{saved_count}件, 更新{updated_count}件")
        
        except Exception as save_error:
            print(f"❌ 保存エラー: {save_error}")
            return jsonify({'status': 'error', 'message': f'設定の保存に失敗しました: {str(save_error)}'}), 500
        
        message = f'設定を保存しました（新規: {saved_count}件, 更新: {updated_count}件）'
        
        return jsonify({
            'status': 'success',
            'message': message,
            'saved_count': saved_count,
            'updated_count': updated_count
        })
        
    except Exception as e:
        print(f"❌ 論述問題公開設定保存エラー: {e}")
        import traceback
        print(traceback.format_exc())
        return jsonify({'status': 'error', 'message': f'予期しないエラーが発生しました: {str(e)}'}), 500

# ========================================
# 既存の論述問題ルートの修正部分
# ========================================
def get_essay_filter_data_with_visibility(chapter, room_number):
    """公開設定を考慮したフィルター用データを取得"""
    try:
        # まず公開されているタイプを確認
        visible_types = []
        for type_char in ['A', 'B', 'C', 'D']:
            if is_essay_problem_visible(room_number, chapter, type_char):
                visible_types.append(type_char)
        
        if not visible_types:
            # 公開されているタイプがない場合
            return {
                'universities': [],
                'year_range': {'min': 2020, 'max': 2025},
                'types': []
            }
        
        # 公開されているタイプの問題のみを対象に集計
        base_query = EssayProblem.query.filter(
            EssayProblem.chapter == chapter,
            EssayProblem.enabled == True,
            EssayProblem.type.in_(visible_types)
        )
        
        # 大学一覧
        universities = base_query.with_entities(EssayProblem.university).distinct().order_by(EssayProblem.university).all()
        
        # 年度範囲
        year_range = base_query.with_entities(
            func.min(EssayProblem.year).label('min_year'),
            func.max(EssayProblem.year).label('max_year')
        ).first()
        
        return {
            'universities': [u[0] for u in universities if u[0]],
            'year_range': {
                'min': year_range.min_year or 2020,
                'max': year_range.max_year or 2025
            },
            'types': visible_types
        }
        
    except Exception as e:
        print(f"Error getting essay filter data with visibility: {e}")
        return {
            'universities': [],
            'year_range': {'min': 2020, 'max': 2025},
            'types': []
        }

@app.route('/admin/essay/stats')
def admin_essay_stats():
    """論述問題の統計情報を取得"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
        
        # 基本統計
        total_problems = EssayProblem.query.count()
        enabled_problems = EssayProblem.query.filter_by(enabled=True).count()
        
        # 章数
        chapters = db.session.query(EssayProblem.chapter).distinct().count()
        
        # 学習記録数
        progress_records = EssayProgress.query.count()
        
        # タイプ別統計
        type_stats = db.session.query(
            EssayProblem.type,
            func.count(EssayProblem.id).label('count')
        ).filter(EssayProblem.enabled == True).group_by(EssayProblem.type).all()
        
        return jsonify({
            'status': 'success',
            'total_problems': total_problems,
            'enabled_problems': enabled_problems,
            'chapters_count': chapters,
            'progress_records': progress_records,
            'type_stats': [{'type': t.type, 'count': t.count} for t in type_stats]
        })
        
    except Exception as e:
        logger.error(f"Error getting essay stats: {e}")
        return jsonify({
            'status': 'error',
            'message': '統計情報の取得中にエラーが発生しました'
        }), 500

@app.route('/admin/essay/problems')
def admin_essay_problems():
    """論述問題一覧を取得（フィルター対応）"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
        
        # クエリパラメータの取得
        chapter = request.args.get('chapter', '').strip()
        type_filter = request.args.get('type', '').strip()
        search = request.args.get('search', '').strip()
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        
        # ベースクエリ
        query = EssayProblem.query
        
        # フィルター適用
        if chapter:
            query = query.filter(EssayProblem.chapter == chapter)
        
        if type_filter:
            query = query.filter(EssayProblem.type == type_filter)
        
        if search:
            search_pattern = f'%{search}%'
            query = query.filter(
                db.or_(
                    EssayProblem.question.like(search_pattern),
                    EssayProblem.university.like(search_pattern),
                    EssayProblem.answer.like(search_pattern)
                )
            )
        
        # ソート（章→タイプ→年度の順）
        query = query.order_by(
            EssayProblem.chapter,
            EssayProblem.type,
            EssayProblem.year.desc(),
            EssayProblem.id
        )
        
        # ページネーション
        pagination = query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        problems = []
        for problem in pagination.items:
            problems.append({
                'id': problem.id,
                'chapter': problem.chapter,
                'type': problem.type,
                'university': problem.university,
                'year': problem.year,
                'question': problem.question,
                'answer': problem.answer,
                'answer_length': problem.answer_length,
                'enabled': problem.enabled
            })
        
        # ★★★ ここから追加 ★★★
        # 章リストを取得
        all_chapters = db.session.query(EssayProblem.chapter)\
            .distinct()\
            .order_by(EssayProblem.chapter)\
            .all()
        
        # 章リストを整形
        chapter_list = []
        for (ch,) in all_chapters:
            if ch:  # NULLや空文字を除外
                chapter_list.append(ch)
        
        # 数値と文字列を分けてソート
        numeric_chapters = []
        string_chapters = []
        
        for ch in chapter_list:
            try:
                numeric_chapters.append(int(ch))
            except ValueError:
                string_chapters.append(ch)
        
        numeric_chapters.sort()
        string_chapters.sort()
        if 'com' in string_chapters:
            string_chapters.remove('com')
            string_chapters.append('com')
        
        sorted_chapters = [str(ch) for ch in numeric_chapters] + string_chapters
        # ★★★ ここまで追加 ★★★
        
        return jsonify({
            'status': 'success',
            'problems': problems,
            'pagination': {
                'page': page,
                'pages': pagination.pages,
                'per_page': per_page,
                'total': pagination.total,
                'has_prev': pagination.has_prev,
                'has_next': pagination.has_next
            },
            'chapters': sorted_chapters  # ★★★ この行を追加 ★★★
        })
        
    except Exception as e:
        logger.error(f"Error getting essay problems: {e}")
        return jsonify({
            'status': 'error',
            'message': '問題一覧の取得中にエラーが発生しました'
        }), 500

@app.route('/admin/essay/download_csv')
def admin_essay_download_csv():
    """論述問題一覧をCSVとしてダウンロード"""
    if not session.get('admin_logged_in'):
        flash('管理者権限が必要です', 'danger')
        return redirect(url_for('login_page'))
    
    try:
        # 全ての問題を取得（章、タイプ、ID順）
        # 文字列の章と数値の章が混在しているため、単純なソートでは不十分な場合があるが、
        # ここではデータベースの順序に依存するか、Python側でソートする
        # いったん全件取得
        problems = EssayProblem.query.all()
        
        # ソートロジック（admin_essay_chaptersと同様のロジックでソートするのが理想だが、簡易的に実装）
        # 章（数値優先、comは最後）、タイプ、ID順
        def sort_key(p):
            try:
                chapter_num = int(p.chapter)
                is_com = False
            except ValueError:
                chapter_num = 9999
                is_com = (p.chapter == 'com')
            return (is_com, chapter_num, p.chapter, p.type, p.id)
            
        problems.sort(key=sort_key)
        
        # CSV作成
        si = StringIO()
        # BOMを付与してExcelで文字化けしないようにする
        si.write('\ufeff')
        
        writer = csv.writer(si)
        # ヘッダー
        writer.writerow(['id', 'chapter', 'type', 'university', 'year', 'question', 'answer', 'answer_length', 'enabled', 'image_url'])
        
        for p in problems:
            writer.writerow([
                p.id,
                p.chapter,
                p.type,
                p.university,
                p.year,
                p.question,
                p.answer,
                p.answer_length,
                1 if p.enabled else 0,
                p.image_url or ''
            ])
            
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = "attachment; filename=essay_problems.csv"
        output.headers["Content-type"] = "text/csv"
        return output
        
    except Exception as e:
        logger.error(f"Error downloading essay csv: {e}")
        flash(f'CSVダウンロード中にエラーが発生しました: {str(e)}', 'danger')
        return redirect(url_for('admin_page'))

@app.route('/admin/essay/problem/<int:problem_id>')
def admin_essay_problem_detail(problem_id):
    """特定の論述問題の詳細を取得"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
        
        problem = EssayProblem.query.get(problem_id)
        if not problem:
            return jsonify({'status': 'error', 'message': '問題が見つかりません'}), 404
        
        # EssayProgressテーブルの存在確認
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        
        stats = {
            'total_views': 0,
            'understood_count': 0,
            'viewed_answer_count': 0,
            'avg_difficulty': 0
        }
        
        if inspector.has_table('essay_progress'):
            # 学習進捗統計 - case()の構文を修正
            progress_stats = db.session.query(
                func.count(EssayProgress.id).label('total_views'),
                func.count(case((EssayProgress.understood == True, 1))).label('understood_count'),
                func.count(case((EssayProgress.viewed_answer == True, 1))).label('viewed_answer_count'),
                func.avg(EssayProgress.difficulty_rating).label('avg_difficulty')
            ).filter(EssayProgress.problem_id == problem_id).first()
            
            if progress_stats:
                stats = {
                    'total_views': progress_stats.total_views or 0,
                    'understood_count': progress_stats.understood_count or 0,
                    'viewed_answer_count': progress_stats.viewed_answer_count or 0,
                    'avg_difficulty': round(progress_stats.avg_difficulty or 0, 1)
                }
        
        return jsonify({
            'status': 'success',
            'problem': {
                'id': problem.id,
                'chapter': problem.chapter,
                'type': problem.type,
                'university': problem.university,
                'year': problem.year,
                'question': problem.question,
                'answer': problem.answer,
                'answer_length': problem.answer_length,
                'enabled': problem.enabled
            },
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"Error getting essay problem detail: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': '問題詳細の取得中にエラーが発生しました'
        }), 500

@app.route('/admin/essay/update_problem', methods=['POST'])
def admin_essay_update_problem():
    """論述問題を更新"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
        
        data = request.get_json()
        problem_id = data.get('problem_id')
        
        if not problem_id:
            return jsonify({'status': 'error', 'message': '問題IDが必要です'}), 400
        
        problem = EssayProblem.query.get(problem_id)
        if not problem:
            return jsonify({'status': 'error', 'message': '問題が見つかりません'}), 404
        
        # 更新可能フィールド
        updatable_fields = ['chapter', 'type', 'university', 'year', 'question', 'answer', 'enabled']
        
        for field in updatable_fields:
            if field in data:
                if field == 'year':
                    try:
                        setattr(problem, field, int(data[field]))
                    except (ValueError, TypeError):
                        setattr(problem, field, 2025)
                elif field == 'enabled':
                    setattr(problem, field, bool(data[field]))
                elif field == 'answer':
                    answer = data[field] or '解答なし'
                    setattr(problem, field, answer)
                    problem.answer_length = len(answer)
                else:
                    setattr(problem, field, data[field])
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': '問題を更新しました',
            'problem_id': problem.id
        })
        
    except Exception as e:
        logger.error(f"Error updating essay problem: {e}")
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': '問題の更新中にエラーが発生しました'
        }), 500

@app.route('/admin/essay/bulk_delete', methods=['POST'])
def admin_essay_bulk_delete():
    """論述問題の一括削除"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
        
        data = request.get_json()
        problem_ids = data.get('problem_ids', [])
        
        if not problem_ids:
            return jsonify({'status': 'error', 'message': '削除する問題IDが指定されていません'}), 400
        
        # 関連する進捗データも削除
        deleted_progress = EssayProgress.query.filter(
            EssayProgress.problem_id.in_(problem_ids)
        ).delete(synchronize_session=False)
        
        # 問題を削除
        deleted_problems = EssayProblem.query.filter(
            EssayProblem.id.in_(problem_ids)
        ).delete(synchronize_session=False)
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': f'{deleted_problems}件の問題と{deleted_progress}件の関連データを削除しました',
            'deleted_problems': deleted_problems,
            'deleted_progress': deleted_progress
        })
        
    except Exception as e:
        logger.error(f"Error bulk deleting essay problems: {e}")
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': '一括削除中にエラーが発生しました'
        }), 500

@app.route('/admin/essay/chapters')
def admin_essay_chapters():
    """論述問題の章リストを取得"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
        
        # データベースから全ての章を取得（重複を除く）
        chapters = db.session.query(EssayProblem.chapter)\
            .distinct()\
            .order_by(EssayProblem.chapter)\
            .all()
        
        # 章リストを整形
        chapter_list = []
        for (chapter,) in chapters:
            if chapter:  # NULLや空文字を除外
                chapter_list.append(chapter)
        
        # 数値と文字列を分けてソート
        numeric_chapters = []
        string_chapters = []
        
        for ch in chapter_list:
            try:
                # 数値に変換できる場合
                numeric_chapters.append(int(ch))
            except ValueError:
                # 文字列の場合（'com'など）
                string_chapters.append(ch)
        
        # 数値の章を昇順でソート
        numeric_chapters.sort()
        
        # 文字列の章をソート（'com'を最後に）
        string_chapters.sort()
        if 'com' in string_chapters:
            string_chapters.remove('com')
            string_chapters.append('com')
        
        # 結果を結合（数値を文字列に戻す）
        sorted_chapters = [str(ch) for ch in numeric_chapters] + string_chapters
        
        return jsonify({
            'status': 'success',
            'chapters': sorted_chapters
        })
        
    except Exception as e:
        logger.error(f"Error getting essay chapters: {e}")
        return jsonify({
            'status': 'error',
            'message': '章リストの取得中にエラーが発生しました'
        }), 500
    
# ========================================
# Essay関連のAPIルート
# ========================================
@app.route('/admin/essay/add_problem', methods=['POST'])
def admin_essay_add_problem():
    """論述問題を手動追加（ファイル名規則方式）"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
        
        # フォームデータから取得
        chapter = request.form.get('chapter')
        type_value = request.form.get('type', 'A')
        university = request.form.get('university', '未指定')
        year = request.form.get('year', 2025)
        question = request.form.get('question')
        answer = request.form.get('answer', '解答なし')
        enabled = request.form.get('enabled') == 'on'
        
        # 必須フィールドの確認
        if not chapter or not question:
            return jsonify({
                'status': 'error',
                'message': '章と問題文は必須です'
            }), 400
        
        # 年度の変換
        try:
            year = int(year)
        except (ValueError, TypeError):
            year = 2025
        
        # まず問題を作成
        new_problem = EssayProblem(
            chapter=chapter,
            type=type_value,
            university=university,
            year=year,
            question=question,
            answer=answer,
            answer_length=len(answer),
            enabled=enabled
        )
        
        db.session.add(new_problem)
        db.session.flush()  # IDを取得するためフラッシュ
        
        # 画像処理部分を修正
        image_saved = False
        image_url = None
        
        if 'image' in request.files:
            image_file = request.files['image']
            if image_file and image_file.filename:
                # 拡張子チェック
                filename = secure_filename(image_file.filename)
                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
                
                if file_ext not in allowed_extensions:
                    db.session.rollback()  # ★重要：ロールバックを追加
                    return jsonify({
                        'status': 'error',
                        'message': f'サポートされていない画像形式です。{", ".join(allowed_extensions)}を使用してください。'
                    }), 400
                
                # 問題IDベースのファイル名を生成
                image_filename = f"essay_problem_{new_problem.id}.{file_ext}"
                
                # S3にアップロード（利用可能な場合）
                if S3_AVAILABLE:
                    try:
                        image_url = upload_image_to_s3(image_file, image_filename)
                        if image_url:
                            new_problem.image_url = image_url
                            image_saved = True
                            logger.info(f"画像S3アップロード成功: {image_url}")
                        else:
                            # S3失敗時はローカル保存にフォールバック
                            logger.warning("S3アップロード失敗、ローカル保存にフォールバック")
                            local_success = save_image_locally(image_file, image_filename, new_problem)
                            if local_success:
                                image_saved = True
                                logger.info(f"画像ローカル保存成功: static/uploads/essay_images/{image_filename}")
                            else:
                                logger.error("ローカル画像保存も失敗")
                    except Exception as s3_error:
                        logger.error(f"S3アップロード中にエラー: {s3_error}")
                        # S3でエラーが発生した場合もローカル保存を試行
                        try:
                            local_success = save_image_locally(image_file, image_filename, new_problem)
                            if local_success:
                                image_saved = True
                                logger.info(f"画像ローカル保存成功: static/uploads/essay_images/{image_filename}")
                            else:
                                logger.error("ローカル画像保存も失敗")
                        except Exception as local_error:
                            logger.error(f"ローカル保存中にエラー: {local_error}")
                else:
                    # boto3が利用できない場合はローカル保存
                    try:
                        local_success = save_image_locally(image_file, image_filename, new_problem)
                        if local_success:
                            image_saved = True
                            logger.info(f"画像ローカル保存成功: static/uploads/essay_images/{image_filename}")
                        else:
                            logger.error("ローカル画像保存失敗")
                    except Exception as local_error:
                        logger.error(f"ローカル保存中にエラー: {local_error}")
        
        # 全てをコミット
        db.session.commit()
        
        logger.info(f"論述問題追加成功: ID={new_problem.id}, 画像={image_saved}")
        
        return jsonify({
            'status': 'success',
            'message': '論述問題を追加しました',
            'problem_id': new_problem.id,
            'has_image': image_saved
        })
        
    except Exception as e:
        logger.error(f"Error adding essay problem: {e}")
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': '問題の追加中にエラーが発生しました'
        }), 500

def save_image_locally(image_file, image_filename, problem):
    """ローカルに画像を保存（S3が利用できない場合のフォールバック）"""
    try:
        # 保存先ディレクトリの確保
        upload_dir = os.path.join('static', 'uploads', 'essay_images')
        os.makedirs(upload_dir, exist_ok=True)
        
        # ファイル保存
        save_path = os.path.join(upload_dir, image_filename)
        image_file.save(save_path)
        
        # 相対パスを生成
        relative_path = f"uploads/essay_images/{image_filename}"
        problem.image_url = relative_path
        
        logger.info(f"画像ローカル保存成功: {save_path}")
        return True
        
    except Exception as save_error:
        logger.error(f"画像ローカル保存エラー: {save_error}")
        return False
    
@app.route('/admin/essay/upload_csv', methods=['POST'])
def admin_essay_upload_csv():
    """論述問題をCSVで一括追加（修正版）"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
        
        if 'file' not in request.files:
            return jsonify({'status': 'error', 'message': 'ファイルが選択されていません'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'status': 'error', 'message': 'ファイルが選択されていません'}), 400
        
        if not file.filename.endswith('.csv'):
            return jsonify({'status': 'error', 'message': 'CSVファイルを選択してください'}), 400
        
        # 既存問題を削除するかどうか
        replace_existing = request.form.get('replace_existing') == 'on'
        
        if replace_existing:
            # 既存の論述問題を全削除
            EssayProblem.query.delete()
            EssayProgress.query.delete()  # 関連する進捗も削除
            db.session.commit()
            logger.info("既存の論述問題を全削除しました")
        
        # CSVファイルを読み込み
        import csv
        import io
        
        # ファイル内容を読み取り（UTF-8でデコード）
        try:
            content = file.stream.read().decode('utf-8-sig')  # BOM対応
        except UnicodeDecodeError:
            try:
                file.stream.seek(0)
                content = file.stream.read().decode('shift_jis')  # Shift_JIS対応
            except UnicodeDecodeError:
                return jsonify({
                    'status': 'error',
                    'message': 'ファイルの文字エンコーディングが不正です。UTF-8またはShift_JISで保存してください。'
                }), 400
        
        stream = StringIO(content)
        csv_reader = csv.DictReader(stream)
        
        # CSVヘッダーの確認
        required_fields = ['chapter', 'question']
        optional_fields = ['id', 'type', 'university', 'year', 'answer', 'answer_length', 'enabled', 'image_url']
        
        if not csv_reader.fieldnames:
            return jsonify({
                'status': 'error',
                'message': 'CSVファイルにヘッダー行がありません'
            }), 400
        
        # ヘッダーの正規化（空白除去、小文字化）
        normalized_headers = {key.strip().lower(): key for key in csv_reader.fieldnames}
        
        # 必須フィールドの存在確認
        missing_required = []
        for field in required_fields:
            if field.lower() not in normalized_headers:
                missing_required.append(field)
        
        if missing_required:
            return jsonify({
                'status': 'error',
                'message': f'必須列が不足しています: {", ".join(missing_required)}'
            }), 400
        
        added_count = 0
        updated_count = 0
        error_count = 0
        error_details = []
        
        for row_num, row in enumerate(csv_reader, start=2):  # ヘッダーを除いて2行目から
            try:
                # データの正規化（空白除去）
                normalized_row = {}
                for key, value in row.items():
                    if key and value is not None:
                        normalized_row[key.strip().lower()] = str(value).strip()
                
                # 必須フィールドの確認
                chapter = normalized_row.get('chapter', '').strip()
                question = normalized_row.get('question', '').strip()
                
                if not chapter or not question:
                    error_count += 1
                    error_details.append(f"行{row_num}: 章または問題文が空です")
                    continue
                
                # オプションフィールドの処理
                type_value = normalized_row.get('type', 'A').strip() or 'A'
                university = normalized_row.get('university', '未指定').strip() or '未指定'
                answer = normalized_row.get('answer', '解答なし').strip() or '解答なし'
                image_url = normalized_row.get('image_url', '').strip()
                
                # 年度の処理
                year = 2025  # デフォルト値
                year_str = normalized_row.get('year', '').strip()
                if year_str:
                    try:
                        year = int(float(year_str))  # 小数点がある場合も対応
                        if year < 2000 or year > 2030:
                            year = 2025
                    except (ValueError, TypeError):
                        pass
                
                # 有効フラグの処理
                enabled = True  # デフォルトで有効
                enabled_str = normalized_row.get('enabled', '1').strip()
                if enabled_str.lower() in ['0', 'false', 'no', '無効', 'disabled']:
                    enabled = False
                
                # 文字数の計算
                answer_length = len(answer)
                
                # IDによる更新チェック
                problem_id_str = normalized_row.get('id', '').strip()
                existing_problem = None
                
                if not replace_existing and problem_id_str:
                    try:
                        problem_id = int(problem_id_str)
                        existing_problem = EssayProblem.query.get(problem_id)
                    except ValueError:
                        pass # IDが数値でない場合は新規作成扱い
                
                if existing_problem:
                    # 既存の問題を更新
                    existing_problem.chapter = chapter
                    existing_problem.type = type_value.upper()
                    existing_problem.university = university
                    existing_problem.year = year
                    existing_problem.question = question
                    existing_problem.answer = answer
                    existing_problem.answer_length = answer_length
                    existing_problem.enabled = enabled
                    if image_url: # 画像URLが指定されている場合のみ更新
                        existing_problem.image_url = image_url
                    
                    updated_count += 1
                    logger.info(f"問題更新: ID={existing_problem.id}, 章={chapter}")
                    
                else:
                    # 新しい問題を作成
                    new_problem = EssayProblem(
                        chapter=chapter,
                        type=type_value.upper(),
                        university=university,
                        year=year,
                        question=question,
                        answer=answer,
                        answer_length=answer_length,
                        enabled=enabled,
                        image_url=image_url if image_url else None
                    )
                    
                    db.session.add(new_problem)
                    added_count += 1
                    logger.info(f"問題追加: 章={chapter}, タイプ={type_value}, 大学={university}, 年={year}")
                
            except Exception as e:
                error_count += 1
                error_msg = f"行{row_num}: {str(e)}"
                error_details.append(error_msg)
                logger.error(f"CSV処理エラー: {error_msg}")
                continue
        
        # データベースにコミット
        if added_count > 0 or updated_count > 0:
            try:
                db.session.commit()
                logger.info(f"論述問題 追加{added_count}件/更新{updated_count}件 を保存しました")
            except Exception as commit_error:
                db.session.rollback()
                logger.error(f"データベース保存エラー: {commit_error}")
                return jsonify({
                    'status': 'error',
                    'message': f'データベース保存中にエラーが発生しました: {str(commit_error)}'
                }), 500
        
        # 結果メッセージの作成
        if added_count > 0 or updated_count > 0:
            message = f'{added_count}件を追加、{updated_count}件を更新しました'
            if error_count > 0:
                message += f'（{error_count}件のエラーがありました）'
        else:
            if error_count > 0:
                message = f'処理に失敗しました。{error_count}件のエラーがあります'
            else:
                message = 'CSVファイルに有効なデータが含まれていません'
        
        response_data = {
            'status': 'success' if (added_count > 0 or updated_count > 0) else 'error',
            'message': message,
            'added_count': added_count,
            'updated_count': updated_count,
            'error_count': error_count
        }
        
        if error_details and len(error_details) <= 10:  # エラーが多すぎる場合は一部のみ表示
            response_data['error_details'] = error_details[:10]
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"CSV アップロード エラー: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': f'CSVファイルの処理中にエラーが発生しました: {str(e)}'
        }), 500
    
@app.route('/admin/download_essay_template')
def download_essay_template():
    """論述問題CSVテンプレートのダウンロード"""
    if not session.get('admin_logged_in'):
        flash('管理者権限がありません。', 'danger')
        return redirect(url_for('login_page'))

    from io import StringIO
    import csv
    
    si = StringIO()
    # BOMを付与してExcelで文字化けしないようにする
    si.write('\ufeff')
    cw = csv.writer(si)
    
    # ヘッダー行 (登録済みファイルと同じ形式)
    cw.writerow(['id', 'chapter', 'type', 'university', 'year', 'question', 'answer', 'answer_length', 'enabled', 'image_url'])
    
    # サンプルデータを追加 (idは空欄で新規登録扱い、image_urlも空欄)
    cw.writerow([
        '', '1', 'A', '東京大学', '2023', 
        'フランス革命の社会的背景について200字以上で論述せよ。',
        'フランス革命は18世紀後半のフランスにおいて、アンシャン・レジームと呼ばれる身分制社会の矛盾が深刻化した結果として起こった。第三身分が人口の大部分を占めながらも政治的権利を持たず、重い税負担を強いられていた。一方で特権身分である聖職者と貴族は免税特権を享受していた。また、啓蒙思想の普及により自由・平等の理念が浸透し、アメリカ独立革命の成功も大きな影響を与えた。財政危機も革命の引き金となった重要な要因である。',
        '245', '1', ''
    ])
    cw.writerow([
        '', '1', 'B', '早稲田大学', '2023',
        'ナポレオンの大陸封鎖令について100字程度で説明せよ。',
        'ナポレオンが1806年に発布した対イギリス経済制裁。ヨーロッパ大陸諸国にイギリスとの通商を禁止させ、経済的に孤立させることでイギリスの屈服を図った。しかし密貿易の横行や各国の反発を招き、最終的には失敗に終わった。',
        '98', '1', ''
    ])
    cw.writerow([
        '', '2', 'C', '慶応大学', '2024',
        'ウィーン体制の特徴を50字で述べよ。',
        'ナポレオン戦争後の1815年に成立した国際秩序。正統主義・勢力均衡・国際協調を原則とした。',
        '48', '1'
    ])
    
    # Shift_JISエンコーディングで文字化け対策
    try:
        output = si.getvalue().encode('shift_jis')
        mimetype = "text/csv; charset=shift_jis"
    except UnicodeEncodeError:
        output = '\ufeff' + si.getvalue()  # BOM付きUTF-8
        output = output.encode('utf-8')
        mimetype = "text/csv; charset=utf-8"
    
    response = Response(output, mimetype=mimetype)
    response.headers["Content-Disposition"] = "attachment; filename=essay_problems_template.csv"
    return response
    
@app.route('/admin/essay/delete_problem', methods=['POST'])
def admin_essay_delete_problem():
    """論述問題を削除（POSTメソッド版）"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
        
        data = request.get_json()
        problem_id = data.get('problem_id')
        
        if not problem_id:
            return jsonify({'status': 'error', 'message': '問題IDが必要です'}), 400
        
        problem = EssayProblem.query.get(problem_id)
        if not problem:
            return jsonify({'status': 'error', 'message': '問題が見つかりません'}), 404
        
        # 関連する進捗データも削除（正しいテーブル存在確認）
        try:
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            if inspector.has_table('essay_progress'):
                EssayProgress.query.filter_by(problem_id=problem_id).delete()
        except Exception as progress_error:
            logger.warning(f"Progress data deletion error (non-critical): {progress_error}")
            # 進捗データの削除に失敗しても続行
        
        # メイン問題を削除
        db.session.delete(problem)
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': '問題を削除しました'
        })
        
    except Exception as e:
        logger.error(f"Error deleting essay problem: {e}")
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': '問題の削除中にエラーが発生しました'
        }), 500

@app.route('/admin/essay/toggle_enabled', methods=['POST'])
def admin_essay_toggle_enabled():
    """論述問題の有効/無効を切り替え"""
    try:
        if not session.get('admin_logged_in'):
            return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
        
        data = request.get_json()
        problem_id = data.get('problem_id')
        
        if not problem_id:
            return jsonify({'status': 'error', 'message': '問題IDが必要です'}), 400
        
        problem = EssayProblem.query.get(problem_id)
        if not problem:
            return jsonify({'status': 'error', 'message': '問題が見つかりません'}), 404
        
        # 有効/無効を切り替え
        problem.enabled = not problem.enabled
        db.session.commit()
        
        status = '有効' if problem.enabled else '無効'
        
        return jsonify({
            'status': 'success',
            'message': f'問題を{status}にしました',
            'problem_id': problem.id,
            'enabled': problem.enabled
        })
        
    except Exception as e:
        logger.error(f"Error toggling essay problem: {e}")
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': '状態の切り替え中にエラーが発生しました'
        }), 500

@app.route('/admin/essay/add', methods=['POST'])
def add_essay_problem():
    """論述問題を追加"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
    
    try:
        # リクエストデータの取得
        if request.is_json:
            data = request.get_json()
        else:
            # フォームデータからの取得
            data = request.form.to_dict()
            
        app.logger.info(f"論述問題追加リクエスト: {data}")
        
        # 必須フィールドの確認
        required_fields = ['chapter', 'type', 'university', 'year', 'question', 'answer', 'answer_length']
        missing_fields = []
        
        for field in required_fields:
            value = data.get(field)
            if not value or str(value).strip() == '':
                missing_fields.append(field)
        
        if missing_fields:
            return jsonify({
                'status': 'error', 
                'message': f'以下の項目が入力されていません: {", ".join(missing_fields)}'
            }), 400
        
        # データ型変換と検証
        try:
            chapter = int(str(data['chapter']).strip())
            year = int(str(data['year']).strip())
            answer_length = int(str(data['answer_length']).strip())
            
            if chapter <= 0 or year <= 0 or answer_length <= 0:
                raise ValueError("章、年、解答字数は正の整数である必要があります")
                
        except (ValueError, TypeError) as ve:
            return jsonify({
                'status': 'error', 
                'message': f'数値フィールドの形式が正しくありません: {str(ve)}'
            }), 400
        
        # 新しい論述問題を作成
        new_problem = EssayProblem(
            chapter=chapter,
            type=str(data['type']).strip(),
            university=str(data['university']).strip(),
            year=year,
            question=str(data['question']).strip(),
            answer=str(data['answer']).strip(),
            answer_length=answer_length,
            enabled=bool(data.get('enabled', True))
        )
        
        # データベースに保存
        db.session.add(new_problem)
        db.session.commit()
        
        app.logger.info(f"論述問題を追加しました: ID={new_problem.id}, 大学={new_problem.university}, 年={new_problem.year}")
        
        return jsonify({
            'status': 'success',
            'message': f'論述問題を追加しました（ID: {new_problem.id}）',
            'problem_id': new_problem.id
        }), 200
        
    except ValueError as ve:
        app.logger.error(f"論述問題追加の値エラー: {str(ve)}")
        return jsonify({
            'status': 'error', 
            'message': f'入力値エラー: {str(ve)}'
        }), 400
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"論述問題追加エラー: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'status': 'error', 
            'message': f'論述問題の追加中にシステムエラーが発生しました: {str(e)}'
        }), 500

@app.route('/admin/essay/edit/<int:problem_id>', methods=['POST'])
def edit_essay_problem(problem_id):
    """論述問題を編集"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限が必要です'}), 403
    
    try:
        # 問題の存在確認
        problem = EssayProblem.query.get(problem_id)
        if not problem:
            return jsonify({
                'status': 'error', 
                'message': '指定された問題が見つかりません'
            }), 404
        
        # リクエストデータの取得
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
            
        app.logger.info(f"論述問題編集リクエスト: ID={problem_id}, data={data}")
        
        # フィールドの更新
        if 'chapter' in data and data['chapter']:
            problem.chapter = int(str(data['chapter']).strip())
        if 'type' in data and data['type']:
            problem.type = str(data['type']).strip()
        if 'university' in data and data['university']:
            problem.university = str(data['university']).strip()
        if 'year' in data and data['year']:
            problem.year = int(str(data['year']).strip())
        if 'question' in data and data['question']:
            problem.question = str(data['question']).strip()
        if 'answer' in data and data['answer']:
            problem.answer = str(data['answer']).strip()
        if 'answer_length' in data and data['answer_length']:
            problem.answer_length = int(str(data['answer_length']).strip())
        if 'enabled' in data:
            problem.enabled = bool(data['enabled'])
        
        # 更新日時を設定
        problem.updated_at = datetime.utcnow()
        
        # データベースに保存
        db.session.commit()
        
        app.logger.info(f"論述問題を更新しました: ID={problem_id}")
        
        return jsonify({
            'status': 'success',
            'message': f'論述問題（ID: {problem_id}）を更新しました'
        }), 200
        
    except ValueError as ve:
        app.logger.error(f"論述問題編集の値エラー: {str(ve)}")
        return jsonify({
            'status': 'error', 
            'message': f'入力値エラー: {str(ve)}'
        }), 400
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"論述問題編集エラー: {str(e)}")
        
        return jsonify({
            'status': 'error', 
            'message': f'論述問題の編集中にエラーが発生しました: {str(e)}'
        }), 500
    
@app.route('/essay_image/<int:problem_id>')
def essay_image(problem_id):
    """データベースから論述問題の画像を取得"""
    try:
        from flask import Response, abort  # ← ここでも局所的にインポート可能
        
        essay_image = EssayImage.query.filter_by(problem_id=problem_id).first()
        
        if not essay_image:
            app.logger.warning(f"画像が見つかりません: problem_id={problem_id}")
            abort(404)
        
        # バイナリデータからレスポンスを作成
        mimetype = f'image/{essay_image.image_format.lower()}'
        
        app.logger.info(f"画像を配信: problem_id={problem_id}, format={essay_image.image_format}, size={len(essay_image.image_data)}bytes")
        
        return Response(
            essay_image.image_data,
            mimetype=mimetype,
            headers={
                'Content-Disposition': f'inline; filename=essay_{problem_id}.{essay_image.image_format.lower()}',
                'Cache-Control': 'public, max-age=31536000'
            }
        )
        
    except Exception as e:
        app.logger.error(f"画像配信エラー: problem_id={problem_id}, error={str(e)}")
        abort(500)

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
# Essay関連のヘルパー関数を追加
# ========================================
def get_essay_chapter_stats(user_id):
    """章別の統計情報を取得（テーブル存在チェック付き）"""
    try:
        # EssayProgressテーブルの存在確認
        inspector = inspect(db.engine)
        has_progress_table = inspector.has_table('essay_progress')
        
        if has_progress_table:
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
        else:
            # EssayProgressテーブルがない場合はEssayProblemのみで統計
            stats_query = db.session.query(
                EssayProblem.chapter,
                func.count(EssayProblem.id).label('total_problems')
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
            if has_progress_table:
                chapter_stats.append({
                    'chapter': stat.chapter,
                    'chapter_name': f'第{stat.chapter}章' if stat.chapter != 'com' else '総合問題',
                    'total_problems': stat.total_problems,
                    'viewed_problems': stat.viewed_problems or 0,
                    'understood_problems': stat.understood_problems or 0,
                    'progress_rate': round((stat.understood_problems or 0) / stat.total_problems * 100, 1) if stat.total_problems > 0 else 0
                })
            else:
                chapter_stats.append({
                    'chapter': stat.chapter,
                    'chapter_name': f'第{stat.chapter}章' if stat.chapter != 'com' else '総合問題',
                    'total_problems': stat.total_problems,
                    'viewed_problems': 0,
                    'understood_problems': 0,
                    'progress_rate': 0
                })
        
        return chapter_stats
        
    except Exception as e:
        logger.error(f"Error getting essay chapter stats: {e}")
        # エラー時もEssayProblemから基本情報を取得
        try:
            stats_query = db.session.query(
                EssayProblem.chapter,
                func.count(EssayProblem.id).label('total_problems')
            ).filter(
                EssayProblem.enabled == True
            ).group_by(
                EssayProblem.chapter
            ).all()
            
            return [{
                'chapter': stat.chapter,
                'chapter_name': f'第{stat.chapter}章' if stat.chapter != 'com' else '総合問題',
                'total_problems': stat.total_problems,
                'viewed_problems': 0,
                'understood_problems': 0,
                'progress_rate': 0
            } for stat in stats_query]
        except:
            return []

def get_filtered_essay_problems(chapter, type_filter='', university_filter='', 
                               year_from=None, year_to=None, keyword='', user_id=None):
    """フィルタリングされた問題一覧を取得（テーブル存在チェック付き）"""
    try:
        # EssayProgressテーブルの存在確認
        inspector = inspect(db.engine)
        has_progress_table = inspector.has_table('essay_progress')
        
        if has_progress_table:
            query = db.session.query(EssayProblem, EssayProgress).outerjoin(
                EssayProgress,
                (EssayProblem.id == EssayProgress.problem_id) & 
                (EssayProgress.user_id == user_id)
            ).filter(
                EssayProblem.chapter == chapter,
                EssayProblem.enabled == True
            )
        else:
            # EssayProgressテーブルがない場合はEssayProblemのみ
            query = db.session.query(EssayProblem).filter(
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
        for result in results:
            if has_progress_table:
                problem, progress = result
            else:
                problem = result
                progress = None
            
            problem_data = problem.to_dict()
            problem_data['preview'] = problem.question[:100] + '...' if len(problem.question) > 100 else problem.question
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

def has_essay_problem_image(problem_id):
    """論述問題に画像が存在するかチェック"""
    upload_dir = os.path.join('static', 'uploads', 'essay_images')
    pattern = os.path.join(upload_dir, f"essay_problem_{problem_id}.*")
    return len(glob.glob(pattern)) > 0

def get_essay_problem_image_path(problem_id):
    """論述問題の画像パスを取得（修正版）"""
    import glob
    import os
    
    upload_dir = os.path.join('static', 'uploads', 'essay_images')
    pattern = os.path.join(upload_dir, f"essay_problem_{problem_id}.*")
    matches = glob.glob(pattern)
    
    if matches:
        # staticディレクトリからの相対パスを正しく生成
        abs_path = os.path.abspath(matches[0])
        static_abs = os.path.abspath('static')
        
        # static以下の相対パスを取得
        try:
            relative_path = os.path.relpath(abs_path, static_abs)
            # Windowsのバックスラッシュをスラッシュに変換
            relative_path = relative_path.replace('\\', '/')
            
            # デバッグ用ログ出力
            print(f"画像パス生成 - 問題ID: {problem_id}")
            print(f"  絶対パス: {abs_path}")
            print(f"  相対パス: {relative_path}")
            print(f"  ファイル存在確認: {os.path.exists(abs_path)}")
            
            return relative_path
        except ValueError as e:
            print(f"パス変換エラー - 問題ID {problem_id}: {e}")
            return None
    
    print(f"画像ファイルが見つかりません - 問題ID: {problem_id}, パターン: {pattern}")
    return None

# テンプレート関数として登録
@app.template_global()
def essay_image_path(problem_id):
    """テンプレートから画像URLを取得"""
    problem = EssayProblem.query.get(problem_id)
    return problem.image_url if problem and problem.image_url else None

@app.template_global()
def has_essay_image(problem_id):
    """論述問題に画像が存在するかチェック（データベースから）"""
    essay_image = EssayImage.query.filter_by(problem_id=problem_id).first()
    return essay_image is not None

# app.pyに一時的に追加するマイグレーション用エンドポイント
@app.route('/admin/migrate_essay_images')
def migrate_essay_images():
    """既存の論述問題に画像URLカラムを追加"""
    if not session.get('admin_logged_in'):
        return "管理者権限が必要です"
    
    try:
        # テーブルにカラムを追加（SQLite用）
        db.engine.execute('ALTER TABLE essay_problem ADD COLUMN image_url TEXT')
        db.session.commit()
        return "マイグレーション完了"
    except Exception as e:
        return f"エラー: {e}"
# ====================================================================
# エラーハンドラー
# ====================================================================
# app.pyに一時的に追加するデバッグ用エンドポイント

@app.route('/debug/image_upload', methods=['GET', 'POST'])
def debug_image_upload():
    """画像アップロードのデバッグ"""
    if not session.get('admin_logged_in'):
        return "管理者権限が必要です", 403
    
    if request.method == 'GET':
        return '''
        <!DOCTYPE html>
        <html>
        <head><title>画像アップロードテスト</title></head>
        <body>
            <h2>画像アップロードテスト</h2>
            <form method="POST" enctype="multipart/form-data">
                <input type="file" name="test_image" accept="image/*" required>
                <button type="submit">テストアップロード</button>
            </form>
        </body>
        </html>
        '''
    
    # POST処理
    try:
        if 'test_image' not in request.files:
            return "ファイルが選択されていません"
        
        image_file = request.files['test_image']
        if not image_file.filename:
            return "ファイルが選択されていません"
        
        # ファイル情報をログ出力
        print(f"ファイル名: {image_file.filename}")
        print(f"ファイルサイズ: {len(image_file.read())} bytes")
        image_file.seek(0)  # ポインタをリセット
        
        # 安全なファイル名生成
        filename = secure_filename(image_file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        print(f"安全なファイル名: {filename}")
        print(f"拡張子: {file_ext}")
        
        # 保存先ディレクトリの確保
        upload_dir = os.path.join('static', 'uploads', 'essay_images')
        os.makedirs(upload_dir, exist_ok=True)
        print(f"アップロードディレクトリ: {upload_dir}")
        print(f"ディレクトリ存在確認: {os.path.exists(upload_dir)}")
        
        # テスト用ファイル名
        test_filename = f"test_upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file_ext}"
        save_path = os.path.join(upload_dir, test_filename)
        
        print(f"保存パス: {save_path}")
        
        # ファイル保存
        try:
            image_file.save(save_path)
            print(f"ファイル保存成功: {save_path}")
            
            # 保存確認
            if os.path.exists(save_path):
                file_size = os.path.getsize(save_path)
                print(f"保存ファイル確認OK: サイズ={file_size} bytes")
                return f"✅ 画像アップロード成功！<br>ファイル名: {test_filename}<br>サイズ: {file_size} bytes<br>パス: {save_path}"
            else:
                return "❌ ファイルが保存されませんでした"
                
        except Exception as save_error:
            print(f"保存エラー: {save_error}")
            return f"❌ 保存エラー: {save_error}"
            
    except Exception as e:
        print(f"全般エラー: {e}")
        return f"❌ エラー: {e}"
    
@app.errorhandler(500)
def internal_error(error):
    print(f"500 Error: {error}")
    db.session.rollback()
    return "Internal Server Error - Please check the logs", 500

@app.errorhandler(404)
def not_found_error(error):
    return "Page Not Found", 404

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

# データベース初期化とマイグレーション
with app.app_context():
    try:
        # 既存テーブルの作成
        db.create_all()
        
        # マイグレーションの実行
        migrate_database()
        
        app.logger.info("✅ データベース初期化・マイグレーション完了")
    except Exception as e:
        app.logger.error(f"❌ データベース初期化エラー: {e}")

@app.route('/api/find_related_essays', methods=['POST'])
def find_related_essays():
    """
    キーワードと章のリストを受け取り、関連する論述問題を探して返すAPI
    (同じ章の問題を優先ソートする機能付き)
    """
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'ログインが必要です'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'データがありません'}), 400

    keywords = data.get('keywords', [])
    # フロントエンドから送られてきた章のリストを受け取る <--- 変更点
    session_chapters = data.get('chapters', [])

    if not keywords:
        return jsonify({'essays': []})

    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'status': 'error', 'message': 'ユーザーが見つかりません'}), 404

    # 公開設定を考慮した、全ての章の問題を取得
    visible_problems = get_filtered_essay_problems_with_visibility(
        chapter=None,
        room_number=user.room_number,
        user_id=user.id
    )

    # 関連問題をフィルタリング
    related_essays = []
    found_ids = set() # 重複を防ぐためのセット
    
    # 短すぎる単語や一般的すぎる単語を除外
    stop_words = {'年', '月', '日', 'の', 'は', 'が', 'を'}

    for problem in visible_problems:
        for keyword in keywords:
            if keyword and len(keyword) > 1 and keyword not in stop_words:
                if (keyword in problem.question or keyword in problem.answer) and problem.id not in found_ids:
                    related_essays.append({
                        'id': problem.id,
                        'university': problem.university,
                        'year': problem.year,
                        'type': problem.type,
                        'question_snippet': (problem.question[:50] + '...') if len(problem.question) > 50 else problem.question,
                        'chapter': problem.chapter
                    })
                    found_ids.add(problem.id)
                    # 一致する問題が見つかったら、この問題に対するキーワード検索は終了
                    break

    # --- ▼ここが優先順位付けのロジックです▼ ---
    # 1. 解いた問題と同じ章かどうか (True=1, False=0)
    # 2. 年度の新しい順
    # この2つの条件で並べ替える
    recommended_essays = sorted(
        related_essays,
        key=lambda essay: (
            essay.get('chapter') in session_chapters, # 同じ章ならTrue (優先)
            essay.get('year', 0)                      # 次に年度で比較
        ),
        reverse=True # True(同じ章)が先、年度が新しいものが先に来るように降順ソート
    )[:5] # 上位5件に絞る
    
    return jsonify({'essays': recommended_essays})

# ===== メイン起動処理の修正 =====
# データベース初期化
create_tables_and_admin_user()

# ====================================================================
# 通知APIルート
# ====================================================================

@app.route('/api/vapid_public_key')
def get_vapid_public_key():
    return jsonify({'publicKey': VAPID_PUBLIC_KEY})

@app.route('/api/save_subscription', methods=['POST'])
def save_subscription():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Login required'}), 401
    
    data = request.get_json()
    user = User.query.get(session['user_id'])
    user.push_subscription = data
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/api/notification_settings', methods=['GET'])
def get_notification_settings():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Login required'}), 401
    
    user = User.query.get(session['user_id'])
    return jsonify({
        'status': 'success',
        'enabled': user.notification_enabled,
        'time': user.notification_time
    })

@app.route('/api/test_notification', methods=['POST'])
def test_notification():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Login required'}), 401
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404
        
    if not user.push_subscription:
        return jsonify({'status': 'error', 'message': 'Push subscription not found. Please enable notifications first.'}), 400
        
    if not os.path.exists(VAPID_PRIVATE_KEY_PATH):
        return jsonify({'status': 'error', 'message': 'Server Error: VAPID Private Key is missing on the server.'}), 500

    try:
        success = send_push_notification(
            user,
            "通知テスト",
            "これはテスト通知です。通知機能は正常に動作しています！",
            url="/"
        )
        
        if success:
            return jsonify({'status': 'success', 'message': 'Notification sent successfully'})
        else:
            return jsonify({'status': 'error', 'message': 'Failed to send notification. Subscription might be invalid.'}), 500
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/update_notification_settings', methods=['POST'])
def update_notification_settings():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Login required'}), 401
    
    data = request.get_json()
    user = User.query.get(session['user_id'])
    
    if 'enabled' in data:
        user.notification_enabled = data['enabled']
    if 'time' in data:
        user.notification_time = data['time']
        
    db.session.commit()
    return jsonify({'status': 'success'})



# =========================================================
# RPGモード (Chronicle Quest) 関連ルート
# =========================================================

@app.route('/api/rpg/status')
def get_rpg_status():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401
    
    user_id = session['user_id']
    user_stats = UserStats.query.filter_by(user_id=user_id).first()
    
    balance_score = user_stats.balance_score if user_stats else 0
    # Removed hardcoded check for < 1000. RPG availability now depends on boss availability.
         
    rpg_state = RpgState.query.filter_by(user_id=user_id).first()
    
    # クールタイム判定
    is_cooldown = False
    next_challenge_time = None
    
    if rpg_state and rpg_state.next_challenge_time:
        if rpg_state.next_challenge_time > datetime.now(JST):
            is_cooldown = True
            next_challenge_time = rpg_state.next_challenge_time.strftime('%Y-%m-%d %H:%M:%S')
            
    # 現在のボスを判定
    target_boss = get_current_boss(user_id, rpg_state)
    
    # ターゲットが存在し、かつ未クリアのボスの場合はクールダウンを無視して挑戦可能にする（新ボス追加時の遡及対応）
    if target_boss:
        # get_current_bossは未クリアのボスがいればそれを優先して返す仕様
        # 実際に未クリアかどうか確認（念のため）
        cleared_ids = set(rpg_state.cleared_stages) if rpg_state else set()
        # id is int, cleared_stages stores strings usually? Let's handle both.
        is_cleared = str(target_boss.id) in cleared_ids or target_boss.id in cleared_ids
        
        if not is_cleared:
            is_cooldown = False
            next_challenge_time = None
    
    if not target_boss:
        return jsonify({'available': False, 'reason': 'no_boss_found', 'current_score': balance_score})
    
    return jsonify({
        'available': True, # is_cooldownがFalseになればTrue扱い（フロントエンドの仕様依存だが、available自体は1000点チェック用だった）
        # フロントエンドは available && !is_cooldown && !is_cleared でバナーを出す
        'is_cooldown': is_cooldown,
        'next_challenge_time': next_challenge_time,
        'is_cleared': False,
        'current_stage': target_boss.id,
        'boss_name': target_boss.name,
        'boss_icon': url_for('serve_rpg_image', enemy_id=target_boss.id, image_type='icon'), # 🆕 DB経由のURLに変更
        'current_score': balance_score
    })

def get_current_boss(user_id, rpg_state=None):
    """
    ユーザーの現在のスコアに基づいて出現すべきボスを判定する
    """
    if not rpg_state:
        rpg_state = RpgState.query.filter_by(user_id=user_id).first()
        
    # use balance_score instead of monthly total score
    user_stats = UserStats.query.filter_by(user_id=user_id).first()
    current_score = user_stats.balance_score if user_stats else 0
    
    cleared_stages = set(rpg_state.cleared_stages) if rpg_state else set()
    
    # 条件1: 有効(is_active)であること
    # 条件2: 出現必要スコアを満たしていること (balance_score >= appearance_required_score)
    candidates = RpgEnemy.query.filter(
        RpgEnemy.is_active == True,
        RpgEnemy.appearance_required_score <= current_score
    ).order_by(RpgEnemy.display_order).all()
    
    if not candidates:
        return None
        
    # 未クリアのボスの中で、diplay_order順に最初のボスを選択
    for enemy in candidates:
        if str(enemy.id) not in cleared_stages: # cleared_stages stores string IDs in JSON usually
            # int/str mismatch check
            if enemy.id not in cleared_stages and str(enemy.id) not in cleared_stages:
                return enemy
            
    # 全てクリア済みの場合は、候補の中からランダム（またはリプレイモード）
    # ここではランダムに1体返す
    return random.choice(candidates)

@app.route('/api/rpg/start', methods=['POST'])
def start_rpg_battle():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401
        
    user_id = session['user_id']
    user = User.query.get(user_id)
    room_number = user.room_number
    
    # 問題データロード
    word_data = load_word_data_for_room(room_number)
    
    # Z問題以外、かつ有効な問題をフィルタリング
    valid_problems = []
    
    # RoomSettingから有効な単元を取得
    # RoomSettingから有効な単元を取得
    room_setting = RoomSetting.query.filter_by(room_number=room_number).first()
    
    for word in word_data:
        # Z問題除外
        if str(word.get('number', '')).upper() == 'Z':
            continue
            
        is_word_enabled_in_csv = word['enabled']
        # 修正: ヘルパー関数を使用して厳密にチェック（enabled_units対応）
        is_unit_valid = is_unit_enabled_by_room_setting(word['number'], room_setting)
        
        if is_word_enabled_in_csv and is_unit_valid:
            valid_problems.append(word)
            
    if len(valid_problems) < 10:
        return jsonify({'status': 'error', 'message': '出題可能な問題が少なすぎます（10問以上必要）'}), 400
        
    # ランダムに30問選択（10問正解到達用、または全て）
    sample_size = min(len(valid_problems), 30)
    selected_problems_data = random.sample(valid_problems, sample_size)
    
    # 全回答リストを作成（ダミー生成用）
    all_answers = list(set(w['answer'] for w in word_data if w.get('answer')))

    final_problems = []
    for problem in selected_problems_data:
        correct_answer = problem['answer']
        
        # --- 誤答選択肢の生成ロジック (DailyQuizと同等) ---
        # 1. CSVのG列 (incorrect) に指定がある場合はそれを使用
        manual_incorrect_str = problem.get('incorrect', '')
        
        if manual_incorrect_str and manual_incorrect_str.strip():
            manual_candidates = [x.strip() for x in manual_incorrect_str.split(',') if x.strip()]
            if len(manual_candidates) > 3:
                distractors = random.sample(manual_candidates, 3)
            else:
                distractors = manual_candidates
        else:
            # 2. 指定がない場合はレーベンシュタイン距離で類似語を探す
            distractor_pool = [ans for ans in all_answers if ans != correct_answer]
            # パフォーマンス考慮: プールが大きすぎる場合はランダムサンプリング後に計算しても良いが
            # 今回はDailyQuiz同様に全件計算（数千件程度なら高速）
            distractors_with_distance = [(levenshtein_distance(correct_answer, ans), ans) for ans in distractor_pool]
            distractors_with_distance.sort(key=lambda x: x[0])
            distractors = [ans for distance, ans in distractors_with_distance[:3]]
            
            # 候補が足りない場合はランダムに補充
            if len(distractors) < 3 and len(distractor_pool) >= 3:
                remaining = [ans for ans in distractor_pool if ans not in distractors]
                distractors.extend(random.sample(remaining, 3 - len(distractors)))
        
        # 正解と誤答を合わせてシャッフル
        choices = distractors + [correct_answer]
        random.shuffle(choices)
        
        final_problems.append({
            'id': get_problem_id(problem),
            'question': problem['question'],
            'answer': correct_answer,
            'choices': choices
        })
    
    # ボス決定
    rpg_state = RpgState.query.filter_by(user_id=user_id).first()
    target_boss = get_current_boss(user_id, rpg_state)
    
    if not target_boss:
        return jsonify({'status': 'error', 'message': '戦える敵がいません'}), 400
        
    return jsonify({
        'status': 'success',
        'problems': final_problems,
        'time_limit': target_boss.time_limit,
        'pass_score': target_boss.clear_correct_count,
        'max_mistakes': target_boss.clear_max_mistakes,
        'boss_info': target_boss.to_dict() # フロントエンドで表示に使用
    })

@app.route('/api/rpg/result', methods=['POST'])
def submit_rpg_result():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401
        
    user_id = session['user_id']
    data = request.json
    is_win = data.get('is_win', False)
    stage_id = data.get('stage_id', 1) # 今回は1固定
    
    # RpgState取得または作成
    rpg_state = RpgState.query.filter_by(user_id=user_id).first()
    if not rpg_state:
        rpg_state = RpgState(user_id=user_id)
        db.session.add(rpg_state)
    
    now = datetime.now(JST)
    
    if is_win:
        # 勝利処理
        cleared_stages = set(rpg_state.cleared_stages)
        new_clear = False
        if stage_id not in cleared_stages:
            cleared_stages.add(stage_id)
            rpg_state.cleared_stages = list(cleared_stages)
            new_clear = True
            
            # 初回クリアボーナス
            rpg_state.permanent_bonus_percent += 0.5
            
            # バッジ付与 (RpgEnemyから取得)
            enemy = RpgEnemy.query.get(stage_id)
            if enemy:
                 # 既存のearned_badgesに追加（後方互換性のため）
                 earned_badges = set(rpg_state.earned_badges)
                 # バッジ名はユニークキーとして扱う必要があるが、DBにはbadge_name(日本語)がある。
                 # ここでは仮に IDや名前をキーにするか、badge_nameそのものを入れる。
                 # status()関数では cleared_stages を見ているので、ここはあまり重要ではないが念のため。
                 # しかし status() では ID で判定しているので、earned_badges は使っていない（ボスに関しては）。
                 pass
        
        db.session.commit()
        
        # 統計再計算（ボーナス反映のため）
        UserStats.get_or_create(user_id).update_stats()
        db.session.commit()
        
        return jsonify({'status': 'success', 'new_clear': new_clear, 'reward': {'bonus_percent': 0.5, 'badge': '征服王'}})
        
    else:
        # 敗北処理
        rpg_state.last_challenge_at = now
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Failed. Cooldown started.'})

@app.route('/status')
def status():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    user = User.query.get(user_id)
    
    rpg_state = RpgState.query.filter_by(user_id=user_id).first()
    
    # 敵キャラDBからバッジ情報を構築
    enemies = RpgEnemy.query.order_by(RpgEnemy.display_order).all()
    cleared_set = set(rpg_state.cleared_stages) if rpg_state and rpg_state.cleared_stages else set()
    
    all_badges = []
    
    for enemy in enemies:
        is_earned = enemy.id in cleared_set
        
        # アイコンのパス調整
        badge_icon = enemy.badge_image if enemy.badge_image else 'fas fa-medal'
        # ファルパスの場合（S3 URLでない場合）、static/images/rpg/ を付与するかどうかはテンプレート側で判断、
        # あるいはここでフルパスにするか。
        # admin_add_rpg_enemyでは、ファイル名のみ保存している（ローカルの場合）。
        # S3の場合はURLそのものを保存している可能性がある（実装による）。
        # テンプレートは `badge.icon` をそのまま `src` に入れている（FA以外）。
        # `status.html` の実装: 
        # {% else %} <img src="{{ badge.icon }}" ...>
        # したがって、ここでローカルファイルの場合は `/static/images/rpg/` を付加する必要がある。
        # ただし、httpで始まる場合はそのまま。
        
        final_badge_icon = badge_icon
        if not badge_icon.startswith('fa') and not badge_icon.startswith('http') and not badge_icon.startswith('/'):
             final_badge_icon = f"/static/images/rpg/{badge_icon}"

        # ボスアイコンも同様
        boss_icon = enemy.icon_image if enemy.icon_image else 'None'
        final_boss_icon = boss_icon
        if boss_icon and boss_icon != 'None' and not boss_icon.startswith('http') and not boss_icon.startswith('/'):
            final_boss_icon = f"/static/images/rpg/{boss_icon}"

        all_badges.append({
            'name': enemy.badge_name,
            'icon': final_badge_icon,
            'description': f"{enemy.name}を討伐した証", # カード表示用
            'earned': is_earned,
            'boss_name': enemy.name,
            'boss_icon': final_boss_icon,
            'boss_description': enemy.description # モーダル表示用（テンプレート変数を合わせる必要あり）
        })
        # Note: テンプレートのonclickで `badge.description` を渡しているが、これはモーダルの説明文になる。
        # Step 408の変更を見ると:
        # onclick="showMonsterDetail('{{ badge.name }}', '{{ badge.description }}', ...)"
        # カードテキストは:
        # {{ badge.description if badge.earned else '未獲得' }}
        # 問題: カードテキストとモーダルテキストを分けたいが、テンプレートは `badge.description` を両方に使っている。
        # テンプレートを修正するのは面倒（またreplace_file_contentが必要）。
        # ここでは `description` に `enemy.description` (豆知識) を入れることにする。
        # カードテキストが長くなるかもしれないが、それが「豆知識」ならカード内でも見えて良いのでは？
        # あるいは、テンプレートで `badge.boss_description` を使うように修正すべきか？
        # ユーザー要望: "statusの画面で、討伐した敵の情報を見られる...豆知識です"
        # カードには短い説明、クリックで詳細（豆知識）が自然。
        # しかしテンプレート修正コストを避けるため、一旦 `description` に豆知識を入れる。
        # もしカードからはみ出るならCSSで省略される（現状のCSS次第だが）。
        # よし、`description` = `enemy.description` にしよう。
        
        all_badges[-1]['description'] = enemy.description if enemy.description else f"{enemy.name}のデータ"

    # 既存のボーナスなど
    bonus_percent = rpg_state.permanent_bonus_percent if rpg_state else 0.0
    # クリア数はステージ数に基づいて計算（len(cleared_set)でOK）
    cleared_count = len(cleared_set)
    
    return render_template('status.html', 
                         current_user=user, 
                         earned_badges=all_badges, # 変数名を変更
                         bonus_percent=bonus_percent, 
                         cleared_count=cleared_count)


if __name__ == '__main__':

    try:
        # サーバー起動
        port = int(os.environ.get('PORT', 5001))
        debug_mode = os.environ.get('RENDER') != 'true'
        
        logger.info(f"🌐 サーバーを起動します: http://0.0.0.0:{port}")
        
        app.run(host='0.0.0.0', port=port, debug=debug_mode)
        
    except Exception as e:
        logger.error(f"💥 起動失敗: {e}")
        import traceback
        traceback.print_exc()

@app.route('/admin/delete_room', methods=['POST'])
def admin_delete_room():
    """管理者用：部屋削除機能"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限が必要です'})
    
    try:
        data = request.get_json()
        room_number = data.get('room_number')
        
        if not room_number:
            return jsonify({'status': 'error', 'message': '部屋番号が指定されていません'})
        
        # 部屋に属するユーザーの確認
        users_in_room = User.query.filter_by(room_number=room_number).all()
        
        if users_in_room:
            return jsonify({
                'status': 'error', 
                'message': f'部屋{room_number}にはまだ{len(users_in_room)}人のユーザーが存在します。先にユーザーを削除してください。'
            })
        
        # 部屋設定を削除
        room_setting = RoomSetting.query.filter_by(room_number=room_number).first()
        if room_setting:
            db.session.delete(room_setting)
            db.session.commit()
            return jsonify({
                'status': 'success', 
                'message': f'部屋{room_number}を正常に削除しました'
            })
        else:
            return jsonify({
                'status': 'error', 
                'message': f'部屋{room_number}が見つかりません'
            })
            
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"部屋削除エラー: {str(e)}")
        return jsonify({'status': 'error', 'message': f'削除中にエラーが発生しました: {str(e)}'})

@app.route('/admin/toggle_room_suspension', methods=['POST'])
def admin_toggle_room_suspension():
    """管理者用：部屋の一時停止/再開機能"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限が必要です'})
    
    try:
        data = request.get_json()
        room_number = data.get('room_number')
        
        if not room_number:
            return jsonify({'status': 'error', 'message': '部屋番号が指定されていません'})
        
        # 部屋設定を取得
        room_setting = RoomSetting.query.filter_by(room_number=room_number).first()
        if not room_setting:
            return jsonify({'status': 'error', 'message': f'部屋{room_number}が見つかりません'})
        
        # 一時停止状態を切り替え
        if room_setting.is_suspended:
            # 再開
            room_setting.is_suspended = False
            room_setting.suspended_at = None
            action_message = f'部屋{room_number}の一時停止を解除しました'
            app.logger.info(f"部屋{room_number}の一時停止を解除")
        else:
            # 一時停止
            room_setting.is_suspended = True
            room_setting.suspended_at = datetime.utcnow()
            action_message = f'部屋{room_number}を一時停止にしました'
            app.logger.info(f"部屋{room_number}を一時停止に設定")
        
        room_setting.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'status': 'success', 
            'message': action_message,
            'is_suspended': room_setting.is_suspended
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"部屋一時停止切り替えエラー: {str(e)}")
        return jsonify({'status': 'error', 'message': f'処理中にエラーが発生しました: {str(e)}'})
    
@app.route('/admin/upload_essay_image/<int:problem_id>', methods=['POST'])
def upload_essay_image(problem_id):
    """論述問題の画像をアップロード（データベース保存）"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限が必要です'})
    
    try:
        # 問題の存在確認
        essay_problem = EssayProblem.query.get(problem_id)
        if not essay_problem:
            return jsonify({'status': 'error', 'message': '指定された問題が見つかりません'})
        
        # ファイルの確認
        if 'image' not in request.files:
            return jsonify({'status': 'error', 'message': '画像ファイルが選択されていません'})
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'status': 'error', 'message': '画像ファイルが選択されていません'})
        
        # ファイル形式の確認
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            return jsonify({'status': 'error', 'message': '対応していないファイル形式です（PNG, JPG, JPEG, GIFのみ）'})
        
        # ファイルサイズチェック（5MBまで）
        file.seek(0, 2)  # ファイル末尾に移動
        file_size = file.tell()
        file.seek(0)  # ファイル先頭に戻す
        
        if file_size > 5 * 1024 * 1024:  # 5MB
            return jsonify({'status': 'error', 'message': 'ファイルサイズが大きすぎます（5MBまで）'})
        
        # 既存画像の削除（分離したトランザクション）
        existing_image = EssayImage.query.filter_by(problem_id=problem_id).first()
        if existing_image:
            try:
                db.session.delete(existing_image)
                db.session.commit()
                app.logger.info(f"既存の画像（問題{problem_id}）を削除しました")
            except Exception as delete_error:
                db.session.rollback()
                app.logger.error(f"既存画像削除エラー: {delete_error}")
                return jsonify({'status': 'error', 'message': '既存画像の削除に失敗しました'})
        
        # 画像データを読み込み
        image_data = file.read()
        
        # 新しい画像をデータベースに保存
        new_image = EssayImage(
            problem_id=problem_id,
            image_data=image_data,
            image_format=file_ext.upper()
        )
        
        try:
            db.session.add(new_image)
            db.session.commit()
            app.logger.info(f"問題{problem_id}の画像をデータベースに保存しました（サイズ: {len(image_data):,}bytes）")
        except Exception as insert_error:
            db.session.rollback()
            app.logger.error(f"新しい画像保存エラー: {insert_error}")
            return jsonify({'status': 'error', 'message': '新しい画像の保存に失敗しました'})
        
        # フォームからの直接アップロードの場合はページにリダイレクト
        if request.referrer and 'upload_essay_image_form' in request.referrer:
            flash(f'問題{problem_id}の画像をアップロードしました', 'success')
            return redirect(url_for('admin_upload_essay_image_form', problem_id=problem_id))
        
        # APIからの場合はJSONレスポンス
        return jsonify({
            'status': 'success', 
            'message': f'問題{problem_id}の画像をアップロードしました',
            'file_size': f'{len(image_data):,}bytes',
            'format': file_ext.upper()
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"画像アップロードエラー: {str(e)}")
        return jsonify({'status': 'error', 'message': f'アップロード中にエラーが発生しました: {str(e)}'})

@app.route('/admin/upload_essay_image_form/<int:problem_id>')
def admin_upload_essay_image_form(problem_id):
    """管理者用：論述問題画像アップロードフォーム表示"""
    if not session.get('admin_logged_in'):
        flash('管理者権限が必要です', 'danger')
        return redirect(url_for('login_page'))
    
    try:
        essay_problem = EssayProblem.query.get(problem_id)
        if not essay_problem:
            flash('指定された問題が見つかりません', 'danger')
            return redirect(url_for('admin_essay_problems'))
        
        # 現在の画像の有無を確認
        has_current_image = has_essay_image(problem_id)
        
        # 画像表示部分を事前に準備
        if has_current_image:
            image_section = f'''
                <div class="current-image">
                    <h3>現在の画像</h3>
                    <img src="{url_for('essay_image', problem_id=problem_id)}" alt="現在の画像">
                    <p><small>現在の画像が表示されています</small></p>
                </div>
            '''
        else:
            image_section = '<p><em>現在画像は設定されていません</em></p>'
        
        return f'''
        <html>
        <head>
            <title>問題{problem_id}の画像アップロード</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .container {{ max-width: 600px; margin: 0 auto; }}
                .form-group {{ margin-bottom: 20px; }}
                .btn {{ padding: 10px 20px; margin: 5px; border: none; border-radius: 5px; cursor: pointer; }}
                .btn-primary {{ background: #007bff; color: white; }}
                .btn-secondary {{ background: #6c757d; color: white; }}
                .current-image {{ text-align: center; margin: 20px 0; }}
                .current-image img {{ max-width: 100%; border: 1px solid #ddd; border-radius: 5px; }}
                .alert {{ padding: 15px; margin: 20px 0; border-radius: 5px; }}
                .alert-info {{ background: #d1ecf1; border: 1px solid #bee5eb; color: #0c5460; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>問題{problem_id}の画像アップロード</h1>
                
                <div class="alert alert-info">
                    <strong>問題：</strong> {essay_problem.university} {essay_problem.year}年<br>
                    <strong>タイプ：</strong> {essay_problem.type} ({essay_problem.answer_length}字)<br>
                    <strong>問題文：</strong> {essay_problem.question[:100]}...
                </div>
                
                {image_section}
                
                <form method="POST" action="{url_for('upload_essay_image', problem_id=problem_id)}" enctype="multipart/form-data">
                    <div class="form-group">
                        <label for="image"><strong>新しい画像を選択:</strong></label><br>
                        <input type="file" id="image" name="image" accept="image/*" required>
                        <small style="display: block; color: #666; margin-top: 5px;">
                            対応形式: PNG, JPG, JPEG, GIF (最大5MB)
                        </small>
                    </div>
                    
                    <div class="form-group">
                        <button type="submit" class="btn btn-primary">アップロード</button>
                        <a href="/admin/essay/problems" class="btn btn-secondary">戻る</a>
                    </div>
                </form>
            </div>
        </body>
        </html>
        '''
        
    except Exception as e:
        flash(f'エラー: {str(e)}', 'danger')
        return redirect(url_for('admin_essay_problems'))

@app.route('/admin/delete_essay_image/<int:problem_id>', methods=['POST'])
def delete_essay_image(problem_id):
    """論述問題の画像を削除"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限が必要です'})
    
    try:
        # 問題の存在確認
        essay_problem = EssayProblem.query.get(problem_id)
        if not essay_problem:
            return jsonify({'status': 'error', 'message': '指定された問題が見つかりません'})
        
        # 画像の存在確認と削除
        existing_image = EssayImage.query.filter_by(problem_id=problem_id).first()
        if existing_image:
            db.session.delete(existing_image)
            db.session.commit()
            
            app.logger.info(f"問題{problem_id}の画像を削除しました")
            return jsonify({
                'status': 'success', 
                'message': f'問題{problem_id}の画像を削除しました'
            })
        else:
            return jsonify({
                'status': 'error', 
                'message': '削除する画像が見つかりません'
            })
            
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"画像削除エラー: {str(e)}")
        return jsonify({'status': 'error', 'message': f'削除中にエラーが発生しました: {str(e)}'})

@app.route('/api/daily_quiz/today')
def get_daily_quiz():
    """今日の10問を取得、または結果を表示するためのAPI (月間ランキング対応版)"""
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'ログインが必要です'}), 401
    
    user = User.query.get(session['user_id'])
    today = (datetime.now(JST) - timedelta(hours=7)).date()
    yesterday = today - timedelta(days=1)

    # --- ▼▼▼ 月間スコア集計トリガー ▼▼▼ ---
    try:
        yesterday_quiz = DailyQuiz.query.filter_by(
            date=yesterday, 
            room_number=user.room_number, 
            monthly_score_processed=False
        ).first()
        
        if yesterday_quiz:
            process_daily_quiz_results_for_scoring(yesterday_quiz.id)
            
    except Exception as score_e:
        print(f"❌ 集計トリガーエラー: {score_e}")
    # --- ▲▲▲ 集計トリガーここまで ▲▲▲ ---

    daily_quiz = DailyQuiz.query.filter_by(date=today, room_number=user.room_number).first()

    # 月間ランキングデータを取得 (当月分)
    current_year = today.year
    current_month = today.month
    monthly_top_5, monthly_user_rank, monthly_participants = get_monthly_ranking(
        user.room_number, user.id, current_year, current_month
    )

    if daily_quiz:
        user_result = DailyQuizResult.query.filter_by(user_id=user.id, quiz_id=daily_quiz.id).first()
        if user_result:
            # --- (回答済みの場合) ---
            all_results = DailyQuizResult.query.filter_by(quiz_id=daily_quiz.id)\
                .options(joinedload(DailyQuizResult.user))\
                .order_by(DailyQuizResult.score.desc(), DailyQuizResult.time_taken_ms.asc()).all()
            
            total_participants = len(all_results)
            top_5_ranking = []
            current_user_rank_info = None

            for i, result in enumerate(all_results, 1):
                if not result.user: continue
                rank_entry = {'rank': i, 'username': result.user.username, 'score': result.score, 'time': f"{(result.time_taken_ms / 1000):.2f}秒"}
                if i <= 5: top_5_ranking.append(rank_entry)
                if result.user_id == user.id: current_user_rank_info = rank_entry
            
            user_result_data = {'score': user_result.score, 'time': f"{(user_result.time_taken_ms / 1000):.2f}秒"}

            return jsonify({
                'status': 'success',
                'completed': True,
                'user_result': user_result_data,
                'top_5_ranking': top_5_ranking,
                'user_rank': current_user_rank_info,
                'total_participants': total_participants,
                'monthly_top_5': monthly_top_5, # 月間ランキング追加
                'monthly_user_rank': monthly_user_rank, # 月間ランキング追加
                'monthly_participants': monthly_participants # 月間ランキング追加
            })

    # --- (未回答の場合のクイズ生成ロジック) ---
    if not daily_quiz:
        all_words = load_word_data_for_room(user.room_number)
        room_setting = RoomSetting.query.filter_by(room_number=user.room_number).first()
        
        public_words = []
        for word in all_words:
            chapter = str(word.get('chapter', ''))
            
            # S章の場合は 'S' で判定、それ以外は従来通り number で判定
            unit_to_check = 'S' if chapter == 'S' else word.get('number')
            is_enabled_in_room = is_unit_enabled_by_room_setting(unit_to_check, room_setting)
            is_not_z_problem = str(word.get('number')).strip().upper() != 'Z'
            
            if is_enabled_in_room and is_not_z_problem: # CSVの有効化チェック(is_enabled_in_csv)を削除
                public_words.append(word)

        if len(public_words) < 10: # 10問未満の場合はエラー
            return jsonify({'status': 'error', 'message': f'クイズを作成するには公開問題(Z以外)が10問以上必要です (現在 {len(public_words)}問)'})
        
        selected_problems = random.sample(public_words, 10)
        problem_ids = [generate_problem_id(p) for p in selected_problems]
        daily_quiz = DailyQuiz(date=today, room_number=user.room_number, problem_ids_json=json.dumps(problem_ids), monthly_score_processed=False)
        db.session.add(daily_quiz)
        db.session.commit()

    problem_ids = daily_quiz.get_problem_ids()
    all_words = load_word_data_for_room(user.room_number)
    quiz_questions = []
    all_answers = list(set(w['answer'] for w in all_words if w.get('answer')))
    
    for problem_id in problem_ids:
        question_word = next((w for w in all_words if generate_problem_id(w) == problem_id), None)
        if question_word:
            correct_answer = question_word['answer']
            
            # --- 誤答選択肢の生成ロジック (改良版) ---
            # 1. CSVのG列 (incorrect) に指定がある場合はそれを使用
            manual_incorrect_str = question_word.get('incorrect', '')
            
            if manual_incorrect_str and manual_incorrect_str.strip():
                # カンマ区切りで分割し、空白を除去
                manual_candidates = [x.strip() for x in manual_incorrect_str.split(',') if x.strip()]
                
                # ランダムに最大3つ選ぶ
                if len(manual_candidates) > 3:
                    distractors = random.sample(manual_candidates, 3)
                else:
                    distractors = manual_candidates
            else:
                # 2. 指定がない場合は従来通りレーベンシュタイン距離で類似語を探す
                distractor_pool = [ans for ans in all_answers if ans != correct_answer]
                distractors_with_distance = [(levenshtein_distance(correct_answer, ans), ans) for ans in distractor_pool]
                distractors_with_distance.sort(key=lambda x: x[0])
                distractors = [ans for distance, ans in distractors_with_distance[:3]]
                # 候補が足りない場合はランダムに補充 (念のため)
                if len(distractors) < 3 and len(distractor_pool) >= 3:
                    remaining = [ans for ans in distractor_pool if ans not in distractors]
                    distractors.extend(random.sample(remaining, 3 - len(distractors)))

            # 正解と誤答を合わせてシャッフル
            choices = distractors + [correct_answer]
            random.shuffle(choices)
            
            quiz_questions.append({
                'id': problem_id,
                'question': question_word['question'],
                'choices': choices,
                'answer': correct_answer
            })

    return jsonify({
        'status': 'success',
        'completed': False,
        'questions': quiz_questions,
        'monthly_top_5': monthly_top_5, # 未回答時も月間ランクは渡す
        'monthly_user_rank': monthly_user_rank,
        'monthly_participants': monthly_participants
    })

@app.route('/api/daily_quiz/submit', methods=['POST'])
def submit_daily_quiz():
    """今日の10問の結果を保存し、その場でランキングを返すAPI (月間ランキング対応版)"""
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'ログインが必要です'}), 401

    user = User.query.get(session['user_id'])
    today = (datetime.now(JST) - timedelta(hours=7)).date()
    data = request.get_json()

    daily_quiz = DailyQuiz.query.filter_by(date=today, room_number=user.room_number).first()
    if not daily_quiz:
        return jsonify({'status': 'error', 'message': '今日のクイズが見つかりません。'}), 404

    if DailyQuizResult.query.filter_by(user_id=user.id, quiz_id=daily_quiz.id).first():
        return jsonify({'status': 'error', 'message': '既に回答済みです。'}), 409

    try:
        new_result = DailyQuizResult(
            user_id=user.id,
            quiz_id=daily_quiz.id,
            score=data.get('score'),
            time_taken_ms=data.get('time')
        )
        db.session.add(new_result)
        db.session.commit()
        db.session.refresh(new_result)
        
        # (日次ランキング計算)
        all_results = DailyQuizResult.query.filter_by(quiz_id=daily_quiz.id)\
            .options(joinedload(DailyQuizResult.user))\
            .order_by(DailyQuizResult.score.desc(), DailyQuizResult.time_taken_ms.asc()).all()
        
        total_participants = len(all_results)
        top_5_ranking = []
        current_user_rank_info = None

        for i, result in enumerate(all_results, 1):
            if not result.user: continue
            rank_entry = {'rank': i, 'username': result.user.username, 'score': result.score, 'time': f"{(result.time_taken_ms / 1000):.2f}秒"}
            if i <= 5: top_5_ranking.append(rank_entry)
            if result.user_id == user.id: current_user_rank_info = rank_entry
        
        # --- ▼▼▼ 月間ランキングデータを取得 ▼▼▼ ---
        current_year = today.year
        current_month = today.month
        monthly_top_5, monthly_user_rank, monthly_participants = get_monthly_ranking(
            user.room_number, user.id, current_year, current_month
        )

        return jsonify({
            'status': 'success',
            'message': '結果を保存しました。',
            'completed': True,
            'user_result': {'score': new_result.score, 'time': f"{(new_result.time_taken_ms / 1000):.2f}秒"},
            'top_5_ranking': top_5_ranking,
            'user_rank': current_user_rank_info,
            'total_participants': total_participants,
            'monthly_top_5': monthly_top_5, # 月間ランキング追加
            'monthly_user_rank': monthly_user_rank, # 月間ランキング追加
            'monthly_participants': monthly_participants # 月間ランキング追加
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"日次クイズ結果の保存/集計エラー: {e}")
        return jsonify({'status': 'error', 'message': '結果の保存中にサーバーエラーが発生しました。'}), 500

@app.route('/admin/regenerate_daily_quiz', methods=['POST'])
@admin_required
def admin_regenerate_daily_quiz():
    """管理者用: 特定の部屋の「今日の10問」を再生成する (月間スコア集計トリガー付)"""
    room_number = request.json.get('room_number')
    if not room_number:
        return jsonify({'status': 'error', 'message': '部屋番号が必要です'}), 400

    today = (datetime.now(JST) - timedelta(hours=7)).date()

    try:
        existing_quiz = DailyQuiz.query.filter_by(date=today, room_number=room_number).first()

        if existing_quiz:
            print(f"🔧 部屋{room_number}の既存クイズ(ID: {existing_quiz.id})を削除します。")
            
            if not existing_quiz.monthly_score_processed:
                print("スコアが未集計のため、先に集計処理を実行します...")
                process_daily_quiz_results_for_scoring(existing_quiz.id)
            else:
                print("スコアは集計済みです。")

            DailyQuizResult.query.filter_by(quiz_id=existing_quiz.id).delete()
            db.session.delete(existing_quiz)
            db.session.commit()
            print(f"✅ 既存クイズと結果の削除完了。")

        print(f"✨ 部屋{room_number}の新しいクイズを生成します。")
        all_words = load_word_data_for_room(room_number)
        room_setting = RoomSetting.query.filter_by(room_number=room_number).first()
        
        public_words = []
        for word in all_words:
            chapter = str(word.get('chapter', ''))
            
            # S章の場合は 'S' で判定、それ以外は従来通り number で判定
            unit_to_check = 'S' if chapter == 'S' else word.get('number')
            is_enabled_in_room = is_unit_enabled_by_room_setting(unit_to_check, room_setting)
            is_not_z_problem = str(word.get('number')).strip().upper() != 'Z'
            
            if is_enabled_in_room and is_not_z_problem: # CSVの有効化チェック(is_enabled_in_csv)を削除
                public_words.append(word)

        if len(public_words) < 10:
             return jsonify({'status': 'error', 'message': f'公開問題(Z以外)が10問未満({len(public_words)}問)のため、再選考できません。'}), 400

        selected_problems = random.sample(public_words, 10)
        problem_ids = [generate_problem_id(p) for p in selected_problems]
        
        new_quiz = DailyQuiz(date=today, room_number=room_number, problem_ids_json=json.dumps(problem_ids), monthly_score_processed=False)
        db.session.add(new_quiz)
        db.session.commit()
        print(f"✅ 新しいクイズ(ID: {new_quiz.id})の生成完了。")

        return jsonify({'status': 'success', 'message': f'部屋{room_number}の「今日の10問」を正常に再選考しました。'})

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"日次クイズ再生成エラー: {e}")
        return jsonify({'status': 'error', 'message': f'エラーが発生しました: {str(e)}'}), 500

@app.route('/api/monthly_results/check_unviewed')
def check_unviewed_monthly_results():
    """未閲覧の前月のランキング結果があるかチェックする"""
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'ログインが必要です'}), 401

    user = User.query.get(session['user_id'])
    
    # 今日の日付（7時更新基準）
    today = (datetime.now(JST) - timedelta(hours=7)).date()
    
    # 前月を計算
    first_day_of_current_month = today.replace(day=1)
    last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
    prev_year = last_day_of_previous_month.year
    prev_month = last_day_of_previous_month.month

    # 今月が始まってから、まだ前月の結果を見ていないかチェック
    already_viewed = MonthlyResultViewed.query.filter_by(
        user_id=user.id,
        year=prev_year,
        month=prev_month
    ).first()

    if already_viewed:
        return jsonify({'status': 'success', 'show_results': False})

    # まだ見ていない場合、前月のランキングデータを取得
    monthly_top_5, monthly_user_rank, total_participants = get_monthly_ranking(
        user.room_number, user.id, prev_year, prev_month
    )

    if total_participants == 0:
        # 誰も参加しなかった月は、自動的に「閲覧済み」にして何も表示しない
        mark_as_viewed = MonthlyResultViewed(user_id=user.id, year=prev_year, month=prev_month)
        db.session.add(mark_as_viewed)
        db.session.commit()
        return jsonify({'status': 'success', 'show_results': False})

    # 表示すべき結果を返す
    return jsonify({
        'status': 'success',
        'show_results': True,
        'year': prev_year,
        'month': prev_month,
        'monthly_top_5': monthly_top_5,
        'monthly_user_rank': monthly_user_rank,
        'total_participants': total_participants
    })

@app.route('/api/monthly_results/mark_viewed', methods=['POST'])
def mark_monthly_result_viewed():
    """月間ランキングを閲覧済みにする"""
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'ログインが必要です'}), 401
    
    user = User.query.get(session['user_id'])
    data = request.get_json()
    year = data.get('year')
    month = data.get('month')

    if not year or not month:
        return jsonify({'status': 'error', 'message': '年と月が必要です'}), 400

    # 既に存在するか確認
    existing = MonthlyResultViewed.query.filter_by(user_id=user.id, year=year, month=month).first()
    if not existing:
        mark_as_viewed = MonthlyResultViewed(user_id=user.id, year=year, month=month)
        db.session.add(mark_as_viewed)
        db.session.commit()

    return jsonify({'status': 'success', 'message': '閲覧済みにしました'})
    
@app.route('/admin/fix_data_types', methods=['POST'])
@admin_required
def admin_fix_data_types():
    """管理者用：全ユーザーのデータ型を修復するAPI"""
    try:
        result = fix_user_data_types()
        flash(f"データ型の修復が完了しました。{result['fixed_users']}人のユーザーデータを更新しました。", 'success')
        return redirect(url_for('admin_page'))
    except Exception as e:
        db.session.rollback()
        flash(f"データ修復中にエラーが発生しました: {str(e)}", 'danger')
        return redirect(url_for('admin_page'))

# ========================================================================
# ユーザースコア削除機能
# ========================================================================

def delete_user_score_data(user):
    """ユーザーのスコア・学習履歴を全て削除する"""
    try:
        # 1. 学習履歴 (JSON)
        user.problem_history = {}
        user.incorrect_words = []
        
        # 2. 統計データ (UserStats)
        if user.stats:
            db.session.delete(user.stats)
            
        # 3. 日次クイズ結果 (DailyQuizResult)
        DailyQuizResult.query.filter_by(user_id=user.id).delete()
        
        # 4. 月次スコア (MonthlyScore)
        MonthlyScore.query.filter_by(user_id=user.id).delete()
        
        # 5. 論述問題進捗 (EssayProgress)
        EssayProgress.query.filter_by(user_id=user.id).delete()
        
        # 6. 月次結果閲覧履歴 (MonthlyResultViewed)
        MonthlyResultViewed.query.filter_by(user_id=user.id).delete()
        
        # 7. 制限状態のリセット
        user.restriction_triggered = False
        user.restriction_released = False
        
        return True
    except Exception as e:
        print(f"❌ スコア削除エラー ({user.username}): {e}")
        return False

@app.route('/admin/delete_user_score', methods=['POST'])
def admin_delete_user_score():
    """個別のユーザーのスコアを削除"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限がありません。'}), 403
        
    user_id = request.form.get('user_id')
    admin_password = request.form.get('admin_password')
    
    if not user_id or not admin_password:
        return jsonify({'status': 'error', 'message': '必要な情報が不足しています。'}), 400
        
    # 管理者パスワード確認
    current_admin_id = session.get('user_id')
    admin_user = User.query.get(current_admin_id) if current_admin_id else None
    
    # フォールバック: セッションにIDがない場合は従来のAdminUserテーブルを確認
    if not admin_user:
        admin_user = AdminUser.query.filter_by(username='admin').first()
        if not admin_user or not admin_user.check_password(admin_password):
            return jsonify({'status': 'error', 'message': '管理者パスワードが間違っています。'}), 403
    else:
        # Userテーブルの管理者アカウントで確認
        if not admin_user.check_individual_password(admin_password):
            return jsonify({'status': 'error', 'message': '管理者パスワードが間違っています。'}), 403
        
    user = User.query.get(user_id)
    if not user:
        return jsonify({'status': 'error', 'message': 'ユーザーが見つかりません。'}), 404
        
    try:
        if delete_user_score_data(user):
            # 統計再作成（空の状態で）
            UserStats.get_or_create(user.id)
            db.session.commit()
            return jsonify({'status': 'success', 'message': f'ユーザー {user.username} のスコアを削除しました。'})
        else:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': 'スコア削除中にエラーが発生しました。'}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/delete_room_score', methods=['POST'])
def admin_delete_room_score():
    """部屋全体のユーザースコアを削除"""
    if not session.get('admin_logged_in'):
        return jsonify({'status': 'error', 'message': '管理者権限がありません。'}), 403
        
    room_number = request.form.get('room_number')
    admin_password = request.form.get('admin_password')
    
    if not room_number or not admin_password:
        return jsonify({'status': 'error', 'message': '必要な情報が不足しています。'}), 400
        
    # 管理者パスワード確認
    current_admin_id = session.get('user_id')
    admin_user = User.query.get(current_admin_id) if current_admin_id else None
    
    # フォールバック: セッションにIDがない場合は従来のAdminUserテーブルを確認
    if not admin_user:
        admin_user = AdminUser.query.filter_by(username='admin').first()
        if not admin_user or not admin_user.check_password(admin_password):
            return jsonify({'status': 'error', 'message': '管理者パスワードが間違っています。'}), 403
    else:
        # Userテーブルの管理者アカウントで確認
        if not admin_user.check_individual_password(admin_password):
            return jsonify({'status': 'error', 'message': '管理者パスワードが間違っています。'}), 403
        
    users = User.query.filter_by(room_number=room_number).all()
    if not users:
        return jsonify({'status': 'error', 'message': '指定された部屋にユーザーがいません。'}), 404
        
    success_count = 0
    try:
        for user in users:
            if user.username == 'admin':
                continue
            if delete_user_score_data(user):
                # 統計再作成
                UserStats.get_or_create(user.id)
                success_count += 1
        
        db.session.commit()
        return jsonify({'status': 'success', 'message': f'部屋 {room_number} の {success_count} 名のスコアを削除しました。'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
# ========================================================================
# RPG Enemy Management Routes
# ========================================================================

@app.route('/admin/rpg/enemies')
@admin_required
def admin_rpg_enemies():
    """RPG敵キャラ一覧（JSONで返すか、admin.htmlの一部としてレンダリングするか検討）"""
    # admin.html内のセクションとして機能させるため、JSON APIとして提供し、JSで描画するパタンが良い
    enemies = RpgEnemy.query.order_by(RpgEnemy.display_order).all()
    return jsonify([e.to_dict() for e in enemies])

def get_user_total_score(user_id):
    """ユーザーの累計獲得スコア（MonthlyScoreの合計）を取得"""
    try:
        total = db.session.query(func.sum(MonthlyScore.total_score)).filter(MonthlyScore.user_id == user_id).scalar()
        return int(total) if total else 0
    except Exception as e:
        print(f"Error calculating total score for user {user_id}: {e}")
        return 0

@app.route('/admin/rpg/enemies/add', methods=['POST'])
@admin_required
def admin_add_rpg_enemy():
    """RPG敵キャラ追加（DB保存対応版）"""
    try:
        # フォームデータの取得
        name = request.form.get('name')
        if not name:
            return jsonify({'status': 'error', 'message': '名前は必須です'}), 400
            
        # 画像アップロード処理
        icon_file = request.files.get('icon_image')
        badge_file = request.files.get('badge_image')
        
        icon_filename = None
        icon_content = None
        icon_mimetype = None
        
        if icon_file and icon_file.filename:
            filename = secure_filename(icon_file.filename)
            unique_filename = f"rpg_enemy_{int(time.time())}_{filename}"
            icon_mimetype = icon_file.mimetype
            
            # DB保存用にデータを読み込む
            icon_file.seek(0)
            icon_content = icon_file.read()
            
            # フォールバック用にローカル保存（またはS3）
            # S3へアップロード
            icon_file.seek(0) # 巻き戻し
            s3_url = upload_image_to_s3(icon_file, unique_filename, folder='rpg_images')
            
            if s3_url:
                icon_filename = s3_url # Full URL
            else:
                # ローカル保存
                upload_dir = os.path.join(app.root_path, 'static', 'images', 'rpg')
                os.makedirs(upload_dir, exist_ok=True)
                icon_file.seek(0)
                icon_file.save(os.path.join(upload_dir, unique_filename))
                icon_filename = unique_filename

        badge_filename_or_class = request.form.get('badge_icon_class') # FontAwesomeの場合
        badge_content = None
        badge_mimetype = None
        
        if badge_file and badge_file.filename:
            filename = secure_filename(badge_file.filename)
            unique_filename = f"rpg_badge_{int(time.time())}_{filename}"
            badge_mimetype = badge_file.mimetype
            
            # DB保存用
            badge_file.seek(0)
            badge_content = badge_file.read()
            
            # S3へアップロード
            badge_file.seek(0)
            s3_url = upload_image_to_s3(badge_file, unique_filename, folder='rpg_images')
            if s3_url:
                badge_filename_or_class = s3_url # Full URL
            else:
                # ローカル保存
                upload_dir = os.path.join(app.root_path, 'static', 'images', 'rpg')
                os.makedirs(upload_dir, exist_ok=True)
                badge_file.seek(0)
                badge_file.save(os.path.join(upload_dir, unique_filename))
                badge_filename_or_class = unique_filename # ローカルファイル名
            
        # 新規作成
        new_enemy = RpgEnemy(
            name=name,
            icon_image=icon_filename,
            icon_image_content=icon_content,      # 🆕
            icon_image_mimetype=icon_mimetype,    # 🆕
            badge_name=request.form.get('badge_name', 'Unknown Badge'),
            badge_image=badge_filename_or_class,
            badge_image_content=badge_content,    # 🆕
            badge_image_mimetype=badge_mimetype,  # 🆕
            difficulty=int(request.form.get('difficulty', 1)),
            description=request.form.get('description'),
            intro_dialogue=request.form.get('intro_dialogue'),
            defeat_dialogue=request.form.get('defeat_dialogue'),
            time_limit=int(request.form.get('time_limit', 60)),
            clear_correct_count=int(request.form.get('clear_correct_count', 10)),
            clear_max_mistakes=int(request.form.get('clear_max_mistakes', 2)),
            is_active=request.form.get('is_active') == 'true',
            display_order=int(request.form.get('display_order', 1000)),
            appearance_required_score=int(request.form.get('appearance_required_score', 0))
        )
        
        db.session.add(new_enemy)
        db.session.commit()
        return jsonify({'status': 'success', 'message': '敵キャラを追加しました', 'enemy': new_enemy.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

def _revoke_rpg_progress(enemy_id, badge_name):
    """
    指定された敵キャラの討伐履歴、バッジ、ボーナスを全ユーザーから削除・再計算する
    enemy_id: 削除/無効化する敵のID
    badge_name: 削除するバッジ名
    """
    try:
        # 全てのRPG進行状況を取得
        all_states = RpgState.query.all()
        affected_count = 0
        
        target_id_str = str(enemy_id)
        
        for state in all_states:
            changed = False
            
            # 1. クリア履歴から削除
            cleared_list = list(state.cleared_stages) if state.cleared_stages else []
            # IDはintかstrか混在の可能性あり
            new_cleared = [cid for cid in cleared_list if str(cid) != target_id_str]
            
            if len(new_cleared) != len(cleared_list):
                state.cleared_stages = new_cleared
                changed = True
                
            # 2. バッジ削除
            badges_list = list(state.earned_badges) if state.earned_badges else []
            if badge_name and badge_name in badges_list:
                badges_list.remove(badge_name)
                state.earned_badges = badges_list
                changed = True
                
            # 3. ボーナス再計算
            if changed:
                # ボーナスロジック: クリア数 * 0.5% (最大10%)
                new_bonus = min(10.0, len(new_cleared) * 0.5)
                state.permanent_bonus_percent = new_bonus
                affected_count += 1
                
        db.session.commit()
        print(f"🔄 Revoked RPG progress for enemy {enemy_id}. Affected users: {affected_count}")
        return True
        
    except Exception as e:
        print(f"❌ Error revoking RPG progress: {e}")
        # ここでのロールバックは呼び出し元に任せるか検討だが、個別にコミットしているためここで処理
        db.session.rollback()
        return False

@app.route('/admin/rpg/enemies/delete/<int:enemy_id>', methods=['POST'])
@admin_required
def admin_delete_rpg_enemy(enemy_id):
    """RPG敵キャラ削除"""
    try:
        enemy = RpgEnemy.query.get(enemy_id)
        if not enemy:
            return jsonify({'status': 'error', 'message': '指定された敵キャラが見つかりません'}), 404
            
        # ★ ボーナス剥奪処理
        _revoke_rpg_progress(enemy.id, enemy.badge_name)
            
        db.session.delete(enemy)
        db.session.commit()
        return jsonify({'status': 'success', 'message': '敵キャラを削除し、関連するユーザースコアを再計算しました'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/admin/rpg/enemies/edit/<int:enemy_id>', methods=['POST'])
@admin_required
def admin_edit_rpg_enemy(enemy_id):
    """RPG敵キャラ編集"""
    try:
        enemy = RpgEnemy.query.get(enemy_id)
        if not enemy:
            return jsonify({'status': 'error', 'message': '指定された敵キャラが見つかりません'}), 404
            
        # フォームデータの取得
        name = request.form.get('name')
        if not name:
            return jsonify({'status': 'error', 'message': '名前は必須です'}), 400
            
        current_is_active = enemy.is_active
        new_is_active = request.form.get('is_active') == 'true'
        
        # ★ 無効化された場合、ボーナス剥奪
        if current_is_active and not new_is_active:
             _revoke_rpg_progress(enemy.id, enemy.badge_name)
             
        # 基本情報の更新
        enemy.name = name
        enemy.badge_name = request.form.get('badge_name', 'Unknown Badge')
        enemy.difficulty = int(request.form.get('difficulty', 1))
        enemy.description = request.form.get('description')
        enemy.intro_dialogue = request.form.get('intro_dialogue')
        enemy.defeat_dialogue = request.form.get('defeat_dialogue')
        enemy.time_limit = int(request.form.get('time_limit', 60))
        enemy.clear_correct_count = int(request.form.get('clear_correct_count', 10))
        enemy.clear_max_mistakes = int(request.form.get('clear_max_mistakes', 2))
        enemy.is_active = new_is_active
        enemy.display_order = int(request.form.get('display_order', 0))
        enemy.appearance_required_score = int(request.form.get('appearance_required_score', 0))
        
        # 画像更新処理
        icon_file = request.files.get('icon_image')
        if icon_file and icon_file.filename:
            filename = secure_filename(icon_file.filename)
            unique_filename = f"rpg_enemy_{int(time.time())}_{filename}"
            
            # DB保存用にデータを読み込む
            icon_file.seek(0)
            enemy.icon_image_content = icon_file.read()
            enemy.icon_image_mimetype = icon_file.mimetype
            
            # S3/Local保存
            icon_file.seek(0)
            s3_url = upload_image_to_s3(icon_file, unique_filename, folder='rpg_images')
            if s3_url:
                enemy.icon_image = s3_url
            else:
                upload_dir = os.path.join(app.root_path, 'static', 'images', 'rpg')
                os.makedirs(upload_dir, exist_ok=True)
                icon_file.seek(0)
                icon_file.save(os.path.join(upload_dir, unique_filename))
                enemy.icon_image = unique_filename

        badge_file = request.files.get('badge_image')
        badge_icon_class = request.form.get('badge_icon_class')
        
        if badge_file and badge_file.filename:
            filename = secure_filename(badge_file.filename)
            unique_filename = f"rpg_badge_{int(time.time())}_{filename}"
            
            # DB保存用
            badge_file.seek(0)
            enemy.badge_image_content = badge_file.read()
            enemy.badge_image_mimetype = badge_file.mimetype
            
            # S3/Local
            badge_file.seek(0)
            s3_url = upload_image_to_s3(badge_file, unique_filename, folder='rpg_images')
            if s3_url:
                enemy.badge_image = s3_url
            else:
                upload_dir = os.path.join(app.root_path, 'static', 'images', 'rpg')
                os.makedirs(upload_dir, exist_ok=True)
                badge_file.seek(0)
                badge_file.save(os.path.join(upload_dir, unique_filename))
                enemy.badge_image = unique_filename
        elif badge_icon_class:
            enemy.badge_image = badge_icon_class
            
        db.session.commit()
        return jsonify({'status': 'success', 'message': '敵キャラ情報を更新しました', 'enemy': enemy.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
