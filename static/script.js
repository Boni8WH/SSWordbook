// static/script.js

// デバッグ用: window オブジェクトが存在するかどうかを確認
if (typeof window === 'undefined') {
    console.error("Error: 'window' object is undefined. This script might be running in a non-browser environment.");
} else {

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

window.word_data = [];  // この行を追加
let word_data = window.word_data;  // この行も追加

// ==========================================
// Global Confirm Modal Logic (Replaces native confirm)
// ==========================================
let genericConfirmCallback = null;

window.showConfirmModal = function (title, message, callback, btnText = '実行', btnClass = 'btn-primary') {
    const titleEl = document.getElementById('genericConfirmTitle');
    const bodyEl = document.getElementById('genericConfirmBody');
    const btnEl = document.getElementById('genericConfirmBtn');

    if (!titleEl || !bodyEl || !btnEl) {
        console.warn('Generic Confirm Modal elements not found. Falling back to native confirm.');
        if (confirm(`${title}\n\n${message}`)) {
            if (callback) callback();
        }
        return;
    }

    titleEl.textContent = title;
    bodyEl.innerHTML = message.replace(/\n/g, '<br>');

    btnEl.textContent = btnText;
    btnEl.className = 'btn ' + btnClass;

    genericConfirmCallback = callback;

    const modalEl = document.getElementById('genericConfirmModal');
    const modal = new bootstrap.Modal(modalEl);
    modal.show();
};

window.executeGenericConfirm = function () {
    if (genericConfirmCallback) {
        genericConfirmCallback();
    }
    const modalEl = document.getElementById('genericConfirmModal');
    const modal = bootstrap.Modal.getInstance(modalEl);
    if (modal) modal.hide();
};
// ==========================================

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
// 問題ID生成関数
// =========================================================

function generateProblemId(word) {
    try {
        // Python: str(word.get('chapter', '0')).zfill(3)
        // JS: String(...) -> Pythonのstr()相当
        // もし入力が " 1 " の場合:
        //   Python: " 1 ".zfill(3) -> " 1 " (長さ3なので変化なし)
        //   JS:     " 1 ".padStart(3, '0') -> " 1 " (長さ3なので変化なし)
        // もし入力が "1" の場合:
        //   Python: "1".zfill(3) -> "001"
        //   JS:     "1".padStart(3, '0') -> "001"
        // ★重要: CSVのパース時にスペースが残っている可能性を考慮し、Trimしない（Python側もしていないため）
        // ただし、もし不整合が起きるなら、Python/JS両方でTrimすべきだが、
        // 既存の履歴との互換性を保つため、Pythonの挙動に合わせる。

        const chapterStr = String(word.chapter !== undefined ? word.chapter : '0');
        const numberStr = String(word.number !== undefined ? word.number : '0');

        let chapter = chapterStr;
        if (chapter.length < 3) {
            chapter = chapter.padStart(3, '0');
        }

        let number = numberStr;
        if (number.length < 3) {
            number = number.padStart(3, '0');
        }

        const question = String(word.question || '');
        const answer = String(word.answer || '');

        // Python: re.sub(r'[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', '', question[:15])
        // JS: substring(0, 15) はPythonの [:15] と同じ挙動（文字数）
        // ★Surrogate Pairの扱いが違う可能性があるが、まずはこのまま

        const questionClean = question.substring(0, 15).replace(/[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]/g, '');
        const answerClean = answer.substring(0, 10).replace(/[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]/g, '');

        const problemId = `${chapter}-${number}-${questionClean}-${answerClean}`;

        return problemId;

    } catch (e) {
        console.error('ID Generation Error:', e);
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
        checkAnnouncementStatus(); // 🆕 お知らせ状態チェック

        setTimeout(() => {
            loadSelectionState();
            initializeSelectAllButtons();
            initializeMobileOptimizations();
            improveTouchExperience();
            optimizeScrolling();
            updateIncorrectOnlySelection();
            loadFontSize(); // フォントサイズ読み込み
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
                    updateSelectionTotalCount(); // カウント更新
                }, 500);
            } else {
                console.error('❌ ユーザーデータ読み込み失敗:', data.message);
            }
        })
        .catch(error => {
            console.error('❌ ユーザーデータ読み込みエラー:', error);
            flashMessage('ユーザーデータの読み込みに失敗しました。', 'danger');
        });
}

// 🆕 制限状態をサーバーに保存する関数を追加
function saveRestrictionState() {
    const restrictionData = {
        hasBeenRestricted: hasBeenRestricted,
        restrictionReleased: restrictionReleased
    };

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

            } else {
                console.error('❌ 制限状態保存失敗:', data.message);
                flashMessage('制限状態の保存に失敗しました: ' + data.message, 'danger');
            }
        })
        .catch(error => {
            console.error('❌ 制限状態保存エラー:', error);
            flashMessage('制限状態の保存中にエラーが発生しました。', 'danger');
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
                updateSelectionTotalCount(); // カウント更新
            }, 500);

        })
        .catch(error => {
            console.error('❌ 単語データ読み込みエラー:', error);
            flashMessage('単語データのロード中にエラーが発生しました。', 'danger');
        });
}

function updateIncorrectOnlyRadio() {
    const incorrectOnlyRadio = document.getElementById('incorrectOnlyRadio');
    const unsolvedOnlyCheckbox = document.getElementById('unsolvedOnlyCheckbox');
    const unmasteredOnlyCheckbox = document.getElementById('unmasteredOnlyCheckbox');
    const authMessageIncorrectOnly = document.querySelector('.auth-message-incorrect-only');

    if (window.appInfoFromFlask && window.appInfoFromFlask.isLoggedIn) {
        if (incorrectOnlyRadio) incorrectOnlyRadio.disabled = false;
        if (unsolvedOnlyCheckbox) unsolvedOnlyCheckbox.disabled = false;
        if (unmasteredOnlyCheckbox) unmasteredOnlyCheckbox.disabled = false;
        if (authMessageIncorrectOnly) authMessageIncorrectOnly.classList.add('hidden');
    } else {
        if (incorrectOnlyRadio) incorrectOnlyRadio.disabled = true;
        if (unsolvedOnlyCheckbox) unsolvedOnlyCheckbox.disabled = true;
        if (unmasteredOnlyCheckbox) unmasteredOnlyCheckbox.disabled = true;
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

// ======================// ===================================
// フォントサイズ調整機能 (Refined)
// ===================================

const decreaseFontBtn = document.getElementById('decreaseFontSize');
const increaseFontBtn = document.getElementById('increaseFontSize');

let currentFontSize = 1.3; // Default rem
const MIN_FONT_SIZE = 0.8;
const MAX_FONT_SIZE = 3.0;
const FONT_STEP = 0.2;

function applyFontSize(size) {
    const questionEl = document.getElementById('question');
    const answerEl = document.getElementById('answer');

    if (questionEl) questionEl.style.fontSize = `${size}rem`;
    if (answerEl) answerEl.style.fontSize = `${size}rem`;

    // Persist
    try {
        localStorage.setItem('quiz_font_size_val', size);
    } catch (e) { console.warn(e); }
}

function adjustFontSize(delta) {
    let newSize = currentFontSize + delta;
    // Round to 1 decimal place to avoid float errors
    newSize = Math.round(newSize * 10) / 10;

    if (newSize < MIN_FONT_SIZE) newSize = MIN_FONT_SIZE;
    if (newSize > MAX_FONT_SIZE) newSize = MAX_FONT_SIZE;

    currentFontSize = newSize;
    applyFontSize(currentFontSize);
}

function loadFontSize() {
    try {
        const saved = localStorage.getItem('quiz_font_size_val');
        if (saved) {
            currentFontSize = parseFloat(saved);
            // Validation
            if (isNaN(currentFontSize) || currentFontSize < MIN_FONT_SIZE || currentFontSize > MAX_FONT_SIZE) {
                currentFontSize = 1.3;
            }
        }
    } catch (e) { }
    applyFontSize(currentFontSize);
}

// Event Listeners
if (decreaseFontBtn) {
    decreaseFontBtn.addEventListener('click', (e) => {
        e.preventDefault();
        adjustFontSize(-FONT_STEP);
    });
}

if (increaseFontBtn) {
    increaseFontBtn.addEventListener('click', (e) => {
        e.preventDefault();
        adjustFontSize(FONT_STEP);
    });
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
        updateSelectionTotalCount(); // カウント更新
    }, 100);
}

