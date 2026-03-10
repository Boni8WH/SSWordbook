import os
import json
import requests
import xml.etree.ElementTree as ET
import email.utils
import feedparser
from datetime import datetime
from calendar import timegm
from urllib.parse import urlparse
import pytz
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables
basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
load_dotenv(os.path.join(basedir, '.env'))

JST = pytz.timezone('Asia/Tokyo')

# AWS S3設定
S3_BUCKET = os.environ.get('S3_BUCKET')
S3_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
S3_SECRET = os.environ.get('AWS_SECRET_ACCESS_KEY')
S3_REGION = os.environ.get('S3_REGION', 'ap-northeast-1')
S3_AVAILABLE = all([S3_KEY, S3_SECRET, S3_BUCKET])

def get_s3_client():
    """Boto3を遅延インポートしてS3クライアントを取得"""
    if not S3_AVAILABLE:
        return None
    try:
        import boto3
        return boto3.client(
            's3',
            aws_access_key_id=S3_KEY,
            aws_secret_access_key=S3_SECRET,
            region_name=S3_REGION
        )
    except Exception as e:
        print(f"⚠️ S3クライアント初期化失敗: {e}")
        return None

def upload_json_to_s3(data, s3_path):
    """辞書データをJSONとしてS3にアップロード"""
    s3_client = get_s3_client()
    if not s3_client:
        return False
    try:
        json_data = json.dumps(data, ensure_ascii=False, indent=2)
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_path,
            Body=json_data,
            ContentType='application/json'
        )
        return True
    except Exception as e:
        print(f"⚠️ S3 JSONアップロードエラー ({s3_path}): {e}")
        return False

# URLドメインから出典メディア名を推定するマッピング
DOMAIN_SOURCE_MAP = {
    'nhk.or.jp': 'NHK',
    'nikkei.com': '日経新聞',
    'asia.nikkei.com': '日経アジア',
    'asahi.com': '朝日新聞',
    'yomiuri.co.jp': '読売新聞',
    'japannews.yomiuri.co.jp': 'The Japan News',
    'bbc.com': 'BBCニュース',
    'bbc.co.uk': 'BBCニュース',
    'theguardian.com': 'ガーディアン',
    'nytimes.com': 'ニューヨーク・タイムズ',
    'aljazeera.com': 'アルジャジーラ',
    'france24.com': 'France 24',
    'dw.com': 'DW',
    'reuters.com': 'ロイター',
    'reutersagency.com': 'ロイター',
    'apnews.com': 'AP通信',
    'scmp.com': 'SCMP',
}

def source_from_url(url):
    """URLからドメインを抽出し、出典メディア名を返す"""
    try:
        hostname = urlparse(url).hostname or ''
        hostname = hostname.removeprefix('www.')
        # 完全一致 → サブドメイン含む一致の順で探す
        if hostname in DOMAIN_SOURCE_MAP:
            return DOMAIN_SOURCE_MAP[hostname]
        for domain, name in DOMAIN_SOURCE_MAP.items():
            if hostname.endswith(domain):
                return name
        return hostname
    except Exception:
        return ''

# --- 追加: Pydanticモデルを定義して出力を構造化 ---
class Article(BaseModel):
    title: str = Field(description="ニュースのタイトル（必ず日本語に翻訳してください）")
    summary: str = Field(description="歴史的背景を含めた詳しい要約（日本語、200〜300文字）")
    significance: str = Field(description="世界史のどの単元と関連するか、何を学ぶべきかの解説（日本語、100〜200文字）")
    keywords: list[str] = Field(description="関連する世界史の重要用語（例: 帝国主義、冷戦、サイクス・ピコ協定など）3〜5個")
    url: str = Field(description="出典URL")
    source: str = Field(description="出典メディア名（日本語翻訳、例: BBCニュース）")
    created_at: str = Field(description="元の記事の公開日時。必ず日本時間(JST)に変換して、日本の高校生が読みやすい月日・時刻を含む形式（例: '3月9日 10:30'）で出力してください。元の日時(PubDate)がJSTでない場合は、提供された現在の基準時刻(JST)を基に計算してください。")

