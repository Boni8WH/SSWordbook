深夜の「カノッサの屈辱！」が世界史を救う：不審者扱いの先に待つ長期記憶のために
 
世界史学習アプリ開発シリーズ第何弾
 
先日の記事で、一問一答の答え方について、「タイピングだるい」「選択肢問題は甘え」という点に言及しましたが、この問題解決に向けて一歩前進しました。
 
音声入力はじめました～♪（AMEMIYA?）。
 
語学学習アプリだとかではよくみますが、他媒体ではあまり使われないヤツ。
遊び半分でやってみたら思いの外ハマりました。
 
これね、実際に使ってみると完全に「詠唱」なんですよ。
画面に向かって「ナポレオン！」とか「ワシントン会議！」とか叫ぶの。周りから見たらヤバい人ですが、学習効果は爆上がりです。
 
今回は、この機能をどうやって実装したのか、実際のコードを交えながら技術的な側面も公開しちゃいます。
 
なぜ「音声入力」なのか？
 
ぶっちゃけ、4択クイズを作るだけなら秒で終わるんです。
でもね、現場で生徒を見ていて一番思うのが、「わかった気になっている」ことの多さ。
 
選択肢があれば正解できる。でも、何もないところから用語が出てこない。
これじゃあ記述模試や論述で戦えないわけです。
 
かといって、スマホで毎回「マルクス＝アウレリウス＝アントニヌス」とか「王侯将相いずくんぞ種あらんや」とかフリック入力するのは拷問に近い。書き込み機能も実装してもいいが、タブレットや専用のペンを持っていない子にとっては不服な機能…
 
そこで「声」ですよ。Web Speech API を叩いて、ブラウザに耳を持たせるのです。
 
蓮舫「AIじゃダメなんですか？」
 
ダメなんです。
OpenAIのWhisperなど、超絶優秀な音声認識AIはたくさんありますが、あえて「AIに頼らない」選択をしました。理由はシンプル。「反応が遅いから」です。
 
「録音 → サーバーへ送信 → AIが解析 → 結果受信」
 
このフローだと、どれだけ優秀な設計でも1～3秒のタイムラグが生じます。コンマ数秒のテンポで用語を叩き込みたい生徒にとって、この「間」は致命的。詠唱してから魔法が発動するまで3秒も待たされるようでは、学習の熱が冷めてしまいます。そこで、ブラウザが標準装備している「耳」をフル活用することにしました。
 
Step 1: ブラウザに「答え」を耳打ちする（Grammar Injection）
 
Webブラウザには標準で「Web Speech API」という音声認識機能がついています。これを使えば簡単に声を聞き取れる…と思いきや、罠があります。
 
歴史の用語って、一般的じゃない言葉のオンパレードなんですよ。
例えば「墾田永年私財法」なんて、普通の会話で言いませんよね？
普通に認識させると「今電王ねん取材法」とか謎の変換をしてきやがります。私の滑舌が悪いのか、何度「パンジャーブ地方」と言っても「誕生日地方」とかほざくのです。使えねぇ…。
 
そこで登場するのが、「Grammar Injection（文法インジェクション）」という技術。
JSGF (JSpeech Grammar Format) を使って、ブラウザに対して「これからこの単語が来る確率が高いぞ！」と事前に教えてあげるのです。
 
実際のコード (`static/script.js`) はこんな感じです：
 
