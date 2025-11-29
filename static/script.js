// static/script.js - 完全修正版（全機能保持）

// デバッグ用: window オブジェクトが存在するかどうかを確認
if (typeof window === 'undefined') {
    console.error("Error: 'window' object is undefined. This script might be running in a non-browser environment.");
} else {
    console.log("Window object is defined. Script is running in browser.");
}

// グローバル変数
let currentQuizData = [];
let currentQuestionIndex = 0;
let correctCount = 0;
let incorrectCount = 0;
let totalQuestions = 0;
let problemHistory = {};
let incorrectWords = [];
let quizStartTime;
let isAnswerButtonDisabled = false;
let answerButtonTimeout = null;
let hasBeenRestricted = false; // 一度でも制限されたかのフラグ
let restrictionReleased = false; // 制限が解除されたかのフラグ

// word_data をグローバルに明示的に定義
window.word_data = [];  // この行を追加
let word_data = window.word_data;  // この行も追加

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



// =========================================================
// スマホ対応関数
// =========================================================

// 「全て選択」ボタンのテキストと色を更新する関数（スマホ対応版）
function updateSelectAllButtonText(button, isAllSelected) {
    // ★ 修正: null チェックを追加
    if (!button) {
        console.warn('updateSelectAllButtonText: button parameter is null or undefined');
        return;
    }

    const isMobile = window.innerWidth <= 767;

    if (isAllSelected) {
        button.textContent = isMobile ? '解除' : '選択解除';
        button.style.backgroundColor = '#e74c3c';
        button.style.borderColor = '#c0392b';
        button.classList.add('deselect-mode');
    } else {
        button.textContent = isMobile ? '選択' : '全て選択';
        button.style.backgroundColor = '#3498db';
        button.style.borderColor = '#2980b9';
        button.classList.remove('deselect-mode');
    }
}

// スマホでの表示を最適化するための初期化関数
function initializeMobileOptimizations() {
    // 画面サイズをチェック
    const isMobile = window.innerWidth <= 767;

    if (isMobile) {
        // 「全て選択」ボタンのテキストを短縮
        document.querySelectorAll('.select-all-chapter-btn').forEach(button => {
            const chapterNum = button.dataset.chapter;
            const chapterItem = button.closest('.chapter-item');
            if (chapterItem) {
                const checkboxes = chapterItem.querySelectorAll(`input[type="checkbox"][data-chapter="${chapterNum}"]`);

                const enabledCheckboxes = Array.from(checkboxes).filter(cb => !cb.disabled);
                const allChecked = enabledCheckboxes.length > 0 && enabledCheckboxes.every(cb => cb.checked);

                updateSelectAllButtonText(button, allChecked);
            }
        });

        // テーブルにラッパーを追加してスクロール対応
        const tables = document.querySelectorAll('.progress-container table, .user-list-table');
        tables.forEach(table => {
            // ランキングテーブルでないことを確認
            if (!table.classList.contains('ranking-table') && !table.closest('.table-responsive')) {
                const wrapper = document.createElement('div');
                wrapper.className = 'table-responsive';
                table.parentNode.insertBefore(wrapper, table);
                wrapper.appendChild(table);
            }
        });

        // 長いテキストの省略対応
        const longTexts = document.querySelectorAll('.chapter-title, .unit-item label');
        longTexts.forEach(element => {
            if (element.textContent.length > 20) {
                element.title = element.textContent; // ツールチップで全文表示
            }
        });
    }
}

// 画面サイズ変更時の対応
function handleResize() {
    const isMobile = window.innerWidth <= 767;

    // ボタンテキストの動的変更
    document.querySelectorAll('.select-all-chapter-btn').forEach(button => {
        const chapterNum = button.dataset.chapter;
        const chapterItem = button.closest('.chapter-item');
        if (chapterItem) {
            const checkboxes = chapterItem.querySelectorAll(`input[type="checkbox"][data-chapter="${chapterNum}"]`);

            const enabledCheckboxes = Array.from(checkboxes).filter(cb => !cb.disabled);
            const allChecked = enabledCheckboxes.length > 0 && enabledCheckboxes.every(cb => cb.checked);

            updateSelectAllButtonText(button, allChecked);
        }
    });
}

// スマホでのタッチ操作改善
function improveTouchExperience() {
    // タッチデバイスの検出
    const isTouchDevice = ('ontouchstart' in window) || (navigator.maxTouchPoints > 0);

    if (isTouchDevice) {
        // チェックボックスとラベルのタッチエリア拡大
        document.querySelectorAll('.unit-item').forEach(item => {
            const checkbox = item.querySelector('input[type="checkbox"]');
            const label = item.querySelector('label');

            if (checkbox && label) {
                // ラベルクリックでチェックボックスを切り替え
                label.addEventListener('touchstart', (e) => {
                    e.stopPropagation();
                }, { passive: true });

                label.addEventListener('click', (e) => {
                    if (!checkbox.disabled) {
                        checkbox.checked = !checkbox.checked;
                    }
                    e.preventDefault();
                });
            }
        });

        // 章ヘッダーのタッチフィードバック
        document.querySelectorAll('.chapter-header').forEach(header => {
            header.addEventListener('touchstart', () => {
                header.style.backgroundColor = '#d5dbdb';
            }, { passive: true });

            header.addEventListener('touchend', () => {
                setTimeout(() => {
                    header.style.backgroundColor = '';
                }, 150);
            }, { passive: true });
        });
    }
}

// スクロール最適化（スマホ用）
function optimizeScrolling() {
    const containers = document.querySelectorAll('.chapters-container, .ranking-container, .progress-container');

    containers.forEach(container => {
        // スムーズスクロールの有効化
        container.style.scrollBehavior = 'smooth';

        // iOS Safari のバウンス効果対策
        container.addEventListener('touchstart', (e) => {
            const startY = e.touches[0].clientY;
            const scrollTop = container.scrollTop;
            const maxScroll = container.scrollHeight - container.clientHeight;

            if (scrollTop <= 0 && startY > 0) {
                container.scrollTop = 1;
            } else if (scrollTop >= maxScroll && startY < 0) {
                container.scrollTop = maxScroll - 1;
            }
        }, { passive: true });
    });
}

// =========================================================
// 問題ID生成関数（修正版 - 衝突を防ぐ）
// =========================================================

// script.jsの問題ID生成関数を以下に置き換え（約197行目付近）

// script.js の generateProblemId 関数を以下に置き換え

// script.js の generateProblemId 関数を以下に置き換え
// 既存のID形式に合わせて修正

// script.js の generateProblemId 関数を以下に置き換え

// script.js の generateProblemId 関数を以下に置き換え

function generateProblemId(word) {
    /**
     * 統一された問題ID生成（Python側と完全一致）
     */
    try {
        const chapter = String(word.chapter || '0').padStart(3, '0');
        const number = String(word.number || '0').padStart(3, '0');
        const question = String(word.question || '');
        const answer = String(word.answer || '');

        // 問題文と答えから英数字と日本語文字のみ抽出（Python側と同じ処理）
        const questionClean = question.substring(0, 15).replace(/[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]/g, '');
        const answerClean = answer.substring(0, 10).replace(/[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]/g, '');

        // 統一フォーマット: chapter-number-question-answer
        const problemId = `${chapter}-${number}-${questionClean}-${answerClean}`;

        return problemId;

    } catch (error) {
        console.error('ID生成エラー:', error);
        const chapter = String(word.chapter || '0').padStart(3, '0');
        const number = String(word.number || '0').padStart(3, '0');
        return `${chapter}-${number}-error`;
    }
}

// =========================================================
// 初期ロードとデータ取得
// =========================================================
document.addEventListener('DOMContentLoaded', () => {
    try {
        // ページの準備が完了したこのタイミングで、情報を表示する
        if (typeof window.appInfoFromFlask !== 'undefined') {
            if (lastUpdatedDateSpan) lastUpdatedDateSpan.textContent = window.appInfoFromFlask.lastUpdatedDate;
            if (updateContentP) updateContentP.textContent = window.appInfoFromFlask.updateContent;

            const appInfoTitle = document.getElementById('appInfoTitle');
            if (appInfoTitle) {
                appInfoTitle.textContent = window.appInfoFromFlask.appName || 'アプリ情報';
            }

            const contactSection = document.getElementById('contactSection');
            const contactEmail = document.getElementById('contactEmail');
            if (contactSection && contactEmail && window.appInfoFromFlask.contactEmail) {
                contactEmail.href = 'mailto:' + window.appInfoFromFlask.contactEmail;
                contactEmail.textContent = window.appInfoFromFlask.contactEmail;
                contactSection.style.display = 'block';
            }
        }

        updateIncorrectOnlyRadio();
        loadUserData();
        loadWordDataFromServer();
        setupEventListeners();

        setTimeout(() => {
            loadSelectionState();
            initializeSelectAllButtons();
            initializeMobileOptimizations();
            improveTouchExperience();
            optimizeScrolling();
            updateIncorrectOnlySelection();
        }, 1500);

        if (noWeakWordsMessage) {
            noWeakWordsMessage.classList.add('hidden');
        }
    } catch (error) {
        console.error('❌ 初期化エラー:', error);
    }

    document.addEventListener('keydown', handleEscapeKey);
});