// =========================================================
// 苦手問題選択時の視覚的フィードバック
// =========================================================
function updateIncorrectOnlySelection() {
    const incorrectOnlyRadio = document.getElementById('incorrectOnlyRadio');
    const chaptersContainer = document.querySelector('.chapters-container');
    const rangeSelectionArea = document.querySelector('.range-selection-area');
    const rangeSelectionTitleText = document.getElementById('rangeSelectionTitleText');
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
        if (rangeSelectionTitleText) {
            rangeSelectionTitleText.textContent = '苦手問題モード';
            rangeSelectionTitleText.style.color = '#95a5a6';
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
        if (rangeSelectionTitleText) {
            rangeSelectionTitleText.textContent = '出題数を選択';
            rangeSelectionTitleText.style.color = '#34495e';
        }

        const existingWarning = document.getElementById('weakProblemWarning');
        if (existingWarning) {
            existingWarning.remove();
        }
    }
}

// =========================================================
// イベントリスナーの設定
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

        // 検索機能
        const openSearchButton = document.getElementById('openSearchButton');
        const searchExecuteButton = document.getElementById('searchExecuteButton');
        const searchInput = document.getElementById('searchInput');

        if (openSearchButton) {
            openSearchButton.addEventListener('click', () => {
                const searchModal = new bootstrap.Modal(document.getElementById('searchModal'));
                searchModal.show();
                setTimeout(() => {
                    if (searchInput) searchInput.focus();
                }, 500);
            });
        }

        if (searchExecuteButton) {
            searchExecuteButton.addEventListener('click', executeSearch);
        }

        if (searchInput) {
            searchInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    executeSearch();
                }
            });
        }

        questionCountRadios.forEach(radio => {
            radio.addEventListener('change', () => {
                updateIncorrectOnlySelection();
                updateSelectionTotalCount(); // カウント更新
            });
        });

        // ★未解答のみ・未マスターのみの排他制御
        const unsolvedCheckbox = document.getElementById('unsolvedOnlyCheckbox');
        const unmasteredCheckbox = document.getElementById('unmasteredOnlyCheckbox');

        if (unsolvedCheckbox && unmasteredCheckbox) {
            unsolvedCheckbox.addEventListener('change', function () {
                if (this.checked) {
                    unmasteredCheckbox.checked = false;
                }
                updateSelectionTotalCount(); // カウント更新
            });

            unmasteredCheckbox.addEventListener('change', function () {
                if (this.checked) {
                    unsolvedCheckbox.checked = false;
                }
                updateSelectionTotalCount(); // カウント更新
            });
        }

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
                    updateSelectionTotalCount(); // カウント更新
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

        // 単元チェックボックスの変更イベント
        if (chaptersContainer) {
            chaptersContainer.addEventListener('change', (e) => {
                if (e.target.type === 'checkbox' && e.target.closest('.unit-item')) {
                    updateSelectionTotalCount();
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
    // ★修正: 重複を除外してカウント (Setを使用)
    const validWeakProblems = new Set(incorrectWords.filter(id => validProblemIds.has(id)));

    return validWeakProblems.size;
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

function getFilteredQuestions() {
    let quizQuestions = [];
    // 常にDOMから現在の状態を取得
    const isIncorrectOnly = document.querySelector('input[name="questionCount"][value="incorrectOnly"]')?.checked;

    // ★重要: チェックボックスの状態を直接取得
    const unsolvedCheckbox = document.getElementById('unsolvedOnlyCheckbox');
    const unmasteredCheckbox = document.getElementById('unmasteredOnlyCheckbox');

    const isUnsolvedOnly = unsolvedCheckbox ? unsolvedCheckbox.checked : false;
    const isUnmasteredOnly = unmasteredCheckbox ? unmasteredCheckbox.checked : false;

    if (isIncorrectOnly) {
        // 苦手問題モードの場合
        quizQuestions = word_data.filter(word => {
            const wordIdentifier = generateProblemId(word);
            return incorrectWords.includes(wordIdentifier);
        });
    } else {
        // 通常モード：選択された範囲から出題
        quizQuestions = getSelectedQuestions();
    }

    // ★未マスターのみフィルタリング
    if (isUnmasteredOnly) {
        quizQuestions = quizQuestions.filter(word => {
            const wordIdentifier = generateProblemId(word);
            const history = problemHistory[wordIdentifier];

            if (!history) return true; // 未解答

            const correct = history.correct_attempts || 0;
            const incorrect = history.incorrect_attempts || 0;
            const total = correct + incorrect;

            if (total === 0) return true; // 未解答

            const accuracy = correct / total;
            return accuracy < 0.8;
        });
    }

    // ★未解答のみフィルタリング
    if (isUnsolvedOnly) {
        quizQuestions = quizQuestions.filter(word => {
            const wordIdentifier = generateProblemId(word);
            const history = problemHistory[wordIdentifier];
            return !history || ((history.correct_attempts || 0) + (history.incorrect_attempts || 0) === 0);
        });
    }

    // 空の問題を除外
    quizQuestions = quizQuestions.filter(q => q.question && q.answer && q.question.trim() !== '' && q.answer.trim() !== '');

    return quizQuestions;
}

function updateSelectionTotalCount() {
    const countSpan = document.getElementById('selectionTotalCount');
    if (!countSpan) return;

    const questions = getFilteredQuestions();
    const count = questions.length;

    if (count > 0) {
        countSpan.textContent = `(全${count}問)`;
    } else {
        countSpan.textContent = '(0問)';
    }
}

function shuffleArray(array) {
    const shuffled = [...array]; // 元の配列をコピー
    for (let i = shuffled.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    return shuffled;
}

// ユーティリティ: スロットリング関数
function throttle(func, limit) {
    let inThrottle;
    return function () {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        } else {

        }
    }
}

const lastFlashMessage = { text: '', time: 0 };

function flashMessage(message, category) {
    const now = Date.now();
    // 同じメッセージは1秒間表示しない（スロットリング）
    if (message === lastFlashMessage.text && (now - lastFlashMessage.time) < 1000) {

        return;
    }
    lastFlashMessage.text = message;
    lastFlashMessage.time = now;

    const container = document.querySelector('.container') || document.body;

    // 重複チェック（現在表示中のもの）
    const existingAlerts = container.querySelectorAll('.alert');
    for (const alert of existingAlerts) {
        if (alert.textContent.includes(message)) {
            return;
        }
    }

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
    isUnsolvedOnly: false,
    isUnmasteredOnly: false,
    availableQuestions: []
};

function startQuiz() {
    try {

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

        const weakProblemCount = getValidWeakProblemCount();
        const rawWeakProblemCount = incorrectWords.length; // 表示用などに元の数も保持
        const selectedQuestionCount = getSelectedQuestionCount();
        const isCurrentlyRestricted = hasBeenRestricted && !restrictionReleased;
        const isUnsolvedOnly = document.getElementById('unsolvedOnlyCheckbox')?.checked || false;
        const isUnmasteredOnly = document.getElementById('unmasteredOnlyCheckbox')?.checked || false;

        if (isCurrentlyRestricted && selectedQuestionCount !== 'incorrectOnly') {
            // ★追加: 制限中だが、有効な苦手問題が0問の場合（データの不整合など）
            // 自動的に制限を解除して、通常モードで開始できるようにする
            if (weakProblemCount === 0) {
                console.warn('⚠️ 制限中ですが有効な苦手問題が0問です。制限を自動解除します。');
                hasBeenRestricted = false;
                restrictionReleased = true;
                saveRestrictionState(); // サーバーに保存

                flashMessage('有効な苦手問題が見つからないため、制限を解除しました。', 'info');

                // 状態更新のためにリロードせず、そのまま処理を続行させる（再帰呼び出しは避ける）
                // UI更新
                updateIncorrectOnlySelection();

                // 続行許可（下の処理へ）
            } else {
                if (weakProblemCount >= 20) {
                    flashMessage('苦手問題が20問以上あります。まず苦手問題モードで学習してください。', 'danger');
                } else {
                    flashMessage(`苦手問題を10問以下に減らすまで、苦手問題モードで学習してください。（現在${weakProblemCount}問）`, 'warning');
                }
                return;
            }
        }

        let quizQuestions = getFilteredQuestions();
        const isIncorrectOnly = (selectedQuestionCount === 'incorrectOnly');

        // 苦手問題モード・未解答モード・未マスターモードの場合は範囲選択チェックをスキップ
        // ただし通常モードの場合は、単元が選択されているか確認
        if (!isIncorrectOnly) {
            const rawSelected = getSelectedQuestions();
            if (rawSelected.length === 0 && !isIncorrectOnly) {
                // 通常モードで単元未選択の場合のチェック（UnsolvedOnlyなどがない場合）
                if (!isUnsolvedOnly && !isUnmasteredOnly) {
                    flashMessage('出題範囲を選択してください。', 'danger');
                    return;
                }
            }
        }

        // ★最後のクイズ設定を確実に初期化
        lastQuizSettings = {
            questionCount: selectedQuestionCount,
            isIncorrectOnly: isIncorrectOnly,
            isUnsolvedOnly: isUnsolvedOnly,
            isUnmasteredOnly: isUnmasteredOnly,
            selectedUnits: [],
            availableQuestions: [],
            totalSelectedRangeQuestions: 0
        };



        if (!isIncorrectOnly) {
            // 選択された単元情報を保存
            document.querySelectorAll('.unit-item input[type="checkbox"]:checked').forEach(checkbox => {
                lastQuizSettings.selectedUnits.push({
                    chapter: checkbox.dataset.chapter,
                    unit: checkbox.value
                });
            });
        }

        // ログ出力（デバッグ用）
        if (isIncorrectOnly) {

        } else {

        }
        lastQuizSettings.availableQuestions = [...quizQuestions]; // フィルタ後の問題を保存
        lastQuizSettings.totalSelectedRangeQuestions = quizQuestions.length;


        if (selectedQuestionCount !== 'incorrectOnly') {
            saveSelectionState();
        }

        // 問題数の制限（苦手問題モード以外）
        // ※「全問」かつ「全問題数 > 出題数」の場合はシャッフルして制限
        if (selectedQuestionCount !== 'all' && selectedQuestionCount !== 'incorrectOnly') {
            const count = parseInt(selectedQuestionCount);
            if (quizQuestions.length > count) {
                quizQuestions = shuffleArray(quizQuestions).slice(0, count);
            }
        }

        if (quizQuestions.length === 0) {
            // エラーメッセージの詳細化
            if (isUnsolvedOnly) flashMessage('選択範囲に未解答の問題はありません。', 'info');
            else if (isUnmasteredOnly) flashMessage('選択範囲に未マスターの問題はありません。', 'success');
            else if (isIncorrectOnly) flashMessage('有効な苦手問題がありません。', 'info');
            else flashMessage('選択された条件に合う問題がありませんでした。', 'danger');
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
        correctCount = 0;
        incorrectCount = 0;
        totalQuestions = currentQuizData.length;
        quizStartTime = Date.now();

        // UIの切り替え
        if (selectionArea) selectionArea.classList.add('hidden');
        if (cardArea) cardArea.classList.remove('hidden');
        if (quizResultArea) quizResultArea.classList.add('hidden');
        // weakWordsListSection reference removed
        if (noWeakWordsMessage) noWeakWordsMessage.classList.add('hidden');

        updateProgressBar();
        showNextQuestion();

    } catch (error) {
        console.error('❌ startQuiz error:', error);
        alert('Error in startQuiz: ' + error.message);
    }
}

function restartWeakProblemsQuiz() {


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


        if (questionElement) {

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

// クイズ中の軽量通知 (Throttled)
const showQuizTimeNotification = throttle(function (message, type = 'info') {
    // 既存の通知があれば削除（メッセージが同じなら何もしない）
    const existingNotification = document.querySelector('.quiz-time-notification');
    if (existingNotification) {
        // 同じメッセージが表示されている場合は更新しない（点滅防止）
        if (existingNotification.textContent.includes(message)) {
            return;
        }
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
}, 500); // 500ms Throttle Limit

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

        updateIncorrectOnlySelection();

        // ★条件付きリセット：制限解除されている場合のみUIをリセット
        // ★修正：有効な苦手問題数を使用
        const currentWeakCount = getValidWeakProblemCount();
        const isCurrentlyRestricted = hasBeenRestricted && !restrictionReleased;

        // ★重要：制限解除済み、または制限が元々ない場合はUIをリセット
        if (!isCurrentlyRestricted) {

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

            // 制限中の場合は何もしない（updateIncorrectOnlySelectionが適切に処理）
        }
    }, 200);
}

function debugCelebrationMessages() {
    const celebrations = document.querySelectorAll('.no-weak-problems-celebration');

    celebrations.forEach((element, index) => {

    });
    return celebrations;
}

window.debugCelebrationMessages = debugCelebrationMessages;

function restartQuiz() {

    // 苦手問題モードの場合は専用処理
    if (lastQuizSettings.isIncorrectOnly) {
        restartWeakProblemsQuiz();
        return;
    }

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

    // 前回と同じ範囲の全問題を取得
    let newQuizQuestions = [...lastQuizSettings.availableQuestions];

    // ★未解答モードの場合、学習済みの問題を除外する
    if (lastQuizSettings.isUnsolvedOnly) {

        newQuizQuestions = newQuizQuestions.filter(word => {
            const wordIdentifier = generateProblemId(word);
            const history = problemHistory[wordIdentifier];
            // 履歴がない、または正解数+不正解数が0の場合
            return !history || ((history.correct_attempts || 0) + (history.incorrect_attempts || 0) === 0);
        });

        if (newQuizQuestions.length === 0) {
            flashMessage('全ての未解答問題を学習しました！', 'success');
            backToSelectionScreen();
            return;
        }
    }

    // ★未マスターモードの場合、マスター済みの問題（80%以上）を除外する
    if (lastQuizSettings.isUnmasteredOnly) {

        newQuizQuestions = newQuizQuestions.filter(word => {
            const wordIdentifier = generateProblemId(word);
            const history = problemHistory[wordIdentifier];

            // 履歴がない (未解答) -> 対象
            if (!history) return true;

            const correct = history.correct_attempts || 0;
            const incorrect = history.incorrect_attempts || 0;
            const total = correct + incorrect;

            // 未解答 -> 対象
            if (total === 0) return true;

            // 正答率80%未満 -> 対象 (未マスター)
            const accuracy = correct / total;
            return accuracy < 0.8;
        });

        if (newQuizQuestions.length === 0) {
            flashMessage('全ての未マスター問題を克服しました！', 'success');
            backToSelectionScreen();
            return;
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


    } else if (lastQuizSettings.isUnsolvedOnly) {
        // 未解答モードの場合
        restartButton.innerHTML = '<i class="fas fa-redo"></i> 未解答問題で再学習';

        if (explanationDiv) {
            explanationDiv.innerHTML = `
                <small>
                    <i class="fas fa-info-circle" style="color: #27ae60;"></i>
                    <strong>「未解答問題で再学習」</strong>：選択範囲の未解答問題から出題されます。
                </small>
            `;
            explanationDiv.style.borderLeftColor = '#27ae60';
            explanationDiv.style.backgroundColor = '#eafaf1';
        }

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

    // 未解答のみチェックボックスをリセット
    const unsolvedOnlyCheckbox = document.getElementById('unsolvedOnlyCheckbox');
    if (unsolvedOnlyCheckbox) unsolvedOnlyCheckbox.checked = false;

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

    // 6. 問題数カウントをリセット (0問に更新)
    updateSelectionTotalCount();
}

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


    return lastQuizSettings;
}

// グローバル関数として公開
window.debugLastQuizSettings = debugLastQuizSettings;

function debugSelectionDetails() {
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

async function openInfoPanel() {
    if (infoPanel) {
        infoPanel.classList.remove('hidden');

        // お知らせを取得して表示 (awaitして確実にリストを表示)
        await fetchAnnouncements();

        // 🆕 未読バッジがあれば消して既読APIを叩く
        if (infoIcon && infoIcon.classList.contains('has-new')) {
            infoIcon.classList.remove('has-new');
            markAnnouncementsAsViewed();
        }

        // 外側クリックイベントを追加（少し遅延させて即座に閉じるのを防ぐ）
        setTimeout(() => {
            document.addEventListener('click', handleOutsideClick);
        }, 100);
    }
}

// 🆕 お知らせ状態チェック関数
async function checkAnnouncementStatus() {
    if (!infoIcon) return;

    try {
        const response = await fetch('/api/announcements/status');
        const data = await response.json();

        if (data.status === 'success' && data.has_new) {
            infoIcon.classList.add('has-new');
        } else {
            infoIcon.classList.remove('has-new');
        }
    } catch (error) {
        console.error('お知らせ状態チェックエラー:', error);
    }
}

// 🆕 お知らせ既読化関数
async function markAnnouncementsAsViewed() {
    try {
        await fetch('/api/announcements/mark_viewed', { method: 'POST' });
    } catch (error) {
        console.error('お知らせ既読化エラー:', error);
    }
}

async function fetchAnnouncements() {
    const announcementsList = document.getElementById('announcementsList');
    if (!announcementsList) return;

    try {
        const response = await fetch('/api/announcements');
        const data = await response.json();

        if (data.status === 'success') {
            if (data.announcements.length === 0) {
                announcementsList.innerHTML = '<p class="text-muted" style="font-size: 0.9em;">現在お知らせはありません。</p>';
            } else {
                let html = '<div class="accordion-list" style="display: flex; flex-direction: column; gap: 8px;">';
                data.announcements.forEach(ann => {
                    // 日時をJSTでフォーマット（サーバーから既にJSTで来ている前提だが、念のため調整）
                    // サーバーが "YYYY-MM-DD HH:MM:SS" 形式で返している場合、そのまま表示でOK
                    // 必要なら new Date(ann.date).toLocaleString('ja-JP', { timeZone: 'Asia/Tokyo' }) など

                    // NEWバッジのHTML
                    // NEWバッジのHTML
                    let badgeText = 'NEW';
                    let badgeClass = 'new-badge';
                    if (ann.badge_type === 'update') {
                        badgeText = '更新';
                        badgeClass += ' update';
                    }
                    const newBadgeHtml = ann.is_new ? `<span class="${badgeClass}">${badgeText}</span>` : '';

                    html += `
                        <details style="border: 1px solid #eee; border-radius: 6px; overflow: hidden; background-color: #fff;">
                            <summary style="padding: 10px; cursor: pointer; background-color: #f9f9f9; font-size: 0.95em; outline: none; list-style: none; display: flex; flex-direction: column;">
                                <div class="d-flex justify-content-between align-items-center mb-1">
                                    <small class="text-muted d-flex align-items-center flex-wrap">
                                        <i class="far fa-calendar-alt me-1"></i>${ann.date}
                                        ${newBadgeHtml}
                                        ${ann.updated_at ? `<div class="w-100"></div><small class="text-muted mt-1" style="font-size: 0.9em;"><i class="fas fa-sync-alt" style="font-size: 0.9em;"></i> 更新: ${ann.updated_at}</small>` : ''}
                                    </small>
                                </div>
                                <span style="font-weight: bold; color: #2c3e50;">
                                    ${ann.title}
                                </span>
                            </summary>
                            <div style="padding: 12px; font-size: 0.9em; color: #34495e; white-space: pre-wrap; border-top: 1px solid #eee; background-color: #fff;">${ann.content}</div>
                        </details>
                    `;
                });

                html += `
                    <div style="text-align: right; margin-top: 10px; padding-right: 5px;">
                        <a href="/announcements" class="text-decoration-none" style="font-size: 0.9em; color: #3498db; font-weight: bold;">
                            <i class="fas fa-list-ul me-1"></i>過去のお知らせを見る
                        </a>
                    </div>
                `;
                html += '</div>';
                announcementsList.innerHTML = html;

                // イベントリスナー設定: 詳細を開いたら既読APIを叩く
                const detailsElements = announcementsList.querySelectorAll('details');
                detailsElements.forEach((details, index) => {
                    const ann = data.announcements[index];
                    details.addEventListener('toggle', function () {
                        if (this.open) {
                            // NEWバッジがあれば消す
                            const badge = this.querySelector('.new-badge');
                            if (badge) {
                                badge.remove();

                                // API呼び出し
                                fetch(`/api/announcements/${ann.id}/read`, {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json'
                                    }
                                }).catch(err => console.error("Error marking announcement read:", err));
                            }
                        }
                    });
                });
            }
        } else {
            announcementsList.innerHTML = '<p class="text-danger" style="font-size: 0.9em;">お知らせの読み込みに失敗しました。</p>';
        }
    } catch (error) {
        console.error('お知らせ取得エラー:', error);
        announcementsList.innerHTML = '<p class="text-danger" style="font-size: 0.9em;">エラーが発生しました。</p>';
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
    // モーダルが開いている場合は処理しない（干渉を防ぐため）
    if (document.body.classList.contains('modal-open')) {
        return;
    }
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

// キーボードショートカット対応
document.addEventListener('keydown', (event) => {
    // クイズ画面が表示されていない場合は何もしない
    if (!cardArea || cardArea.classList.contains('hidden')) return;

    // 入力フォームなどにフォーカスがある場合は何もしない
    if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') return;

    // スペースキー: 答えを見る
    if (event.code === 'Space') {
        event.preventDefault(); // スクロール防止
        if (!showAnswerButton.classList.contains('hidden') && !showAnswerButton.disabled) {
            showAnswerButton.click();
        }
    }

    // Mキー: 正解
    if (event.code === 'KeyM') {
        if (!correctButton.classList.contains('hidden')) {
            correctButton.click();
        }
    }

    // Xキー: 不正解
    if (event.code === 'KeyX') {
        if (!incorrectButton.classList.contains('hidden')) {
            incorrectButton.click();
        }
    }
});

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
    const existingWarning = document.getElementById('weakProblemWarning');
    if (existingWarning) {
        // すでに表示されている場合は内容だけ確認して、同じなら更新しない
        if (existingWarning.innerHTML.includes(`${count}問`)) {
            return;
        }
        existingWarning.remove();
    }

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
    const existingWarning = document.getElementById('weakProblemWarning');
    if (existingWarning) {
        // すでに表示されている場合は内容だけ確認して、同じなら更新しない
        if (existingWarning.innerHTML.includes(`${count}問`)) {
            return;
        }
        existingWarning.remove();
    }

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

}

// デバッグ用：制限状態を強制的にセット
function setRestrictionState(hasBeenRestricted_val, restrictionReleased_val) {
    hasBeenRestricted = hasBeenRestricted_val;
    restrictionReleased = restrictionReleased_val;

    updateIncorrectOnlySelection();
}

// デバッグ用：制限状態をリセット
function resetRestrictionState() {
    hasBeenRestricted = false;
    restrictionReleased = false;

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


    return collisions;
};

window.checkWeakProblemsStatus = function () {

};

// グローバル関数として関数を公開（onclickから呼び出せるように）
window.toggleIncorrectAnswer = toggleIncorrectAnswer;
// window.toggleWeakAnswer = toggleWeakAnswer; // Removed

// 検索実行関数
function executeSearch() {
    const searchInput = document.getElementById('searchInput');
    const searchResults = document.getElementById('searchResults');

    if (!searchInput || !searchResults) return;

    const query = searchInput.value.trim().toLowerCase();
    if (!query) {
        searchResults.innerHTML = '<div class="list-group-item text-muted">キーワードを入力してください</div>';
        return;
    }

    searchResults.innerHTML = '<div class="list-group-item text-center"><i class="fas fa-spinner fa-spin"></i> 検索中...</div>';

    // クライアントサイドで検索（word_dataを使用）
    setTimeout(() => {
        const results = word_data.filter(word => {
            const question = (word.question || '').toLowerCase();
            const answer = (word.answer || '').toLowerCase();
            return question.includes(query) || answer.includes(query);
        });

        if (results.length === 0) {
            searchResults.innerHTML = '<div class="list-group-item text-muted">該当する問題は見つかりませんでした</div>';
        } else {
            searchResults.innerHTML = '';
            // 最大50件まで表示
            results.slice(0, 50).forEach(word => {
                const item = document.createElement('div');
                item.className = 'list-group-item';
                item.innerHTML = `
                    <div class="d-flex w-100 justify-content-between">
                        <h6 class="mb-1">${word.chapter === 'S' ? '歴史総合' : '第' + word.chapter + '章'} - ${word.number}</h6>
                        <small class="text-muted">${word.answer}</small>
                    </div>
                    <p class="mb-1">${word.question}</p>
                `;
                searchResults.appendChild(item);
            });

            if (results.length > 50) {
                const more = document.createElement('div');
                more.className = 'list-group-item text-center text-muted';
                more.textContent = `他 ${results.length - 50} 件が見つかりました（表示制限）`;
                searchResults.appendChild(more);
            }
        }
    }, 100); // UIブロックを防ぐための微小な遅延
}

// ==========================================
// 通知機能 (Notification)
// ==========================================

document.addEventListener('DOMContentLoaded', function () {
    initNotificationSettings();
});

function initNotificationSettings() {
    const saveBtn = document.getElementById('saveSettingsBtn');
    if (!saveBtn) return; // 設定モーダルがないページでは何もしない

    // 設定読み込み
    fetch('/api/notification_settings')
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                const toggle = document.getElementById('notificationToggle');
                const timeInput = document.getElementById('notificationTime');

                if (toggle) toggle.checked = data.enabled;
                if (timeInput) timeInput.value = data.time || '21:00';

                // トグル状態に応じて時間入力の有効/無効切り替え
                toggleTimeInput(data.enabled);

                if (toggle) {
                    toggle.addEventListener('change', (e) => {
                        toggleTimeInput(e.target.checked);
                    });
                }

                if (data.enabled && Notification.permission === 'granted') {
                    registerServiceWorker().catch(err => console.error('Auto-register SW failed:', err));
                }
            }
        })
        .catch(err => console.error('設定読み込みエラー:', err));

    // 通知テストボタン
    const testBtn = document.getElementById('testNotificationBtn');
    if (testBtn) {
        testBtn.addEventListener('click', function () {
            // ボタンを一時的に無効化
            testBtn.disabled = true;
            testBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> 送信中...';

            fetch('/api/test_notification', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status === 'success') {
                        alert('送信成功！\n\nもし通知が届かない場合は、スマホの「おやすみモード」や「通知設定」を確認してください。\n（PC/Androidは数秒、iOSは少し時間がかかることがあります）');
                    } else {
                        alert('送信失敗:\n' + data.message + '\n\n(詳細エラー: ' + JSON.stringify(data) + ')');
                    }
                })
                .catch(err => {
                    console.error('テスト送信エラー:', err);
                    alert('通信エラーが発生しました');
                })
                .finally(() => {
                    // ボタンを元に戻す
                    testBtn.disabled = false;
                    testBtn.innerHTML = '<i class="fas fa-paper-plane me-1"></i> 通知をテスト送信';
                });
        });
    }

    // 保存ボタン
    saveBtn.addEventListener('click', async function () {
        const toggle = document.getElementById('notificationToggle');
        const timeInput = document.getElementById('notificationTime');

        const enabled = toggle ? toggle.checked : false;
        const time = timeInput ? timeInput.value : '21:00';

        // 通知有効化時は権限リクエストとSW登録
        if (enabled) {
            const permission = await Notification.requestPermission();
            if (permission === 'granted') {
                await registerServiceWorker();
            } else {
                alert('通知権限が許可されませんでした。ブラウザの設定を確認してください。');
                return;
            }
        }

        // 設定保存
        fetch('/api/update_notification_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: enabled, time: time })
        })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    // モーダルを閉じる前にフォーカスを外す（aria-hidden警告対策）
                    saveBtn.blur();

                    const modalEl = document.getElementById('settingsModal');
                    const modal = bootstrap.Modal.getInstance(modalEl);
                    if (modal) modal.hide();

                    flashMessage('設定を保存しました', 'success');
                } else {
                    alert('保存に失敗しました: ' + data.message);
                }
            })
            .catch(err => {
                console.error('保存エラー:', err);
                alert('通信エラーが発生しました');
            });
    });
}