```javascript
// 文法サポート：正解への偏りとグローバル語彙
// わずかな発音の誤りや難しい単語でも認識をサポート
if (currentQuizData && currentQuizData[currentQuestionIndex]) {
    // 正解データの取得
    const currentData = currentQuizData[currentQuestionIndex];
    const correctAnswer = currentData.answer;
    const correctReading = currentData.reading || ""; // 読み仮名も取得
 
    const SpeechGrammarList = window.SpeechGrammarList || window.webkitSpeechGrammarList;
 
    if (SpeechGrammarList) {
        const speechRecognitionList = new SpeechGrammarList();
 
        // 1. バリエーションの生成（正規化や分割）
        const variations = new Set();
        variations.add(correctAnswer.replace(/[;]/g, '')); // 生の正解
       
        if (correctReading) {
            // 読み仮名があればそれを最優先に追加
            const readingParts = correctReading.split(/[\/,]+/);
            readingParts.forEach(r => variations.add(r.trim()));
        }
 
        // JSGF用に整形
        const variationArray = Array.from(variations)
            .map(v => v.replace(/[;|<>\*\(\)\[\]\/,]/g, '')) // 文法記号を除去
            .filter(v => v.length > 0);
       
        const currentGrammarString = variationArray.join(' | ');
 
        // JSpeech Grammar Format using alternatives
        if (currentGrammarString) {
            const grammar = '#JSGF V1.0; grammar answer; public <answer> = ' + currentGrammarString + ' ;';
 
            // 重み「10」で強力にバイアスをかける
            speechRecognitionList.addFromString(grammar, 10);
            recognition.grammars = speechRecognitionList;
        }
    }
}
```
 
こうすることで、多少滑舌が悪くても、ブラウザくんが
 
「え？アーメンポテト音声？あ、はいはいアメンヘテプ４世ね！」
 
と空気を読んでくれるようになります。
 
えっ、それってズルじゃないかって？
いいえ、「親切設計」です（キリッ）。
 
Step 2: 漢字変換の壁をハックする（Katakana Fallback）
 
しかし、Grammar Injection だけでは万事解決とはいきませんでした。
最大の敵、「漢字変換」です。
 
正解が「始皇帝」のとき、いくら耳打ちしても「施工程」と漢字変換して返してくることがあるんです。APIの気分次第で。
これではユーザーが「合ってるのに！！」とブチ切れてしまいます（間違った漢字変換のままでもそれなりに正しく判定してくれますが、限界はある…）。
 
そこで実装したのが、「サーバーサイド・カタカナ・フォールバック」。
フロントエンド（JS）で正解できなかった場合、諦めずにサーバー（Python）にテキストを送り、「カタカナ」に変換し直してから再判定を行うロジックです。
 
サーバー側 (`app.py`)
Pythonの神ライブラリ `pykakasi` を使って、送られてきた謎の漢字をカタカナに戻します。
 
```python
@app.route('/api/to_katakana', methods=['POST'])
def to_katakana():
    try:
        data = request.get_json()
        text = data.get('text', '')
       
        if not text:
            return jsonify({'status': 'error', 'message': 'No text provided'})
 
        # pykakasiで変換
        kks = pykakasi.kakasi()
        result = kks.convert(text)
       
        # 全てをカタカナ成分だけ結合して返す
        katakana_text = "".join([item['kana'] for item in result])
       
        return jsonify({
            'status': 'success',
            'original': text,
            'katakana': katakana_text
        })
       
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})
```
 
クライアント側 (`static/script.js`)
JS側では、一度不正解になっても諦めず、このAPIを叩きに行きます。
 
```javascript
if (candidates.length > 0) {
    const bestCandidate = candidates[0]; // 最有力候補
 
    // ユーザーに「確認中だよ」と伝える
    if (voiceFeedback) {
        voiceFeedback.innerHTML = `
            <div style="...">
            <i class="fas fa-sync fa-spin"></i> 読み仮名変換で再確認中...
            </div>`;
    }
 
    // APIへGO
    fetch('/api/to_katakana', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: bestCandidate })
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'success') {
            const katakana = data.katakana;
            console.log(`Server conversion: ${bestCandidate} -> ${katakana}`);
 
            // 変換されたカタカナでもう一度判定！
            const res = checkTranscriptMatch(katakana);
            if (res.match) {
                executeSuccess(katakana, res.type); // 起死回生の正解！！
            } else {
                executeFailure();
            }
        } else {
            executeFailure();
        }
    });
}
```
 
