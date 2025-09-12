// static/essay_quiz.js - 完成版
// このファイルは、論述問題ページでの「準備運動クイズ」機能専用です

/**
 * クイズ用のモーダル（ポップアップウィンドウ）を生成し、インスタンスを返す関数。
 * モーダルが閉じられた際には、自動的にHTMLから要素を削除する後片付けも行います。
 */
function createQuizModal() {
    // 既存のモーダルがあれば念のため削除
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

    // ★改善点: モーダルが完全に閉じられた時にDOMから削除するイベントリスナー
    modalElement.addEventListener('hidden.bs.modal', () => {
        modalElement.remove();
    }, { once: true });

    return new bootstrap.Modal(modalElement);
}

/**
 * クイズを開始するメインの関数
 * @param {number} problemId - 論述問題のID
 */
async function startWarmUpQuiz(problemId) {
    // 1. サーバーに関連問題のデータを問い合わせる
    const response = await fetch(`/api/essay/get_keywords/${problemId}`);
    const data = await response.json();

    if (data.status !== 'success' || !data.quiz_data || data.quiz_data.length === 0) {
        alert('この問題に関連する一問一答問題が見つかりませんでした。');
        return;
    }

    // 2. クイズモーダルを生成して表示
    const quizModal = createQuizModal();
    quizModal.show();

    // 3. クイズロジックの初期化
    let quizData = data.quiz_data;
    let currentQuestionIndex = 0;
    let correctCount = 0;
    let incorrectCount = 0;
    const quizCardContainer = document.getElementById('quizCardContainer');

    /**
     * ★改善点: 「もう一度挑戦」のためのリセット関数
     * モーダルを再生成せず、中身だけをリセットする
     */
    function resetAndRestartQuiz() {
        currentQuestionIndex = 0;
        correctCount = 0;
        incorrectCount = 0;
        quizData.sort(() => Math.random() - 0.5); // 問題をシャッフル
        showNextQuestion();
    }

    /**
     * 次の問題を表示、または結果を表示する関数
     */
    function showNextQuestion() {
        if (currentQuestionIndex >= quizData.length) {
            showQuizResult();
            return;
        }
        const word = quizData[currentQuestionIndex];
        quizCardContainer.innerHTML = `
            <div id="quizCardContainer">
                <div class="quiz-progress">${currentQuestionIndex + 1} / ${quizData.length} 問</div>
                <div class="quiz-question">${word.question}</div>
                <div class="quiz-answer is-hidden">${word.answer}</div>
                <div class="quiz-buttons">
                    <button class="btn btn-primary" id="warmupShowAnswerBtn">答えを見る</button>
                    <button class="btn btn-success is-hidden" id="warmupCorrectBtn">正解</button>
                    <button class="btn btn-danger is-hidden" id="warmupIncorrectBtn">不正解</button>
                </div>
            </div>
        `;
        setupButtonListeners();
    }

    /**
     * 動的に生成されたボタンにイベントリスナーを設定する関数
     */
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

    /**
     * ユーザーの回答を処理し、スコアを計上する関数
     * @param {boolean} isCorrect - 正解かどうか
     */
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
    
    /**
     * クイズ結果を表示する関数
     */
    function showQuizResult() {
        const accuracy = quizData.length > 0 ? (correctCount / quizData.length * 100).toFixed(1) : 0;
        quizCardContainer.innerHTML = `
            <div id="quizCardContainer">
                <h4>準備運動完了！</h4>
                <p>正解数: ${correctCount} / ${quizData.length} 問</p>
                <p>正答率: ${accuracy}%</p>
                <p>学習結果がスコアに反映されました。</p>
                <button class="btn btn-primary" id="restartWarmupQuizBtn">もう一度挑戦</button>
            </div>
        `;
        // クイズが終わったらサーバーに進捗を保存
        saveQuizProgressToServer();
        // 「もう一度挑戦」ボタンにリセット関数を割り当て
        document.getElementById('restartWarmupQuizBtn').addEventListener('click', resetAndRestartQuiz);
    }

    // 最初の問題を表示
    showNextQuestion();
}


/**
 * ページ読み込み完了時に、準備運動クイズ開始ボタンにイベントリスナーを追加
 */
document.addEventListener('DOMContentLoaded', () => {
    // script.jsからメインの学習履歴がロードされるのを少し待つ
    setTimeout(() => {
        // グローバル変数がなければ安全のために初期化
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