function loadUserData() {
    fetch('/api/load_quiz_progress')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                problemHistory = data.problemHistory || {};
                incorrectWords = data.incorrectWords || [];

                if (data.restrictionState) {
                    hasBeenRestricted = data.restrictionState.hasBeenRestricted || false;
                    restrictionReleased = data.restrictionState.restrictionReleased || false;
                } else {
                    const weakCount = incorrectWords.length;
                    if (weakCount >= 20) {
                        hasBeenRestricted = true;
                        restrictionReleased = false;
                    } else {
                        hasBeenRestricted = false;
                        restrictionReleased = false;
                    }
                }

                setTimeout(() => {
                    updateIncorrectOnlySelection();
                }, 500);
            } else {
                console.error('❌ ユーザーデータ読み込み失敗:', data.message);
            }
        })
        .catch(error => {
            console.error('❌ ユーザーデータ読み込みエラー:', error);
        });
}

// 🆕 制限状態をサーバーに保存する関数を追加
function saveRestrictionState() {
    const restrictionData = {
        hasBeenRestricted: hasBeenRestricted,
        restrictionReleased: restrictionReleased
    };

    console.log('🔄 制限状態をサーバーに保存:', restrictionData);

    fetch('/api/update_restriction_state', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(restrictionData)
    })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                console.log('✅ 制限状態保存成功');
            } else {
                console.error('❌ 制限状態保存失敗:', data.message);
            }
        })
        .catch(error => {
            console.error('❌ 制限状態保存エラー:', error);
        });
}

function loadWordDataFromServer() {
    fetch('/api/word_data')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success' && data.word_data) {
                // 必須フィールドのチェック（クライアント側でもフィルタリング）
                // ★修正: 空白のみのデータも除外
                word_data = data.word_data.filter(w => w.question && w.answer && w.question.trim() !== '' && w.answer.trim() !== '');

                if (data.star_availability) {
                    starProblemStatus = data.star_availability;
                }
                if (data.star_requirements) {
                    starRequirements = data.star_requirements;
                }

            } else if (Array.isArray(data)) {
                word_data = data.filter(w => w.question && w.answer && w.question.trim() !== '' && w.answer.trim() !== '');
            } else {
            }

            updateUnitCheckboxStates();

            setTimeout(() => {
                if (typeof updateStarProblemUI === 'function') {
                    updateStarProblemUI();
                }
                // ★追加：データロード後に制限状態を再評価
                updateIncorrectOnlySelection();
            }, 500);

        })
        .catch(error => {
            console.error('❌ 単語データ読み込みエラー:', error);
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
            let hasEnabledUnits = false;

            for (const unitNum in chapter.units) {
                if (chapter.units.hasOwnProperty(unitNum)) {
                    const unit = chapter.units[unitNum];
                    const checkbox = document.getElementById(`unit-${chapterNum}-${unitNum}`);
                    if (checkbox) {
                        // Z問題の特別処理
                        const isSpecialProblem = unitNum.toUpperCase() === 'Z';  // 変更
                        let isEnabled = unit.enabled;

                        if (isSpecialProblem) {
                            // Z問題の解放状態をリアルタイムでチェック
                            isEnabled = unit.enabled && checkSpecialUnlockClientSide(chapterNum);  // 関数名変更
                        }

                        // 以下既存の処理...
                        if (!isEnabled) {
                            const unitItem = checkbox.closest('.unit-item');
                            if (unitItem) {
                                unitItem.style.display = 'none';
                            }
                        } else {
                            const unitItem = checkbox.closest('.unit-item');
                            if (unitItem) {
                                unitItem.style.display = 'block';
                            }
                            hasEnabledUnits = true;
                        }
                        checkbox.disabled = !isEnabled;
                        if (checkbox.disabled && checkbox.checked) {
                            checkbox.checked = false;
                        }
                    }
                }
            }

            // 章の表示/非表示制御
            const chapterItem = document.querySelector(`.chapter-item[data-chapter="${chapterNum}"]`);
            if (chapterItem) {
                if (hasEnabledUnits) {
                    chapterItem.style.display = 'block';
                } else {
                    chapterItem.style.display = 'none';
                }
            }
        }
    }
}

function checkSpecialUnlockClientSide(chapterNum) {
    // 同じ章の通常問題（Z以外）を取得
    const regularProblems = word_data.filter(word =>
        word.chapter === chapterNum &&
        String(word.number).toUpperCase() !== 'Z'
    );

    if (regularProblems.length === 0) return false;

    // 全ての通常問題がマスターされているかチェック
    for (const word of regularProblems) {
        const problemId = generateProblemId(word);
        const history = problemHistory[problemId];

        if (!history) return false;

        const correct = history.correct_attempts || 0;
        const incorrect = history.incorrect_attempts || 0;
        const total = correct + incorrect;

        if (total === 0 || (correct / total) < 0.8) {
            return false;
        }
    }

    return true;
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
    const rangeSelectionArea = document.querySelector('.range-selection-area');
    const rangeSelectionTitle = document.querySelector('.selection-area h3');
    const questionCountRadios = document.querySelectorAll('input[name="questionCount"]:not(#incorrectOnlyRadio)');

    // ★修正：有効な苦手問題数を使用
    const weakProblemCount = getValidWeakProblemCount();
    const rawWeakProblemCount = incorrectWords.length;

    let stateChanged = false;
    const oldHasBeenRestricted = hasBeenRestricted;
    const oldRestrictionReleased = restrictionReleased;

    // 制限状態の更新ロジック
    if (weakProblemCount >= 20) {
        if (!hasBeenRestricted || restrictionReleased) {
            hasBeenRestricted = true;
            restrictionReleased = false;
            stateChanged = true;
        }
    }

    if (hasBeenRestricted && !restrictionReleased && weakProblemCount <= 10) {
        restrictionReleased = true;
        stateChanged = true;
    }

    // 状態が変更された場合はサーバーに保存
    if (stateChanged) {
        saveRestrictionState();
    }

    // 現在の制限状態判定
    let isCurrentlyRestricted = false;

    if (weakProblemCount >= 20) {
        isCurrentlyRestricted = true;
    } else if (hasBeenRestricted && !restrictionReleased && weakProblemCount >= 11) {
        isCurrentlyRestricted = true;
    } else {
        isCurrentlyRestricted = false;
    }

    if (isCurrentlyRestricted) {
        // 制限発動中
        if (incorrectOnlyRadio) {
            incorrectOnlyRadio.checked = true;
        }

        questionCountRadios.forEach(radio => {
            radio.disabled = true;
            radio.parentElement.style.opacity = '0.5';
        });

        if (rangeSelectionArea) {
            rangeSelectionArea.style.display = 'none';
        }
        if (chaptersContainer) {
            chaptersContainer.style.display = 'none';
        }

        if (weakProblemCount >= 20) {
            showWeakProblemWarning(weakProblemCount);
        } else if (weakProblemCount > 10) {
            showIntermediateWeakProblemWarning(weakProblemCount);
        }

    } else if (incorrectOnlyRadio && incorrectOnlyRadio.checked) {
        // 手動で苦手問題が選択されている場合
        if (rangeSelectionArea) {
            rangeSelectionArea.style.display = 'none';
        }
        if (rangeSelectionTitle) {
            rangeSelectionTitle.textContent = '出題数を選択（苦手問題モードでは無効）';
            rangeSelectionTitle.style.color = '#95a5a6';
        }
    } else {
        // 制限なし（通常モード）
        questionCountRadios.forEach(radio => {
            radio.disabled = false;
            radio.parentElement.style.opacity = '1';
        });

        if (rangeSelectionArea) {
            rangeSelectionArea.style.display = 'block';
        }
        if (chaptersContainer) {
            chaptersContainer.style.display = 'block';
            chaptersContainer.style.opacity = '1';
            chaptersContainer.style.pointerEvents = 'auto';
        }
        if (rangeSelectionTitle) {
            rangeSelectionTitle.textContent = '出題数を選択';
            rangeSelectionTitle.style.color = '#34495e';
        }

        removeWeakProblemWarning();
    }
}

