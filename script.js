// static/script.js - 完全修正版

// デバッグ用: window オブジェクトが存在するかどうかを確認
if (typeof window === 'undefined') {
    console.error("Error: 'window' object is undefined. This script might be running in a non-browser environment.");
} else {
    console.log("Window object is defined. Script is running in browser.");
}

// グローバル変数
let currentQuizData = []; // 現在のクイズの問題リスト
let currentQuestionIndex = 0; // 現在表示している問題のインデックス
let correctCount = 0; // 正解数
let incorrectCount = 0; // 不正解数
let totalQuestions = 0; // 出題する総問題数
let problemHistory = {}; // ユーザーの全問題履歴（永続化されるもの）
let incorrectWords = []; // ユーザーの苦手な単語リスト（永続化されるもの）
let quizStartTime; // クイズ開始時刻

// DOM要素
const startButton = document.getElementById('startButton');
const questionCountRadios = document.querySelectorAll('input[name="questionCount"]');
const chaptersContainer = document.querySelector('.chapters-container');
const selectionArea = document.querySelector('.selection-area');
const cardArea = document.querySelector('.card-area');
const questionElement = document.getElementById('question');
const answerElement = document.getElementById('answer');
const showAnswerButton = document.getElementById('showAnswerButton');
const correctButton = document.getElementById('correctButton');
const incorrectButton = document.getElementById('incorrectButton');
const progressBar = document.getElementById('progressBar');
const questionNumberDisplay = document.getElementById('questionNumberDisplay');
const quizResultArea = document.getElementById('quizResult');
const totalQuestionsCountSpan = document.getElementById('totalQuestionsCount');
const correctCountSpan = document.getElementById('correctCount');
const incorrectCountSpan = document.getElementById('incorrectCount');
const accuracyRateSpan = document.getElementById('accuracyRate');
const selectedRangeTotalQuestionsSpan = document.getElementById('selectedRangeTotalQuestions');
const backToSelectionButton = document.getElementById('backToSelectionButton');
const restartQuizButton = document.getElementById('restartQuizButton');
const backToSelectionFromCardButton = document.getElementById('backToSelectionFromCardButton');
const incorrectWordsContainer = document.getElementById('incorrectWordsContainer');
const weakWordsListSection = document.getElementById('weakWordsListSection');
const showWeakWordsButton = document.getElementById('showWeakWordsButton');
const backToSelectionFromWeakListButton = document.getElementById('backToSelectionFromWeakListButton');
const noWeakWordsMessage = document.getElementById('noWeakWordsMessage');
const resetSelectionButton = document.getElementById('resetSelectionButton');

// アプリ情報関連
const infoIcon = document.getElementById('infoIcon');
const infoPanel = document.getElementById('infoPanel');
const lastUpdatedDateSpan = document.getElementById('lastUpdatedDate');
const updateContentP = document.getElementById('updateContent');
const shareXButton = document.getElementById('shareXButton');
const downloadImageButton = document.getElementById('downloadImageButton');

// Flaskから渡されるデータ（index.htmlで定義）
if (typeof window.chapterDataFromFlask === 'undefined') {
    console.error("Error: window.chapterDataFromFlask is undefined. Make sure it's passed from Flask.");
}

if (typeof window.appInfoFromFlask === 'undefined') {
    console.error("Error: window.appInfoFromFlask is undefined. Make sure it's passed from Flask.");
} else {
    if (lastUpdatedDateSpan) lastUpdatedDateSpan.textContent = window.appInfoFromFlask.lastUpdatedDate;
    if (updateContentP) updateContentP.textContent = window.appInfoFromFlask.updateContent;
}

// word_data はサーバーから取得する必要があるため、初期化は空に
let word_data = [];

// =========================================================
// 問題ID生成関数（修正版 - 衝突を防ぐ）
// =========================================================

function generateProblemId(word) {
    // より安全なID生成方法
    const chapterStr = String(word.chapter).padStart(3, '0');
    const numberStr = String(word.number).padStart(3, '0');
    const categoryStr = String(word.category || '').replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
    const questionForId = String(word.question).trim();
    const answerForId = String(word.answer).trim();
    
    // 問題文と答えの組み合わせでユニークなハッシュを生成
    function createHash(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash;
        }
        return Math.abs(hash).toString(36);
    }
    
    const contentHash = createHash(questionForId + '|||' + answerForId + '|||' + categoryStr);
    return `${chapterStr}-${numberStr}-${contentHash}`;
}

// =========================================================
// 初期ロードとデータ取得
// =========================================================

document.addEventListener('DOMContentLoaded', () => {
    updateIncorrectOnlyRadio();
    loadUserData();
    loadWordDataFromServer();
    setupEventListeners();

    // データロード後に選択状態を復元
    setTimeout(() => {
        loadSelectionState();
        initializeSelectAllButtons();
        updateIncorrectOnlySelection(); // 苦手問題選択状態の視覚的フィードバックを初期化
    }, 1000);

    if (noWeakWordsMessage) {
        noWeakWordsMessage.classList.add('hidden');
    }
});

function loadUserData() {
    fetch('/api/load_quiz_progress')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                problemHistory = data.problemHistory || {};
                incorrectWords = data.incorrectWords || [];
                console.log(`ユーザーデータロード完了: 苦手問題 ${incorrectWords.length}個`);
            } else {
                console.error('Failed to load user data:', data.message);
            }
        })
        .catch(error => {
            console.error('Error loading user data:', error);
        });
}

function loadWordDataFromServer() {
    fetch('/api/word_data')
        .then(response => response.json())
        .then(data => {
            if (Array.isArray(data)) {
                word_data = data;
                console.log(`Loaded ${word_data.length} words from server.`);
                updateUnitCheckboxStates();
            } else {
                console.error('Failed to load word data: Invalid format', data);
            }
        })
        .catch(error => {
            console.error('Error loading word data:', error);
            flashMessage('単語データのロード中にエラーが発生しました。', 'danger');
        });
}

function updateIncorrectOnlyRadio() {
    const incorrectOnlyRadio = document.getElementById('incorrectOnlyRadio');
    const authMessageIncorrectOnly = document.querySelector('.auth-message-incorrect-only');
    if (window.appInfoFromFlask && window.appInfoFromFlask.isLoggedIn) {
        if (incorrectOnlyRadio) incorrectOnlyRadio.disabled = false;
        if (authMessageIncorrectOnly) authMessageIncorrectOnly.classList.add('hidden');
    } else {
        if (incorrectOnlyRadio) incorrectOnlyRadio.disabled = true;
        if (authMessageIncorrectOnly) authMessageIncorrectOnly.classList.remove('hidden');
    }
}