function toggleTimeInput(enabled) {
    const area = document.getElementById('notificationTimeArea');
    const input = document.getElementById('notificationTime');
    if (area && input) {
        if (enabled) {
            area.style.opacity = '1';
            input.disabled = false;
        } else {
            area.style.opacity = '0.5';
            input.disabled = true;
        }
    }
}

async function registerServiceWorker() {
    if (!('serviceWorker' in navigator)) return;
    if (!('PushManager' in window)) return;

    try {
        const registration = await navigator.serviceWorker.register('/static/sw.js');


        // VAPIDキー取得
        const keyRes = await fetch('/api/vapid_public_key');
        const keyData = await keyRes.json();
        const applicationServerKey = urlBase64ToUint8Array(keyData.publicKey);

        const subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: applicationServerKey
        });

        // サブスクリプション送信
        await fetch('/api/save_subscription', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(subscription)
        });

    } catch (error) {
        console.error('Service Worker Error:', error);
    }
}

function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding)
        .replace(/\-/g, '+')
        .replace(/_/g, '/');

    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);

    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

/* =========================================
   RPG Mode Logic
   ========================================= */

let currentPostBattleDialogues = []; // 🆕 Store dialogues from result
let rpgGameData = null;
let rpgCurrentIndex = 0;
let rpgCorrectCount = 0;
let rpgTimerInterval = null;
let rpgTimeLeft = 60;
// Boss HP is purely visual based on correct count?
// Plan says: "Pass Score: 8". Boss HP implies we deplete it.
// Let's make it 10 HP. Every correct answer deals 1 damage.

