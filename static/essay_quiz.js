//　論述問題ページでの「準備運動クイズ」機能専用

// クイズ用のモーダル（ポップアップウィンドウ）を生成する関数
// 差し替え後の createQuizModal 関数
function createQuizModal() {
    // 既存のモーダルはここでは削除しない
    const existingModal = document.getElementById('warmUpQuizModal');
    if (existingModal) existingModal.remove();

    const modalHTML = `
        <div class="modal fade" id="warmUpQuizModal" tabindex="-1" aria-labelledby="quizModalLabel" aria-hidden="true">
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title" id="quizModalLabel"><i class="fas fa-running"></i> 準備運動クイズ</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        <div id="quizCardContainer"></div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">クイズを終了</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    const modalElement = document.getElementById('warmUpQuizModal');
    
    // モーダルが完全に閉じられた時にDOMから削除する
    modalElement.addEventListener('hidden.bs.modal', () => {
        modalElement.remove();
    }, { once: true });

    return new bootstrap.Modal(modalElement);
}

// 差し替え後の startWarmUpQuiz 関数
async function startWarmUpQuiz(problemId) {
    const existingModal = document.getElementById('warmUpQuizModal');
    // もし既存のモーダルがあれば、まず正しく閉じる
    if (existingModal) {
        const modalInstance = bootstrap.Modal.getInstance(existingModal);
        if (modalInstance) {
            // hideイベントが完了してから次の処理へ
            await new Promise(resolve => {
                existingModal.addEventListener('hidden.bs.modal', resolve, { once: true });
                modalInstance.hide();
            });
        }
    }
    
    const response = await fetch(`/api/essay/get_keywords/${problemId}`);
    const data = await response.json();

    if (data.status !== 'success' || !data.quiz_data || data.quiz_data.length === 0) {
        alert('この問題に関連する一問一答問題が見つかりませんでした。');
        return;
    }

    const quizModal = createQuizModal();
    quizModal.show();
    
    // (これ以降のクイズロジックは変更なし)
    let currentQuestionIndex = 0;
    let quizData = data.quiz_data;
    let correctCount = 0;
    let incorrectCount = 0;
    const quizCardContainer = document.getElementById('quizCardContainer');

    function showNextQuestion() {
        if (currentQuestionIndex >= quizData.length) {
            showQuizResult();
            return;
        }
        const word = quizData[currentQuestionIndex];
        quizCardContainer.innerHTML = `
            <div class="quiz-progress">${currentQuestionIndex + 1} / ${quizData.length} 問</div>
            <div class="quiz-question">${word.question}</div>
            <div class="quiz-answer is-hidden">${word.answer}</div>
            <div class="quiz-buttons">
                <button class="btn btn-primary" id="warmupShowAnswerBtn">答えを見る</button>
                <button class="btn btn-success is-hidden" id="warmupCorrectBtn">正解</button>
                <button class="btn btn-danger is-hidden" id="warmupIncorrectBtn">不正解</button>
            </div>
        `;
        setupButtonListeners();
    }

    function setupButtonListeners() {
        document.getElementById('warmupShowAnswerBtn').addEventListener('click', () => {
            document.querySelector('#warmUpQuizModal .quiz-answer').classList.remove('is-hidden');
            document.getElementById('warmupShowAnswerBtn').classList.add('is-hidden');
            document.getElementById('warmupCorrectBtn').classList.remove('is-hidden');
            document.getElementById('warmupIncorrectBtn').classList.remove('is-hidden');
        });
        document.getElementById('warmupCorrectBtn').addEventListener('click', () => handleAnswer(true));
        document.getElementById('warmupIncorrectBtn').addEventListener('click', () => handleAnswer(false));
    }

    function handleAnswer(isCorrect) {
        const word = quizData[currentQuestionIndex];
        const problemId = generateProblemId(word);
        if (isCorrect) correctCount++;
        else incorrectCount++;
        if (!window.problemHistory[problemId]) {
            window.problemHistory[problemId] = { correct_attempts: 0, incorrect_attempts: 0, correct_streak: 0 };
        }
        const history = window.problemHistory[problemId];
        if (isCorrect) {
            history.correct_attempts++;
            history.correct_streak++;
            if (history.correct_streak >= 2) {
                const index = window.incorrectWords.indexOf(problemId);
                if (index > -1) window.incorrectWords.splice(index, 1);
            }
        } else {
            history.incorrect_attempts++;
            history.correct_streak = 0;
            if (!window.incorrectWords.includes(problemId)) {
                window.incorrectWords.push(problemId);
            }
        }
        currentQuestionIndex++;
        showNextQuestion();
    }
    
    function showQuizResult() {
        const accuracy = quizData.length > 0 ? (correctCount / quizData.length * 100).toFixed(1) : 0;
        quizCardContainer.innerHTML = `
            <h4>準備運動完了！</h4>
            <p>正解数: ${correctCount} / ${quizData.length} 問</p>
            <p>正答率: ${accuracy}%</p>
            <p>学習結果がスコアに反映されました。</p>
            <button class="btn btn-primary" onclick="startWarmUpQuiz(${problemId})">もう一度挑戦</button>
        `;
        saveQuizProgressToServer();
    }

    showNextQuestion();
}

// クイズを開始するメインの関数
async function startWarmUpQuiz(problemId) {
    // 1. サーバーにキーワードと問題データを問い合わせる
    const response = await fetch(`/api/essay/get_keywords/${problemId}`);
    const data = await response.json();

    if (data.status !== 'success' || !data.quiz_data || data.quiz_data.length === 0) {
        alert('この問題に関連する一問一答問題が見つかりませんでした。');
        return;
    }

    // 2. クイズモーダルを表示
    const quizModal = createQuizModal();
    quizModal.show();

    // 3. クイズロジックの初期化
    let currentQuestionIndex = 0;
    let quizData = data.quiz_data;
    let correctCount = 0;
    let incorrectCount = 0;

    const quizCardContainer = document.getElementById('quizCardContainer');

    // 4. 次の問題を表示する関数
    function showNextQuestion() {
        if (currentQuestionIndex >= quizData.length) {
            showQuizResult();
            return;
        }
        const word = quizData[currentQuestionIndex];
        quizCardContainer.innerHTML = `
            <div class="quiz-progress">${currentQuestionIndex + 1} / ${quizData.length} 問</div>
            <div class="quiz-question">${word.question}</div>
            <div class="quiz-answer is-hidden">${word.answer}</div>
            <div class="quiz-buttons">
                <button class="btn btn-primary" id="warmupShowAnswerBtn">答えを見る</button>
                <button class="btn btn-success is-hidden" id="warmupCorrectBtn">正解</button>
                <button class="btn btn-danger is-hidden" id="warmupIncorrectBtn">不正解</button>
            </div>
        `;
        setupButtonListeners();
    }

    // 5. ボタンのイベントリスナーを設定
    function setupButtonListeners() {
        document.getElementById('warmupShowAnswerBtn').addEventListener('click', () => {
        // is-hidden クラスの付け外しで表示を切り替える
        document.querySelector('#warmUpQuizModal .quiz-answer').classList.remove('is-hidden');
        document.getElementById('warmupShowAnswerBtn').classList.add('is-hidden');
        document.getElementById('warmupCorrectBtn').classList.remove('is-hidden');
        document.getElementById('warmupIncorrectBtn').classList.remove('is-hidden');
    });

        document.getElementById('warmupCorrectBtn').addEventListener('click', () => handleAnswer(true));
        document.getElementById('warmupIncorrectBtn').addEventListener('click', () => handleAnswer(false));
    }

    // 6. 回答を処理する関数
    function handleAnswer(isCorrect) {
        const word = quizData[currentQuestionIndex];
        const problemId = generateProblemId(word); // script.jsの関数を再利用

        // スコアを計上
        if (isCorrect) correctCount++;
        else incorrectCount++;

        // problemHistoryを更新 (script.jsのグローバル変数にアクセス)
        if (!window.problemHistory[problemId]) {
            window.problemHistory[problemId] = { correct_attempts: 0, incorrect_attempts: 0, correct_streak: 0 };
        }
        const history = window.problemHistory[problemId];
        if (isCorrect) {
            history.correct_attempts++;
            history.correct_streak++;
            if (history.correct_streak >= 2) {
                const index = window.incorrectWords.indexOf(problemId);
                if (index > -1) window.incorrectWords.splice(index, 1);
            }
        } else {
            history.incorrect_attempts++;
            history.correct_streak = 0;
            if (!window.incorrectWords.includes(problemId)) {
                window.incorrectWords.push(problemId);
            }
        }
        
        currentQuestionIndex++;
        showNextQuestion();
    }
    
    // 7. クイズ結果を表示する関数
    function showQuizResult() {
        const accuracy = quizData.length > 0 ? (correctCount / quizData.length * 100).toFixed(1) : 0;
        quizCardContainer.innerHTML = `
            <h4>準備運動完了！</h4>
            <p>正解数: ${correctCount} / ${quizData.length} 問</p>
            <p>正答率: ${accuracy}%</p>
            <button class="btn btn-primary" onclick="startWarmUpQuiz(${problemId})">もう一度挑戦</button>
        `;
        // ★重要：クイズが終わったらサーバーに進捗を保存
        saveQuizProgressToServer();
    }

    // 最初の問題を表示
    showNextQuestion();
}

// ページ読み込み時に、準備運動クイズ開始ボタンにイベントリスナーを追加
document.addEventListener('DOMContentLoaded', () => {
    // script.jsからproblemHistoryとincorrectWordsをロードするのを待つ
    setTimeout(() => {
        // グローバル変数がなければ初期化
        if (typeof window.problemHistory === 'undefined') window.problemHistory = {};
        if (typeof window.incorrectWords === 'undefined') window.incorrectWords = [];
        
        const startBtn = document.getElementById('startWarmUpQuizBtn');
        if (startBtn) {
            startBtn.addEventListener('click', () => {
                const problemId = startBtn.dataset.problemId;
                startWarmUpQuiz(problemId);
            });
        }
    }, 1000); // 1秒待ってから実行
});