// =========================================================
// イベントリスナーの設定（修正版）
// =========================================================
function setupEventListeners() {
    try {
        if (startButton) startButton.addEventListener('click', startQuiz);
        if (showAnswerButton) {
            showAnswerButton.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();

                if (isAnswerButtonDisabled) {
                    return false;
                }

                showAnswer();
            });
        }
        if (correctButton) correctButton.addEventListener('click', () => handleAnswer(true));
        if (incorrectButton) incorrectButton.addEventListener('click', () => handleAnswer(false));
        if (backToSelectionButton) backToSelectionButton.addEventListener('click', backToSelectionScreen);
        if (restartQuizButton) restartQuizButton.addEventListener('click', restartQuiz);
        if (backToSelectionFromCardButton) backToSelectionFromCardButton.addEventListener('click', backToSelectionScreen);
        if (resetSelectionButton) resetSelectionButton.addEventListener('click', resetSelections);
        // if (showWeakWordsButton) showWeakWordsButton.addEventListener('click', showWeakWordsList); // Removed
        if (backToSelectionFromWeakListButton) backToSelectionFromWeakListButton.addEventListener('click', backToSelectionScreen);
        if (infoIcon) infoIcon.addEventListener('click', toggleInfoPanel);
        if (shareXButton) shareXButton.addEventListener('click', shareOnX);
        if (downloadImageButton) downloadImageButton.addEventListener('click', downloadQuizResultImage);

        questionCountRadios.forEach(radio => {
            radio.addEventListener('change', updateIncorrectOnlySelection);
        });

        if (chaptersContainer) {
            chaptersContainer.addEventListener('click', (event) => {
                // 「全て選択」ボタンがクリックされた場合の処理
                if (event.target.classList.contains('select-all-chapter-btn')) {
                    event.stopPropagation();
                    event.preventDefault();

                    const selectAllBtn = event.target;
                    const chapterNum = selectAllBtn.dataset.chapter;
                    const chapterItem = selectAllBtn.closest('.chapter-item');
                    if (!chapterItem) return;

                    const checkboxes = chapterItem.querySelectorAll(`input[type="checkbox"][data-chapter="${chapterNum}"]`);
                    const enabledCheckboxes = Array.from(checkboxes).filter(cb => !cb.disabled);
                    const allChecked = enabledCheckboxes.every(cb => cb.checked);

                    enabledCheckboxes.forEach(checkbox => {
                        checkbox.checked = !allChecked;
                    });

                    updateSelectAllButtonText(selectAllBtn, !allChecked);
                    return;
                }

                // 章ヘッダーがクリックされた場合の展開/折りたたみ処理
                const chapterHeader = event.target.closest('.chapter-header');
                if (chapterHeader &&
                    !event.target.classList.contains('select-all-chapter-btn') &&
                    !event.target.closest('.select-all-chapter-btn') &&
                    !event.target.closest('input[type="checkbox"]') &&
                    !event.target.closest('label')) {

                    event.stopPropagation();
                    event.preventDefault();

                    const chapterItem = chapterHeader.closest('.chapter-item');
                    if (chapterItem) {
                        const isCurrentlyExpanded = chapterItem.classList.contains('expanded');

                        if (isCurrentlyExpanded) {
                            chapterItem.classList.remove('expanded');
                        } else {
                            chapterItem.classList.add('expanded');
                        }

                        const toggleIcon = chapterHeader.querySelector('.toggle-icon');
                        if (toggleIcon) {
                            toggleIcon.textContent = chapterItem.classList.contains('expanded') ? '▼' : '▶';
                        }

                        if (chapterItem.classList.contains('expanded')) {
                            setTimeout(() => {
                                if (typeof updateStarProblemUI === 'function') {
                                    updateStarProblemUI();
                                }
                            }, 100);
                        }
                    }
                }
            });
        }

    } catch (error) {
        console.error('❌ イベントリスナー設定エラー:', error);
    }
}

// ページ読み込み時に各ボタンの初期状態を設定
function initializeSelectAllButtons() {
    document.querySelectorAll('.select-all-chapter-btn').forEach(button => {
        const chapterNum = button.dataset.chapter;
        const chapterItem = button.closest('.chapter-item');
        if (chapterItem) {
            const checkboxes = chapterItem.querySelectorAll(`input[type="checkbox"][data-chapter="${chapterNum}"]`);

            const enabledCheckboxes = Array.from(checkboxes).filter(cb => !cb.disabled);
            const allChecked = enabledCheckboxes.length > 0 && enabledCheckboxes.every(cb => cb.checked);

            updateSelectAllButtonText(button, allChecked);
        }
    });
}

// =========================================================
// ヘルパー関数
// =========================================================

// ★新規追加：有効な苦手問題数を計算する関数
function getValidWeakProblemCount() {
    if (!word_data || word_data.length === 0) return 0;

    // 現在のword_dataに存在する問題IDのセットを作成
    const validProblemIds = new Set(word_data.map(word => generateProblemId(word)));

    // incorrectWordsのうち、現在も存在する有効なものだけをカウント
    const validWeakProblems = incorrectWords.filter(id => validProblemIds.has(id));

    console.log(`🔍 苦手問題カウント詳細: 全${incorrectWords.length}問中、有効${validWeakProblems.length}問`);
    return validWeakProblems.length;
}

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
// クイズロジック
// =========================================================

let lastQuizSettings = {
    questionCount: null,
    selectedUnits: [],
    isIncorrectOnly: false,
    availableQuestions: [] // 選択範囲の全問題
};

function startQuiz() {
    // ★重要：クイズ開始時に答えを見るボタンの状態を確実にリセット
    isAnswerButtonDisabled = false;
    if (answerButtonTimeout) {
        clearTimeout(answerButtonTimeout);
        answerButtonTimeout = null;
    }
    if (showAnswerButton) {
        showAnswerButton.disabled = false;
        showAnswerButton.style.opacity = '1';
        showAnswerButton.style.cursor = 'pointer';
        showAnswerButton.style.pointerEvents = 'auto';
    }
    console.log('📍 クイズ開始 - 答えを見るボタンの状態をリセット');

    // ★修正：有効な苦手問題数を使用
    const weakProblemCount = getValidWeakProblemCount();
    const rawWeakProblemCount = incorrectWords.length; // 表示用などに元の数も保持
    const selectedQuestionCount = getSelectedQuestionCount();

    // ★修正：制限状態の判定をシンプルに
    const isCurrentlyRestricted = hasBeenRestricted && !restrictionReleased;

    console.log(`startQuiz制限チェック: 有効苦手${weakProblemCount}問(全${rawWeakProblemCount}問), isCurrentlyRestricted=${isCurrentlyRestricted}`);

    // ★修正：制限中は苦手問題モード以外を明確に拒否
    if (isCurrentlyRestricted && selectedQuestionCount !== 'incorrectOnly') {
        if (weakProblemCount >= 20) {
            flashMessage('苦手問題が20問以上あります。まず苦手問題モードで学習してください。', 'danger');
        } else {
            flashMessage(`苦手問題を10問以下に減らすまで、苦手問題モードで学習してください。（現在${weakProblemCount}問）`, 'warning');
        }
        return;
    }

    // 既存のstartQuiz処理を続行...
    const selectedQuestions = getSelectedQuestions();

    // 苦手問題モードの場合は範囲選択チェックをスキップ
    if (selectedQuestionCount !== 'incorrectOnly' && selectedQuestions.length === 0) {
        flashMessage('出題範囲を選択してください。', 'danger');
        return;
    }

    // ★最後のクイズ設定を確実に初期化
    lastQuizSettings = {
        questionCount: selectedQuestionCount,
        isIncorrectOnly: (selectedQuestionCount === 'incorrectOnly'),
        selectedUnits: [],
        availableQuestions: [],
        totalSelectedRangeQuestions: 0  // ★新規追加：選択範囲の正確な問題数
    };

    console.log('🔄 クイズ設定初期化:', lastQuizSettings);

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
            flashMessage('有効な苦手問題がありません。まずは通常の学習で問題に取り組んでください。', 'info');
            return;
        }

        // 苦手問題の場合は利用可能な全問題として保存
        lastQuizSettings.availableQuestions = [...quizQuestions];
        lastQuizSettings.totalSelectedRangeQuestions = quizQuestions.length;  // ★苦手問題の総数

    } else {
        // 通常モード：選択された範囲から出題
        console.log('\n📚 通常モード開始');

        // ★重要：選択された単元情報を保存（getSelectedQuestions実行前に）
        document.querySelectorAll('.unit-item input[type="checkbox"]:checked').forEach(checkbox => {
            lastQuizSettings.selectedUnits.push({
                chapter: checkbox.dataset.chapter,
                unit: checkbox.value
            });
        });

        quizQuestions = selectedQuestions;

        // ★重要：選択範囲の全問題数を正確に計算
        const selectedUnitIds = new Set();
        lastQuizSettings.selectedUnits.forEach(unit => {
            selectedUnitIds.add(`${unit.chapter}-${unit.unit}`);
        });

        // 選択された単元に含まれる全問題をカウント
        const allQuestionsInSelectedRange = word_data.filter(word => {
            return selectedUnitIds.has(`${word.chapter}-${word.number}`);
        });

        lastQuizSettings.availableQuestions = [...allQuestionsInSelectedRange];
        lastQuizSettings.totalSelectedRangeQuestions = allQuestionsInSelectedRange.length;  // ★正確な選択範囲数

        console.log(`📊 選択範囲詳細:`);
        console.log(`  選択単元数: ${lastQuizSettings.selectedUnits.length}`);
        console.log(`  選択範囲の全問題数: ${lastQuizSettings.totalSelectedRangeQuestions}問`);
        console.log(`  実際の出題対象: ${quizQuestions.length}問`);
    }

    // 選択状態を保存（苦手問題モード以外の場合のみ）
    if (selectedQuestionCount !== 'incorrectOnly') {
        saveSelectionState();
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

    // ★最終安全チェック：空の問題を除外
    quizQuestions = quizQuestions.filter(q => q.question && q.answer && q.question.trim() !== '' && q.answer.trim() !== '');
    if (quizQuestions.length === 0) {
        flashMessage('有効な問題が見つかりませんでした。', 'danger');
        return;
    }

    currentQuizData = shuffleArray(quizQuestions);
    currentQuestionIndex = 0;

    // ★デバッグログ: 最初の問題をチェック
    if (currentQuizData.length > 0) {
        console.log('🔍 クイズ開始: 最初の問題データ', currentQuizData[0]);
        console.log('   Question:', currentQuizData[0].question);
        console.log('   Answer:', currentQuizData[0].answer);
        console.log('   Question Type:', typeof currentQuizData[0].question);
        console.log('   Question Length:', currentQuizData[0].question.length);
        console.log('   Question CharCodes:', currentQuizData[0].question.split('').map(c => c.charCodeAt(0)));
    }

    correctCount = 0;
    incorrectCount = 0;
    totalQuestions = currentQuizData.length;
    quizStartTime = Date.now();

    console.log('✅ クイズ開始設定完了:', {
        mode: lastQuizSettings.isIncorrectOnly ? '苦手問題' : '通常',
        totalQuestions: totalQuestions,
        totalSelectedRangeQuestions: lastQuizSettings.totalSelectedRangeQuestions,
        availableQuestions: lastQuizSettings.availableQuestions.length
    });

    // UIの切り替え
    if (selectionArea) selectionArea.classList.add('hidden');
    if (cardArea) cardArea.classList.remove('hidden');
    if (quizResultArea) quizResultArea.classList.add('hidden');
    // weakWordsListSection reference removed
    if (noWeakWordsMessage) noWeakWordsMessage.classList.add('hidden');

    updateProgressBar();
    showNextQuestion();
}


