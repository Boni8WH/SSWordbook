# models.py - アプリ情報管理機能追加版

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator, Text
import json
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pytz

# 日本時間のタイムゾーンオブジェクトを作成
JST = pytz.timezone('Asia/Tokyo')

db = None

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
    student_id = db.Column(db.String(50), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    # パスワードはハッシュ化して保存
    _room_password_hash = db.Column(db.String(128), nullable=False)
    _individual_password_hash = db.Column(db.String(128), nullable=False)
    
    # ★★★ 以下のフィールドを追加 ★★★
    original_username = db.Column(db.String(80), nullable=False)
    is_first_login = db.Column(db.Boolean, default=True, nullable=False)
    password_changed_at = db.Column(db.DateTime)
    username_changed_at = db.Column(db.DateTime)
    restriction_triggered = db.Column(db.Boolean, default=False, nullable=False)
    restriction_released = db.Column(db.Boolean, default=False, nullable=False)
    
    # 問題履歴をJSON形式で保存 (問題ID: {total: N, correct: M, consecutive_correct: K})
    problem_history = db.Column(JSONEncodedDict, default={})
    # 苦手問題をJSON形式で保存 (問題オブジェクトのリスト)
    incorrect_words = db.Column(JSONEncodedDict, default=[])
    # 最終ログイン日時
    last_login = db.Column(db.DateTime, default=lambda: datetime.now(JST))

    def set_room_password(self, password):
        self._room_password_hash = generate_password_hash(password)

    def check_room_password(self, password):
        return check_password_hash(self._room_password_hash, password)

    def set_individual_password(self, password):
        self._individual_password_hash = generate_password_hash(password)

    def check_individual_password(self, password):
        return check_password_hash(self._individual_password_hash, password)

    def __repr__(self):
        return f'<User {self.username} (Room: {self.room_number}, ID: {self.student_id})>'
    
    def get_problem_history(self):
        """問題履歴を取得"""
        if self.problem_history:
            return self.problem_history
        return {}

    def set_problem_history(self, history):
        """問題履歴を設定"""
        self.problem_history = history

    def get_incorrect_words(self):
        """苦手問題を取得"""
        if self.incorrect_words:
            return self.incorrect_words
        return []

    def set_incorrect_words(self, words):
        """苦手問題を設定"""
        self.incorrect_words = words

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

class AdminUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    _password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self._password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self._password_hash, password)

    def __repr__(self):
        return f'<AdminUser {self.username}>'

# 部屋ごとの設定モデル（CSVファイル設定を追加）
class RoomSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(50), unique=True, nullable=False)
    max_enabled_unit_number = db.Column(db.String(50), default="9999", nullable=False)
    csv_filename = db.Column(db.String(100), default="words.csv", nullable=False)
    ranking_display_count = db.Column(db.Integer, default=10, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(JST), onupdate=lambda: datetime.now(JST))

    def __repr__(self):
        return f'<RoomSetting {self.room_number}, Max Unit: {self.max_enabled_unit_number}, CSV: {self.csv_filename}>'

# 部屋ごとのカスタムCSVファイル情報を管理するモデル（オプション）
class RoomCsvFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), unique=True, nullable=False)
    original_filename = db.Column(db.String(100), nullable=False)  # アップロード時の元のファイル名
    file_size = db.Column(db.Integer, nullable=False)  # バイト単位
    word_count = db.Column(db.Integer, default=0)  # 単語数
    upload_date = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    description = db.Column(db.Text)  # ファイルの説明（オプション）
    
    def __repr__(self):
        return f'<RoomCsvFile {self.filename} ({self.word_count} words)>'

# ★ 新規追加：アプリ情報管理モデル
class AppInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    app_name = db.Column(db.String(100), default="世界史単語帳", nullable=False)
    version = db.Column(db.String(20), default="1.0.0", nullable=False)
    last_updated_date = db.Column(db.String(50), default="2025年6月15日", nullable=False)
    update_content = db.Column(db.Text, default="アプリケーションが開始されました。", nullable=False)
    footer_text = db.Column(db.String(200), default="", nullable=True)
    contact_email = db.Column(db.String(100), default="", nullable=True)
    school_name = db.Column(db.String(100), default="朋優学院", nullable=False)
    # アプリの設定を保存するJSON
    app_settings = db.Column(JSONEncodedDict, default={})
    # 作成・更新日時
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(JST), onupdate=lambda: datetime.now(JST))
    # 最後に更新した管理者
    updated_by = db.Column(db.String(80), default="system")

# models.py の最後に追加するコード（既存のインポートとクラスは変更しない）

# 論述問題の部屋別公開設定モデル
class EssayVisibilitySetting(db.Model):
    __tablename__ = 'essay_visibility_setting'
    
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(50), nullable=False)
    chapter = db.Column(db.String(10), nullable=False)  # '1', '2', 'com' など
    problem_type = db.Column(db.String(1), nullable=False)  # 'A', 'B', 'C', 'D'
    is_visible = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(JST), onupdate=lambda: datetime.now(JST))
    
    # 複合ユニーク制約（部屋・章・タイプの組み合わせは一意）
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
    
class EssayProblemImage(db.Model):
    __tablename__ = 'essay_problem_images'
    
    id = db.Column(db.Integer, primary_key=True)
    problem_id = db.Column(db.Integer, nullable=False, unique=True)  # essay_problemsのidと対応
    image_data = db.Column(db.LargeBinary, nullable=False)  # 画像のバイナリデータ
    image_filename = db.Column(db.String(255), nullable=False)  # 元のファイル名
    image_content_type = db.Column(db.String(100), nullable=False)  # MIME type (image/jpeg など)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(JST))
    
    def __repr__(self):
        return f'<EssayProblemImage problem_id={self.problem_id} filename={self.image_filename}>'

    @classmethod
    def get_current_info(cls):
        """現在のアプリ情報を取得。存在しない場合はデフォルトを作成"""
        app_info = cls.query.first()
        if not app_info:
            app_info = cls()
            db.session.add(app_info)
            db.session.commit()
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
        'schoolName': self.school_name,  # ← 追加
        'isLoggedIn': True,
        'username': None,
        'roomNumber': None
        }

    def __repr__(self):
        return f'<AppInfo {self.app_name} v{self.version}>'