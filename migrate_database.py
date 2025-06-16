# migrate_database.py
# 既存のデータベースに新しいカラムを追加するマイグレーションスクリプト

import sqlite3
import os
from datetime import datetime

def migrate_database():
    """既存のデータベースに新しいカラムを追加"""
    
    # データベースファイルのパス
    db_path = 'quiz_data.db'
    
    if not os.path.exists(db_path):
        print(f"データベースファイル {db_path} が見つかりません。")
        print("新しいデータベースが作成されるため、マイグレーションは不要です。")
        return
    
    # データベースのバックアップを作成
    backup_path = f'quiz_data_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
    try:
        import shutil
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
        
        # room_settingテーブルが存在するかチェック
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='room_setting';")
        table_exists = cursor.fetchone() is not None
        
        if not table_exists:
            print("room_settingテーブルが存在しません。テーブルを作成します。")
            cursor.execute('''
                CREATE TABLE room_setting (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_number VARCHAR(50) NOT NULL UNIQUE,
                    max_enabled_unit_number VARCHAR(50) NOT NULL DEFAULT '9999',
                    csv_filename VARCHAR(100) NOT NULL DEFAULT 'words.csv'
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
                cursor.execute("ALTER TABLE room_setting ADD COLUMN csv_filename VARCHAR(100) NOT NULL DEFAULT 'words.csv';")
                print("✅ csv_filenameカラムを追加しました。")
            else:
                print("csv_filenameカラムは既に存在します。")
        
        # 新しいテーブル room_csv_file を作成（存在しない場合）
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
                    upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    description TEXT
                )
            ''')
            print("✅ room_csv_fileテーブルを作成しました。")
        else:
            print("room_csv_fileテーブルは既に存在します。")
        
        # 変更をコミット
        conn.commit()
        print("✅ データベースのマイグレーションが完了しました。")
        
        # マイグレーション後の状態を確認
        print("\n📊 マイグレーション後のテーブル構造:")
        cursor.execute("PRAGMA table_info(room_setting);")
        columns = cursor.fetchall()
        for column in columns:
            print(f"  - {column[1]} ({column[2]})")
        
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
        # room_settingテーブルの構造を確認
        cursor.execute("PRAGMA table_info(room_setting);")
        columns = [column[1] for column in cursor.fetchall()]
        
        required_columns = ['id', 'room_number', 'max_enabled_unit_number', 'csv_filename']
        missing_columns = [col for col in required_columns if col not in columns]
        
        if missing_columns:
            print(f"❌ 必要なカラムが不足しています: {missing_columns}")
            return False
        
        # room_csv_fileテーブルの存在を確認
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='room_csv_file';")
        csv_table_exists = cursor.fetchone() is not None
        
        if not csv_table_exists:
            print("❌ room_csv_fileテーブルが存在しません。")
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
        else:
            print("\n❌ マイグレーションの検証に失敗しました。")
            print("手動でデータベースを確認してください。")
    except Exception as e:
        print(f"\n💥 マイグレーションに失敗しました: {e}")
        print("バックアップファイルからデータベースを復元してください。")
    
    print("=" * 50)