class OtherTopic(BaseModel):
    title: str = Field(description="ニュースのタイトル（必ず日本語に翻訳してください）")
    url: str = Field(description="出典URL")
    source: str = Field(description="出典メディア名（日本語翻訳、例: BBCニュース）")

class NewsResponse(BaseModel):
    articles: list[Article] = Field(description="厳選された3つのニュース記事")
    other_topics: list[OtherTopic] = Field(description="その他の注目トピック（6個）")
# --------------------------------------------------

def get_gemini_summary(news_items):
    """Gemini APIを使ってニュースを要約する"""
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("⚠️ GEMINI_API_KEY is not set.")
        return None

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        
        # ニュース項目をプロンプト用に整形（全件渡す）
        news_text = "\n".join([f"- [{item['source']}] {item['title']} (PubDate: {item.get('pub_date')}): {item['description']} (URL: {item['link']})" for item in news_items])
        
        # 前回選出された記事の情報を取得して、重複を避ける
        prev_articles_text = "なし"
        json_path = os.path.join(basedir, 'data', 'featured_article.json')
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    prev_data = json.load(f)
                    prev_titles = [a.get('title') for a in prev_data.get('articles', [])]
                    if prev_titles:
                        prev_articles_text = ", ".join(prev_titles)
            except Exception:
                pass

        current_time = datetime.now(JST).strftime("%Y年%m月%d日 %H:%M")
        prompt = f"""
あなたは、現代の国際情勢と世界史を結びつける解説が得意な、予備校のカリスマ world history 講師です。
現在は **{current_time}** です。この日時を基準に、最新の状況を正確に判断してください（例：役職や現職・前職の区別など）。

以下の最新ニュースリストの中から、**世界史を学んでいる日本の高校生**にとって知的好奇心を刺激し、学習の助けとなるトピックを選んでください。

**構成の指示:**
1. **厳選記事 (articles)**: 最も重要なものを**厳密に3つ**選び、詳細な解説を作成してください。
2. **その他の注目トピック (other_topics)**: 次点で興味深いものを**厳密に6個**選び、タイトル、URL、出典メディア名をリストアップしてください。**特定のメディアに偏らず、できるだけ多様な出典（NHK, Nikkei, BBC, Guardian等）からバランスよく選出してください。** **重要: 各トピックのsourceフィールドには必ず出典メディア名（例: BBCニュース、ガーディアン、NHK等）を含めてください。空にしないでください。**

**選出・要約のガイドライン（最優先）:**
1. **事実の正確性**: あなたの事前学習知識よりも、**提供されたニュースリストのテキスト内容を絶対的に優先**してください。人名、役職、現状について、リストと矛盾する推測や古い情報を入れないでください。
2. **歴史的背景・継続性**: 現在の出来事が、過去の歴史的事象（植民地支配、冷戦、宗教対立、条約など）と深く結びついているものを優先してください。
3. **トピックの多様性**: 前回のトピックと極力被らないようにしてください。
   - 前回の記事タイトル: {prev_articles_text}
   - 同じ問題（例：イラン情勢）に大きな進展がない限り、別の地域や異なる歴史テーマを優先してください。
4. **翻訳の徹底**: 記事のタイトルは、日本の高校生が理解しやすい自然な日本語に必ず翻訳してください。
5. **現代社会の理解**: 単なるニュースではなく「教科書の知識が現在の世界を理解するレンズになる」ことが実感できる内容にしてください。
6. **地域バランス**: 欧米、アジア、中東、アフリカなど、地域が偏らないよう配慮してください。

ニュースリスト:
{news_text}
"""
        # Pydanticモデルを使って出力を強制する
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': NewsResponse, # ここでスキーマを指定
                'temperature': 0.3 # 事実ベースの出力を安定させるため少し低めに設定
            }
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"⚠️ Gemini API Error: {e}")
        return None