document.addEventListener('DOMContentLoaded', () => {
    // Check Status on load
    setTimeout(checkRpgStatus, 1000); // Delay slightly to ensure session/load
});

function checkRpgStatus() {
    fetch('/api/rpg/status')
        .then(res => res.json())
        .then(data => {
            const banner = document.getElementById('rpgTriggerBanner');
            if (data.available && !data.is_cooldown && !data.is_cleared) {
                // Show banner
                if (banner) banner.classList.remove('hidden');

                // Update Boss Name & Icon
                if (data.boss_name) {
                    const bossNameEl = document.getElementById('rpgBossName');
                    if (bossNameEl) bossNameEl.textContent = data.boss_name;
                }
                if (data.boss_icon) {
                    const bossImgEl = document.getElementById('rpgBossImage');
                    if (bossImgEl) {
                        let iconUrl = data.boss_icon;
                        if (!iconUrl.startsWith('http') && !iconUrl.startsWith('/')) {
                            iconUrl = '/static/images/rpg/' + iconUrl;
                        }
                        // Cache busting
                        const finalUrl = iconUrl + '?t=' + new Date().getTime();

                        // Pre-load logic to handle shadow
                        bossImgEl.onload = () => {
                            const shadow = bossImgEl.parentElement.querySelector('.boss-shadow');
                            if (shadow) shadow.style.display = 'none';
                            bossImgEl.style.display = 'block';
                        };
                        bossImgEl.src = finalUrl;
                    }
                }

                // Update Difficulty Stars
                if (data.difficulty) {
                    const starsEl = document.getElementById('rpgDifficultyStars') || document.querySelector('.difficulty-stars');
                    if (starsEl) {
                        const tenStars = Math.floor(data.difficulty / 10);
                        const normalStars = data.difficulty % 10;

                        let starStr = '';
                        for (let i = 0; i < tenStars; i++) {
                            starStr += '✪';
                        }
                        for (let i = 0; i < normalStars; i++) {
                            starStr += '★';
                        }
                        starsEl.textContent = starStr;

                        let html = '';
                        for (let i = 0; i < tenStars; i++) {
                            html += '<span style="color: #e74c3c; font-size: 1.2em;">✪</span>'; // Red/Orange big star
                        }
                        for (let i = 0; i < normalStars; i++) {
                            html += '★';
                        }
                        starsEl.innerHTML = html;
                    }
                }

                // Update Dialogue & Rules
                if (data.intro_dialogue) {
                    const dialogEl = document.getElementById('rpgIntroDialog');
                    if (dialogEl) dialogEl.textContent = `"${data.intro_dialogue}"`;
                }

                if (data.time_limit) {
                    const timeEl = document.getElementById('rpgRuleTime');
                    if (timeEl) timeEl.textContent = `制限時間 ${data.time_limit}秒`;
                }

                if (data.clear_correct_count) {
                    const condEl = document.getElementById('rpgRuleCondition');
                    if (condEl) condEl.textContent = `合格ライン ${data.clear_correct_count}問正解`;
                }

                if (data.clear_max_mistakes !== undefined) {
                    const mistEl = document.getElementById('rpgRuleMistake');
                    if (mistEl) mistEl.textContent = `${data.clear_max_mistakes + 1}ミスで即終了`;
                }
            } else {
                if (banner) banner.classList.add('hidden');
            }
        })
        .catch(err => console.error("RPG check failed", err));
}

