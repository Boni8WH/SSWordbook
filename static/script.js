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
let currentSessionAnswered = new Set(); // 今回のセッションで回答した問題のIDを記録
let quizStartTime;
let isAnswerButtonDisabled = false;
let answerButtonTimeout = null;
let hasBeenRestricted = false; // 一度でも制限されたかのフラグ
let restrictionReleased = false; // 制限が解除されたかのフラグ
let isStrategicRetreat = false; // 戦略的撤退（強制終了）が発生したかのフラグ
let pendingReloadAfterRelease = false; // 制限解除後のリロード待ちフラグ


window.word_data = [];
let word_data = window.word_data;
let voice_vocab_data = []; // 🆕 音声認識用の軽量データ用変数を分離

// ==========================================
// 🆕 Load Full Vocabulary for Voice Recognition
// ==========================================
function fetchFullVocabulary() {
    fetch('/api/get_full_vocabulary')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success' && data.vocabulary) {
                // console.log(`🎤 Full Vocabulary Loaded: ${data.count} words`);
                voice_vocab_data = data.vocabulary;
            }
        })
        .catch(err => {
            console.warn('Failed to load full vocabulary:', err);
        });
}

// Call on load
document.addEventListener('DOMContentLoaded', () => {
    fetchFullVocabulary();
});


// ==========================================
// Constants for Weakness Mode (Penalty Delay)
// ==========================================
const COOLDOWN_DURATION = 4 * 60 * 60 * 1000; // 4 hours in milliseconds

function isCoolingDown(history) {
    if (!history || !history.cooldown_until) return false;
    return history.cooldown_until > Date.now();
}

function getValidWeakProblemCount() {
    if (!incorrectWords || incorrectWords.length === 0) return 0;
    if (!word_data || word_data.length === 0) return 0;

    // 現在のword_dataに存在する問題IDのセットを作成 (削除された問題を除外するため)
    const validDataIds = new Set(word_data.map(word => generateProblemId(word)));

    // Count only problems that exist in current data AND are NOT in cooldown
    const validWeakSet = new Set();
    for (const problemId of incorrectWords) {
        if (!validDataIds.has(problemId)) continue;

        const history = problemHistory[problemId];
        if (!isCoolingDown(history)) {
            validWeakSet.add(problemId);
        }
    }
    return validWeakSet.size;
}


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
const voiceAnswerBtn = document.getElementById('voiceAnswerBtn');
const voiceAnswerBtnMobile = document.getElementById('voiceAnswerBtnMobile');
const voiceFeedback = document.getElementById('voiceFeedback');
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
        button.style.color = '#ffffff';
        button.classList.add('deselect-mode');
    } else {
        button.textContent = isMobile ? '選択' : '全て選択';
        button.style.backgroundColor = '#3498db';
        button.style.borderColor = '#2980b9';
        button.style.color = '#ffffff';
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

        // ログイン時のみデータをロードする
        if (window.appInfoFromFlask && window.appInfoFromFlask.isLoggedIn) {
            loadUserData();
            loadWordDataFromServer();
            checkAnnouncementStatus(); // 🆕 お知らせ状態チェック
        } else {
            console.log("Not logged in, skipping data load.");
        }

        setupEventListeners();

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
            let loadedData = null;

            // 修正: APIは配列を直接返す場合がある
            if (Array.isArray(data)) {
                loadedData = data;
            } else if (data.status === 'success' && data.word_data) {
                loadedData = data.word_data;

                if (data.star_availability) {
                    starProblemStatus = data.star_availability;
                }
            }

            if (loadedData) {
                // 必須フィールドのチェック（クライアント側でもフィルタリング）
                // ★修正: 空白のみのデータも除外
                word_data = loadedData.filter(w => w.question && w.answer && w.question.trim() !== '' && w.answer.trim() !== '');

                console.log(`✅ User Word Data Loaded: ${word_data.length} words`); // Debug Log
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
    const rangeSelectionIcon = document.getElementById('rangeSelectionIcon');
    const questionCountRadios = document.querySelectorAll('input[name="questionCount"]:not(#incorrectOnlyRadio)');
    const weakCheckbox = document.getElementById('incorrectOnlyCheckbox2');
    const startBtn = document.getElementById('startButton');
    const resetBtn = document.getElementById('resetSelectionButton');
    const mainHeader = document.querySelector('.question-count-selection .section-header-styled');

    // ★修正：有効な苦手問題数を使用
    const weakProblemCount = getValidWeakProblemCount();

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
        pendingReloadAfterRelease = true; // ★追記: 解除されたらリロード待ちにする
        stateChanged = true;
    }

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

    const isOvercomeModeOn = isCurrentlyRestricted || (weakCheckbox && weakCheckbox.checked);

    if (isOvercomeModeOn) {
        // 克服モードON（制限中または手動ON）
        if (isCurrentlyRestricted && weakCheckbox) {
            weakCheckbox.checked = true;
            weakCheckbox.disabled = true;
            weakCheckbox.closest('.filter-option-btn')?.classList.add('disabled');
        }

        questionCountRadios.forEach(radio => {
            radio.disabled = false;
            radio.parentElement.style.opacity = '1';
        });

        if (rangeSelectionArea) {
            const searchBtn = document.getElementById('openSearchButton');
            if (isCurrentlyRestricted) {
                // 制限がかかっている場合：出題範囲セクションごと非表示にする
                rangeSelectionArea.style.display = 'none';

                if (mainHeader && startBtn && startBtn.parentElement !== mainHeader) {
                    if (resetBtn) resetBtn.style.display = 'none';
                    mainHeader.appendChild(startBtn);
                    // ヘッダー用のコンパクトな微調整
                    startBtn.style.setProperty('width', 'auto', 'important');
                    startBtn.style.setProperty('padding', '5px 15px', 'important');
                    startBtn.style.setProperty('font-size', '0.85rem', 'important');
                    startBtn.style.setProperty('min-width', '0', 'important');
                    startBtn.style.setProperty('display', 'inline-flex', 'important');
                    startBtn.style.setProperty('flex', '0 0 auto', 'important');
                    startBtn.classList.add('btn-sm', 'rounded-pill', 'shadow-sm');
                }
            } else {
                // 制限はないが「克服モード」がONの場合（手動）：構成要素を再表示し、チャプター類のみを薄くする
                rangeSelectionArea.style.display = 'block';
                const rangeHeader = rangeSelectionArea.querySelector('.section-header-styled h3');
                if (rangeHeader) rangeHeader.style.display = 'block';
                if (searchBtn) {
                    searchBtn.style.display = 'inline-flex';
                    searchBtn.classList.add('dimmed');
                }
                if (chaptersContainer) {
                    chaptersContainer.style.display = 'block';
                    chaptersContainer.classList.add('dimmed');
                    chaptersContainer.style.opacity = '';
                    chaptersContainer.style.pointerEvents = 'none';
                }
                rangeSelectionArea.classList.remove('dimmed');

                // 開始ボタンを元の位置に戻す（もし移動していたら）
                const originalBtnParent = document.querySelector('.range-selection-area .section-header-styled div:last-child');
                if (originalBtnParent && startBtn && startBtn.parentElement !== originalBtnParent) {
                    if (resetBtn) resetBtn.style.display = 'inline-block';
                    originalBtnParent.appendChild(startBtn);
                    // スタイルのリセット
                    startBtn.style.marginLeft = '';
                    startBtn.style.setProperty('width', '', '');
                    startBtn.style.setProperty('padding', '8px 20px', '');
                    startBtn.style.setProperty('font-size', '', '');
                    startBtn.style.setProperty('min-width', '', '');
                    startBtn.style.setProperty('display', '', '');
                    startBtn.style.setProperty('flex', '', '');
                    startBtn.classList.remove('btn-sm', 'rounded-pill', 'shadow-sm');
                }
            }
        }

        if (rangeSelectionTitleText) {
            rangeSelectionTitleText.textContent = '克服モード';
            if (!rangeSelectionTitleText.classList.contains('overcome-title')) {
                rangeSelectionTitleText.classList.remove('overcome-title');
                void rangeSelectionTitleText.offsetWidth; // reflow
                rangeSelectionTitleText.classList.add('overcome-title');
            }
            rangeSelectionTitleText.style.color = '';
        }
        if (rangeSelectionIcon) {
            rangeSelectionIcon.className = 'fas fa-fire';
            rangeSelectionIcon.style.color = '#f5a623';
        }

        if (isCurrentlyRestricted) {
            if (weakProblemCount >= 20) {
                showWeakProblemWarning(weakProblemCount);
            } else if (weakProblemCount > 10) {
                showIntermediateWeakProblemWarning(weakProblemCount);
            }
        }

    } else {
        // 通常モード
        questionCountRadios.forEach(radio => {
            radio.disabled = false;
            radio.parentElement.style.opacity = '1';
        });

        if (weakCheckbox) {
            weakCheckbox.disabled = false;
            weakCheckbox.closest('.filter-option-btn')?.classList.remove('disabled');
        }

        if (rangeSelectionArea) {
            rangeSelectionArea.style.display = 'block';
            rangeSelectionArea.classList.remove('dimmed');
            const rangeHeader = rangeSelectionArea.querySelector('.section-header-styled h3');
            if (rangeHeader) rangeHeader.style.display = 'block';
        }
        if (chaptersContainer) {
            chaptersContainer.style.display = 'block';
            chaptersContainer.style.opacity = '1';
            chaptersContainer.style.pointerEvents = 'auto';
            chaptersContainer.classList.remove('dimmed');
        }
        const searchBtn = document.getElementById('openSearchButton');
        if (searchBtn) {
            searchBtn.style.display = 'inline-flex';
            searchBtn.classList.remove('dimmed');
        }

        // 開始ボタンを元の位置に戻す
        const originalBtnParent = document.querySelector('.range-selection-area .section-header-styled div:last-child');
        if (originalBtnParent && startBtn && startBtn.parentElement !== originalBtnParent) {
            if (resetBtn) resetBtn.style.display = 'inline-block';
            originalBtnParent.appendChild(startBtn);
            // スタイルのリセット
            startBtn.style.marginLeft = '';
            startBtn.style.setProperty('width', '', '');
            startBtn.style.setProperty('padding', '8px 20px', '');
            startBtn.style.setProperty('font-size', '', '');
            startBtn.style.setProperty('min-width', '', '');
            startBtn.style.setProperty('display', '', '');
            startBtn.style.setProperty('flex', '', '');
            startBtn.classList.remove('btn-sm', 'rounded-pill', 'shadow-sm');
        }

        if (rangeSelectionTitleText) {
            rangeSelectionTitleText.textContent = '出題数を選択';
            rangeSelectionTitleText.classList.remove('overcome-title');
            rangeSelectionTitleText.style.color = '';
        }
        if (rangeSelectionIcon) {
            rangeSelectionIcon.className = 'fas fa-layer-group';
            rangeSelectionIcon.style.color = '';
        }

        const existingWarning = document.getElementById('weakProblemWarning');
        if (existingWarning) {
            existingWarning.remove();
        }
    }

    // ★追記: 表示を同期させる（制限中の「全20問」などの表示を反映）
    updateSelectionTotalCount();
}