function restartWeakProblemsQuiz() {
    console.log('\n🎯 苦手問題モード専用再学習');

    // ★既存のお祝いメッセージがあれば削除
    const existingCelebration = document.querySelector('.no-weak-problems-celebration');
    if (existingCelebration) {
        existingCelebration.remove();
    }

    // 最新の苦手問題リストを取得
    const currentWeakProblems = word_data.filter(word => {
        const wordIdentifier = generateProblemId(word);
        return incorrectWords.includes(wordIdentifier);
    });

    console.log(`現在の苦手問題数: ${currentWeakProblems.length}`);
    console.log(`前回の問題数: ${currentQuizData.length}`);

    if (currentWeakProblems.length === 0) {
        // 苦手問題がなくなった場合
        showNoWeakProblemsMessage();
        return;
    }

    // 前回解いた問題のうち、まだ苦手問題として残っているものをチェック
    const stillWeakFromLastQuiz = currentQuizData.filter(word => {
        const wordIdentifier = generateProblemId(word);
        return incorrectWords.includes(wordIdentifier);
    });

    console.log(`前回の問題で依然苦手: ${stillWeakFromLastQuiz.length}問`);

    // ★改善メッセージを控えめに表示
    if (stillWeakFromLastQuiz.length < currentQuizData.length) {
        const improvedCount = currentQuizData.length - stillWeakFromLastQuiz.length;
        flashMessage(`✨ ${improvedCount}問の苦手問題を克服しました！`, 'success');
    }

    // 新しい苦手問題セットでクイズを開始
    currentQuizData = shuffleArray(currentWeakProblems);
    currentQuestionIndex = 0;
    correctCount = 0;
    incorrectCount = 0;
    totalQuestions = currentQuizData.length;
    quizStartTime = Date.now();

    console.log(`✅ 新しい苦手問題セット: ${totalQuestions}問`);

    // UIの切り替え
    if (quizResultArea) quizResultArea.classList.add('hidden');
    if (cardArea) cardArea.classList.remove('hidden');

    updateProgressBar();
    showNextQuestion();
}

function clearPreviousCelebrationMessages() {
    const existingCelebrations = document.querySelectorAll('.no-weak-problems-celebration');
    existingCelebrations.forEach(element => {
        element.remove();
    });
}

function showNoWeakProblemsMessage() {
    // ★重要：既存のお祝いメッセージを削除
    const existingCelebration = document.querySelector('.no-weak-problems-celebration');
    if (existingCelebration) {
        existingCelebration.remove();
        console.log('🧹 既存のお祝いメッセージを削除しました');
    }

    // ★シンプルなデザインのメッセージを作成
    const messageDiv = document.createElement('div');
    messageDiv.className = 'no-weak-problems-celebration';
    messageDiv.innerHTML = `
        <div style="text-align: center; padding: 25px; background-color: #f8f9fa; border: 2px solid #28a745; border-radius: 8px; margin: 20px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
            <div style="font-size: 3em; margin-bottom: 15px;">🎉</div>
            <h3 style="margin: 0 0 10px 0; color: #28a745; font-size: 1.4em;">おめでとうございます！</h3>
            <p style="color: #495057; margin: 10px 0; font-size: 1.1em;">苦手問題を全て克服しました</p>
            <p style="color: #6c757d; margin: 15px 0; font-size: 0.95em;">新しい問題に挑戦して、さらに学習を進めましょう。</p>
            <button onclick="backToSelectionScreen()" class="btn btn-success" style="margin-top: 15px; padding: 10px 25px; font-weight: 600;">
                <i class="fas fa-arrow-left"></i> 新しい範囲を選択する
            </button>
        </div>
    `;

    // ★quizResultAreaの先頭に挿入（既存コンテンツの前に）
    if (quizResultArea) {
        const firstChild = quizResultArea.firstChild;
        if (firstChild) {
            quizResultArea.insertBefore(messageDiv, firstChild);
        } else {
            quizResultArea.appendChild(messageDiv);
        }
    }

    console.log('🎉 苦手問題完全克服のメッセージを表示しました');

    // ★フラッシュメッセージも表示
    flashMessage('🎉 すべての苦手問題を克服しました！', 'success');
}

function showNextQuestion() {
    if (answerElement) answerElement.classList.add('hidden');
    if (showAnswerButton) showAnswerButton.classList.remove('hidden');
    if (correctButton) correctButton.classList.add('hidden');
    if (incorrectButton) incorrectButton.classList.add('hidden');

    // 答えを見るボタンを1.5秒間無効化（最初の問題以外）
    if (currentQuestionIndex > 0) {
        isAnswerButtonDisabled = true;
        if (showAnswerButton) {
            showAnswerButton.disabled = true;
            showAnswerButton.style.opacity = '0.5';
            showAnswerButton.style.cursor = 'not-allowed';
            showAnswerButton.style.pointerEvents = 'none';
        }

        if (answerButtonTimeout) {
            clearTimeout(answerButtonTimeout);
        }

        answerButtonTimeout = setTimeout(() => {
            isAnswerButtonDisabled = false;
            if (showAnswerButton) {
                showAnswerButton.disabled = false;
                showAnswerButton.style.opacity = '1';
                showAnswerButton.style.cursor = 'pointer';
                showAnswerButton.style.pointerEvents = 'auto';
            }
        }, 1500);
    }

    if (currentQuestionIndex < totalQuestions) {
        const currentWord = currentQuizData[currentQuestionIndex];
        console.log(`🔍 showNextQuestion: Index ${currentQuestionIndex}`, currentWord);

        if (questionElement) {
            console.log('   Setting question text to:', currentWord.question);
            questionElement.textContent = currentWord.question;
            // 強制再描画
            questionElement.style.display = 'none';
            questionElement.offsetHeight; // trigger reflow
            questionElement.style.display = 'block';
        } else {
            console.error('❌ questionElement not found!');
        }

        if (answerElement) answerElement.textContent = currentWord.answer;
    } else {
        showQuizResult();
    }
}

function showAnswer() {
    // ★新機能：無効化中は処理を停止
    if (isAnswerButtonDisabled) {
        console.log('答えを見るボタンは無効化中です');
        return;
    }

    if (answerElement) answerElement.classList.remove('hidden');
    if (showAnswerButton) showAnswerButton.classList.add('hidden');
    if (correctButton) correctButton.classList.remove('hidden');
    if (incorrectButton) incorrectButton.classList.remove('hidden');
}

function handleAnswer(isCorrect) {
    const currentWord = currentQuizData[currentQuestionIndex];

    if (!currentWord) {
        console.error('handleAnswer: currentWord is undefined');
        return;
    }

    const wordIdentifier = generateProblemId(currentWord);

    if (!problemHistory[wordIdentifier]) {
        problemHistory[wordIdentifier] = {
            correct_attempts: 0,
            incorrect_attempts: 0,
            correct_streak: 0,
            last_answered: ''
        };
    }

    problemHistory[wordIdentifier].last_answered = new Date().toISOString();

    if (isCorrect) {
        correctCount++;
        problemHistory[wordIdentifier].correct_attempts++;
        problemHistory[wordIdentifier].correct_streak++;

        if (problemHistory[wordIdentifier].correct_streak >= 2) {
            const incorrectIndex = incorrectWords.indexOf(wordIdentifier);
            if (incorrectIndex > -1) {
                incorrectWords.splice(incorrectIndex, 1);
            }
        }
    } else {
        incorrectCount++;
        problemHistory[wordIdentifier].incorrect_attempts++;
        problemHistory[wordIdentifier].correct_streak = 0;

        if (!incorrectWords.includes(wordIdentifier)) {
            incorrectWords.push(wordIdentifier);
        }
    }

    // ★修正：1問ごとに即座に保存（統計更新対応版）
    saveQuizProgressToServer().then(() => {
        // 制限状態の即座更新
        setTimeout(() => {
            updateIncorrectOnlySelection();
        }, 300);

    }).catch((error) => {
        console.error('❌ 1問回答後の保存エラー:', error);
    });

    // 次の問題へ進む
    currentQuestionIndex++;
    updateProgressBar();

    if (currentQuestionIndex < totalQuestions) {
        showNextQuestion();
    } else {
        showQuizResult();
    }
}

// 1問回答後の軽量な進捗通知
function showQuizTimeProgressNotification(weakCount) {
    // 制限状態に関わる重要な変化のみ通知
    const wasRestricted = hasBeenRestricted && !restrictionReleased;
    // ★修正：有効な苦手問題数を使用
    const currentWeakCount = getValidWeakProblemCount();

    // 制限解除の瞬間のみ通知
    if (wasRestricted && currentWeakCount <= 10) {
        showQuizTimeNotification('🔓 制限解除まであと少し！', 'success');
    }
    // 制限発動の瞬間のみ通知
    else if (!wasRestricted && currentWeakCount >= 20) {
        showQuizTimeNotification('⚠️ 苦手問題が蓄積されています', 'warning');
    }
}