function openRpgIntro() {
    const overlay = document.getElementById('rpgOverlay');
    const intro = document.getElementById('rpgIntroScreen');
    const battle = document.getElementById('rpgBattleScreen');
    const result = document.getElementById('rpgResultScreen');

    if (overlay) overlay.classList.remove('hidden');
    if (intro) intro.classList.remove('hidden');
    if (battle) battle.classList.add('hidden');
    if (result) result.classList.add('hidden');

    // Set Image with onload handler to hide shadow
    const img = document.getElementById('rpgBossImage');
    if (img) {
        img.onload = () => {
            const shadow = img.parentElement.querySelector('.boss-shadow');
            if (shadow) shadow.style.display = 'none';
        };
        // img.src assignment removed to rely on checkRpgStatus
    }
}

// Add event listeners if elements exist (safe check)
const btnRpgCancel = document.getElementById('btnRpgCancel');
if (btnRpgCancel) btnRpgCancel.addEventListener('click', closeRpgModal);

const btnRpgClose = document.getElementById('btnRpgClose');
if (btnRpgClose) btnRpgClose.addEventListener('click', handleRpgResultDismiss); // 🆕 Custom handler

const btnRpgStart = document.getElementById('btnRpgStart');
if (btnRpgStart) btnRpgStart.addEventListener('click', startRpgGame);