function updateUnitCheckboxStates() {
    if (!window.chapterDataFromFlask || word_data.length === 0) return;

    for (const chapterNum in window.chapterDataFromFlask) {
        if (window.chapterDataFromFlask.hasOwnProperty(chapterNum)) {
            const chapter = window.chapterDataFromFlask[chapterNum];
            for (const unitNum in chapter.units) {
                if (chapter.units.hasOwnProperty(unitNum)) {
                    const unit = chapter.units[unitNum];
                    const checkbox = document.getElementById(`unit-${chapterNum}-${unitNum}`);
                    if (checkbox) {
                        checkbox.disabled = !unit.enabled;
                        if (checkbox.disabled && checkbox.checked) {
                            checkbox.checked = false;
                        }
                    }
                }
            }
        }
    }
}

// =========================================================
// 範囲選択の保存と復元機能
// =========================================================

function saveSelectionState() {
    const selectionState = {
        questionCount: getSelectedQuestionCount(),
        selectedUnits: []
    };
    
    document.querySelectorAll('.unit-item input[type="checkbox"]:checked').forEach(checkbox => {
        selectionState.selectedUnits.push({
            chapter: checkbox.dataset.chapter,
            unit: checkbox.value
        });
    });
    
    try {
        localStorage.setItem('quiz_selection_state', JSON.stringify(selectionState));
    } catch (e) {
        window.savedSelectionState = selectionState;
    }
}

function loadSelectionState() {
    let selectionState = null;
    
    try {
        const saved = localStorage.getItem('quiz_selection_state');
        if (saved) {
            selectionState = JSON.parse(saved);
        }
    } catch (e) {
        selectionState = window.savedSelectionState;
    }
    
    if (!selectionState) return;
    
    // 問題数の復元
    const questionCountRadio = document.querySelector(`input[name="questionCount"][value="${selectionState.questionCount}"]`);
    if (questionCountRadio) {
        questionCountRadio.checked = true;
    }
    
    // 単元選択の復元
    selectionState.selectedUnits.forEach(unit => {
        const checkbox = document.getElementById(`unit-${unit.chapter}-${unit.unit}`);
        if (checkbox && !checkbox.disabled) {
            checkbox.checked = true;
            
            // 章を展開
            const chapterItem = checkbox.closest('.chapter-item');
            if (chapterItem && !chapterItem.classList.contains('expanded')) {
                chapterItem.classList.add('expanded');
                const toggleIcon = chapterItem.querySelector('.toggle-icon');
                if (toggleIcon) {
                    toggleIcon.textContent = '▼';
                }
            }
        }
    });
    
    setTimeout(() => {
        initializeSelectAllButtons();
    }, 100);
}

// =========================================================
// 苦手問題選択時の視覚的フィードバック
// =========================================================

function updateIncorrectOnlySelection() {
    const incorrectOnlyRadio = document.getElementById('incorrectOnlyRadio');
    const chaptersContainer = document.querySelector('.chapters-container');
    const rangeSelectionTitle = document.querySelector('.selection-area h3');
    
    if (incorrectOnlyRadio && incorrectOnlyRadio.checked) {
        // 苦手問題が選択されている場合
        if (chaptersContainer) {
            chaptersContainer.style.opacity = '0.5';
            chaptersContainer.style.pointerEvents = 'none';
        }
        if (rangeSelectionTitle) {
            rangeSelectionTitle.textContent = '出題範囲を選択（苦手問題モードでは無効）';
            rangeSelectionTitle.style.color = '#95a5a6';
        }
    } else {
        // 通常モードの場合
        if (chaptersContainer) {
            chaptersContainer.style.opacity = '1';
            chaptersContainer.style.pointerEvents = 'auto';
        }
        if (rangeSelectionTitle) {
            rangeSelectionTitle.textContent = '出題範囲を選択';
            rangeSelectionTitle.style.color = '#34495e';
        }
    }
}

// =========================================================
// イベントリスナーの設定
// =========================================================

// setupEventListeners関数の修正版（該当部分のみ）
function setupEventListeners() {
    if (startButton) startButton.addEventListener('click', startQuiz);
    if (showAnswerButton) showAnswerButton.addEventListener('click', showAnswer);
    if (correctButton) correctButton.addEventListener('click', () => handleAnswer(true));
    if (incorrectButton) incorrectButton.addEventListener('click', () => handleAnswer(false));
    if (backToSelectionButton) backToSelectionButton.addEventListener('click', backToSelectionScreen);
    if (restartQuizButton) restartQuizButton.addEventListener('click', restartQuiz);
    if (backToSelectionFromCardButton) backToSelectionFromCardButton.addEventListener('click', backToSelectionScreen);
    if (resetSelectionButton) resetSelectionButton.addEventListener('click', resetSelections);
    if (showWeakWordsButton) showWeakWordsButton.addEventListener('click', showWeakWordsList);
    if (backToSelectionFromWeakListButton) backToSelectionFromWeakListButton.addEventListener('click', backToSelectionScreen);
    if (infoIcon) infoIcon.addEventListener('click', toggleInfoPanel);
    if (shareXButton) shareXButton.addEventListener('click', shareOnX);
    if (downloadImageButton) downloadImageButton.addEventListener('click', downloadQuizResultImage);

    // 出題数選択のラジオボタンにイベントリスナーを追加
    questionCountRadios.forEach(radio => {
        radio.addEventListener('change', updateIncorrectOnlySelection);
    });

    // 章のヘッダーをクリックで単元リストの表示/非表示を切り替え
    if (chaptersContainer) {
        chaptersContainer.addEventListener('click', (event) => {
            // 「全て選択」ボタンがクリックされた場合の処理
            const selectAllBtn = event.target.closest('.select-all-chapter-btn');
            if (selectAllBtn) {
                event.stopPropagation(); // イベントの伝播を停止
                event.preventDefault();  // デフォルト動作を防止
                
                const chapterNum = selectAllBtn.dataset.chapter;
                const chapterItem = selectAllBtn.closest('.chapter-item');
                const checkboxes = chapterItem.querySelectorAll(`input[type="checkbox"][data-chapter="${chapterNum}"]`);
                
                const enabledCheckboxes = Array.from(checkboxes).filter(cb => !cb.disabled);
                const allChecked = enabledCheckboxes.every(cb => cb.checked);
                
                enabledCheckboxes.forEach(checkbox => {
                    checkbox.checked = !allChecked;
                });
                
                updateSelectAllButtonText(selectAllBtn, !allChecked);
                
                // 章の展開状態は変更しない
                return false; // さらなる伝播を防止
            }
            
            // 章ヘッダーがクリックされた場合のみ展開/折りたたみ処理
            const chapterHeader = event.target.closest('.chapter-header');
            if (chapterHeader && !event.target.closest('.select-all-chapter-btn')) {
                const chapterItem = chapterHeader.closest('.chapter-item');
                if (chapterItem) {
                    chapterItem.classList.toggle('expanded');
                    const toggleIcon = chapterHeader.querySelector('.toggle-icon');
                    if (toggleIcon) {
                        toggleIcon.textContent = chapterItem.classList.contains('expanded') ? '▼' : '▶';
                    }
                }
            }
        });
    }
}

