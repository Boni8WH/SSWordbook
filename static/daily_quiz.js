// static/daily_quiz.js

document.addEventListener('DOMContentLoaded', () => {
    const dailyQuizButton = document.getElementById('dailyQuizButton');
    if (dailyQuizButton) {
        dailyQuizButton.addEventListener('click', initializeDailyQuiz);
    }
});

let quizTimerInterval;
let startTime;
const beforeUnloadHandler = (e) => {
    e.preventDefault();
    e.returnValue = '';
};
/**
 * クイズ用のモーダル（ポップアップ）を作成して表示
 */
function createDailyQuizModal() {
    // 既存のモーダルがあれば削除
    const existingModal = document.getElementById('dailyQuizModal');
    if (existingModal) existingModal.remove();

    const modalHTML = `
        <div class="modal fade daily-quiz-modal" id="dailyQuizModal" tabindex="-1">
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title"><i class="fas fa-stopwatch"></i> 今日の10問</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body" id="dailyQuizContainer">
                        <div class="text-center">
                            <div class="spinner-border text-success" role="status">
                                <span class="visually-hidden">Loading...</span>
                            </div>
                            <p class="mt-2">今日の問題を取得中...</p>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">閉じる</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    const modalElement = document.getElementById('dailyQuizModal');
    
    modalElement.addEventListener('hidden.bs.modal', () => {
        clearInterval(quizTimerInterval);
        window.removeEventListener('beforeunload', beforeUnloadHandler);
        modalElement.remove();
    }, { once: true });
    return new bootstrap.Modal(modalElement, {
        backdrop: 'static', // 背景をクリックしても閉じない
        keyboard: false     // Escキーで閉じない
    });
}

/**
 * クイズの初期化処理
 */
async function initializeDailyQuiz() {
    const quizModal = createDailyQuizModal();
    quizModal.show();

    try {
        const response = await fetch('/api/daily_quiz/today');
        const data = await response.json();

        if (data.status !== 'success') {
            throw new Error(data.message);
        }

        if (data.completed) {
            // 既に回答済みの場合
            displayQuizResult(data.user_result, data.top_5_ranking, data.user_rank, data.total_participants);
        } else {
            // これから回答する場合
            runQuiz(data.questions);
        }

    } catch (error) {
        document.getElementById('dailyQuizContainer').innerHTML = `<div class="alert alert-danger">${error.message || '問題の取得に失敗しました。'}</div>`;
    }
}

/**
 * クイズを実行する
 * @param {Array} questions - サーバーから受け取った問題の配列
 */
function runQuiz(questions) {
    let currentQuestionIndex = 0;
    let score = 0;

    const quizContainer = document.getElementById('dailyQuizContainer');
    const modalElement = document.getElementById('dailyQuizModal');
    if (modalElement) {
        // 右上の×ボタンとフッターの閉じるボタンを非表示にする
        modalElement.querySelector('.btn-close').style.display = 'none';
        modalElement.querySelector('.modal-footer .btn-secondary').style.display = 'none';
    }
    window.addEventListener('beforeunload', beforeUnloadHandler);

    function showQuestion() {
        if (currentQuestionIndex >= questions.length) {
            // クイズ終了
            const timeTaken = Date.now() - startTime;
            clearInterval(quizTimerInterval);
            submitQuizResult(score, timeTaken);
            return;
        }

        const q = questions[currentQuestionIndex];
        quizContainer.innerHTML = `
            <div class="quiz-header">
                <span class="quiz-progress-text">${currentQuestionIndex + 1} / ${questions.length}</span>
                <span class="quiz-timer" id="quizTimer">0.00秒</span>
            </div>
            <div class="quiz-question-text">${q.question}</div>
            <div class="quiz-choices">
                ${q.choices.map((choice, index) => `<button class="btn choice-btn" data-choice-index="${index}">${choice}</button>`).join('')}
            </div>
        `;
        
        // 選択肢ボタンにイベントリスナーを設定
        quizContainer.querySelectorAll('.choice-btn').forEach(button => {
            button.addEventListener('click', handleAnswer);
        });
    }

    function handleAnswer(event) {
        const selectedButton = event.target;
        const selectedChoice = selectedButton.textContent;
        const correctAnswer = questions[currentQuestionIndex].answer;

        // 全てのボタンを無効化
        quizContainer.querySelectorAll('.choice-btn').forEach(btn => btn.disabled = true);

        if (selectedChoice === correctAnswer) {
            score++;
            selectedButton.classList.add('correct');
            selectedButton.innerHTML += ' <i class="fas fa-check-circle feedback-icon"></i>';
        } else {
            selectedButton.classList.add('incorrect');
            selectedButton.innerHTML += ' <i class="fas fa-times-circle feedback-icon"></i>';
            // 正解の選択肢をハイライト
            quizContainer.querySelectorAll('.choice-btn').forEach(btn => {
                if (btn.textContent === correctAnswer) {
                    btn.classList.add('correct');
                }
            });
        }
        
        // 1.5秒後に次の問題へ
        setTimeout(() => {
            currentQuestionIndex++;
            showQuestion();
        }, 1500);
    }

    function updateTimer() {
        const elapsed = (Date.now() - startTime) / 1000;
        document.getElementById('quizTimer').textContent = `${elapsed.toFixed(2)}秒`;
    }

    // クイズ開始
    startTime = Date.now();
    quizTimerInterval = setInterval(updateTimer, 50); // 50msごとにタイマー更新
    showQuestion();
}

/**
 * クイズの結果をサーバーに送信
 * @param {number} score - 正解数
 * @param {number} time - かかった時間（ミリ秒）
 */
async function submitQuizResult(score, time) {
    const quizContainer = document.getElementById('dailyQuizContainer');
    quizContainer.innerHTML = `<div class="text-center"><p>結果を送信中...</p></div>`;

    // ページ離脱警告を解除し、閉じるボタンを有効化
    window.removeEventListener('beforeunload', beforeUnloadHandler);
    const modalElement = document.getElementById('dailyQuizModal');
    if (modalElement) {
        // 非表示にしていたボタンを再度表示する
        modalElement.querySelector('.btn-close').style.display = 'block';
        modalElement.querySelector('.modal-footer .btn-secondary').style.display = 'block';
    }

    try {
        // 結果をPOSTで送信し、そのレスポンスに全て含まれているデータを受け取る
        const response = await fetch('/api/daily_quiz/submit', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ score, time }),
        });
        
        const data = await response.json();

        // レスポンスのデータを使って結果を表示
        if (data.status === 'success' && data.completed) {
            displayQuizResult(data.user_result, data.top_5_ranking, data.user_rank, data.total_participants);
        } else {
            // サーバーからのエラーメッセージを表示
            throw new Error(data.message || '結果の表示に失敗しました。');
        }

    } catch (error) {
        quizContainer.innerHTML = `<div class="alert alert-danger">${error.message || '結果の送信に失敗しました。'}</div>`;
    }
}

/**
 * 結果とランキングを表示する
 */
function displayQuizResult(userResult, top5Ranking, userRank, totalParticipants) {
    const quizContainer = document.getElementById('dailyQuizContainer');
    let rankingHTML = '<p class="text-muted text-center mt-3">まだ誰も挑戦していません。</p>';

    if (top5Ranking && top5Ranking.length > 0) {
        // トップ5のテーブルボディを作成
        const tableBodyHTML = top5Ranking.map(r => `
            <tr class="${r.rank === userRank.rank ? 'current-user-rank' : ''}">
                <td>${r.rank}位</td>
                <td>${r.username}</td>
                <td>${r.score}/10</td>
                <td>${r.time}</td>
            </tr>
        `).join('');

        let tableFootHTML = '';
        // もし自分の順位が5位より下なら、...と自分の順位を追加
        if (userRank && userRank.rank > 5) {
            tableFootHTML = `
                <tfoot>
                    <tr class="rank-ellipsis"><td colspan="4">...</td></tr>
                    <tr class="current-user-rank out-of-top5-rank">
                        <td>${userRank.rank}位</td>
                        <td>${userRank.username}</td>
                        <td>${userRank.score}/10</td>
                        <td>${userRank.time}</td>
                    </tr>
                </tfoot>
            `;
        }

        rankingHTML = `
            <table class="table ranking-table mt-3">
                <thead><tr><th>順位</th><th>名前</th><th>スコア</th><th>タイム</th></tr></thead>
                <tbody>
                    ${tableBodyHTML}
                </tbody>
                ${tableFootHTML}
            </table>
            <p class="text-center text-muted mt-2" style="font-size: 0.9em;">参加人数: ${totalParticipants}人</p>
        `;
    }

    quizContainer.innerHTML = `
        <div class="quiz-result-view">
            <h4>本日の結果</h4>
            <div class="result-summary">
                <p>スコア: <span>${userResult.score} / 10</span></p>
                <p>タイム: <span>${userResult.time}</span></p>
                ${userRank ? `<p>現在の順位: <span>${userRank.rank}位</span> / ${totalParticipants}人中</p>` : ''}
            </div>
            <h5>部屋別ランキング (トップ5)</h5>
            ${rankingHTML}
        </div>
    `;
}