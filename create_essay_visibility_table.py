# create_essay_visibility_table.py - 簡易マイグレーションスクリプト

import sys
import os

# アプリのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def main():
    """論述問題公開設定テーブルの作成とデフォルト設定"""
    print("=" * 60)
    print("📊 論述問題公開設定テーブル作成")
    print("=" * 60)
    
    try:
        # appとdbをインポート（既存のプロジェクト構造に合わせる）
        from app import app, db
        from models import EssayVisibilitySetting, EssayProblem, RoomSetting, User
        from sqlalchemy import text, inspect
        
        with app.app_context():
            inspector = inspect(db.engine)
            
            # 1. テーブル存在チェック
            if inspector.has_table('essay_visibility_setting'):
                print("ℹ️ essay_visibility_settingテーブルは既に存在します")
                
                # 既存設定数を確認
                existing_count = EssayVisibilitySetting.query.count()
                print(f"📊 既存設定数: {existing_count}件")
                
                if existing_count == 0:
                    print("🔧 既存設定がないため、デフォルト設定を作成します")
                else:
                    print("ℹ️ 既存設定があるため、処理を終了します")
                    return True
            else:
                # 2. テーブル作成
                print("🔧 essay_visibility_settingテーブルを作成中...")
                EssayVisibilitySetting.__table__.create(db.engine)
                print("✅ テーブル作成完了")
            
            # 3. デフォルト設定の作成
            print("🔧 デフォルト設定を作成中...")
            
            # 既存の章とタイプを取得
            chapters_types = db.session.query(
                EssayProblem.chapter,
                EssayProblem.type
            ).filter(
                EssayProblem.enabled == True
            ).distinct().all()
            
            if not chapters_types:
                print("⚠️ 論述問題が見つからないため、デフォルト設定作成をスキップします")
                return True
            
            print(f"📊 発見された章・タイプ組み合わせ: {len(chapters_types)}件")
            for ch, pt in chapters_types[:5]:  # 最初の5件を表示
                print(f"   - 第{ch}章 タイプ{pt}")
            if len(chapters_types) > 5:
                print(f"   ... 他{len(chapters_types) - 5}件")
            
            # 部屋番号を取得
            room_numbers = set()
            
            # RoomSettingから取得
            room_settings = db.session.query(RoomSetting.room_number).distinct().all()
            room_numbers.update([r[0] for r in room_settings])
            
            # Userテーブルからも取得
            user_rooms = db.session.query(User.room_number).distinct().all()
            room_numbers.update([r[0] for r in user_rooms if r[0]])
            
            room_list = sorted(list(room_numbers))
            
            if not room_list:
                print("⚠️ 部屋が見つからないため、デフォルト設定作成をスキップします")
                return True
            
            print(f"📋 発見された部屋番号: {len(room_list)}件")
            for room in room_list[:5]:  # 最初の5件を表示
                print(f"   - 部屋{room}")
            if len(room_list) > 5:
                print(f"   ... 他{len(room_list) - 5}件")
            
            # 4. デフォルト設定を一括作成
            created_count = 0
            
            for room_number in room_list:
                for chapter, problem_type in chapters_types:
                    if chapter and problem_type:  # NULLや空文字を除外
                        # 既存設定があるかチェック
                        existing = EssayVisibilitySetting.query.filter_by(
                            room_number=room_number,
                            chapter=chapter,
                            problem_type=problem_type
                        ).first()
                        
                        if not existing:
                            # 新規設定を作成（デフォルトで公開）
                            new_setting = EssayVisibilitySetting(
                                room_number=room_number,
                                chapter=chapter,
                                problem_type=problem_type,
                                is_visible=True
                            )
                            db.session.add(new_setting)
                            created_count += 1
            
            # 5. データベースにコミット
            if created_count > 0:
                db.session.commit()
                print(f"✅ デフォルト設定を{created_count}件作成しました")
            else:
                print("ℹ️ 作成する設定がありませんでした")
            
            # 6. 結果確認
            total_settings = EssayVisibilitySetting.query.count()
            print(f"📊 現在の設定数: {total_settings}件")
            
            # サンプル設定を表示
            sample_settings = EssayVisibilitySetting.query.limit(3).all()
            if sample_settings:
                print("📋 サンプル設定:")
                for setting in sample_settings:
                    status = '公開' if setting.is_visible else '非公開'
                    print(f"   - 部屋{setting.room_number} 第{setting.chapter}章 タイプ{setting.problem_type}: {status}")
            
            print("\n" + "=" * 60)
            print("🎉 テーブル作成とデフォルト設定が正常に完了しました！")
            print("管理画面で論述問題公開設定を使用できるようになりました。")
            print("=" * 60)
            return True
            
    except ImportError as e:
        print(f"❌ インポートエラー: {e}")
        print("app.py または models.py にEssayVisibilitySettingが正しく追加されているか確認してください。")
        return False
    except Exception as e:
        print(f"❌ 実行エラー: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    if success:
        print("\n✅ 処理が完了しました。アプリケーションを再起動してください。")
    else:
        print("\n❌ 処理に失敗しました。エラーを確認して再試行してください。")
    sys.exit(0 if success else 1)