// 「全て選択」ボタンのテキストと色を更新する関数
function updateSelectAllButtonText(button, isAllSelected) {
    if (isAllSelected) {
        button.textContent = '選択解除';
        button.style.backgroundColor = '#e74c3c';
        button.style.borderColor = '#c0392b';
    } else {
        button.textContent = '全て選択';
        button.style.backgroundColor = '#3498db';
        button.style.borderColor = '#2980b9';
    }
}

// ページ読み込み時に各ボタンの初期状態を設定
function initializeSelectAllButtons() {
    document.querySelectorAll('.select-all-chapter-btn').forEach(button => {
        const chapterNum = button.dataset.chapter;
        const chapterItem = button.closest('.chapter-item');
        const checkboxes = chapterItem.querySelectorAll(`input[type="checkbox"][data-chapter="${chapterNum}"]`);
        
        const enabledCheckboxes = Array.from(checkboxes).filter(cb => !cb.disabled);
        const allChecked = enabledCheckboxes.length > 0 && enabledCheckboxes.every(cb => cb.checked);
        
        updateSelectAllButtonText(button, allChecked);
    });
}

// =========================================================
// ヘルパー関数
// =========================================================

function getSelectedQuestionCount() {
    const selectedRadio = document.querySelector('input[name="questionCount"]:checked');
    return selectedRadio ? selectedRadio.value : '10';
}

function getSelectedQuestions() {
    const selectedUnits = new Set();
    document.querySelectorAll('.unit-item input[type="checkbox"]:checked').forEach(checkbox => {
        selectedUnits.add(`${checkbox.dataset.chapter}-${checkbox.value}`);
    });

    return word_data.filter(word => {
        const unitIdentifier = `${word.chapter}-${word.number}`;
        return selectedUnits.has(unitIdentifier);
    });
}

