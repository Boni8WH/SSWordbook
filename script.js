// static/script.js - 完全修正版（全機能保持）

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
let isAnswerButtonDisabled = false; // 答えを見るボタンの無効化フラグ
let answerButtonTimeout = null; // タイムアウト管理用

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
    // 基本情報の設定
    if (lastUpdatedDateSpan) lastUpdatedDateSpan.textContent = window.appInfoFromFlask.lastUpdatedDate;
    if (updateContentP) updateContentP.textContent = window.appInfoFromFlask.updateContent;
    
    // アプリ名の設定
    const appInfoTitle = document.getElementById('appInfoTitle');
    if (appInfoTitle) {
        appInfoTitle.textContent = window.appInfoFromFlask.appName || 'アプリ情報';
    }
    
    // 連絡先情報の設定
    const contactSection = document.getElementById('contactSection');
    const contactEmail = document.getElementById('contactEmail');
    
    if (contactSection && contactEmail && window.appInfoFromFlask.contactEmail) {
        contactEmail.href = 'mailto:' + window.appInfoFromFlask.contactEmail;
        contactEmail.textContent = window.appInfoFromFlask.contactEmail;
        contactSection.style.display = 'block';
    }
}

// word_data はサーバーから取得する必要があるため、初期化は空に
let word_data = [];

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
        const tables = document.querySelectorAll('.ranking-container table, .progress-container table, .user-list-table');
        tables.forEach(table => {
            if (!table.closest('.table-responsive')) {
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
    console.log('DOM loaded, initializing application...');
    
    try {
        updateIncorrectOnlyRadio();
        loadUserData();
        loadWordDataFromServer();
        setupEventListeners();

        // データロード後に選択状態を復元
        setTimeout(() => {
            loadSelectionState();
            initializeSelectAllButtons();
            updateIncorrectOnlySelection(); // 苦手問題選択状態の視覚的フィードバックを初期化
            initializeMobileOptimizations(); // スマホ最適化
            improveTouchExperience(); // タッチ操作改善
            optimizeScrolling(); // スクロール最適化
        }, 1000);

        if (noWeakWordsMessage) {
            noWeakWordsMessage.classList.add('hidden');
        }
    } catch (error) {
        console.error('Error during initialization:', error);
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
            let hasEnabledUnits = false; // 章内に利用可能な単元があるかフラグ
            
            for (const unitNum in chapter.units) {
                if (chapter.units.hasOwnProperty(unitNum)) {
                    const unit = chapter.units[unitNum];
                    const checkbox = document.getElementById(`unit-${chapterNum}-${unitNum}`);
                    if (checkbox) {
                        if (!unit.enabled) {
                            // 利用不可の場合は単元を非表示
                            const unitItem = checkbox.closest('.unit-item');
                            if (unitItem) {
                                unitItem.style.display = 'none';
                            }
                        } else {
                            // 利用可能な場合は表示
                            const unitItem = checkbox.closest('.unit-item');
                            if (unitItem) {
                                unitItem.style.display = 'block';
                            }
                            hasEnabledUnits = true; // 利用可能な単元が見つかった
                        }
                        checkbox.disabled = !unit.enabled;
                        if (checkbox.disabled && checkbox.checked) {
                            checkbox.checked = false;
                        }
                    }
                }
            }
            
            // ★新機能：章内に利用可能な単元がない場合は章全体を非表示
            const chapterItem = document.querySelector(`.chapter-item[data-chapter="${chapterNum}"]`);
            if (chapterItem) {
                if (hasEnabledUnits) {
                    chapterItem.style.display = 'block'; // 章を表示
                } else {
                    chapterItem.style.display = 'none';  // 章を非表示
                    console.log(`第${chapterNum}章は全単元が利用不可のため非表示にしました`);
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
            rangeSelectionTitle.textContent = '出題数を選択（苦手問題モードでは無効）';
            rangeSelectionTitle.style.color = '#95a5a6';
        }
    } else {
        // 通常モードの場合
        if (chaptersContainer) {
            chaptersContainer.style.opacity = '1';
            chaptersContainer.style.pointerEvents = 'auto';
        }
        if (rangeSelectionTitle) {
            rangeSelectionTitle.textContent = '出題数を選択';
            rangeSelectionTitle.style.color = '#34495e';
        }
    }
}

// =========================================================
// イベントリスナーの設定（修正版）
// =========================================================

function setupEventListeners() {
    console.log('Setting up event listeners...');
    
    try {
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

        // 章のヘッダーをクリックで単元リストの表示/非表示を切り替え（スマホ対応版）
        if (chaptersContainer) {
            chaptersContainer.addEventListener('click', (event) => {
                // 「全て選択」ボタンがクリックされた場合の処理
                const selectAllBtn = event.target.closest('.select-all-chapter-btn');
                if (selectAllBtn) {
                    event.stopPropagation();
                    event.preventDefault();
                    
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
                    
                    // 章の展開状態は変更しない
                    return false;
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
        
        console.log('Event listeners setup completed.');
    } catch (error) {
        console.error('Error setting up event listeners:', error);
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
    const selectedQuestions = getSelectedQuestions();
    const selectedQuestionCount = getSelectedQuestionCount();

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
            flashMessage('苦手問題がありません。まずは通常の学習で問題に取り組んでください。', 'info');
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

    currentQuizData = shuffleArray(quizQuestions);
    currentQuestionIndex = 0;
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
    if (weakWordsListSection) weakWordsListSection.classList.add('hidden');
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

    // ★新機能：答えを見るボタンを2秒間無効化
    if (currentQuestionIndex > 0) { // 最初の問題以外で無効化
        isAnswerButtonDisabled = true;
        if (showAnswerButton) {
            showAnswerButton.disabled = true;
            showAnswerButton.style.opacity = '0.5';
            showAnswerButton.style.cursor = 'not-allowed';
        }
        
        // 既存のタイムアウトがあればクリア
        if (answerButtonTimeout) {
            clearTimeout(answerButtonTimeout);
        }
        
        // 2秒後に有効化
        answerButtonTimeout = setTimeout(() => {
            isAnswerButtonDisabled = false;
            if (showAnswerButton) {
                showAnswerButton.disabled = false;
                showAnswerButton.style.opacity = '1';
                showAnswerButton.style.cursor = 'pointer';
            }
            console.log('答えを見るボタンが有効化されました');
        }, 2000);
        
        console.log('答えを見るボタンを2秒間無効化しました');
    }

    if (currentQuestionIndex < totalQuestions) {
        const currentWord = currentQuizData[currentQuestionIndex];
        if (questionElement) questionElement.textContent = currentWord.question;
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

// ★ 修正版 handleAnswer 関数
function handleAnswer(isCorrect) {
    const currentWord = currentQuizData[currentQuestionIndex];
    
    // ★ 修正: null チェックを追加
    if (!currentWord) {
        console.error('handleAnswer: currentWord is undefined');
        return;
    }
    
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
    // 最初に既存のお祝いメッセージを削除
    clearPreviousCelebrationMessages();
    
    if (cardArea) cardArea.classList.add('hidden');
    if (quizResultArea) quizResultArea.classList.remove('hidden');

    if (totalQuestionsCountSpan) totalQuestionsCountSpan.textContent = totalQuestions;
    if (correctCountSpan) correctCountSpan.textContent = correctCount;
    if (incorrectCountSpan) incorrectCountSpan.textContent = incorrectCount;
    
    const accuracy = totalQuestions === 0 ? 0 : (correctCount / totalQuestions) * 100;
    if (accuracyRateSpan) accuracyRateSpan.textContent = accuracy.toFixed(1);

    // ★修正：正確な選択範囲の全問題数を表示
    let displayedRangeTotal = 0;
    
    if (lastQuizSettings.totalSelectedRangeQuestions > 0) {
        // 保存された正確な選択範囲数を使用
        displayedRangeTotal = lastQuizSettings.totalSelectedRangeQuestions;
        console.log(`📊 保存された選択範囲を使用: ${displayedRangeTotal}問`);
    } else {
        // フォールバック：計算で求める
        displayedRangeTotal = calculateAccurateRangeTotal();
        console.log(`📊 フォールバック計算: ${displayedRangeTotal}問`);
    }
    
    if (selectedRangeTotalQuestionsSpan) {
        selectedRangeTotalQuestionsSpan.textContent = displayedRangeTotal;
    }

    displayIncorrectWordsForCurrentQuiz();
    
    // 詳細なログ出力
    console.log('🔍 結果画面表示時の詳細情報:', {
        mode: lastQuizSettings.isIncorrectOnly ? '苦手問題モード' : '通常モード',
        出題数: totalQuestions,
        選択範囲の全問題数: displayedRangeTotal,
        正解数: correctCount,
        正答率: accuracy.toFixed(1) + '%',
        設定保存状況: {
            selectedUnits: lastQuizSettings.selectedUnits?.length || 0,
            availableQuestions: lastQuizSettings.availableQuestions?.length || 0,
            totalSelectedRangeQuestions: lastQuizSettings.totalSelectedRangeQuestions
        }
    });
    
    // 少し遅延させてボタンテキストを更新
    setTimeout(() => {
        updateRestartButtonText();
    }, 100);
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
    console.log('\n=== 進捗保存開始 (JavaScript側) ===');
    console.log(`保存する履歴数: ${Object.keys(problemHistory).length}`);
    console.log(`保存する苦手問題数: ${incorrectWords.length}`);
    
    // 最近の変更を詳細ログ
    const recentEntries = Object.entries(problemHistory)
        .filter(([id, history]) => {
            const lastAnswered = history.last_answered;
            if (!lastAnswered) return false;
            const lastTime = new Date(lastAnswered);
            const now = new Date();
            return (now - lastTime) < 5 * 60 * 1000; // 5分以内
        });
    
    console.log(`最近5分以内の履歴: ${recentEntries.length}件`);
    recentEntries.forEach(([id, history]) => {
        console.log(`  ${id}: 正解${history.correct_attempts}回, 不正解${history.incorrect_attempts}回, 連続${history.correct_streak}回`);
    });

    const dataToSave = {
        problemHistory: problemHistory,
        incorrectWords: incorrectWords
    };

    fetch('/api/save_progress_debug', {  // デバッグ版エンドポイントを使用
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(dataToSave)
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            console.log('✅ 進捗保存成功');
            if (data.debug_info) {
                console.log('保存デバッグ情報:', data.debug_info);
            }
        } else {
            console.error('❌ 進捗保存失敗:', data.message);
            flashMessage(data.message, 'danger');
        }
        console.log('=== 進捗保存終了 ===\n');
    })
    .catch(error => {
        console.error('❌ 進捗保存エラー:', error);
        flashMessage('進捗の保存中にエラーが発生しました。', 'danger');
        console.log('=== 進捗保存終了（エラー） ===\n');
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
    let appName = '世界史単語帳';  // デフォルト値
    let schoolName = '朋優学院';   // デフォルト値
    
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
    const appName = window.appInfoFromFlask ? window.appInfoFromFlask.appName : '世界史単語帳';
    const schoolName = window.appInfoFromFlask ? window.appInfoFromFlask.schoolName : '朋優学院';
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
        onclone: function(clonedDoc) {
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

// パフォーマンス監視の開始
document.addEventListener('DOMContentLoaded', () => {
    // ESCキーでの閉じる機能を追加
    document.addEventListener('keydown', handleEscapeKey);
});

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

// グローバル関数として追加（開発者ツールで実行可能）
window.investigateIdCollisions = function() {
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

window.checkWeakProblemsStatus = function() {
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
window.toggleWeakAnswer = toggleWeakAnswer;