// =========================================================
// イベントリスナーの設定
// =========================================================
function setupEventListeners() {
    try {
        if (startButton) startButton.addEventListener('click', startQuiz);

        // Voice Answer Logic (PC & Mobile)
        if ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window) {
            if (voiceAnswerBtn) {
                voiceAnswerBtn.style.display = 'inline-flex';
                voiceAnswerBtn.addEventListener('click', startVoiceRecognition);
            }
            if (voiceAnswerBtnMobile) {
                voiceAnswerBtnMobile.style.display = 'inline-flex';
                voiceAnswerBtnMobile.addEventListener('click', startVoiceRecognition);
                // モバイル・タブレット向けに touchstart も追加
                // passive: false にして preventDefault を許可する
                voiceAnswerBtnMobile.addEventListener('touchstart', function (e) {
                    startVoiceRecognition(e);
                }, { passive: false });
            }
        } else {
            console.log("Web Speech API not supported.");
        }

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

// getValidWeakProblemCount moved to top level

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
    // ★修正: checkboxの状態をチェック
    const isIncorrectOnly = document.getElementById('incorrectOnlyCheckbox2')?.checked || false;

    // ★重要: チェックボックスの状態を直接取得
    const unsolvedCheckbox = document.getElementById('unsolvedOnlyCheckbox');
    const unmasteredCheckbox = document.getElementById('unmasteredOnlyCheckbox');

    const isUnsolvedOnly = unsolvedCheckbox ? unsolvedCheckbox.checked : false;
    const isUnmasteredOnly = unmasteredCheckbox ? unmasteredCheckbox.checked : false;

    if (isIncorrectOnly) {
        // 苦手問題モードの場合
        // 苦手問題モードの場合
        quizQuestions = word_data.filter(word => {
            const wordIdentifier = generateProblemId(word);
            // 苦手リストに含まれており、かつクールダウン中でないもの
            if (!incorrectWords.includes(wordIdentifier)) return false;

            const history = problemHistory[wordIdentifier];
            if (isCoolingDown(history)) return false;

            return true;
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
        isStrategicRetreat = false; // フラグをリセット

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

        // ★追記: 途中介入（戦略的撤退）で無効化されたボタンを確実に有効化する
        if (correctButton) correctButton.disabled = false;
        if (incorrectButton) incorrectButton.disabled = false;

        const weakProblemCount = getValidWeakProblemCount();
        const rawWeakProblemCount = incorrectWords.length; // 表示用などに元の数も保持
        // ★修正: 'incorrectOnly' 文字列ではなく、数値を取得
        const selectedQuestionCount = getSelectedQuestionCount();
        // ★修正: checkboxの状態をチェック
        let isIncorrectOnly = document.getElementById('incorrectOnlyCheckbox2')?.checked || false;

        const isCurrentlyRestricted = hasBeenRestricted && !restrictionReleased;
        const isUnsolvedOnly = document.getElementById('unsolvedOnlyCheckbox')?.checked || false;
        const isUnmasteredOnly = document.getElementById('unmasteredOnlyCheckbox')?.checked || false;

        if (isCurrentlyRestricted && !isIncorrectOnly) {
            // ★追加: 制限中だが、有効な苦手問題が0問の場合（データの不整合など）
            // 自動的に制限を解除して、通常モードで開始できるようにする
            if (weakProblemCount === 0) {
                console.warn('⚠️ 制限中ですが有効な苦手問題が0問です。制限を自動解除します。');
                hasBeenRestricted = false;
                restrictionReleased = true;
                pendingReloadAfterRelease = true; // ★追記
                saveRestrictionState(); // サーバーに保存

                flashMessage('有効な苦手問題が見つからないため、制限を解除しました。', 'info');

                // 状態更新のためにリロードせず、そのまま処理を続行させる（再帰呼び出しは避ける）
                // UI更新
                updateIncorrectOnlySelection();

                // 続行許可（下の処理へ）
            } else {
                // 制限を適用し、苦手問題モードを強制する
                isIncorrectOnly = true;
                if (document.getElementById('incorrectOnlyCheckbox2')) {
                    document.getElementById('incorrectOnlyCheckbox2').checked = true;
                }
                updateIncorrectOnlySelection();

                // 続行を許可する（下で getFilteredQuestions() が呼ばれる際に isIncorrectOnly=true として扱われる）
                /*
                if (weakProblemCount >= 20) {
                    flashMessage('苦手問題が20問以上あります。まず苦手問題モードで学習してください。', 'danger');
                } else {
                    flashMessage(`苦手問題を10問以下に減らすまで、苦手問題モードで学習してください。（現在${weakProblemCount}問）`, 'warning');
                }
                return;
                */
            }
        }

        let quizQuestions = getFilteredQuestions();

        // 苦手問題モード・未解答モード・未マスターモードの場合は範囲選択チェックをスキップ
        // ただし通常モードの場合は、単元が選択されているか確認
        if (!isIncorrectOnly) {
            const rawSelected = getSelectedQuestions();
            if (rawSelected.length === 0) {
                // 通常モードで単元未選択の場合のチェック（UnsolvedOnlyなどがない場合）
                if (!isUnsolvedOnly && !isUnmasteredOnly) {
                    // console.log('Range selection empty. SelectedRadio:', selectedQuestionCount, 'isIncorrectOnly:', isIncorrectOnly);
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

        // 問題数の制限（苦手問題モード関係なく制限するようになった）
        // ★修正: 苦手問題モードでもカウント制限を行う
        if (selectedQuestionCount !== 'all') {
            const count = parseInt(selectedQuestionCount);
            if (!isNaN(count) && quizQuestions.length > count) {
                quizQuestions = shuffleArray(quizQuestions).slice(0, count);
            }
        }

        if (quizQuestions.length === 0) {
            // エラーメッセージの詳細化
            if (isUnsolvedOnly) flashMessage('選択範囲に未解答の問題はありません。', 'info');
            else if (isUnmasteredOnly) flashMessage('選択範囲に未マスターの問題はありません。', 'success');
            else if (isIncorrectOnly) flashMessage('克服リストに対象の問題がありません。', 'info');
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
        currentSessionAnswered.clear();

        // UIの切り替え
        if (selectionArea) selectionArea.classList.add('hidden');
        if (cardArea) cardArea.classList.remove('hidden');
        if (quizResultArea) quizResultArea.classList.add('hidden');
        // weakWordsListSection reference removed
        if (noWeakWordsMessage) noWeakWordsMessage.classList.add('hidden');

        // ★追加: コラムを非表示にする
        toggleTodaysColumn(false);

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

    // 最新の苦手問題リストを取得 (クールダウン中を除く)
    const currentWeakProblems = word_data.filter(word => {
        const wordIdentifier = generateProblemId(word);
        if (!incorrectWords.includes(wordIdentifier)) return false;

        const history = problemHistory[wordIdentifier];
        if (isCoolingDown(history)) return false;

        return true;
    });

    if (currentWeakProblems.length === 0) {
        // 克服対象の問題がなくなった場合
        // ★修正: 本当に克服したのか、全てクールダウン中なのかを判定
        const allCooldown = incorrectWords.length > 0;
        showNoWeakProblemsMessage(allCooldown);
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
        flashMessage(`✨ ${improvedCount}問を克服しました！`, 'success');
    }

    // 新しい苦手問題セットでクイズを開始
    currentQuizData = shuffleArray(currentWeakProblems);

    // ★修正: 前回と同じ問題数制限を適用する
    const selectedQuestionCount = lastQuizSettings.questionCount;
    if (selectedQuestionCount && selectedQuestionCount !== 'all' && selectedQuestionCount !== 'incorrectOnly') {
        const count = parseInt(selectedQuestionCount);
        if (!isNaN(count) && currentQuizData.length > count) {
            currentQuizData = currentQuizData.slice(0, count);
        }
    }

    currentQuestionIndex = 0;
    correctCount = 0;
    incorrectCount = 0;
    totalQuestions = currentQuizData.length;
    quizStartTime = Date.now();
    currentSessionAnswered.clear();

    // UIの切り替え
    if (quizResultArea) quizResultArea.classList.add('hidden');
    if (cardArea) cardArea.classList.remove('hidden');

    // ★追加: コラムを非表示にする
    toggleTodaysColumn(false);

    updateProgressBar();
    showNextQuestion();
}

function clearPreviousCelebrationMessages() {
    const existingCelebrations = document.querySelectorAll('.no-weak-problems-celebration');
    existingCelebrations.forEach(element => {
        element.remove();
    });
}

function showNoWeakProblemsMessage(isAllCooldown = false) {
    // ★重要：既存のお祝いメッセージを削除
    const existingCelebration = document.querySelector('.no-weak-problems-celebration');
    if (existingCelebration) {
        existingCelebration.remove();

    }

    // ★シンプルなデザインのメッセージを作成
    const messageDiv = document.createElement('div');
    messageDiv.className = 'no-weak-problems-celebration';

    if (isAllCooldown) {
        // ★全てクールダウン中の場合のメッセージ
        messageDiv.innerHTML = `
            <div style="text-align: center; padding: 25px; background-color: #f8f9fa; border: 2px solid #6c757d; border-radius: 8px; margin: 20px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                <div style="font-size: 3em; margin-bottom: 15px;">⏳</div>
                <h3 style="margin: 0 0 10px 0; color: #6c757d; font-size: 1.4em;">クールダウン中</h3>
                <p style="color: #495057; margin: 10px 0; font-size: 1.1em;">現在の克服対象はすべてクールダウン中です。</p>
                <p style="color: #6c757d; margin: 15px 0; font-size: 0.95em;">長期記憶ができているか、時間をおいて確認しましょう。</p>
                <button onclick="backToSelectionScreen()" class="btn btn-secondary" style="margin-top: 15px; padding: 10px 25px; font-weight: 600;">
                    <i class="fas fa-arrow-left"></i> トップに戻る
                </button>
            </div>
        `;
        flashMessage('⏳ 苦手問題はすべてクールダウン中です。', 'info');
    } else {
        // ★本当に克服した場合のメッセージ
        messageDiv.innerHTML = `
            <div style="text-align: center; padding: 25px; background-color: #f8f9fa; border: 2px solid #28a745; border-radius: 8px; margin: 20px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                <div style="font-size: 3em; margin-bottom: 15px;">🎉</div>
                <h3 style="margin: 0 0 10px 0; color: #28a745; font-size: 1.4em;">おめでとうございます！</h3>
                <p style="color: #495057; margin: 10px 0; font-size: 1.1em;">克服リストの全問題をクリアしました！</p>
                <p style="color: #6c757d; margin: 15px 0; font-size: 0.95em;">新しい問題に挑戦して、さらに学習を進めましょう。</p>
                <button onclick="backToSelectionScreen()" class="btn btn-success" style="margin-top: 15px; padding: 10px 25px; font-weight: 600;">
                    <i class="fas fa-arrow-left"></i> 新しい範囲を選択する
                </button>
            </div>
        `;
        flashMessage('🎉 克服リストの全問題をクリアしました！', 'success');
    }

    // ★quizResultAreaの先頭に挿入（既存コンテンツの前に）
    if (quizResultArea) {
        const firstChild = quizResultArea.firstChild;
        if (firstChild) {
            quizResultArea.insertBefore(messageDiv, firstChild);
        } else {
            quizResultArea.appendChild(messageDiv);
        }
    }
}

function showNextQuestion() {
    if (answerElement) answerElement.classList.add('hidden');
    if (showAnswerButton) showAnswerButton.classList.remove('hidden');
    if (correctButton) correctButton.classList.add('hidden');
    if (incorrectButton) incorrectButton.classList.add('hidden');
    // Voice Feedback Cleanup (Fix #3)
    if (voiceFeedback) {
        voiceFeedback.innerHTML = '';
        voiceFeedback.classList.add('hidden');
    }

    // Reset Voice Success Lock
    isProcessingVoiceSuccess = false;

    // Re-enable Voice Buttons
    [voiceAnswerBtn, voiceAnswerBtnMobile].forEach(btn => {
        if (btn) {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.style.cursor = 'pointer';
        }
    });

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

            // ★新機能: 「あと1回で克服」インジケーターを表示
            // 既存のインジケーターがあれば削除
            const existingIndicator = document.getElementById('mastery-indicator');
            if (existingIndicator) existingIndicator.remove();

            const wordIdentifier = generateProblemId(currentWord);
            if (incorrectWords.includes(wordIdentifier)) {
                // 履歴情報を確認
                const history = problemHistory[wordIdentifier];
                if (history && history.correct_streak >= 1) {
                    // あと1回で克服！
                    const indicator = document.createElement('div');
                    indicator.id = 'mastery-indicator';
                    indicator.style.marginBottom = '8px'; // 下に少し余白
                    indicator.style.textAlign = 'left';   // 左寄せ
                    indicator.innerHTML = `
                        <span class="badge bg-warning text-dark animate__animated animate__pulse animate__infinite">
                            <i class="fas fa-fire"></i> ここで正解で克服！
                        </span>
                    `;
                    // 質問文の上（直前）に挿入
                    questionElement.parentNode.insertBefore(indicator, questionElement);
                }
            }

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

    // Disable Voice Buttons when answer is revealed
    [voiceAnswerBtn, voiceAnswerBtnMobile].forEach(btn => {
        if (btn) {
            btn.disabled = true;
            btn.style.opacity = '0.5';
            btn.style.cursor = 'not-allowed';
        }
    });
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
    currentSessionAnswered.add(wordIdentifier);

    if (isCorrect) {
        correctCount++;
        problemHistory[wordIdentifier].correct_attempts++;
        problemHistory[wordIdentifier].correct_streak++;

        // 正解したらクールダウン解除
        if (problemHistory[wordIdentifier].cooldown_until) {
            delete problemHistory[wordIdentifier].cooldown_until;
        }

        // 2回連続正解で克服
        if (problemHistory[wordIdentifier].correct_streak >= 2) {
            const incorrectIndex = incorrectWords.indexOf(wordIdentifier);
            if (incorrectIndex > -1) {
                incorrectWords.splice(incorrectIndex, 1);
            }
        }
    } else {
        incorrectCount++;
        problemHistory[wordIdentifier].incorrect_attempts++;

        // ★修正: 既にリストに入っている かつ 以前に正解したことがある問題のみクールダウン
        const isAlreadyWeak = incorrectWords.includes(wordIdentifier);
        const wasProgressing = (problemHistory[wordIdentifier].correct_streak > 0);

        problemHistory[wordIdentifier].correct_streak = 0;

        if (isAlreadyWeak && wasProgressing) {
            problemHistory[wordIdentifier].cooldown_until = Date.now() + COOLDOWN_DURATION;
        }

        if (!isAlreadyWeak) {
            incorrectWords.push(wordIdentifier);
        }
    }

    // ★修正：1問ごとに即座に保存（統計更新対応版）
    saveQuizProgressToServer().then(() => {
        // 制限状態の即座更新
        setTimeout(() => {
            updateIncorrectOnlySelection();
            checkMidQuizIntervention(); // ★新機能：途中経過での制限・演出チェック
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

let hasShown20Warning = false;

/**
 * 途中経過での制限・演出チェック
 * 苦手が溜まりすぎた際の「戦略的撤退」を促す
 */
function checkMidQuizIntervention() {
    // 克服モード（苦手のみ）実行中は中断しない
    if (lastQuizSettings && lastQuizSettings.isIncorrectOnly) return;

    const weakCount = getValidWeakProblemCount();

    // 20問：戦略的撤退（ハードストップ）
    if (weakCount >= 20) {
        triggerStrategicRetreat();
    }
}

function showWarningPulse() {
    const flash = document.createElement('div');
    flash.style.cssText = `
        position: fixed; inset: 0; z-index: 9000;
        pointer-events: none; border: 10px solid rgba(231, 76, 60, 0.5);
        animation: pulseWarn 1.5s ease-out forwards;
    `;
    document.body.appendChild(flash);

    const style = document.createElement('style');
    style.textContent = `
        @keyframes pulseWarn {
            0% { opacity: 0; transform: scale(1.05); }
            30% { opacity: 1; transform: scale(1); }
            100% { opacity: 0; transform: scale(0.95); }
        }
    `;
    document.head.appendChild(style);

    flashMessage('⚠️ 苦手問題が20問を超えました。一旦区切りをつけて克服に集中しましょう。', 'warning');

    setTimeout(() => {
        flash.remove();
        style.remove();
    }, 2000);
}

function triggerStrategicRetreat() {
    const overlay = document.getElementById('strategicRetreatOverlay');
    if (!overlay) return;

    isStrategicRetreat = true; // 戦略的撤退フラグを立てる

    // ボタン類を無効化して誤操作を防ぐ
    if (correctButton) correctButton.disabled = true;
    if (incorrectButton) incorrectButton.disabled = true;

    // --- シネマティック演出開始 ---
    const slash = document.getElementById('katanaSlash');
    const inkContainer = document.getElementById('inkSplashContainer');

    // 1. スクリーンシェイク (瞬時に開始)
    document.body.classList.add('screen-shake');

    // 2. 一閃 (ほんの少し遅らせ、シェイクと同調)
    if (slash) {
        slash.classList.remove('hidden');
        slash.classList.add('animate');
    }

    // 3. 墨汁の「浸食」 (複数の墨だまりを不規則に発生)
    setTimeout(() => {
        if (inkContainer) {
            inkContainer.classList.remove('hidden');
            spawnInkBlots(inkContainer, 20); // 少し数を増やしてサイズを小さく
        }
    }, 150);

    // 4. モダールの表示と墨の「吸い込み（解散）」
    setTimeout(() => {
        overlay.classList.remove('hidden');
        startSakuraAnimation();

        // 演出用要素のクリーンアップ
        document.body.classList.remove('screen-shake');
        if (slash) {
            slash.classList.add('hidden');
            slash.classList.remove('animate');
        }

        // 墨を吸い込ませる（dissolve）
        dissolveInkBlots();

        // 5. 師範ペルの登場 (カードが出てから少し遅らせる)
        setTimeout(() => {
            const zenPer = document.getElementById('zenPerContainer');
            if (zenPer) zenPer.classList.add('show');
        }, 600);

        // 最後にコンテナを隠す
        setTimeout(() => {
            if (inkContainer) {
                inkContainer.classList.add('hidden');
                inkContainer.innerHTML = '';
            }
        }, 4000); // 1200 -> 4000 (ディレイ ＋ フェードアウトの完遂を待つ)
    }, 800);

    const retreatBtn = document.getElementById('retreatToResultButton');
    if (retreatBtn) {
        retreatBtn.onclick = () => {
            const zenPer = document.getElementById('zenPerContainer');
            if (zenPer) zenPer.classList.remove('show'); // リセット
            stopSakuraAnimation();
            overlay.classList.add('hidden');
            showQuizResult();
        };
    }
}

/**
 * 有機的な「墨だまり」を生成
 */
function spawnInkBlots(container, count) {
    container.innerHTML = '';

    // 画面を均等にカバーするためのセクター分割（5列x4行など）
    const cols = 5;
    const rows = Math.ceil(count / cols);

    for (let i = 0; i < count; i++) {
        const blot = document.createElement('div');
        blot.classList.add('ink-blot');

        // セクターに基づいた基本位置 + ランダムな揺らぎ
        const sectorX = (i % cols) / cols * 100;
        const sectorY = Math.floor(i / cols) / rows * 100;

        // 偏りを防ぐために位置を分散させる
        const left = sectorX + (Math.random() * (100 / cols) - 10);
        const top = sectorY + (Math.random() * (100 / rows) - 10);

        // 画面幅に応じてベースサイズを調整 (スマホ・タブレットは少し大きく)
        const isSmallScreen = window.innerWidth <= 768;
        const minSize = isSmallScreen ? 30 : 15;
        const extraSize = isSmallScreen ? 20 : 20;

        // サイズをさらに小さくし、より繊細な「点」としての表現を強化
        const size = minSize + Math.random() * extraSize;
        const delay = Math.random() * 0.8; // 出現タイミングをよりまばらに (0.3 -> 0.8)

        blot.style.width = `${size}vw`;
        blot.style.height = `${size}vw`;
        blot.style.top = `${top}%`;
        blot.style.left = `${left}%`;
        blot.style.transitionDelay = `${delay}s`;

        container.appendChild(blot);

        // 次のフレームで活性化
        requestAnimationFrame(() => {
            blot.classList.add('active');
        });
    }
}

/**
 * 墨が和紙に吸い込まれるような演出
 */
function dissolveInkBlots() {
    const blots = document.querySelectorAll('.ink-blot');
    blots.forEach((blot, index) => {
        const delay = Math.random() * 1.2; // より長く、まばらに消えるように調整 (0.6 -> 1.2)
        setTimeout(() => {
            blot.classList.remove('active');
            blot.classList.add('dissolve');
        }, delay * 1000);
    });
}

// --- 桜のアニメーション制御 ---
let sakuraInterval = null;

function startSakuraAnimation() {
    const container = document.getElementById('sakuraContainer');
    if (!container) return;

    container.innerHTML = '';

    // 最初にある程度降らせる
    for (let i = 0; i < 15; i++) {
        createSakura(container);
    }

    // 継続的に降らせる
    sakuraInterval = setInterval(() => {
        createSakura(container);
    }, 400);
}

function stopSakuraAnimation() {
    if (sakuraInterval) {
        clearInterval(sakuraInterval);
        sakuraInterval = null;
    }
    const container = document.getElementById('sakuraContainer');
    if (container) container.innerHTML = '';
}

function createSakura(container) {
    const petal = document.createElement('div');
    petal.classList.add('petal');

    const size = Math.random() * 10 + 10;
    const startX = Math.random() * 100;
    const duration = Math.random() * 5 + 5;
    const delay = Math.random() * 2;

    petal.style.width = `${size}px`;
    petal.style.height = `${size}px`;
    petal.style.left = `${startX}vw`;
    petal.style.animationDuration = `${duration}s`;
    petal.style.animationDelay = `-${delay}s`;

    container.appendChild(petal);

    // アニメーション終了後に削除
    setTimeout(() => {
        petal.remove();
    }, duration * 1000);
}

// 1問回答後の軽量な進捗通知
function showQuizTimeProgressNotification(weakCount) {
    // 制限状態に関わる重要な変化のみ通知
    const wasRestricted = hasBeenRestricted && !restrictionReleased;
    // ★修正：有効な苦手問題数を使用
    const currentWeakCount = getValidWeakProblemCount();

    // 制限解除の瞬間のみ通知
    if (wasRestricted && currentWeakCount <= 10) {
        showQuizTimeNotification('🔓 制限解除！', 'success');
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

    // ── アニメーション演出 ──────────────────────────────
    // ① SVG ゲージリングを正答率に合わせてアニメーション
    const gaugeFill = document.getElementById('gaugeFill');
    if (gaugeFill) {
        const circumference = 414.69; // 2π × r(66)
        const offset = circumference * (1 - accuracy / 100);
        // 開始は全て非表示 → 少し遅延後にアニメーション開始
        gaugeFill.style.strokeDashoffset = circumference;
        setTimeout(() => {
            gaugeFill.style.strokeDashoffset = offset;
        }, 150);
    }

    // ② 数字カウントアップ
    function countUp(el, target, decimals = 0, duration = 900) {
        if (!el) return;
        const start = 0;
        const step = (timestamp) => {
            if (!step.startTime) step.startTime = timestamp;
            const progress = Math.min((timestamp - step.startTime) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3); // easeOutCubic
            el.textContent = (start + (target - start) * eased).toFixed(decimals);
            if (progress < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
    }

    setTimeout(() => {
        countUp(totalQuestionsCountSpan, totalQuestions, 0);
        countUp(correctCountSpan, correctCount, 0, 1100);
        countUp(incorrectCountSpan, incorrectCount, 0, 1000);
        countUp(accuracyRateSpan, accuracy, 1, 1400);
    }, 200);

    // ③ stat-box を順番にフェードイン
    const statBoxes = document.querySelectorAll('.stat-box');
    statBoxes.forEach((box, i) => {
        box.classList.remove('visible');
        setTimeout(() => box.classList.add('visible'), 300 + i * 120);
    });
    // ───────────────────────────────────────────────────

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

    // ★重要: 戦略的撤退（強制終了）の場合は「同じ範囲でリプレイ」を表示させない
    const restartButton = document.getElementById('restartQuizButton');
    const explanationDiv = document.querySelector('.restart-explanation');
    if (isStrategicRetreat) {
        if (restartButton) restartButton.style.display = 'none';
        if (explanationDiv) explanationDiv.style.display = 'none';
    } else {
        if (restartButton) restartButton.style.display = 'flex';
        if (explanationDiv) explanationDiv.style.display = 'block';
    }

    // ★追加: 戦略的撤退時は「論述チャレンジ」を非表示にして処理をスキップ
    if (isStrategicRetreat) {
        const recommendedSection = document.getElementById('recommendedEssaysSection');
        if (recommendedSection) recommendedSection.classList.add('hidden');
        return;
    }

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
                        const formattedSnippet = essay.question_snippet.replace(/\n+/g, ' ');
                        li.innerHTML = `
                        <a href="/essay/problem/${essay.id}" class="recommended-essay-link">
                            <span class="essay-title">
                                ${essay.university} ${essay.year}年 (${essay.type})
                            </span>
                            <span class="essay-snippet">${formattedSnippet}</span>
                        </a>
                    `;
                        recommendedContainer.appendChild(li);
                    });
                    recommendedSection.classList.remove('hidden');
                } else {
                    // 4.【見つからなかった場合】セクションごと非表示にする
                    recommendedSection.classList.add('hidden');
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

        if (currentSessionAnswered.has(wordIdentifier) && history && history.incorrect_attempts > 0 && history.correct_streak === 0) {
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
    // ★新機能: 制限解除後の初回戻り時のみリロード
    if (pendingReloadAfterRelease) {
        pendingReloadAfterRelease = false;
        location.reload();
        return;
    }

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
    // weakWordsListSection reference removed
    if (noWeakWordsMessage) noWeakWordsMessage.classList.add('hidden');

    // ★追加: コラムを再表示する
    toggleTodaysColumn(true);

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
                const rangeSelectionTitleText = document.getElementById('rangeSelectionTitleText');
                if (rangeSelectionTitleText) {
                    rangeSelectionTitleText.textContent = '出題数を選択';
                }
                const selectionTotalCount = document.getElementById('selectionTotalCount');
                if (selectionTotalCount) {
                    selectionTotalCount.textContent = ''; // 初期状態なので空にする
                }
                rangeSelectionTitle.style.color = '#34495e';
            }

            // 警告メッセージを削除
            removeWeakProblemWarning();

            // ★追記: 手動リセット後に再度現在のモード状態を評価してUIを正しく反映させる
            updateIncorrectOnlySelection();

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
        currentSessionAnswered.clear();

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

    // ★修正: 前回と同じ問題数制限を適用する
    const selectedQuestionCount = lastQuizSettings.questionCount;
    if (selectedQuestionCount && selectedQuestionCount !== 'all' && selectedQuestionCount !== 'incorrectOnly') {
        const count = parseInt(selectedQuestionCount);
        if (!isNaN(count) && currentQuizData.length > count) {
            currentQuizData = currentQuizData.slice(0, count);
        }
    }

    currentQuestionIndex = 0;
    correctCount = 0;
    incorrectCount = 0;
    totalQuestions = currentQuizData.length;
    quizStartTime = Date.now();
    currentSessionAnswered.clear();

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
        restartButton.innerHTML = '<i class="fas fa-redo"></i> 同じ範囲でリプレイ';

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
        restartButton.innerHTML = '<i class="fas fa-redo"></i> 同じ範囲でリプレイ';
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

/**
 * 今日のコラムウィジェットの表示・非表示を切り替える
 * @param {boolean} show - trueで表示、falseで非表示
 */
function toggleTodaysColumn(show) {
    const columnWidget = document.getElementById('todaysColumnWidget');
    const newsWidget = document.getElementById('dailyNewsWidget');
    
    if (columnWidget) {
        if (show) {
            columnWidget.classList.remove('hidden');
            columnWidget.style.display = 'block';
        } else {
            columnWidget.style.display = 'none';
        }
    }
    
    if (newsWidget) {
        if (show) {
            newsWidget.style.display = 'block';
        } else {
            newsWidget.style.display = 'none';
        }
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
                announcementsList.innerHTML = `
                    <p class="text-muted" style="font-size: 0.9em;">現在お知らせはありません。</p>
                    <div style="text-align: right; margin-top: 10px; padding-right: 5px;">
                        <a href="/announcements" class="text-decoration-none" style="font-size: 0.9em; color: #3498db; font-weight: bold;">
                            <i class="fas fa-list-ul me-1"></i>過去のお知らせを見る
                        </a>
                    </div>
                `;
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
    if (!window.appInfoFromFlask || !window.appInfoFromFlask.isLoggedIn) return; // ログインしていない場合は何もしない

    const saveBtn = document.getElementById('saveSettingsBtn');
    if (!saveBtn) return; // 設定モーダルがないページでは何もしない

    // メール通知トグルのイベントリスナーを即座に登録（fetch完了前でも動作するように）
    const emailToggle = document.getElementById('emailNotificationToggle');
    const emailArea = document.getElementById('emailInputArea');
    const emailInput = document.getElementById('notificationEmail');
    const testEmailBtn = document.getElementById('testEmailBtn');

    // 重複登録防止
    if (emailToggle && !emailToggle.dataset.listenerAttached) {
        emailToggle.dataset.listenerAttached = 'true';
        emailToggle.addEventListener('change', function (e) {
            const isChecked = e.target.checked;
            if (emailArea) {
                emailArea.style.display = isChecked ? 'block' : 'none';
            }
        });
    }

    if (emailInput && !emailInput.dataset.listenerAttached) {
        emailInput.dataset.listenerAttached = 'true';
        emailInput.addEventListener('input', function (e) {
            if (testEmailBtn) {
                testEmailBtn.disabled = !e.target.value.trim();
            }
        });
    }

    // 通知トグルのイベントリスナーも即座に登録
    const toggle = document.getElementById('notificationToggle');
    if (toggle && !toggle.dataset.listenerAttached) {
        toggle.dataset.listenerAttached = 'true';
        toggle.addEventListener('change', function (e) {
            toggleTimeInput(e.target.checked);
        });
    }

    // 設定読み込み（初期値の設定のみ）
    fetch('/api/notification_settings')
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                const timeInput = document.getElementById('notificationTime');

                if (toggle) toggle.checked = data.enabled;
                if (timeInput) timeInput.value = data.time || '21:00';

                // トグル状態に応じて時間入力の有効/無効切り替え
                toggleTimeInput(data.enabled);

                if (data.enabled && Notification.permission === 'granted') {
                    registerServiceWorker().catch(err => console.error('Auto-register SW failed:', err));
                }

                // メール設定の初期値反映
                if (emailToggle) {
                    emailToggle.checked = data.email_enabled || false;
                    // 初期表示状態を設定
                    if (emailArea) {
                        emailArea.style.display = (data.email_enabled) ? 'block' : 'none';
                    }
                }
                if (emailInput) {
                    emailInput.value = data.email || '';
                    if (testEmailBtn) testEmailBtn.disabled = !emailInput.value.trim();
                }
            }
        })
        .catch(err => console.error('設定読み込みエラー:', err));


    // 通知テストボタン（WebPush）
    const testBtn = document.getElementById('testNotificationBtn');
    if (testBtn) {
        testBtn.addEventListener('click', function () {
            // ボタンを一時的に無効化
            testBtn.disabled = true;
            testBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> 送信中...';

            // WebPushテスト（emailパラメータなし）
            fetch('/api/test_notification', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type: 'push' }) // 明示的に区別したい場合
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status === 'success') {
                        alert('WebPush通知ルールで送信しました。\n\nもし通知が届かない場合は、スマホの「おやすみモード」や「通知設定」を確認してください。');
                    } else {
                        // WebPush失敗時はメールアドレス設定があればメールも試すなどのロジックはバックエンド依存
                        alert('送信完了: ' + data.message);
                    }
                })
                .catch(err => {
                    console.error('テスト送信エラー:', err);
                    alert('通信エラーが発生しました');
                })
                .finally(() => {
                    testBtn.disabled = false;
                    testBtn.innerHTML = '<i class="fas fa-paper-plane me-1"></i> 通知をテスト送信';
                });
        });
    }

    // テストメール送信ボタン（testEmailBtnは上で既に取得済み）
    if (testEmailBtn && !testEmailBtn.dataset.clickListenerAttached) {
        testEmailBtn.dataset.clickListenerAttached = 'true';
        testEmailBtn.addEventListener('click', function () {
            const emailInput = document.getElementById('notificationEmail');
            const email = emailInput ? emailInput.value : '';

            if (!email) {
                alert('メールアドレスを入力してください');
                return;
            }

            testEmailBtn.disabled = true;
            const originalIcon = testEmailBtn.innerHTML;
            testEmailBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

            fetch('/api/test_notification', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: email })
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status === 'success') {
                        alert('テストメールを送信しました。\n受信トレイを確認してください。');
                    } else {
                        alert('送信失敗: ' + data.message);
                    }
                })
                .catch(err => {
                    console.error('Error:', err);
                    alert('通信エラーが発生しました');
                })
                .finally(() => {
                    testEmailBtn.disabled = false;
                    testEmailBtn.innerHTML = originalIcon;
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
        const emailToggle = document.getElementById('emailNotificationToggle');
        const emailInput = document.getElementById('notificationEmail');

        const emailEnabled = emailToggle ? emailToggle.checked : false;
        const emailVal = emailInput ? emailInput.value : '';

        fetch('/api/update_notification_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                enabled: enabled,
                time: time,
                email_enabled: emailEnabled,
                email: emailVal
            })
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

        // 既存の購読を確認
        const existingSubscription = await registration.pushManager.getSubscription();
        if (existingSubscription) {
            // キーが一致するか確認（一致しない場合は解除）
            const existingKey = existingSubscription.options.applicationServerKey;
            if (existingKey) {
                const existingKeyUint8 = new Uint8Array(existingKey);
                const isKeyMatch = applicationServerKey.every((val, i) => val === existingKeyUint8[i]);

                if (!isKeyMatch) {
                    console.log('VAPID key mismatch detected. Unsubscribing...');
                    await existingSubscription.unsubscribe();
                }
            }
        }

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
    if (!window.appInfoFromFlask || !window.appInfoFromFlask.isLoggedIn) return; // Login check

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

    if (overlay) {
        overlay.classList.remove('hidden');
        overlay.classList.remove('anim-active');
        void overlay.offsetWidth;
        overlay.classList.add('anim-active');
    }
    if (intro) {
        intro.classList.remove('hidden');
        // Trigger animations
        intro.classList.remove('anim-active');
        void intro.offsetWidth; // Force reflow to restart animation
        intro.classList.add('anim-active');
    }
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
    const intro = document.getElementById('rpgIntroScreen');
    if (overlay) {
        overlay.classList.add('hidden');
        overlay.classList.remove('anim-active');
    }
    if (intro) intro.classList.remove('anim-active');
    if (result) result.classList.remove('anim-victory');
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
        btn.onclick = () => handleRpgAnswer(choice, btn);
        container.appendChild(btn);
    });
}

async function handleRpgAnswer(selectedChoice, btnElement) {
    // Disable buttons
    const btns = document.querySelectorAll('.rpg-choice-btn');
    btns.forEach(b => b.disabled = true);

    try {
        // サーバーに正誤確認を問い合わせる
        const response = await fetch('/api/rpg/check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                index: rpgCurrentIndex,
                choice: selectedChoice
            })
        });
        const data = await response.json();

        if (data.status !== 'success') throw new Error(data.message);

        const isCorrect = data.is_correct;
        const correctAnswer = data.correct_answer;

        if (isCorrect) {
            btnElement.classList.add('correct');
            rpgCorrectCount++;

            // Damage effect
            const dmg = document.getElementById('rpgDamageEffect');
            if (dmg) {
                dmg.classList.remove('hidden');
                dmg.classList.add('damage-text');
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

            // 正解の選択肢をハイライト（DailyQuizと同様の親切設計）
            document.querySelectorAll('.rpg-choice-btn').forEach(btn => {
                if (btn.textContent === correctAnswer) {
                    btn.classList.add('correct');
                }
            });

            // Screen shake
            document.body.classList.add('shake-anim');
            setTimeout(() => document.body.classList.remove('shake-anim'), 500);

            // Lose Condition Check
            if (rpgIncorrectCount > rpgMaxMistakes) {
                setTimeout(() => finishRpgGame(false), 1000);
                return;
            }
        }
    } catch (error) {
        console.error('Answer check error:', error);
        // エラー時は不正解扱いとして次に進める
        rpgIncorrectCount++;
        if (rpgIncorrectCount > rpgMaxMistakes) {
            finishRpgGame(false);
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
    if (resultScreen) {
        resultScreen.classList.remove('hidden');
        resultScreen.classList.remove('anim-victory');
        if (isWin) {
            void resultScreen.offsetWidth;
            resultScreen.classList.add('anim-victory');
        }
    }

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
    if (!window.appInfoFromFlask || !window.appInfoFromFlask.isLoggedIn) return; // Login check

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


// ===================================
// Helper: Levenshtein Distance (for Fuzzy Logic)
// ===================================
function levenshteinDistance(a, b) {
    const matrix = [];
    for (let i = 0; i <= b.length; i++) {
        matrix[i] = [i];
    }
    for (let j = 0; j <= a.length; j++) {
        matrix[0][j] = j;
    }
    for (let i = 1; i <= b.length; i++) {
        for (let j = 1; j <= a.length; j++) {
            if (b.charAt(i - 1) == a.charAt(j - 1)) {
                matrix[i][j] = matrix[i - 1][j - 1];
            } else {
                matrix[i][j] = Math.min(
                    matrix[i - 1][j - 1] + 1,
                    matrix[i][j - 1] + 1,
                    matrix[i - 1][j] + 1
                );
            }
        }
    }
    return matrix[b.length][a.length];
}

// ===================================
// 音声入力機能 (Voice Recognition)
// ===================================

let isProcessingVoiceSuccess = false; // Lock flag to prevent double submission


function startVoiceRecognition(e) {
    if (e && typeof e.preventDefault === 'function' && e.cancelable) {
        e.preventDefault();
        e.stopPropagation();
    }



    // Global tracker (outside, ensure this is top-level or handled)
    if (window.currentRecognition) {
        try {
            window.currentRecognition.onend = null; // Prevent loops
            window.currentRecognition.stop();
            window.currentRecognition.abort();
        } catch (e) { console.error(e); }
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        alert("お使いのブラウザは音声入力に対応していません。ChromeやSafariをお試しください。");
        return;
    }

    // Detect Safari
    const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);

    const recognition = new SpeechRecognition();
    window.currentRecognition = recognition; // Track instance
    recognition.lang = 'ja-JP';

    if (!isSafari) {
        recognition.interimResults = false;
        recognition.maxAlternatives = 20;
    }
    // Safari: Use defaults to prevent "service-not-allowed"

    // Grammar Support: Bias towards the correct answer AND global vocabulary
    // This helps recognition even with slight mispronunciations or difficult words
    // SKIP for Safari to avoid "service-not-allowed" caused by unsupported API usage
    if (!isSafari && currentQuizData && currentQuizData[currentQuestionIndex]) {
        // Correct Answer Data
        const currentData = currentQuizData[currentQuestionIndex];
        const correctAnswer = currentData.answer;
        const correctReading = currentData.reading || ""; // 🆕 Reading from CSV

        const SpeechGrammarList = window.SpeechGrammarList || window.webkitSpeechGrammarList;

        if (SpeechGrammarList) {
            const speechRecognitionList = new SpeechGrammarList();

            // 1. Add ALL vocabulary from word_data (Context)
            // This allows the engine to recognize ANY word in the database better
            if (voice_vocab_data && Array.isArray(voice_vocab_data)) {
                try {
                    const allAnswers = new Set();
                    voice_vocab_data.forEach(w => {
                        // Add Answer
                        if (w.answer) {
                            const parts = w.answer.split(/[（(）)]+/);
                            parts.forEach(p => {
                                const clean = p.replace(/[;|<>\*\(\)\[\]\/,]/g, '').trim(); // Remove symbols including slash/comma
                                if (clean.length > 0) allAnswers.add(clean);
                            });
                        }
                        // 🆕 Add Reading
                        if (w.reading) {
                            // Handle comma in reading
                            const parts = w.reading.split(/[,]+/);
                            parts.forEach(p => {
                                const clean = p.trim();
                                if (clean.length > 0) allAnswers.add(clean);
                            });
                        }
                    });

                    // Join with JSGF OR operator
                    const globalGrammarString = Array.from(allAnswers).join(' | ');

                    if (globalGrammarString) {
                        // Weight 1 for general vocabulary
                        const globalGrammar = '#JSGF V1.0; grammar global_vocab; public <vocab> = ' + globalGrammarString + ' ;';
                        speechRecognitionList.addFromString(globalGrammar, 1);
                        // console.log(`Global Grammar Added: ${allAnswers.size} words`);
                    }
                } catch (e) {
                    console.warn("Failed to add global grammar:", e);
                }
            }

            // 2. Add CURRENT answer (Prioritized)
            // Generate variations for grammar (Same logic as verification)
            const variations = new Set();

            // Raw answer (cleaned)
            variations.add(correctAnswer.replace(/[;]/g, ''));

            // 🆕 Reading (Highest Priority)
            if (correctReading) {
                // Split by comma OR slash to ensure individual words are added
                const readingParts = correctReading.split(/[\/,]+/);
                readingParts.forEach(r => {
                    const val = r.trim();
                    if (!val) return;
                    variations.add(val);

                    // Explicitly add Hiragana/Katakana counterparts for robustness
                    // Simple conversion assuming standard range
                    const toHira = val.replace(/[\u30A1-\u30F6]/g, c => String.fromCharCode(c.charCodeAt(0) - 0x60));
                    const toKata = val.replace(/[\u3041-\u3096]/g, c => String.fromCharCode(c.charCodeAt(0) + 0x60));
                    if (toHira !== val) variations.add(toHira);
                    if (toKata !== val) variations.add(toKata);
                });
            }

            // Normalized parts
            const parts = correctAnswer.split(/[（(）)\/,]+/); // Split by slash/comma too for grammar injection
            parts.forEach(p => {
                if (p.trim()) variations.add(p.trim());
            });

            // Clean for JSGF (remove special grammar chars)
            const variationArray = Array.from(variations).map(v => v.replace(/[;|<>\*\(\)\[\]\/,]/g, '')).filter(v => v.length > 0);
            const currentGrammarString = variationArray.join(' | ');

            // JSpeech Grammar Format using alternatives
            if (currentGrammarString) {
                const grammar = '#JSGF V1.0; grammar answer; public <answer> = ' + currentGrammarString + ' ;';

                // Add with significantly high weight (50) to prioritize current answer
                speechRecognitionList.addFromString(grammar, 50);
                recognition.grammars = speechRecognitionList;
                // console.log(`Target Grammar Added: ${currentGrammarString}`);
            }
        }
        // UI Updates (Disable BOTH buttons)
        const setListeningState = (isListening) => {
            const btns = [voiceAnswerBtn, voiceAnswerBtnMobile].filter(b => b);
            btns.forEach(btn => {
                if (isListening) {
                    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
                    btn.classList.add('listening');
                    btn.disabled = true;
                } else {
                    btn.innerHTML = '<i class="fas fa-microphone"></i>';
                    btn.classList.remove('listening');
                    btn.disabled = false;
                }
            });
        };

        setListeningState(true);

        // Clean previous feedback
        if (voiceFeedback) {
            voiceFeedback.textContent = '';
            voiceFeedback.classList.add('hidden');
        }

        recognition.start();

        recognition.onresult = (event) => {
            // Only process finalized results to prevent flickering
            if (!event.results[0].isFinal) return;

            // Collect ALL candidates
            const candidates = [];
            const results = event.results[0];
            for (let i = 0; i < results.length; i++) {
                candidates.push(results[i].transcript);
            }

            console.log(`Recognized Candidates:`, candidates);
            verifyVoiceAnswer(candidates);
        };

        recognition.onspeechend = () => {
            recognition.stop();
        };

        recognition.onerror = (event) => {
            console.error('Speech recognition error', event.error);

            let errorMsg = '聞き取れませんでした';
            if (event.error === 'no-speech') errorMsg = '音声が検出されませんでした';
            if (event.error === 'audio-capture') errorMsg = 'マイクが見つかりません';
            if (event.error === 'not-allowed') {
                errorMsg = 'マイクの使用が許可されていません。\nブラウザの設定でマイクを許可してください。(スマホの場合はHTTPS接続が必要です)';
                alert(errorMsg);
            }
            if (event.error === 'service-not-allowed') {
                if (isSafari) {
                    errorMsg = '音声入力が利用できません。\n\nMac/iPhoneの「設定」>「キーボード」>「音声入力」がオンになっているか確認してください。\nまたはChromeブラウザをお試しください。';
                } else {
                    errorMsg = '音声入力サービスが利用できません。';
                }
                alert(errorMsg);
            }

            // Restore UI
            setListeningState(false);

            if (voiceFeedback) {
                voiceFeedback.textContent = `❌ ${errorMsg}`;
                voiceFeedback.classList.remove('hidden');
            }
        };

        recognition.onend = () => {
            // Check if any button is still in listening state (safety net)
            if ((voiceAnswerBtn && voiceAnswerBtn.classList.contains('listening')) ||
                (voiceAnswerBtnMobile && voiceAnswerBtnMobile.classList.contains('listening'))) {
                setListeningState(false);
            }
        };
    }

    // ===================================
    // Helper: Dictionary Pre-calculation (Lazy)
    // ===================================
    let globalVoiceDictionary = null;

    function getVoiceDictionary() {
        if (globalVoiceDictionary) return globalVoiceDictionary;

        globalVoiceDictionary = new Set();
        if (voice_vocab_data && Array.isArray(voice_vocab_data)) {
            voice_vocab_data.forEach(w => {
                // Answer
                if (w.answer) {
                    // Split by delimiters to handle "A(B)" -> A, B
                    const parts = w.answer.split(/[（(）)]+/);
                    parts.forEach(p => {
                        // Normalize using the same logic as verify
                        const clean = normalizeString(p);
                        if (clean.length > 0) globalVoiceDictionary.add(clean);
                    });
                }
                // 🆕 Reading
                if (w.reading) {
                    const parts = w.reading.split(/[\/,]+/);
                    parts.forEach(p => {
                        const clean = normalizeString(p);
                        if (clean.length > 0) globalVoiceDictionary.add(clean);
                    });
                }
            });
        }
        // console.log(`Voice Dictionary Initialized: ${globalVoiceDictionary.size} words`);
        return globalVoiceDictionary;
    }

    // Reuse normalization logic for dictionary
    function normalizeString(str) {
        if (!str) return '';
        let s = str.replace(/\s+/g, '') // Remove spaces
            .replace(/[０-９]/g, c => String.fromCharCode(c.charCodeAt(0) - 0xFEE0))
            .replace(/[Ａ-Ｚ]/g, c => String.fromCharCode(c.charCodeAt(0) - 0xFEE0))
            .replace(/[ａ-ｚ]/g, c => String.fromCharCode(c.charCodeAt(0) - 0xFEE0))
            .replace(/[「」『』()（）\[\]【】＝=・、。]/g, '')
            .replace(/ヴァ/g, 'バ').replace(/ヴィ/g, 'ビ').replace(/ヴェ/g, 'ベ').replace(/ヴォ/g, 'ボ').replace(/ヴ/g, 'ブ')
            .toLowerCase();

        // Numbers
        const kanjiDigits = '〇一二三四五六七八九';
        s = s.replace(/[〇一二三四五六七八九]/g, m => kanjiDigits.indexOf(m));
        s = s.replace(/(\d)十(\d)/g, '$1$2').replace(/(\d)十/g, '$10').replace(/十(\d)/g, '1$1').replace(/十/g, '10');
        s = s.replace(/(\d)百(\d+)/g, '$1$2').replace(/(\d)百/g, '$100').replace(/百(\d+)/g, '1$1').replace(/百/g, '100');
        s = s.replace(/(\d)千(\d+)/g, '$1$2').replace(/(\d)千/g, '$1000').replace(/千(\d+)/g, '1$1').replace(/千/g, '1000');
        s = s.replace(/(\d)万(\d+)/g, '$1$2').replace(/(\d)万/g, '$10000').replace(/万(\d+)/g, '1$1').replace(/万/g, '10000');

        // 🆕 Unify Kana (Hiragana -> Katakana) for consistent matching
        s = s.replace(/[\u3041-\u3096]/g, function (ch) {
            return String.fromCharCode(ch.charCodeAt(0) + 0x60);
        });

        return s;
    }

    function verifyVoiceAnswer(candidates) {
        if (!currentQuizData || !currentQuizData[currentQuestionIndex]) return;

        // Ensure array
        if (!Array.isArray(candidates)) candidates = [candidates];

        const currentData = currentQuizData[currentQuestionIndex];
        const correctAnswer = currentData.answer;
        const correctReading = currentData.reading || ""; // 🆕

        // Normalization wrapper
        const normalize = normalizeString;

        // Determine Answer Mode: "Slash (AND)" if either Answer OR Reading contains '/'
        const isSlashMode = correctAnswer.includes('/') || (correctReading && correctReading.includes('/'));

        // ---------------------------------------------------------
        // Function to check Single/Comma (OR) match
        // ---------------------------------------------------------
        const checkSingleOrMatch = (transcript, targetAnswer, targetReading) => {
            const cleanTranscript = normalize(transcript);

            // 1. Prepare Valid Answers Set (OR logic)
            const validSet = new Set();

            // Add Answer variations
            if (targetAnswer) {
                validSet.add(normalize(targetAnswer));
                // Parantheses A(B) -> A, B
                const parts = targetAnswer.split(/[（(）)]+/);
                parts.forEach(p => {
                    const n = normalize(p);
                    if (n) validSet.add(n);
                });
            }

            // 🆕 Add Reading variations (Comma separated)
            if (targetReading) {
                const rParts = targetReading.split(/[,]+/);
                rParts.forEach(r => {
                    const n = normalize(r); // 修正: n を定義
                    if (n) validSet.add(n);
                });
            }

            // 🆕 Calculate Skeleton for Input
            const inputSkeleton = getConsonantSkeleton(cleanTranscript);

            // 2. Check against All Valid Options
            let result = { match: false, type: 'none' };

            for (let target of validSet) {
                // Strict
                if (cleanTranscript === target) {
                    return { match: true, type: 'exact' };
                }

                // 🆕 Consonant Skeleton Match (Ignoring Vowels)
                // Only apply for longer words (length >= 5) to avoid short word collisions (e.g. Kita vs Kata)
                if (target.length >= 5) {
                    const targetSkeleton = getConsonantSkeleton(target);
                    if (targetSkeleton && inputSkeleton === targetSkeleton) {
                        console.log(`💀 Skeleton Match! ${cleanTranscript} (${inputSkeleton}) == ${target} (${targetSkeleton})`);
                        return { match: true, type: 'exact' }; // Treat as exact match (GREEN)
                    }
                }

                // Fuzzy
                if (target.length > 3 && cleanTranscript.includes(target)) {
                    result = { match: true, type: 'fuzzy' }; // Keep looking for exact
                } else {
                    const dist = levenshteinDistance(cleanTranscript, target);

                    // 🆕 Adjusted Threshold based on User Feedback
                    // "Strictness" caused issues, so we relax it for longer words (0.2 -> 0.4)
                    // But keep it "not abnormally wide" for short words (length 4 allows 1 error, not 3).
                    let threshold;
                    if (target.length <= 4) {
                        threshold = 1; // Strict for short words (Prevent 3 errors for 4 chars)
                    } else {
                        threshold = Math.floor(target.length * 0.4); // Relaxed to 40% (e.g., 5 chars -> 2 errors)
                    }

                    if (dist <= threshold) {
                        // 🆕 User Request: 1 char mistake -> Exact match (for length >= 3)
                        if (dist <= 1 && target.length >= 3) {
                            return { match: true, type: 'exact' };
                        }
                        result = { match: true, type: 'fuzzy' };
                    }
                }
            }
            return result;
        };


        let matchFound = false;
        let matchType = 'none'; // 'exact', 'fuzzy'
        let matchedCandidate = '';

        // ==========================================
        // Helpers
        // ==========================================

        // Helper: Execute Success Logic
        const executeSuccess = (text, type) => {
            if (type === 'exact') {
                if (isProcessingVoiceSuccess) return;
                isProcessingVoiceSuccess = true;
                if (voiceFeedback) {
                    voiceFeedback.innerHTML = `
                <div style="padding: 20px; background: #e8f5e9; border: 2px solid #a5d6a7; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.01); text-align: center; animation: pulse 0.5s;">
                    <h3 style="margin: 0 0 10px 0; color: #2e7d32; font-size: 1.4em; font-weight: bold;"><i class="fas fa-check-circle"></i> 正解！</h3>
                    <p style="margin: 0; font-size: 1.1em; color: #388e3c; font-weight: bold;">"${correctAnswer}"</p>
                    <div style="margin-top: 10px; font-size: 0.9em; color: #66bb6a;"><i class="fas fa-spinner fa-spin"></i> 次の問題へ進みます...</div>
                </div>`;
                    voiceFeedback.classList.remove('hidden');
                }
                setTimeout(() => { handleAnswer(true); }, 1500);
            } else {
                // Fuzzy match confirmation
                if (voiceFeedback) {
                    voiceFeedback.innerHTML = `
                <div style="padding: 15px; background: #fffde7; border: 2px solid #fff176; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                    <p style="margin: 0 0 5px; color: #f57f17; font-weight: bold; font-size: 1.1em;">
                        <i class="fas fa-question-circle"></i> 「${correctAnswer}」？
                    </p>
                    <p style="margin: 0 0 10px 0; font-size: 0.95em; color: #777;">
                        聞き取り: "${text}"
                    </p>
                    <div style="display: flex; gap: 10px; justify-content: center;">
                        <button id="voiceConfirmYes" class="btn btn-success btn-sm" style="flex: 1; font-weight: bold;"><i class="fas fa-check"></i> はい</button>
                        <button id="voiceConfirmNo" class="btn btn-secondary btn-sm" style="flex: 1;"><i class="fas fa-times"></i> いいえ</button>
                    </div>
                </div>`;
                    voiceFeedback.classList.remove('hidden');
                    document.getElementById('voiceConfirmYes').onclick = () => {
                        if (isProcessingVoiceSuccess) return;
                        isProcessingVoiceSuccess = true;
                        handleAnswer(true);
                    };
                    document.getElementById('voiceConfirmNo').onclick = () => {
                        voiceFeedback.classList.add('hidden');
                        voiceFeedback.innerHTML = '';
                    };
                }
            }
        };

        // Helper: Execute Failure Logic
        const executeFailure = () => {
            const dictionary = getVoiceDictionary();
            let bestDisplayCandidate = null;
            let isDictionaryTerm = false;

            for (let transcript of candidates) {
                const clean = normalize(transcript);
                if (dictionary.has(clean)) {
                    bestDisplayCandidate = transcript;
                    isDictionaryTerm = true;
                    break;
                }
            }

            if (!bestDisplayCandidate) {
                bestDisplayCandidate = "（用語として認識できませんでした）";
            }

            console.log(`Voice mismatch. Displaying: ${bestDisplayCandidate}`);

            if (voiceFeedback) {
                let msgHtml = '';
                if (isDictionaryTerm) {
                    msgHtml = `
                <div style="background: #fff5f5; padding: 15px; border-radius: 12px; border: 2px solid #ffcccc; margin-bottom: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                    <p style="margin: 0 0 5px; color: #e74c3c; font-weight: bold; font-size: 1.1em;">
                        <i class="fas fa-times-circle"></i> 不正解
                    </p>
                    <p style="margin: 0 0 5px; font-size: 0.95em; color: #555;">
                        聞き取り: "${bestDisplayCandidate}"
                    </p>
                     <p style="margin: 0; font-size: 0.85em; color: #e67e22;">
                        ※辞書にある単語ですが、この問題の正解ではありません。
                    </p>
                </div>`;
                } else {
                    msgHtml = `
                <div style="background: #f8f9fa; padding: 15px; border-radius: 12px; border: 2px solid #dee2e6; margin-bottom: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                     <p style="margin: 0 0 5px; color: #7f8c8d; font-weight: bold; font-size: 1.1em;">
                        <i class="fas fa-microphone-slash"></i> 聞き取れませんでした
                    </p>
                    <p style="margin: 0; font-size: 0.85em; color: #7f8c8d;">
                        歴史用語として認識されませんでした。<br>もう一度お話しください。
                    </p>
                </div>`;
                }

                voiceFeedback.innerHTML = msgHtml;
                voiceFeedback.classList.remove('hidden');
            }
        };

        // ==========================================
        // Helper: Consonant Skeleton Extraction
        // ==========================================
        const getConsonantSkeleton = (str) => {
            if (!str) return "";
            let s = normalize(str); // Base normalization first

            // Remove Vowels and special ignoring chars
            // A I U E O, small ya/yu/yo, long vowel, small tsu (maybe?)
            // Let's map Kana to approximate consonant
            // This is a simplified mapping.

            let res = "";
            for (let i = 0; i < s.length; i++) {
                const c = s.charAt(i);

                // Skip Long Vowels / Small Tsu / Symbols
                if (/[ーっッ]/.test(c)) continue;

                // Map standard Gojuon (Basic Consonant Groups)
                if (/[あいうえおアイウエオ]/.test(c)) { /* Vowel -> Skip (or placeholder?) Skip for skeleton */ continue; }

                if (/[かきくけこカキクケコ]/.test(c)) { res += "K"; continue; }
                if (/[さしすせそサシスセソ]/.test(c)) { res += "S"; continue; }
                if (/[たちつてとタチツテト]/.test(c)) { res += "T"; continue; }
                if (/[なにぬねのナニヌネノ]/.test(c)) { res += "N"; continue; }
                if (/[はひふへほハヒフヘホ]/.test(c)) { res += "H"; continue; }
                if (/[まみむめもマミムメモ]/.test(c)) { res += "M"; continue; }
                if (/[やゆよヤユヨ]/.test(c)) { res += "Y"; continue; }
                if (/[らりるれろラリルレロ]/.test(c)) { res += "R"; continue; }
                if (/[わをワヲ]/.test(c)) { res += "W"; continue; }
                if (/[んン]/.test(c)) { res += "N"; continue; } // N is important

                if (/[がぎぐげごガギグゲゴ]/.test(c)) { res += "G"; continue; }
                if (/[ざじずぜぞザジズゼゾ]/.test(c)) { res += "Z"; continue; }
                if (/[だぢづでどダヂヅデド]/.test(c)) { res += "D"; continue; }
                if (/[ばびぶべぼバビブベボ]/.test(c)) { res += "B"; continue; }
                if (/[ぱぴぷぺぽパピプペポ]/.test(c)) { res += "P"; continue; }

                // Small Ya/Yu/Yo often modify consonant (Kya -> K), so they are skippable if we took the consonant from the main char beforehand.
                // e.g. キャ (Ki-ya) -> Ki (K) + ya (Y or skip). 
                // In strict Hepburn, Kya -> KY. But for skeleton "K" is enough core.
                if (/[ゃゅょャュョ]/.test(c)) continue;

                // If unknown (Kanji or other), keep it? Or skip?
                // Since we normalize to Kana usually via server, this might not be hit often.
                // But if mixed, let's keep it to differentiate.
                res += c;
            }
            return res;
        };


        // Helper: Check a single transcript against logic
        const checkTranscriptMatch = (text) => {
            const clean = normalize(text);

            // 🆕 Calculate Skeleton for Input
            const inputSkeleton = getConsonantSkeleton(clean);

            // Helper: Check if string contains target (Exact or Fuzzy)
            const containsFuzzy = (haystack, needle) => {

                if (haystack.includes(needle)) return true;

                // Fuzzy check
                // We scan the haystack with a window of needle.length size.
                // If any window has small edit distance, return true.
                if (needle.length < 2) return false; // Too short for fuzzy

                // 🆕 Adjusted Threshold for Substring
                let threshold;
                if (needle.length <= 4) {
                    threshold = 1;
                } else {
                    threshold = Math.floor(needle.length * 0.4);
                }

                // Optimization: If difference in length is too big, it can't match? 
                // But we are looking for a SUBSTRING match, so haystack is usually longer.

                // Sliding window approach
                for (let i = 0; i <= haystack.length - needle.length; i++) {
                    const sub = haystack.substr(i, needle.length);
                    const dist = levenshteinDistance(sub, needle);
                    if (dist <= threshold) return true;
                }
                // Check slightly larger/smaller windows too? (e.g. +/- 1 char)
                // For simplicity, just checking exact length window often works for minor typos.
                // Let's add +/- 1 length for robustness if haystack allows.
                for (let lenOffset = -1; lenOffset <= 1; lenOffset++) {
                    if (lenOffset === 0) continue; // Already did
                    const wLen = needle.length + lenOffset;
                    if (wLen < 1) continue;
                    for (let i = 0; i <= haystack.length - wLen; i++) {
                        const sub = haystack.substr(i, wLen);
                        const dist = levenshteinDistance(sub, needle);
                        if (dist <= threshold) return true;
                    }
                }

                return false;
            };

            if (isSlashMode) {
                const answerParts = correctAnswer.split('/').map(s => normalize(s)).filter(s => s && s.trim().length > 0);
                const readingParts = correctReading ? correctReading.split(/[\/,]+/).map(s => normalize(s)).filter(s => s && s.trim().length > 0) : [];

                // Check 1: All Answer Parts
                let allAns = true;
                let ansFuzzy = false;
                for (const p of answerParts) {
                    if (!containsFuzzy(clean, p)) { allAns = false; break; }
                    if (!clean.includes(p)) ansFuzzy = true; // Found via fuzzy
                }
                if (allAns) return { match: true, type: ansFuzzy ? 'fuzzy' : 'exact' };

                // Check 2: All Reading Parts
                if (readingParts.length > 0) {
                    let allRead = true;
                    let readFuzzy = false;
                    for (const p of readingParts) {
                        if (!containsFuzzy(clean, p)) { allRead = false; break; }
                        if (!clean.includes(p)) readFuzzy = true;
                    }
                    if (allRead) return { match: true, type: readFuzzy ? 'fuzzy' : 'exact' };
                }

                // Check 3: Hybrid
                if (answerParts.length === readingParts.length && answerParts.length > 0) {
                    let allSlots = true;
                    let slotFuzzy = false;
                    for (let i = 0; i < answerParts.length; i++) {
                        const hasAns = containsFuzzy(clean, answerParts[i]);
                        const hasRead = containsFuzzy(clean, readingParts[i]);
                        if (!hasAns && !hasRead) { allSlots = false; break; }

                        if (hasAns && !clean.includes(answerParts[i])) slotFuzzy = true;
                        if (!hasAns && hasRead && !clean.includes(readingParts[i])) slotFuzzy = true;
                    }
                    if (allSlots) return { match: true, type: slotFuzzy ? 'fuzzy' : 'exact' };
                }
                return { match: false, type: 'none' };
            } else {
                return checkSingleOrMatch(text, correctAnswer, correctReading);
            }
        };

        // ==========================================
        // Check all candidates
        // ==========================================

        for (let transcript of candidates) {
            const res = checkTranscriptMatch(transcript);
            if (res.match) {
                matchFound = true;
                matchType = res.type;
                matchedCandidate = transcript;
                if (matchType === 'exact') break;
            }
        }


        // If we have a match (correct answer), handle it.
        if (matchFound) {
            executeSuccess(matchedCandidate, matchType);
        } else {
            // 🆕 Fallback: Server-side Katakana Conversion (Batch)
            if (candidates.length > 0) {
                // Take top 5 candidates to increase hit rate (especially for Safari/No-Grammar)
                const fallbackCandidates = candidates.slice(0, 5);

                // Show Loading Feedback
                if (voiceFeedback) {
                    voiceFeedback.innerHTML = `
                 <div style="padding: 15px; background: #e3f2fd; border: 2px solid #90caf9; border-radius: 12px; color: #1565c0; animation: pulse 1s infinite; text-align: center;">
                    <i class="fas fa-sync fa-spin"></i> 読み仮名変換で再確認中...<br>
                    <small>(${fallbackCandidates.length}件の候補を解析中)</small>
                 </div>`;
                    voiceFeedback.classList.remove('hidden');
                }

                fetch('/api/to_katakana', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ texts: fallbackCandidates }) // Send list
                })
                    .then(r => r.json())
                    .then(data => {
                        // Support both new list format and legacy single format (just in case)
                        let convertedList = [];
                        if (data.status === 'success') {
                            if (data.katakana_list) {
                                convertedList = data.katakana_list;
                            } else if (data.katakana) {
                                convertedList = [data.katakana];
                            }

                            console.log(`Server conversion results:`, convertedList);

                            // Check each converted candidate
                            let foundInFallback = false;
                            for (const katakana of convertedList) {
                                const res = checkTranscriptMatch(katakana);
                                if (res.match) {
                                    executeSuccess(katakana, res.type);
                                    foundInFallback = true;
                                    break;
                                }
                            }

                            if (!foundInFallback) {
                                executeFailure();
                            }
                        } else {
                            executeFailure();
                        }
                    })
                    .catch(err => {
                        console.warn("Server conversion failed:", err);
                        executeFailure();
                    });
            } else {
                executeFailure();
            }
        }
    }
}
