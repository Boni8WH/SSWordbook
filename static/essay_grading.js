document.addEventListener('DOMContentLoaded', function () {
    // DOM Elements
    const richTextEditor = document.getElementById('richTextEditor');
    const charCount = document.getElementById('charCount');
    const saveDraftBtn = document.getElementById('saveDraftBtn');
    const gradeEssayBtn = document.getElementById('gradeEssayBtn');
    const essayImageInput = document.getElementById('essayImageInput');
    const imagePreview = document.getElementById('imagePreview');
    const imagePreviewContainer = document.getElementById('imagePreviewContainer');
    const uploadInstructions = document.getElementById('uploadInstructions');
    const processOcrBtn = document.getElementById('processOcrBtn');
    const ocrActionArea = document.getElementById('ocrActionArea');
    const gradingResult = document.getElementById('gradingResult');

    // Get Problem Data
    const problemData = document.getElementById('problem-data');
    if (!problemData) return;
    const problemId = parseInt(problemData.getAttribute('data-problem-id'));
    const problemText = document.querySelector('.question-text').innerText;
    // Assuming model answer is in .answer-text but hidden initially. We can grab textContent.
    const modelAnswerText = document.querySelector('.answer-text').innerText;

    // Rich Text Editor - Character Count
    if (richTextEditor) {
        richTextEditor.addEventListener('input', function () {
            const text = richTextEditor.innerText.replace(/\n/g, '');
            charCount.textContent = text.length + '文字';
        });
        // Initial count
        const initialText = richTextEditor.innerText.replace(/\n/g, '');
        charCount.textContent = initialText.length + '文字';
    }

    // Save Draft
    if (saveDraftBtn) {
        saveDraftBtn.addEventListener('click', function () {
            const draftAnswer = richTextEditor.innerHTML; // HTMLで保存
            saveDraft(problemId, draftAnswer);
        });
    }

    // Image Upload Preview
    if (essayImageInput) {
        essayImageInput.addEventListener('change', function (e) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function (e) {
                    imagePreview.src = e.target.result;
                    imagePreviewContainer.style.display = 'block';
                    uploadInstructions.style.display = 'none';
                    ocrActionArea.style.display = 'block';
                };
                reader.readAsDataURL(file);
            }
        });
    }

    // Process OCR
    if (processOcrBtn) {
        processOcrBtn.addEventListener('click', function () {
            const file = essayImageInput.files[0];
            if (!file) {
                alert('画像を選択してください');
                return;
            }

            processOcrBtn.disabled = true;
            processOcrBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 読み込み中...';

            // Ad Container ID
            const adContainerId = 'ocr-ad-container';

            // Check Ad Setting
            const appInfo = window.appInfoFromFlask || {};
            const settings = appInfo.app_settings || {};
            const isBannerAdEnabled = settings.ad_banner_enabled === true;

            let adContainer = document.getElementById(adContainerId);

            if (isBannerAdEnabled) {
                // Create and append Ad Placeholder ONLY if enabled
                if (!adContainer) {
                    adContainer = document.createElement('div');
                    adContainer.id = adContainerId;
                    adContainer.className = 'mt-3 p-2 bg-light border rounded text-center';
                    adContainer.innerHTML = `
                        <p class="small text-muted mb-1">▼ 読み込み中に広告が表示されます</p>
                        <!-- OCR_Loading AdSense -->
                        <ins class="adsbygoogle"
                             style="display:block"
                             data-ad-client="ca-pub-4793789398503896"
                             data-ad-slot="1531506184"
                             data-ad-format="auto"
                             data-full-width-responsive="true"></ins>
                    `;
                    ocrActionArea.appendChild(adContainer);

                    // Trigger AdSense
                    try {
                        (window.adsbygoogle = window.adsbygoogle || []).push({});
                    } catch (e) {
                        console.error("AdSense Error:", e);
                    }
                }
                adContainer.style.display = 'block';
            } else {
                // Ensure it's hidden if setting is off
                if (adContainer) adContainer.style.display = 'none';
            }

            const formData = new FormData();
            formData.append('image', file);

            fetch('/api/essay/ocr', {
                method: 'POST',
                body: formData
            })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        // Insert into editor
                        // If editor is empty, replace. If not, append? Replace is safer for "reading answer".
                        if (confirm('読み取ったテキストでエディタの内容を上書きしますか？')) {
                            richTextEditor.innerHTML = data.text;
                            // Trigger input event to update char count
                            richTextEditor.dispatchEvent(new Event('input'));

                            // Switch tab to direct input
                            const directTab = document.getElementById('direct-tab');
                            if (directTab) {
                                const tab = new bootstrap.Tab(directTab);
                                tab.show();
                            }
                        }
                    } else {
                        alert('エラー: ' + data.message);
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('画像読み込み中にエラーが発生しました');
                })
                .finally(() => {
                    processOcrBtn.disabled = false;
                    processOcrBtn.innerHTML = '<i class="fas fa-magic"></i> 画像から文字を読み取る (AI)';
                    // Hide/Remove Ad
                    if (adContainer) adContainer.style.display = 'none';
                });
        });
    }

    function addDownloadButton() {
        // Remove existing button if any
        const existingBtn = document.getElementById('downloadPdfBtn');
        if (existingBtn) existingBtn.remove();

        const btn = document.createElement('button');
        btn.id = 'downloadPdfBtn';
        btn.className = 'btn btn-outline-danger mt-4';
        btn.innerHTML = '<i class="fas fa-file-pdf"></i> PDFとして保存';
        btn.onclick = window.downloadPdf;

        const gradingResult = document.getElementById('gradingResult');
        gradingResult.appendChild(btn);
    }

    // Grade Essay
    if (gradeEssayBtn) {
        gradeEssayBtn.addEventListener('click', function () {
            const userAnswer = richTextEditor.innerHTML;
            if (richTextEditor.innerText.trim().length === 0) {
                alert('答案を入力してください');
                return;
            }

            // Validate answer length (must be at least 50% of model answer)
            const currentLength = richTextEditor.innerText.trim().length;
            const problemData = document.getElementById('problem-data');
            const modelAnswerLength = parseInt(problemData.getAttribute('data-answer-length') || '0');

            if (modelAnswerLength > 0 && currentLength < modelAnswerLength / 2) {
                alert(`文字数が不足しています。\n模範解答（約${modelAnswerLength}文字）の半分以上（${Math.ceil(modelAnswerLength / 2)}文字以上）記述してから添削を依頼してください。\n\n現在の文字数: ${currentLength}文字`);
                return;
            }

            if (!confirm('現在の答案で添削を依頼しますか？\n（AIが添削を行います）')) {
                return;
            }

            gradeEssayBtn.disabled = true;
            gradeEssayBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 添削中...';
            gradingResult.style.display = 'block';
            // Check Ad Setting
            const appInfo = window.appInfoFromFlask || {};
            const settings = appInfo.app_settings || {};
            const isAdEnabled = settings.ad_video_enabled === true;

            let adHtml = '';
            if (isAdEnabled) {
                adHtml = `
                    <div class="mt-4 mb-3 text-center">
                        <p class="small text-muted mb-2">▼ 広告が表示されます（15秒後に結果へ移動します）</p>
                        
                        <!-- Grading_Wait AdSense -->
                        <ins class="adsbygoogle"
                             style="display:block"
                             data-ad-client="ca-pub-4793789398503896"
                             data-ad-slot="7123578365"
                             data-ad-format="auto"
                             data-full-width-responsive="true"></ins>
                    </div>
                `;
            }

            gradingResult.innerHTML = `
                <div class="text-center p-4">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                    <p class="mt-2 text-muted">AIが添削中です...<br>（調子が良ければ15秒ほどで完成）</p>
                ${adHtml}
                </div>
            `;

            // Trigger AdSense if enabled
            if (isAdEnabled) {
                try {
                    (window.adsbygoogle = window.adsbygoogle || []).push({});
                } catch (e) {
                    console.error("AdSense Error:", e);
                }
            }

            // Scroll to result
            gradingResult.scrollIntoView({ behavior: 'smooth' });

            // Get Feedback Style
            const feedbackStyle = document.querySelector('input[name="feedbackStyle"]:checked').value;

            // 1. Grading Promise (The heavy lifting)
            const gradingPromise = fetch('/api/essay/grade', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    problem_id: problemId,
                    user_answer: userAnswer,
                    feedback_style: feedbackStyle
                })
            }).then(response => response.json());

            // 2. Ad Wait Promise (The monetization guard)
            const adWaitPromise = new Promise((resolve) => {
                // 広告の有無に関わらず、即座に完了とする（ユーザー要望によりタイマー削除）
                resolve();
            });

            // 3. Wait for BOTH to finish
            Promise.all([gradingPromise, adWaitPromise])
                .then(([data, _]) => {
                    // Both grading is done and ad is finished
                    if (data.status === 'success') {
                        gradingResult.innerHTML = data.feedback;
                        addDownloadButton();
                    } else {
                        gradingResult.innerHTML = `<div class="alert alert-danger">エラーが発生しました: ${data.message}</div>`;
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    gradingResult.innerHTML = `<div class="alert alert-danger">通信エラーが発生しました。もう一度お試しください。</div>`;
                })
                .finally(() => {
                    gradeEssayBtn.disabled = false;
                    gradeEssayBtn.innerHTML = '<i class="fas fa-robot"></i> AI添削を依頼する';
                });
        });
    }

    // PDF Download Function
    window.downloadPdf = function () {
        const element = document.getElementById('gradingResult');
        const problemData = document.getElementById('problem-data');
        const university = problemData.getAttribute('data-university') || '大学不明';
        const year = problemData.getAttribute('data-year') || '年度不明';

        // Date formatting: YYYYMMDD
        const now = new Date();
        const yyyy = now.getFullYear();
        const mm = String(now.getMonth() + 1).padStart(2, '0');
        const dd = String(now.getDate()).padStart(2, '0');
        const dateStr = `${yyyy}${mm}${dd}`;

        const filename = `${dateStr}_${university}_${year}.pdf`;

        const opt = {
            margin: 10,
            filename: filename,
            image: { type: 'jpeg', quality: 1.0 },
            html2canvas: { scale: 3, useCORS: true, letterRendering: true, scrollY: 0 },
            jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
            pagebreak: { mode: ['css', 'legacy'], avoid: ['p', 'li', 'h1', 'h2', 'h3', '.grading-block'] }
        };

        // Create overlay
        const overlay = document.createElement('div');
        overlay.style.position = 'fixed';
        overlay.style.top = '0';
        overlay.style.left = '-10000px'; // Hide off-screen
        overlay.style.width = '100%';
        overlay.style.height = '100%';
        overlay.style.backgroundColor = '#ffffff';
        overlay.style.zIndex = '99999'; // Top of everything
        overlay.style.overflow = 'auto'; // Allow scrolling for html2canvas capture
        overlay.style.padding = '0'; // Reset padding to avoid double margins with pdf margin

        // Content wrapper with specific print styles
        const content = document.createElement('div');
        content.id = 'pdf-content-wrapper';

        // 🆕 Add Title
        const titleContainer = document.createElement('div');
        titleContainer.style.textAlign = 'center';
        titleContainer.style.marginBottom = '20px'; // Give some space

        const pdfTitle = document.createElement('h1');
        pdfTitle.textContent = `論述添削：${university}/${year}`;
        // Ensure the title block doesn't look like a highlighted grading section if not desired,
        // but the user just asked for a title. The centralized alignment is handled by container.

        titleContainer.appendChild(pdfTitle);
        content.appendChild(titleContainer);

        // Original content
        const bodyContent = document.createElement('div');
        bodyContent.innerHTML = element.innerHTML;
        content.appendChild(bodyContent);
        content.style.padding = '20px'; // Internal padding
        content.style.width = '210mm'; // Force A4 width to match PDF
        content.style.maxWidth = '100%';
        content.style.margin = '0 auto';

        // Remove buttons
        const buttons = content.querySelectorAll('button');
        buttons.forEach(btn => btn.remove());

        // 🆕 Add User Answer Section
        const richTextEditor = document.getElementById('richTextEditor');
        if (richTextEditor) {
            const userAnswerDiv = document.createElement('div');
            userAnswerDiv.className = 'user-answer-container';
            userAnswerDiv.style.marginTop = '20px';
            userAnswerDiv.style.borderTop = '2px dashed #bdc3c7'; // Separator
            userAnswerDiv.style.paddingTop = '15px';

            const header = document.createElement('h3');
            header.textContent = '【あなたの解答】';
            // h3 style handled by page CSS injection below, but local style helps structure

            const body = document.createElement('div');
            body.innerHTML = richTextEditor.innerHTML;
            body.style.padding = '10px';
            body.style.backgroundColor = 'rgba(255, 255, 255, 0.5)';
            body.style.border = '1px solid #bdc3c7';
            body.style.borderRadius = '5px';

            userAnswerDiv.appendChild(header);
            userAnswerDiv.appendChild(body);
            content.appendChild(userAnswerDiv);
        }

        // Add Footer with Copyright
        let appName = 'SSWordbook';
        if (window.appInfoFromFlask && window.appInfoFromFlask.appName) {
            appName = window.appInfoFromFlask.appName;
        }

        const footer = document.createElement('div');
        footer.innerHTML = `<small>©︎ ${appName}</small>`;
        footer.style.textAlign = 'right';
        footer.style.marginTop = '20px';
        footer.style.color = '#7f8c8d';
        footer.style.fontSize = '10pt';
        footer.style.borderTop = '1px solid #e5e5e5';
        footer.style.paddingTop = '10px';
        content.appendChild(footer);

        // Apply strong styles and Notebook Design rules
        const style = document.createElement('style');
        style.textContent = `
            @import url('https://fonts.googleapis.com/css2?family=Zen+Maru+Gothic:wght@500;700&display=swap');

            #pdf-content-wrapper {
                color: #2c3e50 !important; /* Slightly softer black */
                background-color: #ffffff !important;
                background-image: 
                    linear-gradient(#e5e5e5 1px, transparent 1px),
                    linear-gradient(90deg, #e5e5e5 1px, transparent 1px) !important;
                background-size: 10mm 10mm !important; /* 1cm grid */
                font-family: 'Zen Maru Gothic', 'Hiragino Maru Gothic ProN', 'Rounded Mplus 1c', sans-serif !important;
                line-height: 1.8 !important;
            }
            #pdf-content-wrapper u {
                text-decoration: underline !important;
                text-decoration-color: #2c3e50 !important;
                text-underline-offset: 3px !important; /* Adjust distance */
                text-decoration-skip-ink: none !important;
                border-bottom: none !important;
            }
            #pdf-content-wrapper * {
                color: #2c3e50 !important;
                background-color: transparent !important;
                text-shadow: none !important;
                box-shadow: none !important;
            }
            /* Marker Effect for Headers */
            #pdf-content-wrapper h1, #pdf-content-wrapper h2 {
                 border-bottom: none !important;
                 background: linear-gradient(transparent 70%, rgba(255, 235, 59, 0.7) 70%) !important;
                 display: inline-block;
                 padding: 0 5mm;
                 margin-bottom: 5mm;
                 page-break-after: avoid;
            }
            #pdf-content-wrapper h3 {
                border-left: 5px solid #ff9800 !important;
                padding-left: 3mm !important;
                margin-top: 5mm;
                page-break-after: avoid !important;
                break-after: avoid !important;
            }
            
            /* Page Break Control */
            #pdf-content-wrapper p, 
            #pdf-content-wrapper li, 
            #pdf-content-wrapper .grading-block, 
            #pdf-content-wrapper blockquote {
                page-break-inside: avoid !important;
                break-inside: avoid !important;
                margin-bottom: 0.5em;
                display: block; /* Ensure block level for better break handling */
            }
            
            #pdf-content-wrapper ul, 
            #pdf-content-wrapper ol {
                page-break-inside: auto; /* Allow lists to break between items */
            }
            
            #pdf-content-wrapper .grade-section {
                page-break-inside: auto;
                margin-bottom: 15px;
            }
            
            .user-answer-container {
                page-break-inside: auto;
            }
            
            /* Emphasis Marker */
            #pdf-content-wrapper strong, #pdf-content-wrapper b {
                background: linear-gradient(transparent 60%, rgba(255, 235, 59, 0.5) 60%) !important;
                font-weight: 700 !important;
            }
        `;

        overlay.appendChild(style);
        overlay.appendChild(content);
        document.body.appendChild(overlay);

        // Update options to be more aggressive with p tags
        // 'css' mode respects page-break-inside: avoid
        // 'legacy' mode is a fallback that tries to calculate breaks
        // We add 'p' to avoid in legacy mode as well
        const updatedOpt = {
            ...opt,
            pagebreak: {
                mode: ['css', 'legacy'],
                avoid: ['h1', 'h2', 'h3', '.grading-block', 'tr', 'blockquote']
                // Removed 'p', 'li' from legacy avoid list to let CSS handle it properly or to avoid too many page breaks if paragraphs are huge.
                // However, user problem is text cutoff. Let's trust CSS 'avoid' first. 
                // If CSS avoid works, legacy isn't needed for p. 
                // Let's rely on CSS page-break-inside: avoid !important for p.
            }
        };

        html2pdf().set(updatedOpt).from(content).save().then(() => {
            document.body.removeChild(overlay);
        }).catch(err => {
            console.error(err);
            document.body.removeChild(overlay);
            alert('PDF作成に失敗しました');
        });
    };

    function saveDraft(problemId, draftAnswer) {
        saveDraftBtn.disabled = true;
        saveDraftBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 保存中...';

        fetch('/api/essay/progress/update', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                problem_id: problemId,
                updates: {
                    draft_answer: draftAnswer
                }
            })
        })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    // Show temporary success message or toast
                    const originalText = saveDraftBtn.innerHTML;
                    saveDraftBtn.innerHTML = '<i class="fas fa-check"></i> 保存しました';
                    saveDraftBtn.classList.remove('btn-outline-primary');
                    saveDraftBtn.classList.add('btn-primary');

                    setTimeout(() => {
                        saveDraftBtn.innerHTML = '<i class="fas fa-save"></i> 下書き保存';
                        saveDraftBtn.classList.add('btn-outline-primary');
                        saveDraftBtn.classList.remove('btn-primary');
                        saveDraftBtn.disabled = false;
                    }, 2000);
                } else {
                    alert('エラー: ' + data.message);
                    saveDraftBtn.disabled = false;
                    saveDraftBtn.innerHTML = '<i class="fas fa-save"></i> 下書き保存';
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('保存中にエラーが発生しました');
                saveDraftBtn.disabled = false;
                saveDraftBtn.innerHTML = '<i class="fas fa-save"></i> 下書き保存';
            });
    }
});
