function initializeDailyQuiz() {
    const dailyQuizButton = document.getElementById('dailyQuizButton');
    if (dailyQuizButton) {
        dailyQuizButton.addEventListener('click', handleDailyQuizClick);
    }
}

// 「今日の10問」ボタンが押されたときの処理
async function handleDailyQuizClick() {
    // まず、ユーザーが挑戦済みか確認
    const statusRes = await fetch('/api/daily_quiz/status');
    const statusData = await statusRes.json();

    if (statusData.status === 'completed') {
        // 挑戦済みの場合、結果を表示
        displayDailyQuizResults(statusData);
    } else if (statusData.status === 'ready') {
        // 未挑戦の場合、クイズを開始
        startDailyQuiz();
    } else {
        alert(statusData.message || 'エラーが発生しました。');
    }
}

// クイズを開始する
async function startDailyQuiz() {
    const startRes = await fetch('/api/daily_quiz/start');
    const startData = await startRes.json();

    if (startData.status !== 'success') {
        alert(startData.message || 'クイズの開始に失敗しました。');
        return;
    }

    const modal = createDailyQuizModal();
    const modalBody = document.getElementById('dq-modal-body');
    const quizQuestions = startData.quiz_questions;
    let currentQuestionIndex = 0;
    let userAnswers = [];

    // タイマー開始
    timeElapsed = 0;
    quizTimer = setInterval(() => {
        timeElapsed++;
        const timerEl = document.getElementById('dq-timer');
        if(timerEl) timerEl.textContent = `${timeElapsed}秒`;
    }, 1000);

    renderQuestion();

    function renderQuestion() {
        const questionData = quizQuestions[currentQuestionIndex];
        modalBody.innerHTML = `
            <div class="dq-header">
                <span class="dq-progress">${currentQuestionIndex + 1} / ${quizQuestions.length}</span>
                <span class="dq-timer" id="dq-timer">0秒</span>
            </div>
            <div class="dq-question">${questionData.question}</div>
            <div class="dq-choices">
                ${questionData.choices.map((choice, index) => `
                    <button class="dq-choice" data-index="${index}">${choice}</button>
                `).join('')}
            </div>
            <div class="dq-feedback"></div>
        `;

        document.querySelectorAll('.dq-choice').forEach(button => {
            button.addEventListener('click', handleAnswerClick);
        });
    }

    function handleAnswerClick(event) {
        const selectedButton = event.target;
        const selectedAnswer = selectedButton.textContent;
        userAnswers.push(selectedAnswer);

        const questionData = quizQuestions[currentQuestionIndex];
        const correctAnswer = questionData.answer;

        // 全てのボタンを無効化
        document.querySelectorAll('.dq-choice').forEach(btn => btn.disabled = true);

        // 正誤判定
        if (selectedAnswer === correctAnswer) {
            selectedButton.classList.add('correct');
            document.querySelector('.dq-feedback').innerHTML = '<span class="dq-feedback-correct">○ 正解！</span>';
        } else {
            selectedButton.classList.add('incorrect');
            document.querySelector('.dq-feedback').innerHTML = `<span class="dq-feedback-incorrect">× 不正解... 正解は「${correctAnswer}」</span>`;
            // 正解の選択肢をハイライト
            document.querySelectorAll('.dq-choice').forEach(btn => {
                if (btn.textContent === correctAnswer) {
                    btn.classList.add('correct');
                }
            });
        }
        
        // 次の問題へ
        currentQuestionIndex++;
        setTimeout(() => {
            if (currentQuestionIndex < quizQuestions.length) {
                renderQuestion();
            } else {
                clearInterval(quizTimer);
                submitResults();
            }
        }, 1500); // 1.5秒待って次へ
    }

    async function submitResults() {
        modalBody.innerHTML = '<p>結果を集計中です...</p>';
        const submitRes = await fetch('/api/daily_quiz/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ answers: userAnswers, time_taken: timeElapsed })
        });
        const resultData = await submitRes.json();
        
        if (resultData.status === 'success') {
            displayDailyQuizResults(resultData, modal);
        } else {
            modalBody.innerHTML = `<p>結果の送信に失敗しました: ${resultData.message}</p>`;
        }
    }
}

// 結果を表示する
function displayDailyQuizResults(resultData, modalInstance = null) {
    if (!modalInstance) {
        modalInstance = createDailyQuizModal();
    }
    
    const modalBody = document.getElementById('dq-modal-body');
    modalBody.innerHTML = `
        <div class="dq-result-header">今日の10問 結果</div>
        <div class="dq-result-grid">
            <div class="dq-result-item">
                <span class="dq-result-label">正解数</span>
                <span class="dq-result-value">${resultData.score} / ${resultData.total_questions}</span>
            </div>
            <div class="dq-result-item">
                <span class="dq-result-label">タイム</span>
                <span class="dq-result-value">${resultData.time_taken}秒</span>
            </div>
            <div class="dq-result-item">
                <span class="dq-result-label">今日の順位</span>
                <span class="dq-result-value">${resultData.rank}位 / ${resultData.total_challengers}人</span>
            </div>
        </div>
        <div class="dq-result-footer">
            また明日挑戦してください！
        </div>
    `;
    modalInstance.show();
}

// モーダルを生成する
function createDailyQuizModal() {
    const existingModal = document.getElementById('dailyQuizModal');
    if (existingModal) existingModal.remove();

    const modalHTML = `
        <div class="modal fade" id="dailyQuizModal" tabindex="-1">
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content">
                    <div class="modal-body" id="dq-modal-body" style="padding: 2rem;">
                        <p>読み込み中...</p>
                    </div>
                </div>
            </div>
        </div>`;
    document.body.insertAdjacentHTML('beforeend', modalHTML);

    const modalElement = document.getElementById('dailyQuizModal');
    modalElement.addEventListener('hidden.bs.modal', () => modalElement.remove(), { once: true });

    return new bootstrap.Modal(modalElement);
}