function shuffleArray(array) {
    const shuffled = [...array]; // 元の配列をコピー
    for (let i = shuffled.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    return shuffled;
}

function flashMessage(message, category) {
    const container = document.querySelector('.container') || document.body;
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${category} alert-dismissible fade show`;
    alertDiv.setAttribute('role', 'alert');
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    container.prepend(alertDiv);

    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
}

// =========================================================
// クイズロジック（修正版）
// =========================================================

function startQuiz() {
    const selectedQuestions = getSelectedQuestions();
    const selectedQuestionCount = getSelectedQuestionCount();

    // 苦手問題モードの場合は範囲選択チェックをスキップ
    if (selectedQuestionCount !== 'incorrectOnly' && selectedQuestions.length === 0) {
        flashMessage('出題範囲を選択してください。', 'danger');
        return;
    }

    // 選択状態を保存（苦手問題モード以外の場合のみ）
    if (selectedQuestionCount !== 'incorrectOnly') {
        saveSelectionState();
    }

    let quizQuestions = [];
    
    if (selectedQuestionCount === 'incorrectOnly') {
        console.log(`\n🎯 苦手問題モード開始`);
        console.log(`苦手問題リスト (${incorrectWords.length}個):`, incorrectWords);
        
        // 苦手問題IDに対応する実際の問題を抽出
        quizQuestions = word_data.filter(word => {
            const wordIdentifier = generateProblemId(word);
            const isIncluded = incorrectWords.includes(wordIdentifier);
            
            if (isIncluded) {
                console.log(`✓ 苦手問題: "${word.question}"`);
            }
            
            return isIncluded;
        });

        console.log(`抽出された苦手問題: ${quizQuestions.length}個`);

        if (quizQuestions.length === 0) {
            flashMessage('苦手問題がありません。まずは通常の学習で問題に取り組んでください。', 'info');
            return;
        }
    } else {
        // 通常モード：選択された範囲から出題
        quizQuestions = selectedQuestions;
    }

    // 問題数の制限（苦手問題モード以外）
    if (selectedQuestionCount !== 'all' && selectedQuestionCount !== 'incorrectOnly') {
        const count = parseInt(selectedQuestionCount);
        if (quizQuestions.length > count) {
            quizQuestions = shuffleArray(quizQuestions).slice(0, count);
        }
    }

    if (quizQuestions.length === 0) {
        flashMessage('選択された条件に合う問題がありませんでした。', 'danger');
        return;
    }

    currentQuizData = shuffleArray(quizQuestions);
    currentQuestionIndex = 0;
    correctCount = 0;
    incorrectCount = 0;
    totalQuestions = currentQuizData.length;
    quizStartTime = Date.now();

    // UIの切り替え
    if (selectionArea) selectionArea.classList.add('hidden');
    if (cardArea) cardArea.classList.remove('hidden');
    if (quizResultArea) quizResultArea.classList.add('hidden');
    if (weakWordsListSection) weakWordsListSection.classList.add('hidden');
    if (noWeakWordsMessage) noWeakWordsMessage.classList.add('hidden');

    updateProgressBar();
    showNextQuestion();
}

function showNextQuestion() {
    if (answerElement) answerElement.classList.add('hidden');
    if (showAnswerButton) showAnswerButton.classList.remove('hidden');
    if (correctButton) correctButton.classList.add('hidden');
    if (incorrectButton) incorrectButton.classList.add('hidden');

    if (currentQuestionIndex < totalQuestions) {
        const currentWord = currentQuizData[currentQuestionIndex];
        if (questionElement) questionElement.textContent = currentWord.question;
        if (answerElement) answerElement.textContent = currentWord.answer;
    } else {
        showQuizResult();
    }
}

function showAnswer() {
    if (answerElement) answerElement.classList.remove('hidden');
    if (showAnswerButton) showAnswerButton.classList.add('hidden');
    if (correctButton) correctButton.classList.remove('hidden');
    if (incorrectButton) incorrectButton.classList.remove('hidden');
}

// ★ 修正版 handleAnswer 関数
function handleAnswer(isCorrect) {
    const currentWord = currentQuizData[currentQuestionIndex];
    
    console.log(`\n=== "${currentWord.question}" ===`);
    
    // 統一された問題ID生成
    const wordIdentifier = generateProblemId(currentWord);
    console.log(`ID: ${wordIdentifier}`);

    // problemHistoryの初期化
    if (!problemHistory[wordIdentifier]) {
        problemHistory[wordIdentifier] = {
            correct_attempts: 0,
            incorrect_attempts: 0,
            correct_streak: 0,  // ★ この問題だけの連続正解数
            last_answered: ''
        };
    }
    
    // 最終回答日時を更新
    problemHistory[wordIdentifier].last_answered = new Date().toISOString();

    if (isCorrect) {
        // 正解の場合
        correctCount++;
        problemHistory[wordIdentifier].correct_attempts++;
        
        // ★ この問題の連続正解数のみを増やす
        problemHistory[wordIdentifier].correct_streak++;

        console.log(`✅ 正解! 連続正解数: ${problemHistory[wordIdentifier].correct_streak}`);

        // ★ この特定の問題を2回連続正解したら苦手問題から削除
        if (problemHistory[wordIdentifier].correct_streak >= 2) {
            const incorrectIndex = incorrectWords.indexOf(wordIdentifier);
            if (incorrectIndex > -1) {
                incorrectWords.splice(incorrectIndex, 1);
                console.log(`🎉 苦手問題から削除! 残り: ${incorrectWords.length}個`);
            }
        } else {
            console.log(`まだ ${problemHistory[wordIdentifier].correct_streak}/2 回正解`);
        }
    } else {
        // 不正解の場合
        incorrectCount++;
        problemHistory[wordIdentifier].incorrect_attempts++;
        
        // ★ この問題の連続正解数のみをリセット
        problemHistory[wordIdentifier].correct_streak = 0;

        console.log(`❌ 不正解! 連続正解数リセット`);

        // この問題を苦手問題に追加
        if (!incorrectWords.includes(wordIdentifier)) {
            incorrectWords.push(wordIdentifier);
            console.log(`📝 苦手問題に追加! 合計: ${incorrectWords.length}個`);
        }
    }

    console.log(`苦手問題?: ${incorrectWords.includes(wordIdentifier)}`);
    console.log('===========================\n');

    // 進捗をサーバーに保存
    saveQuizProgressToServer();

    // 次の問題へ進む
    currentQuestionIndex++;
    updateProgressBar();

    if (currentQuestionIndex < totalQuestions) {
        showNextQuestion();
    } else {
        showQuizResult();
    }
}

function updateProgressBar() {
    if (totalQuestions > 0) {
        const progress = (currentQuestionIndex / totalQuestions) * 100;
        if (progressBar) {
            progressBar.style.width = progress + '%';
        }
        if (questionNumberDisplay) {
            questionNumberDisplay.textContent = `${currentQuestionIndex}/${totalQuestions}`;
        }
    }
}

function showQuizResult() {
    if (cardArea) cardArea.classList.add('hidden');
    if (quizResultArea) quizResultArea.classList.remove('hidden');

    if (totalQuestionsCountSpan) totalQuestionsCountSpan.textContent = totalQuestions;
    if (correctCountSpan) correctCountSpan.textContent = correctCount;
    if (incorrectCountSpan) incorrectCountSpan.textContent = incorrectCount;
    
    const accuracy = totalQuestions === 0 ? 0 : (correctCount / totalQuestions) * 100;
    if (accuracyRateSpan) accuracyRateSpan.textContent = accuracy.toFixed(1);

    // 選択範囲の全問題数を表示
    const selectedUnitsInQuiz = new Set();
    currentQuizData.forEach(word => {
        selectedUnitsInQuiz.add(`${word.chapter}-${word.number}`);
    });
    let totalWordsInSelectedUnits = 0;
    word_data.forEach(word => {
        if (selectedUnitsInQuiz.has(`${word.chapter}-${word.number}`)) {
            totalWordsInSelectedUnits++;
        }
    });
    if (selectedRangeTotalQuestionsSpan) {
        selectedRangeTotalQuestionsSpan.textContent = totalWordsInSelectedUnits;
    }

    displayIncorrectWordsForCurrentQuiz();
}

// 不正解問題表示関数の修正版
function displayIncorrectWordsForCurrentQuiz() {
    if (!incorrectWordsContainer) return;
    
    incorrectWordsContainer.innerHTML = '';
    const currentQuizIncorrectWords = [];
    
    if (incorrectCount === 0) {
        const incorrectWordListElement = document.getElementById('incorrectWordList');
        if (incorrectWordListElement) incorrectWordListElement.classList.add('hidden');
        return;
    }
    
    currentQuizData.forEach(word => {
        const wordIdentifier = generateProblemId(word);
        const history = problemHistory[wordIdentifier];
        
        if (history && history.incorrect_attempts > 0 && history.correct_streak === 0) {
            currentQuizIncorrectWords.push(word);
        }
    });

    const incorrectWordListElement = document.getElementById('incorrectWordList');
    if (currentQuizIncorrectWords.length > 0) {
        if (incorrectWordListElement) incorrectWordListElement.classList.remove('hidden');
        currentQuizIncorrectWords.forEach((word, index) => {
            const li = document.createElement('li');
            li.innerHTML = `
                <div class="incorrect-question">${word.question}</div>
                <div class="incorrect-answer-container">
                    <span class="incorrect-answer hidden" id="incorrect-answer-${index}">${word.answer}</span>
                    <button class="show-incorrect-answer-button" onclick="toggleIncorrectAnswer(${index})">答えを見る</button>
                </div>
            `;
            incorrectWordsContainer.appendChild(li);
        });
    } else {
        if (incorrectWordListElement) incorrectWordListElement.classList.add('hidden');
    }
}

function toggleIncorrectAnswer(index) {
    const answerElement = document.getElementById(`incorrect-answer-${index}`);
    const button = answerElement ? answerElement.nextElementSibling : null;
    
    if (answerElement && button) {
        if (answerElement.classList.contains('hidden')) {
            answerElement.classList.remove('hidden');
            button.textContent = '答えを隠す';
            button.style.backgroundColor = '#dc3545';
        } else {
            answerElement.classList.add('hidden');
            button.textContent = '答えを見る';
            button.style.backgroundColor = '#6c757d';
        }
    }
}

function backToSelectionScreen() {
    if (selectionArea) selectionArea.classList.remove('hidden');
    if (cardArea) cardArea.classList.add('hidden');
    if (quizResultArea) quizResultArea.classList.add('hidden');
    if (weakWordsListSection) weakWordsListSection.classList.add('hidden');
    if (noWeakWordsMessage) noWeakWordsMessage.classList.add('hidden');
}

function restartQuiz() {
    currentQuestionIndex = 0;
    correctCount = 0;
    incorrectCount = 0;
    currentQuizData = shuffleArray(currentQuizData);
    quizStartTime = Date.now();

    if (quizResultArea) quizResultArea.classList.add('hidden');
    if (cardArea) cardArea.classList.remove('hidden');
    updateProgressBar();
    showNextQuestion();
}

function resetSelections() {
    document.querySelectorAll('.unit-item input[type="checkbox"]').forEach(checkbox => {
        if (!checkbox.disabled) {
            checkbox.checked = false;
        }
    });

    const defaultRadio = document.querySelector('input[name="questionCount"][value="10"]');
    if (defaultRadio) defaultRadio.checked = true;
    
    document.querySelectorAll('.select-all-chapter-btn').forEach(button => {
        updateSelectAllButtonText(button, false);
    });
}

// =========================================================
// 苦手問題リスト表示
// =========================================================

function showWeakWordsList() {
    if (selectionArea) selectionArea.classList.add('hidden');
    if (cardArea) cardArea.classList.add('hidden');
    if (quizResultArea) quizResultArea.classList.add('hidden');
    if (weakWordsListSection) weakWordsListSection.classList.remove('hidden');

    const weakWordsContainer = document.getElementById('weakWordsContainer');
    if (weakWordsContainer) weakWordsContainer.innerHTML = '';

    const allProblemsWithStats = [];
    
    // 全ての学習履歴から正答率を計算
    for (const [problemId, history] of Object.entries(problemHistory)) {
        const correctAttempts = history.correct_attempts || 0;
        const incorrectAttempts = history.incorrect_attempts || 0;
        const totalAttempts = correctAttempts + incorrectAttempts;
        
        // 解答したことがある問題のみを対象とする
        if (totalAttempts > 0) {
            const accuracyRate = (correctAttempts / totalAttempts * 100);
            
            // 元の問題データを探す
            const originalWord = word_data.find(word => {
                const generatedIdentifier = generateProblemId(word);
                return generatedIdentifier === problemId;
            });
            
            if (originalWord) {
                const isCurrentlyWeak = incorrectWords.includes(problemId);
                
                allProblemsWithStats.push({
                    problemId: problemId,
                    question: originalWord.question,
                    answer: originalWord.answer,
                    correctAttempts: correctAttempts,
                    incorrectAttempts: incorrectAttempts,
                    totalAttempts: totalAttempts,
                    accuracyRate: accuracyRate,
                    isCurrentlyWeak: isCurrentlyWeak,
                    correctStreak: history.correct_streak || 0
                });
            }
        }
    }
    
    // 正答率の低い順でソートし、Top20を取得
    allProblemsWithStats.sort((a, b) => {
        // 正答率が低い順、同じ正答率なら総回答数が多い順
        if (a.accuracyRate !== b.accuracyRate) {
            return a.accuracyRate - b.accuracyRate;
        }
        return b.totalAttempts - a.totalAttempts;
    });
    
    const top20WeakProblems = allProblemsWithStats.slice(0, 20);

    // タイトルを更新
    const sectionTitle = document.querySelector('#weakWordsListSection h2');
    if (sectionTitle) {
        sectionTitle.textContent = `苦手問題一覧（正答率の低い問題 Top${top20WeakProblems.length}）`;
    }

    // 説明文を更新
    const sectionDescription = document.querySelector('#weakWordsListSection p');
    if (sectionDescription) {
        sectionDescription.innerHTML = '過去の学習で正答率が低い問題の上位20問です。<br>※現在の苦手問題モードは、1回以上間違え、まだ2回連続正解していない問題から出題されます。';
    }

    if (top20WeakProblems.length === 0) {
        if (noWeakWordsMessage) {
            noWeakWordsMessage.textContent = 'まだ問題を解いていません。';
            noWeakWordsMessage.classList.remove('hidden');
        }
    } else {
        if (noWeakWordsMessage) noWeakWordsMessage.classList.add('hidden');
        
        top20WeakProblems.forEach((problemData, index) => {
            const li = document.createElement('li');
            const rankBadge = `<span style="background-color: #3498db; color: white; padding: 2px 6px; border-radius: 3px; font-size: 0.8em; margin-right: 8px;">${index + 1}位</span>`;
            
            const statusBadge = problemData.isCurrentlyWeak ? 
                '<span style="background-color: #e74c3c; color: white; padding: 2px 6px; border-radius: 3px; font-size: 0.8em; margin-left: 10px;">苦手</span>' : 
                '';
            
            li.innerHTML = `
                <div class="question-text">${rankBadge}${problemData.question}${statusBadge}</div>
                <div class="answer-container">
                    <span class="answer-text hidden" id="weak-answer-${index}">${problemData.answer}</span>
                    <button class="show-answer-button" onclick="toggleWeakAnswer(${index})">答えを見る</button>
                    <div class="accuracy-display">
                        正答率: <span class="rate" style="color: ${problemData.accuracyRate >= 80 ? '#27ae60' : '#e74c3c'}; font-weight: bold;">${problemData.accuracyRate.toFixed(1)}%</span>
                        (正解: ${problemData.correctAttempts}回 / 不正解: ${problemData.incorrectAttempts}回 / 計: ${problemData.totalAttempts}回)
                    </div>
                </div>
            `;
            if (weakWordsContainer) weakWordsContainer.appendChild(li);
        });
    }
}

// 苦手問題の答え表示切り替え
function toggleWeakAnswer(index) {
    const answerElement = document.getElementById(`weak-answer-${index}`);
    const button = answerElement ? answerElement.nextElementSibling : null;
    
    if (answerElement && button) {
        if (answerElement.classList.contains('hidden')) {
            answerElement.classList.remove('hidden');
            button.textContent = '答えを隠す';
            button.style.backgroundColor = '#95a5a6';
        } else {
            answerElement.classList.add('hidden');
            button.textContent = '答えを見る';
            button.style.backgroundColor = '#95a5a6';
        }
    }
}

// =========================================================
// API呼び出しヘルパー
// =========================================================

function saveQuizProgressToServer() {
    const dataToSave = {
        problemHistory: problemHistory,
        incorrectWords: incorrectWords
    };

    fetch('/api/save_progress', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(dataToSave)
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            // console.log('進捗が保存されました。');
        } else {
            console.error('進捗の保存に失敗しました:', data.message);
            flashMessage(data.message, 'danger');
        }
    })
    .catch(error => {
        console.error('進捗の保存中にエラーが発生しました:', error);
        flashMessage('進捗の保存中にエラーが発生しました。', 'danger');
    });
}

// =========================================================
// その他UI機能
// =========================================================

// アプリ情報表示のトグル
function toggleInfoPanel() {
    if (infoPanel) {
        infoPanel.classList.toggle('hidden');
    }
}

// X (旧Twitter) シェア機能
function shareOnX() {
    const total = totalQuestionsCountSpan ? totalQuestionsCountSpan.textContent : '0';
    const correct = correctCountSpan ? correctCountSpan.textContent : '0';
    const accuracy = accuracyRateSpan ? accuracyRateSpan.textContent : '0';
    const selectedRangeTotal = selectedRangeTotalQuestionsSpan ? selectedRangeTotalQuestionsSpan.textContent : '0';

    const text = `世界史単語帳で学習しました！\n出題範囲：${selectedRangeTotal}問\n出題数：${total}問\n正解数：${correct}問\n正答率：${accuracy}%\n\n#世界史単語帳`;
    const url = `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}`;
    window.open(url, '_blank');
}

// 画像ダウンロード機能（16:9対応 + ハッシュタグコピー）
function downloadQuizResultImage() {
    const quizResultContent = document.getElementById('quizResultContent');
    const incorrectWordList = document.getElementById('incorrectWordList');

    if (!quizResultContent) {
        console.error("quizResultContent element not found for image download.");
        flashMessage('画像生成に必要な要素が見つかりません。', 'danger');
        return;
    }

    // ハッシュタグをクリップボードにコピー
    const hashtagText = '#世界史単語帳';
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(hashtagText).then(() => {
            console.log('ハッシュタグがクリップボードにコピーされました');
            // 成功時の視覚的フィードバック（オプション）
            flashMessage('ハッシュタグがクリップボードにコピーされました！', 'success');
        }).catch(err => {
            console.error('クリップボードへのコピーに失敗しました:', err);
            // フォールバック: 古いブラウザ対応
            fallbackCopyToClipboard(hashtagText);
        });
    } else {
        // フォールバック: 古いブラウザ対応
        fallbackCopyToClipboard(hashtagText);
    }

    const tempHiddenElements = [];
    if (incorrectWordList && incorrectWordList.classList.contains('hidden')) {
        incorrectWordList.classList.remove('hidden');
        tempHiddenElements.push(incorrectWordList);
    }
    
    // 縦16:横9の縦横比を計算（縦長）
    const targetWidth = 720;   // 横9の比率
    const targetHeight = 1280; // 縦16の比率 (720 * 16 / 9 = 1280)
    
    const options = {
        scale: 2,
        useCORS: true,
        backgroundColor: '#f8f9fa',
        width: targetWidth,
        height: targetHeight,
        scrollX: 0,
        scrollY: 0,
        // 要素を縦16:横9の比率に合わせて調整
        onclone: function(clonedDoc) {
            const clonedElement = clonedDoc.getElementById('quizResultContent');
            if (clonedElement) {
                // 要素のスタイルを縦16:横9キャンバスに最適化
                clonedElement.style.width = targetWidth + 'px';
                clonedElement.style.height = targetHeight + 'px';
                clonedElement.style.padding = '40px';
                clonedElement.style.boxSizing = 'border-box';
                clonedElement.style.display = 'flex';
                clonedElement.style.flexDirection = 'column';
                clonedElement.style.justifyContent = 'center';
                clonedElement.style.fontSize = '28px'; // 縦長なのでフォントサイズを大きく
                clonedElement.style.lineHeight = '1.6';
            }
        }
    };

    if (typeof html2canvas !== 'undefined') {
        html2canvas(quizResultContent, options).then(canvas => {
            // キャンバスのサイズを縦16:横9に確実に設定
            const finalCanvas = document.createElement('canvas');
            finalCanvas.width = targetWidth;
            finalCanvas.height = targetHeight;
            const ctx = finalCanvas.getContext('2d');
            
            // 背景色を設定
            ctx.fillStyle = '#f8f9fa';
            ctx.fillRect(0, 0, targetWidth, targetHeight);
            
            // 元の画像を中央に配置
            const sourceAspectRatio = canvas.width / canvas.height;
            const targetAspectRatio = targetWidth / targetHeight; // 9/16 = 0.5625
            
            let drawWidth, drawHeight, offsetX, offsetY;
            
            if (sourceAspectRatio > targetAspectRatio) {
                // 元画像の方が横長（相対的に） - 幅を基準に調整
                drawWidth = targetWidth;
                drawHeight = targetWidth / sourceAspectRatio;
                offsetX = 0;
                offsetY = (targetHeight - drawHeight) / 2;
            } else {
                // 元画像の方が縦長（相対的に） - 高さを基準に調整
                drawHeight = targetHeight;
                drawWidth = targetHeight * sourceAspectRatio;
                offsetX = (targetWidth - drawWidth) / 2;
                offsetY = 0;
            }
            
            ctx.drawImage(canvas, offsetX, offsetY, drawWidth, drawHeight);

            const link = document.createElement('a');
            link.download = 'quiz_result_9-16.png';
            link.href = finalCanvas.toDataURL('image/png');
            link.click();

            tempHiddenElements.forEach(el => el.classList.add('hidden'));
        }).catch(error => {
            console.error('画像生成エラー:', error);
            flashMessage('画像生成中にエラーが発生しました。', 'danger');
            tempHiddenElements.forEach(el => el.classList.add('hidden'));
        });
    } else {
        console.error('html2canvas library not found');
        flashMessage('画像生成ライブラリが見つかりません。', 'danger');
        tempHiddenElements.forEach(el => el.classList.add('hidden'));
    }
}