function closeRpgModal() {
    const overlay = document.getElementById('rpgOverlay');
    if (overlay) overlay.classList.add('hidden');
    clearInterval(rpgTimerInterval);
}

// 🆕 Dismiss Logic
function handleRpgResultDismiss() {
    // Check for post-battle dialogues
    if (currentPostBattleDialogues && currentPostBattleDialogues.length > 0) {
        playPostBattleDialogue(currentPostBattleDialogues);
        currentPostBattleDialogues = []; // Clear after playing

        // Slight delay to allow overlay to render if needed, but synchronous removal of class should be instant.
        // Close the result modal behind the scene
        // closeRpgModal(); // REMOVED: Keep result modal open behind dialogue, close it in finishRpgIntro
        return;
    }
    closeRpgModal();
}

// ... existing code ...

function finishRpgIntro() {
    const overlay = document.getElementById('rpgStoryOverlay');
    overlay.classList.add('hidden');
    isIntroPlaying = false;

    // Ensure RPG Modal is closed (for post-battle sequence)
    closeRpgModal();

    // Mark as seen API (Harmless to call in rematch)
    fetch('/api/mark_rpg_intro_seen', { method: 'POST' })
        .then(res => res.json())
        .then(data => { });
}

let rpgIncorrectCount = 0; // 新規追加: ミス回数カウント
let rpgPassScore = 10;
let rpgMaxMistakes = 3;
let rpgStageId = 1;
let isRpgRematch = false;

function startRpgGame(enemyId = null) {
    const payload = {};
    if (enemyId && typeof enemyId !== 'object') { // event object avoidance
        payload.rematch_enemy_id = enemyId;
    }

    fetch('/api/rpg/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                rpgGameData = data.problems;
                rpgTimeLeft = data.time_limit || 60;
                rpgPassScore = data.pass_score || 10;
                rpgMaxMistakes = data.max_mistakes || 3;
                isRpgRematch = data.is_rematch || false;

                if (data.boss_info) {
                    rpgStageId = data.boss_info.id;

                    // Update UI Texts
                    document.getElementById('rpgBossName').textContent = data.boss_info.name;
                    document.getElementById('rpgRuleTime').textContent = `制限時間 ${rpgTimeLeft}秒`;
                    document.getElementById('rpgRuleCondition').textContent = `合格ライン ${rpgPassScore}問正解`;
                    document.getElementById('rpgRuleMistake').textContent = `${rpgMaxMistakes + 1}ミスで即終了`; // 3ミスでアウトなら表記は「3ミス」等。サーバーは「max_mistakes=2」を送るかも？
                    // app.py: clear_max_mistakes defaults to 2 (allowed). So 3rd mistake kills.
                    // Text: "3ミスで即終了" -> "2ミスまでOK" or "3ミスで終了".
                    // Let's explicitly say: `${rpgMaxMistakes + 1}ミスで終了`

                    // Update Image
                    // 修正: 永続化された画像URL(icon_url)を優先して使用
                    let iconUrl = data.boss_info.icon_url || data.boss_info.icon_image;

                    // フォールバック: URLでない場合のみ静的パスを付与 (互換性維持)
                    if (iconUrl && !iconUrl.startsWith('http') && !iconUrl.startsWith('/')) {
                        iconUrl = '/static/images/rpg/' + iconUrl;
                    }
                    // Cache busting
                    if (iconUrl) iconUrl += '?t=' + new Date().getTime();

                    const introImg = document.getElementById('rpgBossImage');
                    if (introImg) introImg.src = iconUrl;
                }

                rpgCurrentIndex = 0;
                rpgCorrectCount = 0;
                rpgIncorrectCount = 0; // リセット

                // Switch screen
                document.getElementById('rpgIntroScreen').classList.add('hidden');
                document.getElementById('rpgBattleScreen').classList.remove('hidden');

                updateRpgHud();
                showNextRpgQuestion();
                startRpgTimer();

                // Set battle image
                const battleImg = document.getElementById('rpgBattleBossImage');
                const introImg = document.getElementById('rpgBossImage');
                if (battleImg && introImg) battleImg.src = introImg.src;

            } else {
                alert(data.message || 'Error starting battle');
            }
        })
        .catch(err => {
            console.error(err);
            alert('通信エラーが発生しました');
        });
}

function startRpgTimer() {
    clearInterval(rpgTimerInterval);
    const timerBar = document.getElementById('rpgTimerBar');
    const totalTime = rpgTimeLeft;

    rpgTimerInterval = setInterval(() => {
        rpgTimeLeft--;
        const pct = (rpgTimeLeft / totalTime) * 100;
        if (timerBar) timerBar.style.width = `${pct}%`;

        if (rpgTimeLeft <= 0) {
            clearInterval(rpgTimerInterval);
            finishRpgGame(false); // Time up = Lose
        }
    }, 1000);
}

function updateRpgHud() {
    // Boss HP Logic: Dynamic
    const maxHp = rpgPassScore;
    const currentHp = Math.max(0, maxHp - rpgCorrectCount);
    const pct = (currentHp / maxHp) * 100;

    const hpBar = document.getElementById('rpgBossHpBar');
    if (hpBar) {
        hpBar.style.width = `${pct}%`;

        // 色を変える演出（任意）
        if (pct <= 30) {
            hpBar.style.backgroundColor = '#e74c3c'; // 赤
        } else if (pct <= 60) {
            hpBar.style.backgroundColor = '#f1c40f'; // 黄
        } else {
            hpBar.style.backgroundColor = '#e67e22'; // デフォルト（オレンジ系）
        }
    }
}

function showNextRpgQuestion() {
    // インデックスチェックだけでは終了しない（正解数orミス数で判定）
    if (rpgCurrentIndex >= rpgGameData.length) {
        // 問題が尽きた場合（通常30問あるので稀だが）
        // 目標未達なら失敗扱い
        finishRpgGame(false);
        return;
    }

    const problem = rpgGameData[rpgCurrentIndex];
    const qText = document.getElementById('rpgQuestionText');
    if (qText) qText.textContent = problem.question;

    // Server now provides choices (similar to Daily Quiz)
    const choices = problem.choices;
    const container = document.getElementById('rpgChoicesContainer');
    container.innerHTML = '';

    choices.forEach(choice => {
        const btn = document.createElement('button');
        btn.className = 'rpg-choice-btn';
        btn.textContent = choice;
        btn.onclick = () => handleRpgAnswer(choice === problem.answer, btn);
        container.appendChild(btn);
    });
}

