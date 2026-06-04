# Renderに合わせてPython 3.11を使用
FROM python:3.11.9-slim

# 作業ディレクトリの設定
WORKDIR /app

# PostgreSQL接続やMeCabなどに必要なOSパッケージをインストール
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 依存関係のインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードのコピー
COPY . .

# Renderの起動コマンドと同じGunicornを使用（ポート5000）
ENV PORT=5000
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "-c", "gunicorn.conf.py", "app:app"]