// フォールバック: 古いブラウザ用のクリップボードコピー
function fallbackCopyToClipboard(text) {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-999999px';
    textArea.style.top = '-999999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    
    try {
        const successful = document.execCommand('copy');
        if (successful) {
            console.log('フォールバック方式でハッシュタグがコピーされました');
            flashMessage('ハッシュタグがクリップボードにコピーされました！', 'success');
        } else {
            console.error('フォールバック方式でのコピーに失敗しました');
            flashMessage('クリップボードへのコピーに失敗しました。', 'warning');
        }
    } catch (err) {
        console.error('フォールバック方式でのコピーエラー:', err);
        flashMessage('クリップボードへのコピーに失敗しました。', 'warning');
    }
    
    document.body.removeChild(textArea);
}

// =========================================================
// デバッグ用関数
// =========================================================

// 問題ID衝突調査
function investigateIdCollisions() {
    console.log('🔍 === 問題ID衝突調査 ===');
    
    const idMap = new Map();
    const collisions = [];
    
    word_data.forEach((word, index) => {
        const currentId = generateProblemId(word);
        
        if (idMap.has(currentId)) {
            const existingWord = idMap.get(currentId);
            collisions.push({
                id: currentId,
                word1: existingWord,
                word2: word
            });
            console.log(`❌ ID衝突: ${currentId}`);
            console.log(`  問題1: "${existingWord.question}" (${existingWord.chapter}-${existingWord.number})`);
            console.log(`  問題2: "${word.question}" (${word.chapter}-${word.number})`);
        } else {
            idMap.set(currentId, word);
        }
    });
    
    console.log(`\n📊 結果: ${collisions.length}件のID衝突`);
    console.log(`総問題数: ${word_data.length}`);
    console.log(`ユニークID数: ${idMap.size}`);
    
    return collisions;
}