function handleRpgAnswer(isCorrect, btnElement) {
    // Disable buttons
    const btns = document.querySelectorAll('.rpg-choice-btn');
    btns.forEach(b => b.disabled = true);

    if (isCorrect) {
        btnElement.classList.add('correct');
        rpgCorrectCount++;

        // Damage effect
        const dmg = document.getElementById('rpgDamageEffect');
        if (dmg) {
            dmg.classList.remove('hidden');
            dmg.classList.add('damage-text'); // restart anim (needs re-trigger hack if repetitive)
            // Hack to restart animation: remove class, void offsetWidth, add class
            dmg.classList.remove('damage-text');
            void dmg.offsetWidth;
            dmg.classList.add('damage-text');

            setTimeout(() => dmg.classList.add('hidden'), 800);
        }

        // Shake boss
        const boss = document.getElementById('rpgBattleBossImage');
        if (boss) {
            boss.classList.add('shake-anim');
            setTimeout(() => boss.classList.remove('shake-anim'), 500);
        }

        updateRpgHud();

        // Win Condition Check
        if (rpgCorrectCount >= rpgPassScore) {
            setTimeout(() => finishRpgGame(true), 1000);
            return;
        }

    } else {
        btnElement.classList.add('incorrect');
        rpgIncorrectCount++;

        // Screen shake or visual feedback
        document.body.classList.add('shake-anim');
        setTimeout(() => document.body.classList.remove('shake-anim'), 500);

        // Lose Condition Check: Mistakes > Max
        if (rpgIncorrectCount > rpgMaxMistakes) {
            setTimeout(() => finishRpgGame(false), 1000);
            return;
        }
    }

    // Next question delay
    setTimeout(() => {
        rpgCurrentIndex++;
        showNextRpgQuestion();
    }, 1000);
}

function finishRpgGame(isWin) {
    clearInterval(rpgTimerInterval);

    const resultScreen = document.getElementById('rpgResultScreen');
    const battleScreen = document.getElementById('rpgBattleScreen');

    if (battleScreen) battleScreen.classList.add('hidden');
    if (resultScreen) resultScreen.classList.remove('hidden');

    const title = document.getElementById('rpgResultTitle');
    const winContent = document.getElementById('rpgWinContent');
    const loseContent = document.getElementById('rpgLoseContent');

    if (title) {
        title.textContent = isWin ? "MISSION CLEAR" : "MISSION FAILED";
        title.style.color = isWin ? "#f1c40f" : "#e74c3c";
    }

    // Hide content initially to prevent flickering
    if (winContent) winContent.classList.add('hidden');
    if (loseContent) loseContent.classList.add('hidden');

    // Show Loading or just wait
    // (Optional: Add a spinner if delay is long, but for now just wait)

    // Send result
    fetch('/api/rpg/result', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_win: isWin, stage_id: rpgStageId, is_rematch: isRpgRematch })
    })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                if (isWin) {
                    checkRpgStatus(); // Hide banner

                    // Hide reward box for rematch
                    const rewardBox = document.querySelector('#rpgResultScreen .reward-box');
                    if (isRpgRematch) {
                        if (rewardBox) rewardBox.style.display = 'none';
                    } else {
                        if (rewardBox) rewardBox.style.display = 'block';
                    }

                    if (data.reward) {
                        // Update Badge Name
                        const badgeNameEl = document.getElementById('rpgRewardBadgeName');
                        if (badgeNameEl && data.reward.badge) {
                            badgeNameEl.textContent = data.reward.badge;
                        }

                        // Check if new clear
                        if (data.new_clear) {
                            // Play sound or bigger celebration
                        }
                    }

                    if (data.defeat_dialogue) {
                        const winDialog = document.getElementById('rpgWinDialogue');
                        if (winDialog) winDialog.textContent = `"${data.defeat_dialogue}"`;
                    }

                    // 🆕 Store Dialogues
                    if (data.dialogues) {
                        currentPostBattleDialogues = data.dialogues;
                    } else {
                        currentPostBattleDialogues = [];
                    }
                    // Show Win Content AFTER data population
                    if (winContent) winContent.classList.remove('hidden');
                } else {
                    // Lose
                    checkRpgStatus(); // Hide banner since it's now cooldown
                    // Show Lose Content
                    if (loseContent) loseContent.classList.remove('hidden');
                }
            } else {
                console.error('RPG Result Error:', data.message);
                // Fallback: Show content anyway if error?
                if (isWin && winContent) winContent.classList.remove('hidden');
                if (!isWin && loseContent) loseContent.classList.remove('hidden');
            }
        })
        .catch(err => {
            console.error('RPG Result Network Error:', err);
            // Fallback
            if (isWin && winContent) winContent.classList.remove('hidden');
            if (!isWin && loseContent) loseContent.classList.remove('hidden');
        });
}
// =========================================================
// RPG Intro & Dialogue Logic (Shared)
// =========================================================

let activeScenario = []; // 🆕 Dynamic scenario
const rpgIntroDefaultScenario = [
    {
        text: "ほ、ほわあぁ……目が回るのです……。\nようやく実体化できたのですホー！",
        image: "trouble.png",
        action: "appear"
    },
    {
        text: "はじめまして！ マスターさん！\nボクの名前は『ペル』。\nこの『知恵の館：バイトゥルヒクマ』を管理する、歴史書の精霊ですホー！",
        image: "normal.png",
        action: "normal"
    },
    {
        text: "ずっと待っていたのです。歴史への関心が1000を超える、あなたのような『知の守護者』が現れるのを！",
        image: "normal.png", // Or joy if preferred
        action: "normal"
    },
    {
        text: "実は今、この世界で大変なことが起きているのです。人々の記憶から歴史が薄れることで生じた『忘却の霧』が、ライブラリを侵食していて……",
        image: "grief.png",
        action: "normal"
    },
    {
        text: "そのせいで、偉大な歴史上の英雄たちが、あんな『歪んだ姿』に変えられてしまったのです！",
        image: "grief.png",
        action: "distortion_start" // Start distortion
    },
    {
        text: "あれは……アレクサンドロス大王！？\nいけません、あんな姿では本来の偉業が台無しですホー！",
        image: "trouble.png",
        action: "show_enemy"
    },
    {
        text: "マスターさん、お願いです。あなたの知識の力を貸してください！\n方法は簡単。ボクが出す問題に正解し続けること。",
        image: "analysis.png",
        action: "distortion_end" // End distortion
    },
    {
        text: "あなたの正しい知識こそが、霧を晴らす唯一の光なのです！\n敵を倒して、英雄たちを本来のカッコいい姿に戻してあげるのですホー！",
        image: "analysis.png",
        action: "normal"
    },
    {
        text: "さあ、準備はいいですか？\n歴史を取り戻す冒険へ……出発進行なのです！！",
        image: "caution.png",
        action: "ready"
    }
];

let currentIntroIndex = 0;
let isIntroPlaying = false;
let typeWriterTimeout;
let isTyping = false;
const TYPE_SPEED = 30; // ms per char

function checkAndPlayRpgIntro() {
    // 範囲選択画面にいるかチェック
    const ts = new Date().getTime(); // 🆕 Cache busting
    fetch('/api/check_rpg_intro_eligibility?t=' + ts)
        .then(response => response.json())
        .then(data => {

            if (data.eligible) {
                // Set default scenario
                playRpgIntroSequence(rpgIntroDefaultScenario);
            }
        })
        .catch(err => console.error("Intro check failed", err));
}

function playRpgIntroSequence(scenarioData) {
    if (scenarioData) activeScenario = scenarioData; // Set scenario

    isIntroPlaying = true;
    const overlay = document.getElementById('rpgStoryOverlay');
    const noise = document.getElementById('storyNoiseLayer');
    const light = document.getElementById('storyLightLayer');
    const charContainer = document.getElementById('storyCharacterContainer');

    if (!overlay) return;

    overlay.classList.remove('hidden');
    overlay.classList.add('glitch-active');
    noise.classList.remove('hidden');
    noise.classList.add('intense');

    setTimeout(() => {
        noise.classList.remove('intense');
        overlay.classList.remove('glitch-active');
        noise.classList.add('hidden');
        light.classList.remove('hidden');

        setTimeout(() => {
            light.classList.add('hidden');
            charContainer.classList.remove('hidden');

            setTimeout(() => {
                startIntroDialogue();
            }, 200);

        }, 300);
    }, 500);
}