// クイズ中の軽量通知
function showQuizTimeNotification(message, type = 'info') {
    // 既存の通知があれば削除
    const existingNotification = document.querySelector('.quiz-time-notification');
    if (existingNotification) {
        existingNotification.remove();
    }

    const colors = {
        success: { bg: '#d4edda', border: '#c3e6cb', text: '#155724' },
        warning: { bg: '#fff3cd', border: '#ffeaa7', text: '#856404' },
        info: { bg: '#d1ecf1', border: '#bee5eb', text: '#0c5460' }
    };

    const color = colors[type] || colors.info;

    const notification = document.createElement('div');
    notification.className = 'quiz-time-notification';
    notification.innerHTML = `
        <div style="
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${color.bg};
            color: ${color.text};
            border: 1px solid ${color.border};
            padding: 12px 18px;
            border-radius: 8px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            z-index: 9999;
            font-size: 0.9em;
            font-weight: 500;
            animation: slideInRight 0.3s ease-out;
            max-width: 280px;
        ">
            ${message}
        </div>
    `;

    document.body.appendChild(notification);

    // 2.5秒後に通知を削除
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(100px)';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 2500);
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
    // 最初に既存のお祝いメッセージを削除
    clearPreviousCelebrationMessages();

    if (cardArea) cardArea.classList.add('hidden');
    if (quizResultArea) quizResultArea.classList.remove('hidden');

    if (totalQuestionsCountSpan) totalQuestionsCountSpan.textContent = totalQuestions;
    if (correctCountSpan) correctCountSpan.textContent = correctCount;
    if (incorrectCountSpan) incorrectCountSpan.textContent = incorrectCount;

    const accuracy = totalQuestions === 0 ? 0 : (correctCount / totalQuestions) * 100;
    if (accuracyRateSpan) accuracyRateSpan.textContent = accuracy.toFixed(1);

    // 正確な選択範囲の全問題数を表示
    let displayedRangeTotal = 0;

    if (lastQuizSettings.totalSelectedRangeQuestions > 0) {
        displayedRangeTotal = lastQuizSettings.totalSelectedRangeQuestions;
    } else {
        displayedRangeTotal = calculateAccurateRangeTotal();
    }

    if (selectedRangeTotalQuestionsSpan) {
        selectedRangeTotalQuestionsSpan.textContent = displayedRangeTotal;
    }

    displayIncorrectWordsForCurrentQuiz();

    // ★追加：制限解除チェック（最終確認）
    // ★修正：有効な苦手問題数を使用
    const currentWeakCount = getValidWeakProblemCount();
    const wasRestricted = hasBeenRestricted && !restrictionReleased;

    setTimeout(() => {
        updateIncorrectOnlySelection();

        // 制限解除された場合の最終メッセージ
        const isNowRestricted = hasBeenRestricted && !restrictionReleased;
        if (wasRestricted && !isNowRestricted) {
            if (currentWeakCount === 0) {
                flashMessage('🎉 すべての苦手問題を克服しました！通常学習が利用できます。', 'success');
            } else {
                flashMessage(`✨ 苦手問題が${currentWeakCount}問になりました。通常学習が利用できます。`, 'success');
            }
        }
    }, 300);

    updateRestartButtonText();

    // 1. 今回出題された全ての問題の【答え】と【章】を収集する <--- ★変更点
    const sessionKeywords = new Set();
    const sessionChapters = new Set(); // <--- ★章を保存するSetを追加

    currentQuizData.forEach(word => {
        // 答えをキーワードとして追加
        if (word.answer && word.answer.length > 1) {
            sessionKeywords.add(word.answer);
        }
        // 章を追加 <--- ★ここから追加
        if (word.chapter) {
            sessionChapters.add(word.chapter);
        } // <--- ★ここまで追加
    });

    // 2. おすすめ論述問題の表示エリアを一度リセット
    const recommendedSection = document.getElementById('recommendedEssaysSection');
    const recommendedContainer = document.getElementById('recommendedEssaysContainer');
    recommendedSection.classList.add('hidden');
    recommendedContainer.innerHTML = '';

    // 3. 収集したキーワードがあれば、APIに問い合わせる
    if (sessionKeywords.size > 0) {
        const keywordsArray = Array.from(sessionKeywords);
        const chaptersArray = Array.from(sessionChapters); // <--- ★章の配列を作成

        // ★ローディング表示を追加
        recommendedContainer.innerHTML = '<li class="loading-message"><i class="fas fa-spinner fa-spin"></i> 関連する論述問題を検索中・・・</li>';
        recommendedSection.classList.remove('hidden');

        fetch('/api/find_related_essays', {
            method: 'POST',
            headers: { // <--- この headers の3行を追加してください
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ keywords: keywordsArray, chapters: chaptersArray }),
        })
            .then(response => response.json())
            .then(data => {
                // ローディング表示をクリア
                recommendedContainer.innerHTML = '';

                if (data.essays && data.essays.length > 0) {
                    // 4.【見つかった場合】受け取った問題リストを画面に表示する
                    data.essays.forEach(essay => {
                        const li = document.createElement('li');
                        li.innerHTML = `
                        <a href="/essay/problem/${essay.id}" class="recommended-essay-link">
                            <strong>${essay.university} ${essay.year}年 (${essay.type})</strong>
                            <p>${essay.question_snippet}</p>
                        </a>
                    `;
                        recommendedContainer.appendChild(li);
                    });
                    recommendedSection.classList.remove('hidden');
                } else {
                    // 4.【見つからなかった場合】メッセージを表示する
                    recommendedContainer.innerHTML = '<li class="no-recommendation">関連する論述問題は見つかりませんでした。幅広い分野を学習してみましょう！</li>';
                    recommendedSection.classList.remove('hidden');
                }
            })
            .catch(error => {
                console.error('おすすめ論述問題の取得エラー:', error);
                // エラー時はセクションを隠すか、エラーメッセージを表示
                recommendedContainer.innerHTML = '<li class="error-message">読み込みに失敗しました。</li>';
            });
    }
}

function updateUserStatsAsync() {
    fetch('/api/update_user_stats', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                console.log('統計更新完了');
            }
        })
        .catch(error => {
            console.error('統計更新エラー:', error);
        });
}

function calculateAccurateRangeTotal() {
    if (lastQuizSettings.isIncorrectOnly) {
        // 苦手問題モード：苦手問題の総数
        return incorrectWords.length;
    }

    // 通常モード：選択された単元の全問題数を計算
    if (lastQuizSettings.selectedUnits && lastQuizSettings.selectedUnits.length > 0) {
        const selectedUnitIds = new Set();
        lastQuizSettings.selectedUnits.forEach(unit => {
            selectedUnitIds.add(`${unit.chapter}-${unit.unit}`);
        });

        const rangeTotal = word_data.filter(word => {
            return selectedUnitIds.has(`${word.chapter}-${word.number}`);
        }).length;

        console.log(`🔍 再計算結果: ${rangeTotal}問 (選択単元: ${lastQuizSettings.selectedUnits.length}個)`);
        return rangeTotal;
    }

    // lastQuizSettingsが利用できる場合
    if (lastQuizSettings.availableQuestions && lastQuizSettings.availableQuestions.length > 0) {
        return lastQuizSettings.availableQuestions.length;
    }

    // 最後の手段：現在のクイズデータから推測（これは不正確）
    console.warn('⚠️ 正確な選択範囲が取得できないため、推測値を使用');
    const selectedUnitsInQuiz = new Set();
    currentQuizData.forEach(word => {
        selectedUnitsInQuiz.add(`${word.chapter}-${word.number}`);
    });

    return word_data.filter(word => {
        return selectedUnitsInQuiz.has(`${word.chapter}-${word.number}`);
    }).length;
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
    // お祝いメッセージをクリア
    clearPreviousCelebrationMessages();

    // ★ボタンテキストをデフォルトにリセット
    resetRestartButtonToDefault();

    // ★新機能：タイムアウトをクリア
    if (answerButtonTimeout) {
        clearTimeout(answerButtonTimeout);
        answerButtonTimeout = null;
    }
    isAnswerButtonDisabled = false;

    if (selectionArea) selectionArea.classList.remove('hidden');
    if (cardArea) cardArea.classList.add('hidden');
    if (quizResultArea) quizResultArea.classList.add('hidden');
    if (weakWordsListSection) weakWordsListSection.classList.add('hidden');
    if (noWeakWordsMessage) noWeakWordsMessage.classList.add('hidden');

    // ★重要：範囲選択画面に戻った時に制限状態を更新（少し遅延）
    setTimeout(() => {
        console.log('📍 範囲選択画面に戻る - 制限状態を再確認');
        updateIncorrectOnlySelection();

        // ★条件付きリセット：制限解除されている場合のみUIをリセット
        // ★修正：有効な苦手問題数を使用
        const currentWeakCount = getValidWeakProblemCount();
        const isCurrentlyRestricted = hasBeenRestricted && !restrictionReleased;

        console.log(`🔍 backToSelection制限チェック: 苦手${currentWeakCount}問, 制限中=${isCurrentlyRestricted}`);

        // ★重要：制限解除されている場合のみリセット
        if (!isCurrentlyRestricted && currentWeakCount <= 10 && restrictionReleased) {
            console.log('🔧 制限解除済み - UIを強制リセット');

            // DOM要素を強制的にリセット
            const questionCountRadios = document.querySelectorAll('input[name="questionCount"]:not(#incorrectOnlyRadio)');
            const rangeSelectionArea = document.querySelector('.range-selection-area');
            const chaptersContainer = document.querySelector('.chapters-container');
            const rangeSelectionTitle = document.querySelector('.selection-area h3');

            // ラジオボタンを有効化
            questionCountRadios.forEach(radio => {
                radio.disabled = false;
                radio.parentElement.style.opacity = '1';
            });

            // 範囲選択エリアを表示
            if (rangeSelectionArea) {
                rangeSelectionArea.style.display = 'block';
            }
            if (chaptersContainer) {
                chaptersContainer.style.display = 'block';
                chaptersContainer.style.opacity = '1';
                chaptersContainer.style.pointerEvents = 'auto';
            }
            if (rangeSelectionTitle) {
                rangeSelectionTitle.textContent = '出題数を選択';
                rangeSelectionTitle.style.color = '#34495e';
            }

            // 警告メッセージを削除
            removeWeakProblemWarning();
        } else if (isCurrentlyRestricted) {
            console.log('🔒 制限継続中 - 制限状態を維持');
            // 制限中の場合は何もしない（updateIncorrectOnlySelectionが適切に処理）
        }
    }, 200);
}

