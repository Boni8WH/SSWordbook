#!/bin/bash

# カラー定義
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== 開発環境セットアップを開始します ===${NC}"

# 1. .envファイルの確認と作成
if [ ! -f .env ]; then
    echo "Creating .env file..."
    # Renderの環境に合わせてローカル用の接続情報を書き込む
    echo "DATABASE_URL=postgresql://world_history_user:password@localhost:5432/world_history_db" > .env
    echo "FLASK_APP=app.py" >> .env
    echo "FLASK_DEBUG=1" >> .env
    echo -e "${GREEN}✅ .envファイルを作成しました${NC}"
else
    echo "ℹ️ .envファイルは既に存在します"
    # DATABASE_URLが含まれているか確認（簡易チェック）
    if ! grep -q "DATABASE_URL" .env; then
        echo "⚠️ .envにDATABASE_URLが見つかりません。以下を追記します。"
        echo "DATABASE_URL=postgresql://world_history_user:password@localhost:5432/world_history_db" >> .env
        echo -e "${GREEN}✅ DATABASE_URLを追記しました${NC}"
    fi
fi

# 2. Dockerコンテナの起動
echo -e "\n${BLUE}PostgreSQLコンテナを起動しています...${NC}"
if command -v docker-compose &> /dev/null; then
    docker-compose up -d
elif command -v docker &> /dev/null && docker compose version &> /dev/null; then
    docker compose up -d
else
    echo "❌ Dockerがインストールされていないか、パスが通っていません。"
    exit 1
fi

echo -e "${GREEN}✅ データベースコンテナが起動しました${NC}"
echo -e "\n${BLUE}次のステップ:${NC}"
echo "1. アプリを起動する: python3 app.py (または flask run)"
echo "2. データベース操作: docker exec -it world_history_db psql -U world_history_user -d world_history_db"
