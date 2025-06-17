# fixed_migrate_database.py
# SQLite対応版 - non-constant default問題を解決

import sqlite3
import os
from datetime import datetime
import shutil

def migrate_database():
    """SQLite対応のデータベースマイグレーション"""
    
    # データベースファイルのパス
    db_path = 'quiz_data.db'
    
    if not os.path.exists(db_path):
        print(f"データベースファイル {db_path} が見つかりません。")
        print("新しいデータベースが作成されるため、マイグレーションは不要です。")
        return
    
    # データベースのバックアップを作成
    backup_path = f'quiz_data_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
    try:
        shutil.copy2(db_path, backup_path)
        print(f"✅ データベースのバックアップを作成しました: {backup_path}")
    except Exception as e:
        print(f"⚠️ バックアップの作成に失敗しました: {e}")
        print("続行しますか？ (y/N): ", end="")
        if input().lower() != 'y':
            return
    
    # データベースに接続
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        print("📋 現在のテーブル構造を確認中...")
        
        # 1. room_settingテーブルの処理
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='room_setting';")
        table_exists = cursor.fetchone() is not None
        
        if not table_exists:
            print("room_settingテーブルが存在しません。テーブルを作成します。")
            cursor.execute('''
                CREATE TABLE room_setting (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_number VARCHAR(50) NOT NULL UNIQUE,
                    max_enabled_unit_number VARCHAR(50) NOT NULL DEFAULT '9999',
                    csv_filename VARCHAR(100) NOT NULL DEFAULT 'words.csv',
                    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
                    updated_at DATETIME DEFAULT (datetime('now', 'localtime'))
                )
            ''')
            print("✅ room_settingテーブルを作成しました。")
        else:
            # 既存のテーブルの列を確認
            cursor.execute("PRAGMA table_info(room_setting);")
            columns = [column[1] for column in cursor.fetchall()]
            print(f"現在の列: {columns}")
            
            # csv_filenameカラムが存在しないかチェック
            if 'csv_filename' not in columns:
                print("csv_filenameカラムを追加します...")
                cursor.execute("ALTER TABLE room_setting ADD COLUMN csv_filename VARCHAR(100) DEFAULT 'words.csv';")
                print("✅ csv_filenameカラムを追加しました。")
            else:
                print("csv_filenameカラムは既に存在します。")
            
            # created_atとupdated_atカラムの追加（SQLite対応版）
            if 'created_at' not in columns:
                print("created_atカラムを追加します...")
                # SQLiteではnon-constant defaultを使えないため、NULL許可で追加後に更新
                cursor.execute("ALTER TABLE room_setting ADD COLUMN created_at DATETIME;")
                # 既存のレコードに現在時刻を設定
                cursor.execute("UPDATE room_setting SET created_at = datetime('now', 'localtime') WHERE created_at IS NULL;")
                print("✅ created_atカラムを追加しました。")
            
            if 'updated_at' not in columns:
                print("updated_atカラムを追加します...")
                cursor.execute("ALTER TABLE room_setting ADD COLUMN updated_at DATETIME;")
                cursor.execute("UPDATE room_setting SET updated_at = datetime('now', 'localtime') WHERE updated_at IS NULL;")
                print("✅ updated_atカラムを追加しました。")
        
        # 2. room_csv_fileテーブルの作成
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='room_csv_file';")
        csv_table_exists = cursor.fetchone() is not None
        
        if not csv_table_exists:
            print("room_csv_fileテーブルを作成します...")
            cursor.execute('''
                CREATE TABLE room_csv_file (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename VARCHAR(100) NOT NULL UNIQUE,
                    original_filename VARCHAR(100) NOT NULL,
                    file_size INTEGER NOT NULL,
                    word_count INTEGER DEFAULT 0,
                    upload_date DATETIME DEFAULT (datetime('now', 'localtime')),
                    description TEXT
                )
            ''')
            print("✅ room_csv_fileテーブルを作成しました。")
        else:
            print("room_csv_fileテーブルは既に存在します。")
        
        # 3. app_infoテーブルの作成
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='app_info';")
        app_info_table_exists = cursor.fetchone() is not None
        
        if not app_info_table_exists:
            print("app_infoテーブルを作成します...")
            cursor.execute('''
                CREATE TABLE app_info (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_name VARCHAR(100) NOT NULL DEFAULT '世界史単語帳',
                    version VARCHAR(20) NOT NULL DEFAULT '1.0.0',
                    last_updated_date VARCHAR(50) NOT NULL DEFAULT '2025年6月15日',
                    update_content TEXT NOT NULL DEFAULT 'アプリケーションが開始されました。',
                    footer_text VARCHAR(200) DEFAULT '',
                    contact_email VARCHAR(100) DEFAULT '',
                    app_settings TEXT DEFAULT '{}',
                    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
                    updated_at DATETIME DEFAULT (datetime('now', 'localtime')),
                    updated_by VARCHAR(80) DEFAULT 'system'
                )
            ''')
            print("✅ app_infoテーブルを作成しました。")
            
            # デフォルトのアプリ情報を挿入
            cursor.execute('''
                INSERT INTO app_info (app_name, version, last_updated_date, update_content, updated_by)
                VALUES ('世界史単語帳', '1.0.0', '2025年6月15日', '部屋ごとのCSVファイル対応機能を追加しました。', 'system')
            ''')
            print("✅ デフォルトのアプリ情報を挿入しました。")
        else:
            print("app_infoテーブルは既に存在します。")
            
            # 既存のapp_infoテーブルの列を確認
            cursor.execute("PRAGMA table_info(app_info);")
            app_info_columns = [column[1] for column in cursor.fetchall()]
            print(f"app_infoテーブルの現在の列: {app_info_columns}")
            
            # 必要なカラムを追加（SQLite対応版）
            required_columns = {
                'footer_text': 'VARCHAR(200) DEFAULT ""',
                'contact_email': 'VARCHAR(100) DEFAULT ""',
                'app_settings': 'TEXT DEFAULT "{}"',
                'created_at': 'DATETIME',
                'updated_at': 'DATETIME',
                'updated_by': 'VARCHAR(80) DEFAULT "system"'
            }
            
            for column_name, column_def in required_columns.items():
                if column_name not in app_info_columns:
                    print(f"{column_name}カラムを追加します...")
                    cursor.execute(f"ALTER TABLE app_info ADD COLUMN {column_name} {column_def};")
                    
                    # created_atとupdated_atには現在時刻を設定
                    if column_name in ['created_at', 'updated_at']:
                        cursor.execute(f"UPDATE app_info SET {column_name} = datetime('now', 'localtime') WHERE {column_name} IS NULL;")
                    
                    print(f"✅ {column_name}カラムを追加しました。")
            
            # デフォルトレコードが存在しない場合は作成
            cursor.execute("SELECT COUNT(*) FROM app_info;")
            app_info_count = cursor.fetchone()[0]
            
            if app_info_count == 0:
                print("デフォルトのアプリ情報を挿入します...")
                cursor.execute('''
                    INSERT INTO app_info (app_name, version, last_updated_date, update_content, updated_by)
                    VALUES ('世界史単語帳', '1.0.0', '2025年6月15日', '部屋ごとのCSVファイル対応機能を追加しました。', 'system')
                ''')
                print("✅ デフォルトのアプリ情報を挿入しました。")
        
        # 4. userテーブルにlast_loginカラムを追加
        cursor.execute("PRAGMA table_info(user);")
        user_columns = [column[1] for column in cursor.fetchall()]
        
        if 'last_login' not in user_columns:
            print("userテーブルにlast_loginカラムを追加します...")
            cursor.execute("ALTER TABLE user ADD COLUMN last_login DATETIME;")
            # 既存ユーザーには現在時刻を設定
            cursor.execute("UPDATE user SET last_login = datetime('now', 'localtime') WHERE last_login IS NULL;")
            print("✅ last_loginカラムを追加しました。")
        else:
            print("last_loginカラムは既に存在します。")
        
        # 変更をコミット
        conn.commit()
        print("✅ データベースのマイグレーションが完了しました。")
        
        # マイグレーション後の状態を確認
        print("\n📊 マイグレーション後のテーブル構造:")
        
        # room_settingテーブル
        cursor.execute("PRAGMA table_info(room_setting);")
        columns = cursor.fetchall()
        print("room_settingテーブル:")
        for column in columns:
            print(f"  - {column[1]} ({column[2]})")
        
        # app_infoテーブル
        cursor.execute("PRAGMA table_info(app_info);")
        columns = cursor.fetchall()
        print("app_infoテーブル:")
        for column in columns:
            print(f"  - {column[1]} ({column[2]})")
        
        # userテーブル
        cursor.execute("PRAGMA table_info(user);")
        columns = cursor.fetchall()
        print("userテーブル:")
        for column in columns:
            print(f"  - {column[1]} ({column[2]})")
        
        # app_infoのデータ確認
        cursor.execute("SELECT * FROM app_info;")
        app_info_data = cursor.fetchall()
        print(f"\napp_infoテーブルのデータ数: {len(app_info_data)}")
        if app_info_data:
            print(f"最初のレコード: {app_info_data[0]}")
        
    except Exception as e:
        print(f"❌ マイグレーション中にエラーが発生しました: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def verify_migration():
    """マイグレーションが正常に完了したかを確認"""
    db_path = 'quiz_data.db'
    
    if not os.path.exists(db_path):
        print("データベースファイルが見つかりません。")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # app_infoテーブルの存在確認
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='app_info';")
        app_info_table_exists = cursor.fetchone() is not None
        
        if not app_info_table_exists:
            print("❌ app_infoテーブルが存在しません。")
            return False
        
        # app_infoテーブルの構造確認
        cursor.execute("PRAGMA table_info(app_info);")
        app_info_columns = [column[1] for column in cursor.fetchall()]
        
        required_columns = ['id', 'app_name', 'version', 'last_updated_date', 'update_content']
        missing_columns = [col for col in required_columns if col not in app_info_columns]
        
        if missing_columns:
            print(f"❌ app_infoテーブルに必要なカラムが不足しています: {missing_columns}")
            return False
        
        # デフォルトデータの存在確認
        cursor.execute("SELECT COUNT(*) FROM app_info;")
        app_info_count = cursor.fetchone()[0]
        
        if app_info_count == 0:
            print("⚠️ app_infoテーブルにデフォルトデータが存在しません。")
            return False
        
        print("✅ マイグレーションの検証が完了しました。すべて正常です。")
        return True
        
    except Exception as e:
        print(f"❌ 検証中にエラーが発生しました: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    print("🔄 データベースマイグレーションを開始します...")
    print("=" * 50)
    
    try:
        migrate_database()
        print("\n🔍 マイグレーションの検証を実行します...")
        if verify_migration():
            print("\n🎉 マイグレーションが正常に完了しました！")
            print("これでアプリケーションを起動できます。")
            print("\n📱 新機能：")
            print("- アプリ情報管理機能が追加されました")
            print("- 管理者ページからアプリ名、更新内容等を編集できます")
        else:
            print("\n❌ マイグレーションの検証に失敗しました。")
            print("手動でデータベースを確認してください。")
    except Exception as e:
        print(f"\n💥 マイグレーションに失敗しました: {e}")
        print("バックアップファイルからデータベースを復元してください。")
    
    print("=" * 50)