function debugCelebrationMessages() {
    const celebrations = document.querySelectorAll('.no-weak-problems-celebration');
    console.log(`現在のお祝いメッセージ数: ${celebrations.length}`);
    celebrations.forEach((element, index) => {
        console.log(`${index + 1}. ${element.outerHTML.substring(0, 100)}...`);
    });
    return celebrations;
}

window.debugCelebrationMessages = debugCelebrationMessages;

function restartQuiz() {
    console.log('\n🔄 同じ条件で再学習開始');

    // 苦手問題モードの場合は専用処理
    if (lastQuizSettings.isIncorrectOnly) {
        restartWeakProblemsQuiz();
        return;
    }

    // 以下は通常モードの処理（既存のコード）
    console.log('前回の設定:', lastQuizSettings);

    if (!lastQuizSettings.availableQuestions || lastQuizSettings.availableQuestions.length === 0) {
        console.warn('⚠️ 前回の設定が見つかりません。現在の問題セットで再開始します。');
        currentQuestionIndex = 0;
        correctCount = 0;
        incorrectCount = 0;
        currentQuizData = shuffleArray(currentQuizData);
        quizStartTime = Date.now();

        if (quizResultArea) quizResultArea.classList.add('hidden');
        if (cardArea) cardArea.classList.remove('hidden');
        updateProgressBar();
        showNextQuestion();
        return;
    }

    console.log('📚 通常モードで再学習');
    console.log(`利用可能な問題数: ${lastQuizSettings.availableQuestions.length}`);

    // 前回と同じ範囲の全問題を取得
    let newQuizQuestions = [...lastQuizSettings.availableQuestions];

    // 問題数制限を適用
    if (lastQuizSettings.questionCount !== 'all') {
        const count = parseInt(lastQuizSettings.questionCount);
        if (newQuizQuestions.length > count) {
            // 前回とは異なる問題セットを選択
            newQuizQuestions = shuffleArray(newQuizQuestions).slice(0, count);
            console.log(`${count}問を新しく選択しました`);
        }
    }

    if (newQuizQuestions.length === 0) {
        flashMessage('出題可能な問題がありません。', 'danger');
        backToSelectionScreen();
        return;
    }

    // 新しい問題セットでクイズを再開始
    currentQuizData = shuffleArray(newQuizQuestions);
    currentQuestionIndex = 0;
    correctCount = 0;
    incorrectCount = 0;
    totalQuestions = currentQuizData.length;
    quizStartTime = Date.now();

    console.log(`✅ 新しい問題セット: ${totalQuestions}問`);

    // UIの切り替え
    if (quizResultArea) quizResultArea.classList.add('hidden');
    if (cardArea) cardArea.classList.remove('hidden');

    updateProgressBar();
    showNextQuestion();
}

function updateRestartButtonText() {
    const restartButton = document.getElementById('restartQuizButton');
    const explanationDiv = document.querySelector('.restart-explanation');

    if (!restartButton) {
        console.warn('restartQuizButton が見つかりません');
        return;
    }

    // ★苦手問題モードかどうかを確認
    if (lastQuizSettings.isIncorrectOnly) {
        // 苦手問題モードの場合
        restartButton.innerHTML = '<i class="fas fa-redo"></i> 最新の苦手問題で再学習';

        if (explanationDiv) {
            explanationDiv.innerHTML = `
                <small>
                    <i class="fas fa-info-circle" style="color: #e74c3c;"></i>
                    <strong>「最新の苦手問題で再学習」</strong>：学習の進捗に応じて、現在の苦手問題から出題されます。
                </small>
            `;
            explanationDiv.style.borderLeftColor = '#e74c3c';
            explanationDiv.style.backgroundColor = '#fdf2f2';
        }

        console.log('🎯 苦手問題モード用のボタンテキストに更新');
    } else {
        // ★通常モードの場合
        restartButton.innerHTML = '<i class="fas fa-redo"></i> 同じ範囲から新しい問題で再学習';

        if (explanationDiv) {
            explanationDiv.innerHTML = `
                <small>
                    <i class="fas fa-info-circle" style="color: #3498db;"></i>
                    <strong>「新しい問題で再学習」</strong>：前回と同じ出題範囲・同じ問題数で、異なる問題セットから出題されます。
                </small>
            `;
            explanationDiv.style.borderLeftColor = '#3498db';
            explanationDiv.style.backgroundColor = '#e8f4fd';
        }

        console.log('📚 通常モード用のボタンテキストに更新');
    }
}

function resetRestartButtonToDefault() {
    const restartButton = document.getElementById('restartQuizButton');
    const explanationDiv = document.querySelector('.restart-explanation');

    if (restartButton) {
        restartButton.innerHTML = '<i class="fas fa-redo"></i> 同じ範囲から新しい問題で再学習';
    }

    if (explanationDiv) {
        explanationDiv.innerHTML = `
            <small>
                <i class="fas fa-info-circle" style="color: #3498db;"></i>
                <strong>「新しい問題で再学習」</strong>：前回と同じ出題範囲・同じ問題数で、異なる問題セットから出題されます。
            </small>
        `;
        explanationDiv.style.borderLeftColor = '#3498db';
        explanationDiv.style.backgroundColor = '#e8f4fd';
    }

    console.log('🔄 ボタンテキストをデフォルトにリセット');
}

function resetSelections() {
    // 1. 全てのチェックボックスをリセット
    document.querySelectorAll('.unit-item input[type="checkbox"]').forEach(checkbox => {
        if (!checkbox.disabled) {
            checkbox.checked = false;
        }
    });

    // 2. デフォルトのラジオボタンを選択
    const defaultRadio = document.querySelector('input[name="questionCount"][value="10"]');
    if (defaultRadio) defaultRadio.checked = true;

    // 3. 「全て選択」ボタンのテキストをリセット
    document.querySelectorAll('.select-all-chapter-btn').forEach(button => {
        updateSelectAllButtonText(button, false);
    });

    // 4. ★新機能：展開されている章を全て閉じる
    document.querySelectorAll('.chapter-item.expanded').forEach(chapterItem => {
        // 章の展開状態を削除
        chapterItem.classList.remove('expanded');

        // トグルアイコンを閉じた状態に戻す
        const toggleIcon = chapterItem.querySelector('.toggle-icon');
        if (toggleIcon) {
            toggleIcon.textContent = '▶';
        }
    });

    // 5. 選択状態を保存（リセット状態）
    try {
        localStorage.removeItem('quiz_selection_state');
    } catch (e) {
        window.savedSelectionState = null;
    }
}

// =========================================================
// 苦手問題リスト表示
// =========================================================

// showWeakWordsList and toggleWeakAnswer functions removed



// =========================================================
// API呼び出しヘルパー
// =========================================================
function saveQuizProgressToServer() {
    const dataToSave = {
        problemHistory: problemHistory,
        incorrectWords: incorrectWords
    };

    // ★修正：Promiseを返すように変更
    return fetch('/api/save_progress_debug', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(dataToSave)
    })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // 制限状態の重要な変化を通知
                showQuizTimeProgressNotification(incorrectWords.length);
                return data; // ★データを返す
            } else {
                console.error('❌ 進捗保存失敗:', data.message);
                throw new Error(data.message);
            }
        })
        .catch(error => {
            console.error('❌ 進捗保存エラー:', error);
            throw error; // ★エラーを再スロー
        });
}

function debugLastQuizSettings() {
    console.log('\n=== 前回のクイズ設定 ===');
    console.log('問題数設定:', lastQuizSettings.questionCount);
    console.log('苦手問題モード:', lastQuizSettings.isIncorrectOnly);
    console.log('選択された単元数:', lastQuizSettings.selectedUnits.length);
    console.log('利用可能な問題数:', lastQuizSettings.availableQuestions.length);

    if (lastQuizSettings.selectedUnits.length > 0) {
        console.log('選択された単元:');
        lastQuizSettings.selectedUnits.forEach(unit => {
            console.log(`  第${unit.chapter}章 単元${unit.unit}`);
        });
    }

    if (lastQuizSettings.availableQuestions.length > 0) {
        console.log('利用可能な問題（最初の3問）:');
        lastQuizSettings.availableQuestions.slice(0, 3).forEach((word, index) => {
            console.log(`  ${index + 1}. "${word.question}"`);
        });
    }
    console.log('========================\n');

    return lastQuizSettings;
}

// グローバル関数として公開
window.debugLastQuizSettings = debugLastQuizSettings;

