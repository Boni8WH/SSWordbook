import re
import io
from html.parser import HTMLParser

class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = io.StringIO()
    def handle_data(self, d):
        self.text.write(d)
    def get_data(self):
        return self.text.getvalue()

def strip_tags(html_text):
    if not html_text:
        return ""
    s = MLStripper()
    s.feed(html_text)
    return s.get_data()

text_from_user = """中世初期、教皇権は世俗権力と対立し、叙任権闘争においてグレゴリウス7世が神聖ローマ皇帝ハインリヒ4世を屈服させ、その優位を確立した。教皇権は十字軍運動を主導することで権威を高め、13世紀初頭、インノケンティウス3世の時代に最盛期を迎えた。彼は俗権に対する教皇権の至上性を主張し、俗権への介入を強めた。しかし、14世紀初頭、フランス王フィリップ4世と教皇ボニファティウス8世が聖職者課税問題で対立し、教皇が捕縛されるアナーニ事件が発生すると、教皇権は世俗王権に敗北し衰退に転じた。その後、教皇庁はアヴィニョンに移され（教皇のバビロン捕囚）、フランス王権の強い影響下に置かれた。さらに、教皇庁がローマに戻った後、複数の教皇が同時に正統性を主張する教会大分裂（大シスマ）が発生し、教会の権威は決定的に失墜した。この混乱を収束させるため、皇帝ジギスムントの主導でコンスタンツ公会議が開かれ、大分裂は終結したが、公会議主義の台頭により、教皇の絶対的権威は大きく揺らぐこととなった。"""

# Simulated AI Output (Hypothetical, based on user report)
ai_output_full = f"""<div class="model-rewrite">
{text_from_user}
</div>
※リライト案の文字数：399文字
"""

# App Logic Reproduction
rewrite_match = re.search(r'<div class="model-rewrite">(.*?)</div>', ai_output_full, re.DOTALL)
if rewrite_match:
    original_rewrite_html = rewrite_match.group(1)
    original_rewrite_text = strip_tags(original_rewrite_html)
    original_rewrite_text_norm = re.sub(r'\s+', '', original_rewrite_text)
    
    print(f"Original Text Length: {len(original_rewrite_text_norm)}")
    print(f"Text Content: {original_rewrite_text_norm[:20]}...")

    # Check against limit (e.g., 400)
    target_len = 400
    if len(original_rewrite_text_norm) > target_len:
        print(f"-> EXCEEDS LIMIT! ({len(original_rewrite_text_norm)} > {target_len})")
    else:
        print(f"-> WITHIN LIMIT ({len(original_rewrite_text_norm)} <= {target_len})")
else:
    print("No rewrite match found")

# Check Post-Processing Regex (Injection Logic)
# If the AI puts the text INSIDE the div?
ai_output_inside = f"""<div class="model-rewrite">
{text_from_user}
※リライト案の文字数：399文字
</div>"""

print("\n--- Testing Inside Div ---")
rewrite_match_in = re.search(r'<div class="model-rewrite">(.*?)</div>', ai_output_inside, re.DOTALL)
if rewrite_match_in:
    html_in = rewrite_match_in.group(1)
    
    # Pre-clean regex used in app.py logic BEFORE injecting count?
    # Actually, verify what logic is used for clean count vs display.
    
    # Logic in app.py:
    # 1. Check length using `original_rewrite_text = strip_tags(original_rewrite_html)`
    raw_text = strip_tags(html_in)
    norm_text = re.sub(r'\s+', '', raw_text)
    print(f"Length Inside: {len(norm_text)}")
    
    # 2. Injection logic
    # Clean regex: re.sub(r'[（\(【\[［]\s*\d+文字\s*[）\)】\]］]', '', content)
    # Does it match "※リライト案の文字数：399文字" ?
    cleaned_content = re.sub(r'[（\(【\[［]\s*\d+文字\s*[）\)】\]］]', '', html_in)
    
    if "※" in cleaned_content:
        print("Regex FAILED to remove '※...' string")
    else:
        print("Regex SUCCESS removed '※...' string")