// 🆕 Post-Battle Dialogue Player (No Glitch)
function playPostBattleDialogue(dialogues) {
    // Map backend dialogue to scenario format
    const scenario = dialogues.map(d => ({
        text: d.content,
        // Helper to ensure extension
        image: (d.expression && !d.expression.includes('.')) ? d.expression + '.png' : (d.expression || 'normal.png'),
        action: 'normal'
    }));

    activeScenario = scenario;
    isIntroPlaying = true;

    const overlay = document.getElementById('rpgStoryOverlay');
    const charContainer = document.getElementById('storyCharacterContainer');
    const dialogueBox = document.getElementById('storyDialogueBox');
    const enemySil = document.getElementById('storyEnemySilhouette');
    const perImg = document.getElementById('storyPerImage');

    if (!overlay) return;

    // 1. Reset all previous states thoroughly
    overlay.classList.remove('glitch-active');
    if (enemySil) {
        enemySil.classList.remove('show');
        enemySil.classList.add('hidden');
    }

    // 2. Reset character container completely - remove all state classes
    if (charContainer) {
        charContainer.classList.remove('move-left', 'hidden');
        charContainer.style.opacity = ''; // Clear any inline styles
    }

    // 3. Set initial Per image (first dialogue frame)
    if (perImg && scenario.length > 0) {
        const firstImage = scenario[0].image;
        perImg.src = `/static/pergamon/${firstImage}`;
    }

    // 4. Show overlay
    overlay.classList.remove('hidden');

    // 5. Use requestAnimationFrame to ensure DOM updates before showing Per
    requestAnimationFrame(() => {
        if (charContainer) {
            charContainer.classList.add('show');
        }
        if (dialogueBox) {
            dialogueBox.classList.remove('hidden');
        }

        // Start dialogue after ensuring visibility
        requestAnimationFrame(() => {
            startIntroDialogue();
        });
    });
}

function startIntroDialogue() {
    currentIntroIndex = 0;
    const dialogueBox = document.getElementById('storyDialogueBox');
    dialogueBox.classList.remove('hidden');

    const newDialogueBox = dialogueBox.cloneNode(true);
    dialogueBox.parentNode.replaceChild(newDialogueBox, dialogueBox);
    newDialogueBox.addEventListener('click', handleDialogueClick);

    updateIntroDialogueUI();
}

function handleDialogueClick() {
    const data = activeScenario[currentIntroIndex];
    if (!data) return;

    if (isTyping) {
        clearTimeout(typeWriterTimeout);
        isTyping = false;
        const textDiv = document.getElementById('storyText');
        textDiv.innerText = data.text;
        textDiv.scrollTop = textDiv.scrollHeight; // Ensure scrolled to bottom
    } else {
        nextIntroDialogue();
    }
}

function nextIntroDialogue() {
    currentIntroIndex++;
    if (currentIntroIndex >= activeScenario.length) {
        finishRpgIntro();
    } else {
        updateIntroDialogueUI();
    }
}

function updateIntroDialogueUI() {
    const data = activeScenario[currentIntroIndex];
    if (!data) return;

    const imgInfo = data.image;
    const action = data.action;
    const perImg = document.getElementById('storyPerImage');
    const enemySil = document.getElementById('storyEnemySilhouette');
    const textDiv = document.getElementById('storyText');
    const charContainer = document.getElementById('storyCharacterContainer');
    const dialogueBox = document.getElementById('storyDialogueBox');

    // Handle Actions
    if (action === 'show_enemy') {
        const enemyImg = enemySil.querySelector('img');
        if (enemyImg) {
            if (!enemyImg.src || enemyImg.src.indexOf('alex.png') === -1) {
                enemyImg.src = '/static/pergamon/alex.png';
            }
            enemySil.classList.remove('hidden');
            requestAnimationFrame(() => {
                enemySil.classList.add('show');
            });
        }
        // Move Per Left
        charContainer.classList.add('move-left');

    } else if (action === 'distortion_start') {
        let aura = document.getElementById('tempAura');
        if (!aura) {
            aura = document.createElement('div');
            aura.id = 'tempAura';
            aura.className = 'distortion-aura';
            enemySil.appendChild(aura);
        }
        const enemyImg = enemySil.querySelector('img');
        if (enemyImg) enemyImg.classList.add('enemy-distorted');

    } else if (action === 'distortion_end') {
        const enemyImg = enemySil.querySelector('img');
        const aura = document.getElementById('tempAura');
        if (aura) aura.remove();
        if (enemyImg) enemyImg.classList.remove('enemy-distorted');

        enemySil.classList.remove('show');

        // Return Per to Center immediately
        charContainer.classList.remove('move-left');

        dialogueBox.style.opacity = '0.5';

        setTimeout(() => {
            enemySil.classList.add('hidden');
            enemySil.style.opacity = "";

            perImg.src = `/static/pergamon/${data.image}`;
            dialogueBox.style.opacity = '1';

            // DON'T Hide/Show Per here -> Smooth transition to center is handled by CSS
            // Just update text
            // Wait for image load if source is changing (though here we just set it above)
            // Ideally we wait for perImg load event from line 3899, but we are inside a timeout.
            // Let's attach the load listener right after setting src above if we want to be strict,
            // but for this specific "distortion_end" sequence, the delay (1500ms) plus the transition might be enough.
            // However, to be consistent with the user Request, let's wrap the startTypewriter.

            // Since we set src at line 3899, it might be loading.
            if (perImg.complete) {
                startTypewriter(data.text, textDiv);
            } else {
                perImg.onload = () => {
                    startTypewriter(data.text, textDiv);
                    perImg.onload = null;
                };
                // Fallback in case of error or timeout logic could be added,
                // but for simplicity we assume local assets load or cached.
            }

        }, 1500);

        return;
    }

    // if (perImg) perImg.src = `/static/pergamon/${imgInfo}`;
    // startTypewriter(data.text, textDiv);

    if (perImg) {
        const newSrc = `/static/pergamon/${imgInfo}`;
        // Check if URL is actually changing to avoid unnecessary load waits if same expression
        // Note: src property is absolute URL, so strictly comparing with relative path might be tricky.
        // But usually browsers handle `src = src` as a reload or no-op depending on cache.
        // Let's check if the filename matches to avoid reload if possible,
        // OR just rely on checking `perImg.complete` immediately after setting.

        // If we set src, the browser starts loading.
        perImg.src = newSrc;

        if (perImg.complete) {
            startTypewriter(data.text, textDiv);
        } else {
            // Show loading state? Or just wait (user request: "wait for image then text")
            perImg.onload = () => {
                startTypewriter(data.text, textDiv);
                perImg.onload = null;
            };
            perImg.onerror = () => {
                console.error("Failed to load image:", newSrc);
                startTypewriter(data.text, textDiv); // Fallback: show text anyway
                perImg.onerror = null;
            };
        }
    } else {
        startTypewriter(data.text, textDiv);
    }

    // Ensure Per is validly shown (Essential fix)
    if (!charContainer.classList.contains('show')) {
        charContainer.classList.add('show');
    }
}

function startTypewriter(text, element) {
    if (typeWriterTimeout) clearTimeout(typeWriterTimeout);
    isTyping = true;
    element.innerHTML = "";
    let i = 0;

    function type() {
        if (i < text.length) {
            if (text.charAt(i) === '\n') {
                element.appendChild(document.createElement('br'));
            } else {
                element.append(text.charAt(i));
            }
            // AUTO SCROLL
            element.scrollTop = element.scrollHeight;

            i++;
            typeWriterTimeout = setTimeout(type, TYPE_SPEED);
        } else {
            isTyping = false;
        }
    }
    type();
}

function finishRpgIntro() {
    const overlay = document.getElementById('rpgStoryOverlay');
    overlay.classList.add('hidden');
    isIntroPlaying = false;

    // Mark as seen API
    fetch('/api/mark_rpg_intro_seen', { method: 'POST' })
        .then(res => res.json())
        .then(data => { });
}

// Initialize check on load
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(checkAndPlayRpgIntro, 1000); // Small delay to ensure render
});

// Update ID generation fallback logic
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
        // Fallback
        const chapter = String(word.chapter || '0').padStart(3, '0');
        const number = String(word.number || '0').padStart(3, '0');
        return `${chapter}-${number}-error`;
    }
}