function debugSelectionDetails() {
    console.log('\n=== 選択範囲詳細確認 ===');

    // 現在チェックされているチェックボックス
    const checkedBoxes = document.querySelectorAll('.unit-item input[type="checkbox"]:checked');
    console.log(`現在チェック済み: ${checkedBoxes.length}個`);

    const currentlySelected = [];
    checkedBoxes.forEach(checkbox => {
        currentlySelected.push(`${checkbox.dataset.chapter}-${checkbox.value}`);
    });

    // 現在の選択に基づく問題数
    const currentSelectionCount = word_data.filter(word => {
        return currentlySelected.includes(`${word.chapter}-${word.number}`);
    }).length;

    console.log(`現在の選択による問題数: ${currentSelectionCount}問`);

    // 保存された設定
    console.log(`保存された選択範囲: ${lastQuizSettings.totalSelectedRangeQuestions}問`);
    console.log(`保存された単元数: ${lastQuizSettings.selectedUnits?.length || 0}個`);

    if (lastQuizSettings.selectedUnits) {
        console.log('保存された単元一覧:');
        lastQuizSettings.selectedUnits.forEach(unit => {
            console.log(`  第${unit.chapter}章-単元${unit.unit}`);
        });
    }

    console.log('============================\n');

    return {
        currentlyChecked: checkedBoxes.length,
        currentSelectionCount: currentSelectionCount,
        savedRangeTotal: lastQuizSettings.totalSelectedRangeQuestions,
        savedUnitsCount: lastQuizSettings.selectedUnits?.length || 0
    };
}

// グローバル関数として公開
window.debugSelectionDetails = debugSelectionDetails;

// デバッグ用：現在の学習状況を表示する関数
function debugCurrentProgress() {
    console.log('\n=== 現在の学習状況 ===');
    console.log(`学習履歴数: ${Object.keys(problemHistory).length}`);
    console.log(`苦手問題数: ${incorrectWords.length}`);

    // 回答数の多い順にソート
    const sortedHistory = Object.entries(problemHistory)
        .map(([id, history]) => ({
            id,
            totalAttempts: (history.correct_attempts || 0) + (history.incorrect_attempts || 0),
            correct: history.correct_attempts || 0,
            incorrect: history.incorrect_attempts || 0,
            streak: history.correct_streak || 0
        }))
        .filter(item => item.totalAttempts > 0)
        .sort((a, b) => b.totalAttempts - a.totalAttempts);

    console.log(`実際に回答した問題数: ${sortedHistory.length}`);
    console.log('上位5問:');
    sortedHistory.slice(0, 5).forEach((item, index) => {
        console.log(`  ${index + 1}. ID: ${item.id.substring(0, 20)}... (${item.totalAttempts}回: 正解${item.correct}, 不正解${item.incorrect}, 連続${item.streak})`);
    });
    console.log('========================\n');

    return sortedHistory;
}

// グローバル関数として公開
window.debugCurrentProgress = debugCurrentProgress;

// =========================================================
// その他UI機能
// =========================================================

// アプリ情報表示のトグル
function toggleInfoPanel() {
    if (infoPanel) {
        const isCurrentlyVisible = !infoPanel.classList.contains('hidden');

        if (isCurrentlyVisible) {
            closeInfoPanelWithTouch();
        } else {
            openInfoPanelWithTouch();
        }
    }
}

function openInfoPanel() {
    if (infoPanel) {
        infoPanel.classList.remove('hidden');
        // 外側クリックイベントを追加（少し遅延させて即座に閉じるのを防ぐ）
        setTimeout(() => {
            document.addEventListener('click', handleOutsideClick);
        }, 100);
    }
}

function closeInfoPanel() {
    if (infoPanel) {
        infoPanel.classList.add('hidden');
        // 外側クリックイベントを削除
        document.removeEventListener('click', handleOutsideClick);
    }
}

function handleOutsideClick(event) {
    // クリックされた要素が情報パネル内かiアイコンかを確認
    const isClickInside = infoPanel && infoPanel.contains(event.target);
    const isClickOnIcon = infoIcon && infoIcon.contains(event.target);

    // パネル外かつiアイコン以外をクリックした場合
    if (!isClickInside && !isClickOnIcon) {
        closeInfoPanel();
    }
}

function handleEscapeKey(event) {
    if (event.key === 'Escape' && infoPanel && !infoPanel.classList.contains('hidden')) {
        closeInfoPanel();
    }
}

