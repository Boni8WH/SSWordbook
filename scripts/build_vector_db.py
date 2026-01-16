
import os
import sys
import re
import pickle
import threading
import google.generativeai as genai
from dotenv import load_dotenv
import numpy as np

# 親ディレクトリのモジュールをインポートできるようにパスを追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# .envの読み込み（親ディレクトリにある想定）
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY not found in environment variables.")
    sys.exit(1)

genai.configure(api_key=GEMINI_API_KEY)

TEXTBOOK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'textbook.txt')
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'textbook_vectors.pkl')

class TextbookManagerLogic:
    """app.pyからロジックだけ拝借（依存関係回避のため再定義）"""
    def __init__(self):
        self.sections = {} 
        self.toc = []
        self._load_textbook()

    def _load_textbook(self):
        if not os.path.exists(TEXTBOOK_PATH):
            print(f"Textbook file not found at: {TEXTBOOK_PATH}")
            return

        try:
            with open(TEXTBOOK_PATH, 'r', encoding='utf-8') as f:
                content = f.read()

            lines = content.splitlines()
            current_header = "Introduction"
            current_content = []
            
            # app.py と同じ正規表現
            header_pattern = re.compile(r'^(第[０-９0-9]+[部章].*|[０-９0-9]+　.*|●.*|【.*】.*)') 
            
            for line in lines:
                if header_pattern.match(line):
                    if current_content:
                        self.sections[current_header] = "\n".join(current_content)
                        self.toc.append(current_header)
                    current_header = line.strip()
                    current_content = [line]
                else:
                    current_content.append(line)
            
            if current_content:
                self.sections[current_header] = "\n".join(current_content)
                self.toc.append(current_header)
                
            print(f"✅ Textbook loaded: {len(self.toc)} sections parsed.")
            
        except Exception as e:
            print(f"❌ Failed to parse textbook: {e}")

def get_embedding(text):
    """Gemini APIを使ってテキストをベクトル化"""
    try:
        # embedding-001 モデルを使用
        result = genai.embed_content(
            model="models/embedding-001",
            content=text,
            task_type="retrieval_document",
            title="Textbook Section"
        )
        return result['embedding']
    except Exception as e:
        print(f"⚠️ Embedding failed: {e}")
        return None

def build_vector_db():
    print("🚀 Starting Vector DB Build...")
    
    tm = TextbookManagerLogic()
    if not tm.sections:
        print("❌ No sections found. Exiting.")
        return

    vector_db = [] # List of {'title': title, 'content': content, 'vector': vector}
    
    total = len(tm.toc)
    print(f"Processing {total} sections...")
    
    for i, title in enumerate(tm.toc):
        content = tm.sections[title]
        # 内容が短すぎる場合はスキップするか検討（今回はすべて含める）
        
        # テキストを結合（タイトルも含めると検索精度が上がる可能性がある）
        text_to_embed = f"{title}\n{content}"
        
        vector = get_embedding(text_to_embed)
        
        if vector:
            vector_db.append({
                'title': title,
                'content': content,
                'vector': vector
            })
            print(f"[{i+1}/{total}] Embed success: {title}")
        else:
            print(f"[{i+1}/{total}] Embed FAILED: {title}")
            
        # API制限考慮（必要なら）
        # time.sleep(0.1) 

    print(f"✨ Build complete. Saving {len(vector_db)} items to {OUTPUT_PATH}...")
    
    with open(OUTPUT_PATH, 'wb') as f:
        pickle.dump(vector_db, f)
        
    print("✅ Done!")

if __name__ == "__main__":
    build_vector_db()