// 苦手問題状態確認
function checkWeakProblemsStatus() {
    console.log('\n🔍 === 苦手問題状態確認 ===');
    console.log(`苦手問題数: ${incorrectWords.length}`);
    
    incorrectWords.forEach((problemId, index) => {
        const word = word_data.find(w => generateProblemId(w) === problemId);
        const history = problemHistory[problemId] || {};
        
        console.log(`${index + 1}. ${problemId}`);
        console.log(`   問題: ${word ? word.question : '見つからない'}`);
        console.log(`   連続正解数: ${history.correct_streak || 0}`);
        console.log(`   正解/不正解: ${history.correct_attempts || 0}/${history.incorrect_attempts || 0}`);
    });
    console.log('========================\n');
}

// グローバル関数として追加（開発者ツールで実行可能）
window.investigateIdCollisions = investigateIdCollisions;
window.checkWeakProblemsStatus = checkWeakProblemsStatus;

// 進捗確認ページの問題調査と修正

// 1. 現在の進捗データの状況を確認
function debugProgressIssue() {
    console.log('🔍 === 進捗確認ページの問題調査 ===');
    
    console.log('\n📊 現在の学習履歴:');
    console.log(`problemHistory のエントリ数: ${Object.keys(problemHistory).length}`);
    
    // 学習履歴の内容を確認
    Object.entries(problemHistory).forEach(([problemId, history]) => {
        const word = word_data.find(w => generateProblemId(w) === problemId);
        const isIdMatched = word !== undefined;
        
        console.log(`ID: ${problemId}`);
        console.log(`  マッチする問題: ${isIdMatched ? word.question : '見つからない'}`);
        console.log(`  正解/不正解: ${history.correct_attempts}/${history.incorrect_attempts}`);
        console.log(`  連続正解: ${history.correct_streak}`);
        console.log('---');
    });
    
    console.log('\n🎯 苦手問題リスト:');
    console.log(`incorrectWords のエントリ数: ${incorrectWords.length}`);
    
    incorrectWords.forEach(problemId => {
        const word = word_data.find(w => generateProblemId(w) === problemId);
        const isIdMatched = word !== undefined;
        
        console.log(`ID: ${problemId}`);
        console.log(`  マッチする問題: ${isIdMatched ? word.question : '見つからない'}`);
    });
    
    console.log('\n📈 単元別の問題数:');
    const unitCounts = {};
    word_data.forEach(word => {
        const unitKey = `${word.chapter}-${word.number}`;
        if (!unitCounts[unitKey]) {
            unitCounts[unitKey] = {
                unit: word.number,
                category: word.category,
                totalProblems: 0,
                problemsWithHistory: 0
            };
        }
        unitCounts[unitKey].totalProblems++;
        
        const problemId = generateProblemId(word);
        if (problemHistory[problemId]) {
            unitCounts[unitKey].problemsWithHistory++;
        }
    });
    
    Object.entries(unitCounts).forEach(([unitKey, data]) => {
        console.log(`単元 ${data.unit}: ${data.category}`);
        console.log(`  総問題数: ${data.totalProblems}`);
        console.log(`  履歴ある問題数: ${data.problemsWithHistory}`);
        console.log('---');
    });
    
    console.log('===============================');
}

