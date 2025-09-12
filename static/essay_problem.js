// static/essay_problem.js
// このファイルは、個別論述問題ページ専用のスクリプトです

document.addEventListener('DOMContentLoaded', function() {    
    const problemData = document.getElementById('problem-data');    
    if (!problemData) {
        console.error('problem-data要素が見つかりません');
        return;
    }
    
    const problemId = parseInt(problemData.getAttribute('data-problem-id'));
    let currentRating = parseInt(problemData.getAttribute('data-current-rating'));
        
    const showAnswerBtn = document.getElementById('showAnswerBtn');
    const hideAnswerBtn = document.getElementById('hideAnswerBtn');
    const saveProgressBtn = document.getElementById('saveProgressBtn');
    const answerSection = document.getElementById('answerSection');
    
    if (answerSection) answerSection.classList.remove('show');
    if (showAnswerBtn) showAnswerBtn.style.display = 'flex';
    if (hideAnswerBtn) hideAnswerBtn.style.display = 'none';
    
    if (currentRating > 0) setRating(currentRating);
    
    if (showAnswerBtn) {
        showAnswerBtn.addEventListener('click', function(e) {
            e.preventDefault();
            showAnswer(problemId);
        });
    }
    
    if (hideAnswerBtn) {
        hideAnswerBtn.addEventListener('click', function(e) {
            e.preventDefault();
            hideAnswer();
        });
    }
    
    if (saveProgressBtn) {
        saveProgressBtn.addEventListener('click', function(e) {
            e.preventDefault();
            saveProgress(problemId, currentRating);

        });
    }
    
    const stars = document.querySelectorAll('.star-rating');
    stars.forEach(star => {
        star.addEventListener('click', function(e) {
            e.preventDefault();
            const rating = this.getAttribute('data-rating');
            currentRating = parseInt(rating);
            setRating(currentRating);
        });
    });    
});

function showAnswer(problemId) {
    const answerSection = document.getElementById('answerSection');
    const showBtn = document.getElementById('showAnswerBtn');
    const hideBtn = document.getElementById('hideAnswerBtn');
    
    if (answerSection && showBtn && hideBtn) {
        answerSection.classList.add('show');
        showBtn.style.display = 'none';
        hideBtn.style.display = 'flex';
        updateProgress(problemId, { viewed_answer: true });
    }
}

function hideAnswer() {
    const answerSection = document.getElementById('answerSection');
    const showBtn = document.getElementById('showAnswerBtn');
    const hideBtn = document.getElementById('hideAnswerBtn');
    
    if (answerSection && showBtn && hideBtn) {
        answerSection.classList.remove('show');
        showBtn.style.display = 'flex';
        hideBtn.style.display = 'none';
    }
}

function setRating(rating) {
    const stars = document.querySelectorAll('.star-rating');
    stars.forEach((star, index) => {
        if (index < rating) {
            star.classList.add('active');
        } else {
            star.classList.remove('active');
        }
    });
}

function saveProgress(problemId, currentRating) {
    const understoodEl = document.getElementById('understood');
    const reviewFlagEl = document.getElementById('reviewFlag');
    const memoEl = document.getElementById('memo');

    const updates = {
        understood: understoodEl.checked,
        review_flag: reviewFlagEl.checked,
        memo: memoEl.value,
        difficulty_rating: currentRating
    };
    
    updateProgress(problemId, updates);
}

function updateProgress(problemId, updates) {
    if (!problemId || problemId === 0) {
        alert('問題IDが取得できませんでした');
        return;
    }
    
    fetch('/api/essay/progress/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            problem_id: problemId,
            updates: updates
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            if (updates.understood !== undefined || updates.review_flag !== undefined || updates.memo !== undefined) {
                alert('進捗を保存しました');
                location.reload();
            }
        } else {
            alert('エラー: ' + (data.message || '不明なエラー'));
        }
    })
    .catch(error => {
        alert('進捗の保存中にエラーが発生しました');
    });
}