この「二段構え」により、「漢字は間違ってるけど、読み方は合ってるからヨシ！」という、柔軟さを実現しました。
 
Step 3: 少しのミスは許してあげる（Fuzzy Matching）
 
人間だもの、噛むことだってあります。
国民会議派カルカッタ大会４綱領だとかを一息で言い切るのが理想ですが、「英貨排斥、スワデーシ、シュワラージ、みんじょく教育…」と多少噛んじゃう時もあるでしょう。
 
そこで、厳密な一致だけでなく、「レーベンシュタイン距離（編集距離）」というアルゴリズムを使って、「おしい！」判定も入れています。
 
レーベンシュタイン距離ってなんぞや？という方は、こちらの記事でわかりやすくまとめられているので読んでみましょう（出題する問題の内容によっては、４択問題の誤選択肢を自動で選んでもらう際にも役に立つヤツです）。
https://note.com/noa813/n/nb7ffd5a8f5e9
 
```javascript
// レーベンシュタイン距離の計算（動的計画法）
function levenshteinDistance(a, b) {
    const matrix = [];
    // 行列の初期化
    for (let i = 0; i <= b.length; i++) matrix[i] = [i];
    for (let j = 0; j <= a.length; j++) matrix[0][j] = j;
 
    // 距離計算
    for (let i = 1; i <= b.length; i++) {
        for (let j = 1; j <= a.length; j++) {
            if (b.charAt(i - 1) == a.charAt(j - 1)) {
                matrix[i][j] = matrix[i - 1][j - 1];
            } else {
                matrix[i][j] = Math.min(
                    matrix[i - 1][j - 1] + 1, // 置換
                    matrix[i][j - 1] + 1,     // 挿入
                    matrix[i - 1][j] + 1      // 削除
                );
            }
        }
    }
    return matrix[b.length][a.length];
}
 
// 判定ロジックでの使用
const dist = levenshteinDistance(cleanTranscript, target);

// 文字数に応じた許容ラインの調整
// 短い単語（4文字以下）は厳しく（1文字ミスまで）、長い単語は少し緩めに
let threshold;
if (target.length <= 4) {
    threshold = 1;
} else {
    threshold = Math.floor(target.length * 0.4); // 40%まで許容
}

if (dist <= threshold) {
    // 3文字以上の単語で、ミスが1文字だけなら「正解」扱いに昇格させる優しさ
    if (dist <= 1 && target.length >= 3) {
        return { match: true, type: 'exact' };
    }
    result = { match: true, type: 'fuzzy' }; // それ以外は "もしかして"扱い
}
```
 
このロジックのおかげで、例えば「コンスタンティヌードル」と微妙に噛んでも、アプリは優しく「もしかして：コンスタンティノープル？」と聞き返してくれます。バファリンより優しい。
 
 
 
バファリン舐めんな。
 
 
 
Step 4: 読める！読めるぞ！（Consonant Skeleton）
 
ところが、レーベンシュタイン距離にも弱点があります。
「母音の間違い」に厳しいんです。
 
例えば、タイの王朝「ラタナコーシン朝」。
これを音声認識させると、なぜか「ラタノコウシンチョウ」とか返ってくることがあります。
 
ラタナコーシンチョウ
ラタノコウシンチョウ
 
人間が見れば「あ、滑舌の問題で母音がズレたな」とわかりますが、プログラムから見ると「ナ(na)→ノ(no)」「ー(-)→ウ(u)」と、文字が全然違う判定を受けてしまい、編集距離が稼げずに不正解になってしまうのです。
 
そこで導入したのが、「子音スケルトンマッチング」。
母音（あいうえお）をすべて剥ぎ取り、子音の骨組み（Skeleton）だけで比較するロジックです。
 
