#!/usr/bin/env python3
# scripts/update_progress_cache.py
# Render Cron Jobs用の進捗更新スクリプト

import os
import sys
import logging
from datetime import datetime
import pytz

# プロジェクトルートをPythonパスに追加
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# アプリケーションをインポート
try:
    from app import app, db, ProgressCacheManager, JST
    print("✅ アプリケーションのインポート成功")
except ImportError as e:
    print(f"❌ アプリケーションのインポートエラー: {e}")
    sys.exit(1)

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [CRON] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def main():
    """Cron Job用のメイン関数"""
    try:
        logger.info("🔄 Cron Job による進捗キャッシュ更新を開始")
        
        # 現在時刻をチェック
        now = datetime.now(JST)
        logger.info(f"⏰ 現在時刻: {now.strftime('%Y-%m-%d %H:%M:%S')} JST")
        
        # Flaskアプリケーションコンテキスト内で実行
        with app.app_context():
            # データベース接続確認
            try:
                from sqlalchemy import text
                with db.engine.connect() as conn:
                    conn.execute(text('SELECT 1'))
                logger.info("✅ データベース接続確認")
            except Exception as db_error:
                logger.error(f"❌ データベース接続エラー: {db_error}")
                return False
            
            # 進捗キャッシュ更新実行
            try:
                ProgressCacheManager.update_progress_cache()
                logger.info("✅ 進捗キャッシュ更新完了")
                return True
            except Exception as update_error:
                logger.error(f"❌ 進捗キャッシュ更新エラー: {update_error}")
                import traceback
                traceback.print_exc()
                return False
                
    except Exception as e:
        logger.error(f"❌ Cron Job実行エラー: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # 環境変数の確認
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        logger.error("❌ DATABASE_URL環境変数が設定されていません")
        sys.exit(1)
    
    # メイン処理実行
    success = main()
    
    if success:
        logger.info("🎉 Cron Job正常終了")
        sys.exit(0)
    else:
        logger.error("💥 Cron Job異常終了")
        sys.exit(1)