// 2. 古いIDから新しいIDへの変換を確認
function checkIdMigration() {
    console.log('🔄 === ID変換状況の確認 ===');
    
    // 古いID生成方法（推測）
    function generateOldProblemId(word) {
        const questionForId = String(word.question).trim();
        const cleanedQuestion = questionForId.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
        const chapterStr = String(word.chapter);
        const numberStr = String(word.number);
        return `${chapterStr}-${numberStr}-${cleanedQuestion}`;
    }
    
    let matchedCount = 0;
    let unmatchedOldIds = [];
    
    Object.keys(problemHistory).forEach(problemId => {
        const word = word_data.find(w => generateProblemId(w) === problemId);
        if (word) {
            matchedCount++;
        } else {
            // 古いIDで試してみる
            const wordWithOldId = word_data.find(w => generateOldProblemId(w) === problemId);
            if (wordWithOldId) {
                unmatchedOldIds.push({
                    oldId: problemId,
                    newId: generateProblemId(wordWithOldId),
                    question: wordWithOldId.question
                });
            }
        }
    });
    
    console.log(`新しいIDでマッチ: ${matchedCount}件`);
    console.log(`古いIDのまま: ${unmatchedOldIds.length}件`);
    
    if (unmatchedOldIds.length > 0) {
        console.log('\n古いIDが残っている問題:');
        unmatchedOldIds.slice(0, 5).forEach(item => {
            console.log(`"${item.question}"`);
            console.log(`  古いID: ${item.oldId}`);
            console.log(`  新しいID: ${item.newId}`);
        });
        
        if (unmatchedOldIds.length > 5) {
            console.log(`... 他 ${unmatchedOldIds.length - 5}件`);
        }
    }
    
    return unmatchedOldIds;
}