def update_news():
    """ニュースを更新してJSONに保存する"""
    rss_feeds = [
        {"name": "NHK (Major)", "url": "https://www3.nhk.or.jp/rss/news/cat0.xml"},
        {"name": "NHK (International)", "url": "https://www3.nhk.or.jp/rss/news/cat1.xml"},
        {"name": "Nikkei Asia", "url": "https://asia.nikkei.com/rss/feed/nar"},
        {"name": "Asahi Shimbun (AJW)", "url": "http://www.asahi.com/english/rss/index.rdf"},
        {"name": "The Japan News", "url": "https://japannews.yomiuri.co.jp/feed/"},
        {"name": "BBC News (World)", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
        {"name": "The Guardian (World)", "url": "https://www.theguardian.com/world/rss"},
        {"name": "NYT (World)", "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"},
        {"name": "Al Jazeera (English)", "url": "https://www.aljazeera.com/xml/rss/all.xml"},
        {"name": "France 24 (English)", "url": "https://www.france24.com/en/rss"},
        {"name": "DW (World)", "url": "https://rss.dw.com/rdf/rss-en-world"},
        {"name": "Reuters (World)", "url": "https://www.reutersagency.com/feed/?best-topics=world-news&post_type=best"},
        {"name": "AP News (World)", "url": "https://newsapi.org/fed/621"},
        {"name": "SCMP (Asia)", "url": "https://www.scmp.com/rss/318208/feed"}
    ]
    
    all_items = []
    
    for feed in rss_feeds:
        try:
            response = requests.get(feed["url"], timeout=10)
            response.encoding = 'utf-8'
            parsed = feedparser.parse(response.text)

            # トークン節約のため、各ソースから最新10件のみに絞る
            for entry in parsed.entries[:10]:
                pub_date_jst = ""
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    try:
                        dt = datetime.utcfromtimestamp(timegm(entry.published_parsed))
                        dt = pytz.utc.localize(dt)
                        # より短い形式にする (MM-DD HH:MM)
                        pub_date_jst = dt.astimezone(JST).strftime("%m-%d %H:%M")
                    except Exception:
                        pub_date_jst = getattr(entry, 'published', '')
                elif hasattr(entry, 'published'):
                    pub_date_jst = entry.published

                # 文字数を制限（200文字以内）
                description = getattr(entry, 'summary', '')
                if description and len(description) > 200:
                    description = description[:197] + "..."

                all_items.append({
                    'title': getattr(entry, 'title', ''),
                    'description': description,
                    'link': getattr(entry, 'link', ''),
                    'source': feed["name"],
                    'pub_date': pub_date_jst
                })
        except Exception as e:
            print(f"⚠️ Error fetching RSS from {feed['name']}: {e}")

    if not all_items:
        print("❌ No news items found.")
        return

    # 重複排除
    unique_items = list({item['link']: item for item in all_items}.values())
    
    # さらにトークン節約のため、全体で80件程度に絞る
    if len(unique_items) > 80:
        unique_items = unique_items[:80]
    
    print(f"🔍 {len(unique_items)}件のニュースから厳選します...")
    summarized_news = get_gemini_summary(unique_items)
    
    if summarized_news:
        # sourceが欠けているother_topicsにURLからメディア名を補完
        for topic in summarized_news.get('other_topics', []):
            if not topic.get('source'):
                topic['source'] = source_from_url(topic.get('url', ''))

        data = {
            'updated_at': datetime.now(JST).isoformat(),
            'total_processed': len(unique_items),
            'articles': summarized_news.get('articles', []),
            'other_topics': summarized_news.get('other_topics', [])
        }
        
        data_dir = os.path.join(basedir, 'data')
        os.makedirs(data_dir, exist_ok=True)
        
        file_path = os.path.join(data_dir, 'featured_article.json')
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        # 日付別アーカイブとして保存
        archive_dir = os.path.join(data_dir, 'news_archive')
        os.makedirs(archive_dir, exist_ok=True)
        archive_date = datetime.now(JST).strftime("%Y-%m-%d")
        archive_path = os.path.join(archive_dir, f'{archive_date}.json')
        with open(archive_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"✅ News updated and saved locally: {file_path}")
        
        # S3への永続化
        if S3_AVAILABLE:
            archive_date = datetime.now(JST).strftime("%Y-%m-%d")
            upload_json_to_s3(data, 'data/featured_article.json')
            upload_json_to_s3(data, f'data/news_archive/{archive_date}.json')
            print("☁️ S3へのバックアップが完了しました")
    else:
        print("❌ Failed to get news summaries.")

if __name__ == "__main__":
    update_news()