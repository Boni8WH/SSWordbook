# 音声入力機能を実装したら、世界史の勉強が「詠唱」になった話

先日の記事で「タイピングだるい」「選択肢問題は甘え」という話をしましたが、ついにやってやりましたよ。
**「音声入力機能」、実装完了です。**

これね、実際に使ってみると完全に**「詠唱」**なんですよ。
画面に向かって「ナポレオン！」とか「ワシントン会議！」とか叫ぶの。周りから見たらヤバい人ですが、学習効果は爆上がり（な気がする）。

今回は、この機能をどうやって実装したのか、実際のコードを交えながら技術的な裏側をガッツリ公開しちゃいます。

---

## なぜ「音声入力」なのか？（そこに愛はあるんか？）

ぶっちゃけ、4択クイズを作るだけなら秒で終わるんです。
でもね、現場で生徒を見ていて一番思うのが、**「わかった気になっている」**ことの多さ。

選択肢があれば正解できる。でも、何もないところから用語が出てこない。
これじゃあ記述模試や論述で戦えないわけです。

かといって、スマホで毎回「マルクス＝アウレリウス＝アントニヌス」とか「王侯将相いずくんぞ種あらんや」とかフリック入力するのは拷問に近い。

そこで**「声」**ですよ。Web Speech API を叩いて、ブラウザに耳を持たせるのです。

## Step 1: ブラウザに「答え」を耳打ちする（Grammar Injection）

Webブラウザには標準で「Web Speech API」という音声認識機能がついています。これを使えば簡単に声を聞き取れる…と思いきや、罠があります。

世界史の用語って、一般的じゃない言葉のオンパレードなんですよ。
例えば「墾田永年私財法」なんて、普通の会話で言いませんよね？
普通に認識させると「今電王ねん取材法」とか謎の変換をしてきやがります。使えねぇ…。

そこで登場するのが、**「Grammar Injection（文法インジェクション）」**という技術。
JSGF (JSpeech Grammar Format) を使って、ブラウザに対して「これからこの単語が来る確率が高いぞ！」と事前に教えてあげるのです。

実際のコード (`static/script.js`) はこんな感じです：

```javascript
// Grammar Support: Bias towards the correct answer AND global vocabulary
// This helps recognition even with slight mispronunciations or difficult words
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

こうすることで、多少滑舌が悪くても、ブラウザくんが「あ、はいはいナポレオンですね！」と空気を読んでくれるようになります。
えっ、それってズルじゃないかって？
いいえ、**「親切設計」**です（キリッ）。

## Step 2: 漢字変換の壁をハックする（Katakana Fallback）

しかし、Grammar Injection だけでは万事解決とはいきませんでした。
最大の敵、**「漢字変換」**です。

正解が「**始皇帝**」のとき、いくら耳打ちしても「**施工程**」と漢字変換して返してくることがあるんです。APIの気分次第で。
これではユーザーが「合ってるのに！！」とブチ切れてしまいます。

そこで実装したのが、**「サーバーサイド・カタカナ・フォールバック」**。
フロントエンド（JS）で正解できなかった場合、諦めずにサーバー（Python）にテキストを送り、「カタカナ」に変換し直してから再判定を行うロジックです。

### サーバー側 (`app.py`)
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

### クライアント側 (`static/script.js`)
JS側では、一度不正解になっても諦めず、このAPIを叩きに行きます。

```javascript
// Default: No match found
// 🆕 Fallback: Server-side Katakana Conversion
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

この「二段構え」により、**「漢字は間違ってるけど、読み方は合ってるからヨシ！」**という、人間の採点官のような柔軟さを実現しました。

## Step 3: 少しのミスは許してあげる（Fuzzy Matching）

人間だもの、噛むことだってあります。
「コンスタンティノープル」を一息で言う自信あります？ 僕は無いです。

そこで、厳密な一致だけでなく、**「レーベンシュタイン距離（編集距離）」**というアルゴリズムを使って、「おしい！」判定も入れています。

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
                    matrix[i][j - 1] + 1,     // 挿入
                    matrix[i - 1][j] + 1      // 削除
                );
            }
        }
    }
    return matrix[b.length][a.length];
}

// 判定ロジックでの使用
const dist = levenshteinDistance(cleanTranscript, target);
// 文字数の30%までのミスなら許容する（Max 3文字）
const threshold = Math.max(3, Math.floor(target.length * 0.3));

if (dist <= threshold) {
    result = { match: true, type: 'fuzzy' }; // "もしかして"扱い
}
```

このロジックのおかげで、例えば「コンスタンティ**ヌ**ープル」と微妙に噛んでも、アプリは優しく「もしかして：コンスタンティノープル？」と聞き返してくれます。バファリンより優しい。

## Step 4: 「複数回答」の罠を攻略する（AND Logic）

最後に一番厄介だったのが、「**ヤルタ・ポツダム**」のように、2つの用語をセットで答える問題です。
これを一息で言おうとすると、間に「えーと」が入ったり、順番が逆になったりで、単純な文字列比較では死にます。

そこで、**「順不同の部分一致判定（ANDロジック）」**を実装しました。

```javascript
if (isSlashMode) {
    // 正解をスラッシュで分割（例：[ヤルタ会談, ポツダム会談]）
    const answerParts = correctAnswer.split('/').map(s => normalize(s));
    
    // Check 1: 全てのパーツが含まれているか確認
    let allAns = true;
    for (const p of answerParts) {
        // containsFuzzy は部分一致＋Levenshtein距離チェックを行う自作ヘルパー
        if (!containsFuzzy(clean, p)) { 
            allAns = false; 
            break; 
        }
    }
    
    if (allAns) return { match: true, type: 'exact' };
}
```

音声認識された長い文字列（`clean`）の中に、分割したパーツ（`answerParts`）が**全て**含まれていれば正解とみなします。
これなら、「ポツダムと…あとヤルタ！」みたいに逆順で答えても、間に余計な言葉が入ってもOK。
柔軟性がすごい。もはや人間の耳より賢いのでは？

## 結論：爆速でアウトプットできる快感

こうして完成した音声入力モード。
実際にやってみると、問題を読んでから回答するまでのサイクルが圧倒的に速い。
そして何より、**声を出すことで記憶の定着が違う（気がする）**。

「カノッサの屈辱！」
「神の見えざる手！」
「サンバルテルミの虐殺！」

深夜に部屋で一人、世界史用語を連呼している姿は完全に不審者ですが、記憶定着のためなら安いものです。

これからも「甘やかさないけど、使いやすい」教材アプリを目指して、ゴリゴリコードを書いていきます。
現場からは以上です。