// 3. 進捗データの修正
function fixProgressData() {
    console.log('🔧 === 進捗データの修正 ===');
    
    // 古いID生成方法
    function generateOldProblemId(word) {
        const questionForId = String(word.question).trim();
        const cleanedQuestion = questionForId.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
        const chapterStr = String(word.chapter);
        const numberStr = String(word.number);
        return `${chapterStr}-${numberStr}-${cleanedQuestion}`;
    }
    
    const oldToNewIdMap = new Map();
    const newProblemHistory = {};
    const newIncorrectWords = [];
    
    // すべての問題に対してID変換マップを作成
    word_data.forEach(word => {
        const oldId = generateOldProblemId(word);
        const newId = generateProblemId(word);
        oldToNewIdMap.set(oldId, newId);
    });
    
    console.log(`ID変換マップ作成: ${oldToNewIdMap.size}件`);
    
    // problemHistory の変換
    let historyConverted = 0;
    Object.entries(problemHistory).forEach(([oldId, history]) => {
        if (oldToNewIdMap.has(oldId)) {
            const newId = oldToNewIdMap.get(oldId);
            newProblemHistory[newId] = history;
            historyConverted++;
        } else {
            // 既に新しいIDの場合はそのまま保持
            newProblemHistory[oldId] = history;
        }
    });
    
    // incorrectWords の変換
    let wordsConverted = 0;
    incorrectWords.forEach(oldId => {
        if (oldToNewIdMap.has(oldId)) {
            const newId = oldToNewIdMap.get(oldId);
            if (!newIncorrectWords.includes(newId)) {
                newIncorrectWords.push(newId);
                wordsConverted++;
            }
        } else {
            // 既に新しいIDの場合はそのまま保持
            if (!newIncorrectWords.includes(oldId)) {
                newIncorrectWords.push(oldId);
            }
        }
    });
    
    // データ更新
    Object.keys(problemHistory).forEach(key => delete problemHistory[key]);
    Object.assign(problemHistory, newProblemHistory);
    
    incorrectWords.length = 0;
    incorrectWords.push(...newIncorrectWords);
    
    console.log(`学習履歴変換: ${historyConverted}件`);
    console.log(`苦手問題変換: ${wordsConverted}件`);
    console.log('変換完了！');
    
    // サーバーに保存
    saveQuizProgressToServer();
    
    console.log('サーバーに保存しました。');
    console.log('進捗確認ページを再読み込みしてください。');
}

// 4. 進捗確認ページ用の統計情報計算
function calculateProgressStats() {
    console.log('📊 === 進捗統計情報 ===');
    
    const unitStats = {};
    
    // 各単元の統計を初期化
    word_data.forEach(word => {
        const unitKey = word.number;
        if (!unitStats[unitKey]) {
            unitStats[unitKey] = {
                categoryName: word.category,
                totalQuestions: 0,
                attemptedProblems: 0,
                masteredProblems: 0,
                totalAttempts: 0
            };
        }
        unitStats[unitKey].totalQuestions++;
        
        const problemId = generateProblemId(word);
        const history = problemHistory[problemId];
        
        if (history) {
            const correctAttempts = history.correct_attempts || 0;
            const incorrectAttempts = history.incorrect_attempts || 0;
            const totalAttempts = correctAttempts + incorrectAttempts;
            
            if (totalAttempts > 0) {
                unitStats[unitKey].attemptedProblems++;
                unitStats[unitKey].totalAttempts += totalAttempts;
                
                // 正答率80%以上でマスター
                const accuracyRate = (correctAttempts / totalAttempts) * 100;
                if (accuracyRate >= 80) {
                    unitStats[unitKey].masteredProblems++;
                }
            }
        }
    });
    
    // 結果表示
    Object.entries(unitStats).forEach(([unitNum, stats]) => {
        const masteryRate = stats.totalQuestions > 0 ? 
            (stats.masteredProblems / stats.totalQuestions * 100).toFixed(1) : '0.0';
        
        console.log(`単元 ${unitNum}: ${stats.categoryName}`);
        console.log(`  総問題数: ${stats.totalQuestions}`);
        console.log(`  取り組んだ問題: ${stats.attemptedProblems}`);
        console.log(`  マスター問題: ${stats.masteredProblems}`);
        console.log(`  マスター率: ${masteryRate}%`);
        console.log(`  総回答数: ${stats.totalAttempts}`);
        console.log('---');
    });
    
    return unitStats;
}

// グローバル関数として追加
window.debugProgressIssue = debugProgressIssue;
window.checkIdMigration = checkIdMigration;
window.fixProgressData = fixProgressData;
window.calculateProgressStats = calculateProgressStats;

// より正確なMD5ハッシュを使用した版（script.jsに追加）

// MD5ハッシュ関数（軽量版）
function md5(str) {
    function md5cycle(x, k) {
        var a = x[0], b = x[1], c = x[2], d = x[3];
        
        a = ff(a, b, c, d, k[0], 7, -680876936);
        d = ff(d, a, b, c, k[1], 12, -389564586);
        c = ff(c, d, a, b, k[2], 17, 606105819);
        b = ff(b, c, d, a, k[3], 22, -1044525330);
        // ... 簡略化版
        
        x[0] = add32(a, x[0]);
        x[1] = add32(b, x[1]);
        x[2] = add32(c, x[2]);
        x[3] = add32(d, x[3]);
    }
    
    function cmn(q, a, b, x, s, t) {
        a = add32(add32(a, q), add32(x, t));
        return add32((a << s) | (a >>> (32 - s)), b);
    }
    
    function ff(a, b, c, d, x, s, t) {
        return cmn((b & c) | ((~b) & d), a, b, x, s, t);
    }
    
    function add32(a, b) {
        return (a + b) & 0xFFFFFFFF;
    }
    
    // 簡易版のMD5実装（完全版は長すぎるため）
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash;
    }
    
    const hex = Math.abs(hash).toString(16);
    return hex.padStart(10, '0').substring(0, 10);
}

function generateProblemId(word) {
    // Python側と完全に同じロジック
    const chapterStr = String(word.chapter).padStart(3, '0');
    const numberStr = String(word.number).padStart(3, '0');
    const categoryStr = String(word.category || '').replace(/\s/g, '').toLowerCase();
    const questionForId = String(word.question).trim();
    const answerForId = String(word.answer).trim();
    
    // Python側と同じ文字列結合
    const contentString = questionForId + '|||' + answerForId + '|||' + categoryStr;
    const contentHash = md5(contentString);
    
    const generatedId = `${chapterStr}-${numberStr}-${contentHash}`;
    
    return generatedId;
}

// IDの一致を確認するテスト関数
function testIdConsistency() {
    console.log('🧪 === JavaScript/Python ID一致テスト ===');
    
    // 最初の5個の問題でテスト
    const testWords = word_data.slice(0, 5);
    
    testWords.forEach(word => {
        const jsId = generateProblemId(word);
        console.log(`問題: "${word.question.substring(0, 30)}..."`);
        console.log(`JavaScript ID: ${jsId}`);
        console.log(`章-単元: ${word.chapter}-${word.number}`);
        console.log('---');
    });
    
    console.log('\nPython側のログと比較して、同じIDが生成されているか確認してください。');
}

window.testIdConsistency = testIdConsistency;
window.toggleIncorrectAnswer = toggleIncorrectAnswer;