```javascript
// 母音を取り除き、子音の骨格だけを抽出する
const getConsonantSkeleton = (str) => {
    if (!str) return "";
    
    // ローマ字変換風のマッピングで子音を抽出
    let res = "";
    for (let i = 0; i < str.length; i++) {
        const c = str.charAt(i);
        if (/[かきくけこ]/.test(c)) { res += "K"; continue; }
        if (/[さしすせそ]/.test(c)) { res += "S"; continue; }
        if (/[たちつてと]/.test(c)) { res += "T"; continue; }
        // ... (以下略) ...
        if (/[らりるれろ]/.test(c)) { res += "R"; continue; }
        if (/[ん]/.test(c)) { res += "N"; continue; }
    }
    return res;
};

// 判定ロジック
const inputSkeleton = getConsonantSkeleton(input);
const targetSkeleton = getConsonantSkeleton(target);

// 5文字以上の長い単語で、骨格が一致すれば正解！
if (target.length >= 5 && inputSkeleton === targetSkeleton) {
    return { match: true, type: 'exact' }; 
}
```
これぞ、「母音などゴミのようだ」作戦。
不要な文字を捨て去ることで、王家の血筋（正しい正解データ）が導き出されるのです。
このロジックを入れたことで、長いカタカナ語の認識率が劇的に改善します。
 
Step 5: 「複数解答」の罠を攻略する（AND Logic）
最後に一番厄介だったのが、「アルザス、ロレーヌ」のように、2つの用語をセットで答える問題です。
これを一息で言おうとすると、間に「えーと」が入ったり、順番が逆になったりで、単純な文字列比較では死にます。
 
そこで、「順不同の部分一致判定（ANDロジック）」を実装しました。
 
```javascript
if (isSlashMode) {
    // 正解をスラッシュで分割（例：[アルザス/ロレーヌ]）
    const answerParts = correctAnswer.split('/').map(s => normalize(s));
   
    // Check 1: 全てのパーツが含まれているか確認
    let allAns = true;
    for (const p of answerParts) {
        // containsFuzzy は部分一致＋レーベンシュタイン距離チェックを行うヘルパー
        if (!containsFuzzy(clean, p)) {
            allAns = false;
            break;
        }
    }
   
    if (allAns) return { match: true, type: 'exact' };
}
```
 
音声認識された長い文字列（`clean`）の中に、分割したパーツ（`answerParts`）が全て含まれていれば正解とみなします。
これなら、「ロレーヌと…あとアルザス！」みたいに逆順で答えても、間に余計な言葉が入ってもOK。
 
今後の課題：漢字が書けなくなる問題
 
超便利な音声入力。
 
しかーーーし！
 
「あれ、この単語、漢字でどう書くんだっけ？」
 
音声入力は楽ですが、「書く」というプロセスが抜ける分、漢字の定着率が怪しくなるリスクがあります。 「王羲之」とか「羈縻政策」とか、面倒な漢字が多いですからね。
 
なので、次に実装したいのは「漢字確認モード」。音声でサクサク進めつつ、間違えやすい漢字の単語だけは正誤判定後に
 
「溥儀」「溥義」どっち？
「汪兆銘」「汪挑銘」「王兆名」「汪兆名」どれ？
「膠州湾」「広州湾」どっち？
 
と不意打ちで要求してくる機能。
 
「声で即答」＋「追い討ちで確認」。このハイブリッドこそが最強の学習法だと信じています（ただ、最後は実際に書くことが大事）。
 
結論：爆速でアウトプットできる快感
こうして完成した音声入力モード。
実際にやってみると、問題を読んでから解答するまでのサイクルが圧倒的に速い。
そして何より、声を出すことで記憶の定着が違う。
 
「カノッサの屈辱！」
「テトラルキア！」
「サンバルテルミの虐殺！」
 
深夜に部屋で一人、世界史用語を連呼している姿は完全に不審者ですが、記憶定着のためなら安いものです。
 
これからも「甘やかさないけど、使いやすい」アプリを目指していきます。現場からは以上です。