// X (旧Twitter) シェア機能
function shareOnX() {
    const total = totalQuestionsCountSpan ? totalQuestionsCountSpan.textContent : '0';
    const correct = correctCountSpan ? correctCountSpan.textContent : '0';
    const accuracy = accuracyRateSpan ? accuracyRateSpan.textContent : '0';
    const selectedRangeTotal = selectedRangeTotalQuestionsSpan ? selectedRangeTotalQuestionsSpan.textContent : '0';
    let appName = '単語帳';  // デフォルト値
    let schoolName = '〇〇高校';   // デフォルト値

    if (window.appInfoFromFlask) {
        appName = window.appInfoFromFlask.appName || appName;
        // school_name の取得（複数のプロパティ名をチェック）
        schoolName = window.appInfoFromFlask.schoolName ||
            window.appInfoFromFlask.school_name ||
            schoolName;
    }
    console.log('シェア情報:', {
        appName: appName,
        schoolName: schoolName,
        appInfoFromFlask: window.appInfoFromFlask
    });

    const text = `${appName}で学習しました！\n出題範囲：${selectedRangeTotal}問\n出題数：${total}問\n正解数：${correct}問\n正答率：${accuracy}%\n\n#${appName.replace(/\s/g, '')} ${schoolName}`;
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
    const appName = window.appInfoFromFlask ? window.appInfoFromFlask.appName : '単語帳';
    const schoolName = window.appInfoFromFlask ? window.appInfoFromFlask.schoolName : '〇〇高校';
    const hashtagText = `#${appName.replace(/\s/g, '')} ${schoolName}`;

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(hashtagText).then(() => {
            console.log('ハッシュタグがクリップボードにコピーされました');
            flashMessage('ハッシュタグがクリップボードにコピーされました！', 'success');
        }).catch(err => {
            console.error('クリップボードへのコピーに失敗しました:', err);
            fallbackCopyToClipboard(hashtagText);
        });
    } else {
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
        onclone: function (clonedDoc) {
            const clonedElement = clonedDoc.getElementById('quizResultContent');
            if (clonedElement) {
                clonedElement.style.width = targetWidth + 'px';
                clonedElement.style.height = targetHeight + 'px';
                clonedElement.style.padding = '40px';
                clonedElement.style.boxSizing = 'border-box';
                clonedElement.style.display = 'flex';
                clonedElement.style.flexDirection = 'column';
                clonedElement.style.justifyContent = 'center';
                clonedElement.style.fontSize = '28px';
                clonedElement.style.lineHeight = '1.6';
            }
        }
    };

    if (typeof html2canvas !== 'undefined') {
        html2canvas(quizResultContent, options).then(canvas => {
            const finalCanvas = document.createElement('canvas');
            finalCanvas.width = targetWidth;
            finalCanvas.height = targetHeight;
            const ctx = finalCanvas.getContext('2d');

            ctx.fillStyle = '#f8f9fa';
            ctx.fillRect(0, 0, targetWidth, targetHeight);

            const sourceAspectRatio = canvas.width / canvas.height;
            const targetAspectRatio = targetWidth / targetHeight;

            let drawWidth, drawHeight, offsetX, offsetY;

            if (sourceAspectRatio > targetAspectRatio) {
                drawWidth = targetWidth;
                drawHeight = targetWidth / sourceAspectRatio;
                offsetX = 0;
                offsetY = (targetHeight - drawHeight) / 2;
            } else {
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
// モバイル対応イベントリスナー
// =========================================================

// リサイズイベントの追加
window.addEventListener('resize', handleResize);

// 横向き・縦向き変更への対応
window.addEventListener('orientationchange', () => {
    setTimeout(() => {
        handleResize();
        initializeMobileOptimizations();
    }, 100);
});

// エラーハンドリング強化（スマホ環境向け）
window.addEventListener('error', (event) => {
    console.error('JavaScript Error:', event.error);

    // スマホでの主要な問題への対処
    if (event.error && event.error.message) {
        const message = event.error.message.toLowerCase();

        // タッチイベント関連のエラー
        if (message.includes('touch') || message.includes('passive')) {
            console.warn('Touch event issue detected, attempting to fix...');
            setTimeout(() => {
                improveTouchExperience();
            }, 500);
        }

        // レイアウト関連のエラー
        if (message.includes('layout') || message.includes('resize')) {
            console.warn('Layout issue detected, attempting to fix...');
            setTimeout(() => {
                handleResize();
                initializeMobileOptimizations();
            }, 300);
        }
    }
});

// パフォーマンス監視（スマホ用）
function monitorPerformance() {
    if ('performance' in window && 'memory' in performance) {
        setInterval(() => {
            const memory = performance.memory;
            if (memory.usedJSHeapSize > memory.jsHeapSizeLimit * 0.9) {
                console.warn('Memory usage high, attempting cleanup...');
                if (typeof gc === 'function') {
                    gc();
                }
            }
        }, 30000);
    }
}

// タッチデバイス対応（追加）
function handleTouchOutside(event) {
    // タッチイベントでも同様の処理
    handleOutsideClick(event);
}

// タッチデバイス用のイベントも追加
function addTouchListeners() {
    if ('ontouchstart' in window) {
        document.addEventListener('touchstart', handleTouchOutside);
    }
}

// パネルを開いた時にタッチイベントも設定
function openInfoPanelWithTouch() {
    openInfoPanel();
    addTouchListeners();
}

// パネルを閉じた時にタッチイベントも削除
function closeInfoPanelWithTouch() {
    closeInfoPanel();
    if ('ontouchstart' in window) {
        document.removeEventListener('touchstart', handleTouchOutside);
    }
}

function showWeakProblemWarning(count) {
    removeWeakProblemWarning();

    const warningDiv = document.createElement('div');
    warningDiv.id = 'weakProblemWarning';
    warningDiv.className = 'weak-problem-warning';

    warningDiv.innerHTML = `
        <div style="background-color: #fdf2f2; border: 2px solid #e74c3c; border-radius: 8px; padding: 20px; margin: 20px 0; text-align: center; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
            <h4 style="color: #e74c3c; margin: 0 0 15px 0; font-size: 1.3em;">
                <i class="fas fa-exclamation-triangle"></i> 苦手問題が蓄積されています
            </h4>
            <p style="margin: 10px 0; color: #721c24; font-size: 1.1em; line-height: 1.6;">
                現在 <strong style="font-size: 1.2em; color: #e74c3c;">${count}問</strong> の苦手問題があります。<br>
                まず苦手問題を <strong style="color: #e74c3c;">10問以下</strong> に減らしてから通常学習に戻りましょう。
            </p>
            <p style="margin: 15px 0 0 0; font-size: 1em; color: #a94442; background-color: #f8d7da; padding: 10px; border-radius: 5px;">
                💡 苦手問題モードで学習を続けると、通常モードが利用できるようになります。
            </p>
        </div>
    `;

    const selectionArea = document.querySelector('.selection-area .controls-area');
    if (selectionArea) {
        selectionArea.insertBefore(warningDiv, selectionArea.firstChild);
    }
}

function showIntermediateWeakProblemWarning(count) {
    removeWeakProblemWarning();

    const warningDiv = document.createElement('div');
    warningDiv.id = 'weakProblemWarning';
    warningDiv.className = 'weak-problem-warning';
    warningDiv.innerHTML = `
        <div style="background-color: #fef9e7; border: 2px solid #f39c12; border-radius: 8px; padding: 20px; margin: 20px 0; text-align: center; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
            <h4 style="color: #f39c12; margin: 0 0 15px 0; font-size: 1.3em;">
                <i class="fas fa-lock"></i> 制限継続中
            </h4>
            <p style="margin: 10px 0; color: #b7950b; font-size: 1.1em; line-height: 1.6;">
                苦手問題が <strong style="font-size: 1.2em; color: #f39c12;">${count}問</strong> あります。<br>
                <strong style="color: #f39c12;">10問以下</strong> に減らすまで制限は解除されません。
            </p>
            <p style="margin: 15px 0 0 0; font-size: 1em; color: #d68910; background-color: #fcf3cd; padding: 10px; border-radius: 5px;">
                🎯 あと <strong style="color: #f39c12;">${count - 10}問</strong> 克服すれば制限解除です！
            </p>
        </div>
    `;

    const selectionArea = document.querySelector('.selection-area .controls-area');
    if (selectionArea) {
        selectionArea.insertBefore(warningDiv, selectionArea.firstChild);
    }
}

function removeWeakProblemWarning() {
    const existingWarning = document.getElementById('weakProblemWarning');
    if (existingWarning) {
        existingWarning.remove();
    }
}

// デバッグ用：制限状態の確認
function debugRestrictionState() {
    console.log('\n=== 制限状態デバッグ ===');
    console.log(`苦手問題数: ${incorrectWords.length}`);
    console.log(`hasBeenRestricted: ${hasBeenRestricted}`);
    console.log(`restrictionReleased: ${restrictionReleased}`);
    console.log(`現在制限中?: ${hasBeenRestricted && !restrictionReleased}`);
    console.log('========================\n');
}

// デバッグ用：制限状態を強制的にセット
function setRestrictionState(hasBeenRestricted_val, restrictionReleased_val) {
    hasBeenRestricted = hasBeenRestricted_val;
    restrictionReleased = restrictionReleased_val;
    console.log(`制限状態を設定: hasBeenRestricted=${hasBeenRestricted}, restrictionReleased=${restrictionReleased}`);
    updateIncorrectOnlySelection();
}

// デバッグ用：制限状態をリセット
function resetRestrictionState() {
    hasBeenRestricted = false;
    restrictionReleased = false;
    console.log('制限状態をリセットしました');
    updateIncorrectOnlySelection();
}

/**
 * ログイン時、未閲覧の前月のランキング結果があるか確認し、あれば表示する
 */
document.addEventListener('DOMContentLoaded', () => {
    // ログインしているページ（.navbar-nav .nav-link.text-muted があるか）でのみ実行
    const isLoggedIn = document.querySelector('.navbar-nav .fa-user');
    if (isLoggedIn) {
        checkAndShowMonthlyResults();
    }
});

async function checkAndShowMonthlyResults() {
    try {
        const response = await fetch('/api/monthly_results/check_unviewed');
        const data = await response.json();

        if (data.status === 'success' && data.show_results) {
            // 表示すべき結果がある場合、モーダルを表示
            showMonthlyResultModal(data);
        } else if (data.status !== 'success') {
            console.error('未閲覧ランキングのチェックに失敗:', data.message);
        } else {
            console.log('表示すべき前月のランキングはありません。');
        }
    } catch (error) {
        console.error('未閲覧ランキングの取得エラー:', error);
    }
}

/**
 * 前月のランキング結果をモーダルで表示する
 */
function showMonthlyResultModal(data) {
    // 既存のモーダルがあれば削除
    const existingModal = document.getElementById('monthlyResultModal');
    if (existingModal) existingModal.remove();

    const { year, month, monthly_top_5, monthly_user_rank, total_participants } = data;

    // --- ランキングHTMLの生成 (daily_quiz.jsのロジックとほぼ同じ) ---
    let rankingHTML = '<p class="text-muted text-center mt-2">参加者はいませんでした。</p>';
    if (monthly_top_5 && monthly_top_5.length > 0) {
        const tableBodyHTML = monthly_top_5.map(r => `
            <tr class="${(monthly_user_rank && r.rank === monthly_user_rank.rank) ? 'current-user-rank' : ''}">
                <td>${r.rank}位</td>
                <td>${r.username}</td>
                <td>${r.score} pt</td>
            </tr>
        `).join('');

        let tableFootHTML = '';
        if (monthly_user_rank && monthly_user_rank.rank > 5) {
            tableFootHTML = `
                <tfoot>
                    <tr class="rank-ellipsis"><td colspan="3">...</td></tr>
                    <tr class="current-user-rank out-of-top5-rank">
                        <td>${monthly_user_rank.rank}位</td>
                        <td>${monthly_user_rank.username}</td>
                        <td>${monthly_user_rank.score} pt</td>
                    </tr>
                </tfoot>
            `;
        }
        rankingHTML = `
            <table class="table ranking-table mt-2">
                <thead><tr><th>順位</th><th>名前</th><th>合計スコア</th></tr></thead>
                <tbody>${tableBodyHTML}</tbody>
                ${tableFootHTML}
            </table>
            <p class="text-center text-muted participation-count">参加人数: ${total_participants}人</p>
        `;
    }

    // --- 自分の順位サマリー ---
    let userSummaryHTML = '<p>あなたは前月のクイズに参加しませんでした。</p>';
    if (monthly_user_rank) {
        userSummaryHTML = `
            <h4>あなたの順位: <span>${monthly_user_rank.rank}位</span></h4>
            <h5>合計スコア: <span>${monthly_user_rank.score} pt</span></h5>
        `;
    }

    // --- モーダルHTML本体 ---
    const modalHTML = `
        <div class="modal fade" id="monthlyResultModal" tabindex="-1">
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content monthly-result-modal-content">
                    <div class="modal-header monthly-result-header">
                        <h5 class="modal-title"><i class="fas fa-trophy"></i> 先月の月間ランキング</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body text-center">
                        <h3>${year}年${month}月 の結果</h3>
                        <div class="user-monthly-summary">
                            ${userSummaryHTML}
                        </div>
                        <hr>
                        <h5>トップ5 ランキング</h5>
                        ${rankingHTML}
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-primary" data-bs-dismiss="modal">確認しました</button>
                    </div>
                </div>
            </div>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHTML);
    const modalElement = document.getElementById('monthlyResultModal');
    const modalInstance = new bootstrap.Modal(modalElement);

    // モーダルが閉じられたら「閲覧済み」としてサーバーに送信
    modalElement.addEventListener('hidden.bs.modal', () => {
        fetch('/api/monthly_results/mark_viewed', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ year: year, month: month })
        });
        modalElement.remove(); // DOMから削除
    }, { once: true });

    modalInstance.show();
}

// グローバル関数として公開
window.setRestrictionState = setRestrictionState;
window.resetRestrictionState = resetRestrictionState;
window.debugRestrictionState = debugRestrictionState;

// グローバル関数として追加（開発者ツールで実行可能）
window.investigateIdCollisions = function () {
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
};

window.checkWeakProblemsStatus = function () {
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
};

// グローバル関数として関数を公開（onclickから呼び出せるように）
window.toggleIncorrectAnswer = toggleIncorrectAnswer;
// window.toggleWeakAnswer = toggleWeakAnswer; // Removed