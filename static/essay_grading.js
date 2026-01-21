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
    const uploadArea = document.getElementById('uploadArea');

    // File object for OCR (handles both input selection and drag & drop)
    let ocrFile = null;

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
            // Remove ALL whitespace (newlines, spaces, nbsp) for consistent counting
            const text = richTextEditor.innerText.replace(/\s+/g, '');
            charCount.textContent = text.length + '文字';
        });
        // Initial count
        const initialText = richTextEditor.innerText.replace(/\s+/g, '');
        charCount.textContent = initialText.length + '文字';
    }

    // Save Draft
    if (saveDraftBtn) {
        saveDraftBtn.addEventListener('click', function () {
            const draftAnswer = richTextEditor.innerHTML; // HTMLで保存
            saveDraft(problemId, draftAnswer);
        });
    }

    // Helper to process file
    const processFile = (file) => {
        if (!file || !file.type.startsWith('image/')) return;

        ocrFile = file;
        const reader = new FileReader();
        reader.onload = function (e) {
            imagePreview.src = e.target.result;
            imagePreviewContainer.style.display = 'block';
            uploadInstructions.style.display = 'none';
            ocrActionArea.style.display = 'block';
        };
        reader.readAsDataURL(file);
    };

    // Image Upload Preview (Input Change)
    if (essayImageInput) {
        essayImageInput.addEventListener('change', function (e) {
            if (e.target.files && e.target.files[0]) {
                processFile(e.target.files[0]);
            }
        });
    }

    // Drag and Drop Logic
    if (uploadArea) {
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            uploadArea.addEventListener(eventName, preventDefaults, false);
        });

        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }

        ['dragenter', 'dragover'].forEach(eventName => {
            uploadArea.addEventListener(eventName, highlight, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            uploadArea.addEventListener(eventName, unhighlight, false);
        });

        function highlight(e) {
            uploadArea.style.backgroundColor = '#e9ecef';
            uploadArea.style.borderColor = '#6c757d';
        }

        function unhighlight(e) {
            uploadArea.style.backgroundColor = '#f8f9fa';
            uploadArea.style.borderColor = '#dee2e6';
        }

        uploadArea.addEventListener('drop', handleDrop, false);

        function handleDrop(e) {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files && files[0]) {
                processFile(files[0]);
            }
        }
    }

    // Process OCR
    if (processOcrBtn) {
        processOcrBtn.addEventListener('click', function () {
            const file = ocrFile;
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
        // Remove existing container if any
        const existingContainer = document.getElementById('downloadBtnContainer');
        if (existingContainer) existingContainer.remove();

        const container = document.createElement('div');
        container.id = 'downloadBtnContainer';
        container.className = 'mt-4 d-flex gap-3 justify-content-center align-items-center';

        // 1. Standard PDF Button
        const btn = document.createElement('button');
        btn.id = 'downloadPdfBtn';
        btn.className = 'btn btn-outline-danger';
        btn.innerHTML = '<i class="fas fa-file-pdf"></i> PDFとして保存';

        // 2. Checkbox for skipping question
        const checkDiv = document.createElement('div');
        checkDiv.className = 'form-check mb-0'; // mb-0 to align with button

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'form-check-input';
        checkbox.id = 'skipQuestionCheck';
        checkbox.style.cursor = 'pointer';

        const label = document.createElement('label');
        label.className = 'form-check-label';
        label.htmlFor = 'skipQuestionCheck';
        label.textContent = '問題文割愛';
        label.style.cursor = 'pointer';
        label.style.userSelect = 'none';

        checkDiv.appendChild(checkbox);
        checkDiv.appendChild(label);

        // Click handler: If checked (skip) -> include=false
        btn.onclick = () => window.downloadPdf(!checkbox.checked);

        container.appendChild(btn);
        container.appendChild(checkDiv);

        const gradingResult = document.getElementById('gradingResult');
        gradingResult.appendChild(container);
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
                        <p class="small text-muted mb-2">▼ 広告が表示されます</p>
                        
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
                // 広告の有無に関わらず、即座に完了とする
                resolve();
            });

            // 3. Wait for BOTH to finish
            Promise.all([gradingPromise, adWaitPromise])
                .then(([data, _]) => {
                    // Both grading is done and ad is finished
                    if (data.status === 'success') {
                        gradingResult.innerHTML = data.feedback;
                        addDownloadButton();

                        // 🆕 Style the Logic Flow (Thinking Process)
                        // Note: Logic Flow is NOT rewrite, so no char counting needed.
                        const logicFlowDiv = gradingResult.querySelector('.logic-flow');
                        if (logicFlowDiv) {
                            logicFlowDiv.style.backgroundColor = '#f0f8ff'; // Light Alice Blue
                            logicFlowDiv.style.borderLeft = '5px solid #3498db';
                            logicFlowDiv.style.padding = '15px';
                            logicFlowDiv.style.borderRadius = '5px';
                            logicFlowDiv.style.marginTop = '15px';
                        }

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
    window.downloadPdf = function (includeQuestion = true) {
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
            pagebreak: { mode: ['css', 'legacy'], avoid: ['p', 'li', 'h1', 'h2', 'h3', '.grading-block', '.pdf-footer'] }
        };

        // Create overlay
        // Create overlay
        const overlay = document.createElement('div');
        overlay.style.top = '0';
        overlay.style.left = '0'; // Use 0 to prevent canvas clipping limits
        overlay.style.position = 'fixed'; // Ensure it stays on screen relative to viewport for capture
        overlay.style.width = '210mm'; // Standardize width here too
        overlay.style.zIndex = '-9999'; // Behind everything
        overlay.style.visibility = 'visible'; // Must be visible for html2canvas
        overlay.style.overflow = 'visible';
        overlay.style.padding = '0';

        // Content wrapper with specific print styles
        const content = document.createElement('div');
        content.id = 'pdf-content-wrapper';

        // 🆕 Add Title
        const titleContainer = document.createElement('div');
        titleContainer.style.textAlign = 'center';
        titleContainer.style.marginBottom = '10px'; // Reduced space

        const pdfTitle = document.createElement('h1');
        pdfTitle.textContent = `論述添削：${university}/${year}`;
        pdfTitle.style.marginBottom = '0'; // Remove default margin

        // Ensure the title block doesn't look like a highlighted grading section if not desired,
        // but the user just asked for a title. The centralized alignment is handled by container.

        titleContainer.appendChild(pdfTitle);

        const pdfDate = document.createElement('p');
        pdfDate.textContent = `${now.getFullYear()}/${now.getMonth() + 1}/${now.getDate()}`;
        pdfDate.style.fontSize = '0.9em';
        pdfDate.style.color = '#666';
        pdfDate.style.marginTop = '0px'; // Tighter
        titleContainer.appendChild(pdfDate);

        // 1. Append Title
        content.appendChild(titleContainer);

        // 2. Append Problem Statement (if found and requested)
        const questionSectionElement = document.querySelector('.question-section');
        if (includeQuestion && questionSectionElement) {
            const questionDiv = document.createElement('div');
            questionDiv.className = 'pdf-section-container';
            questionDiv.style.marginBottom = '10px'; // Reduced from 20px
            questionDiv.style.borderBottom = '1px solid #eee';
            questionDiv.style.paddingBottom = '10px'; // Reduced from 15px

            const qHeader = document.createElement('h3');
            qHeader.textContent = '【問題】';
            qHeader.style.color = '#2c3e50';
            qHeader.style.borderLeft = '4px solid #667eea';
            qHeader.style.paddingLeft = '10px';
            qHeader.style.marginBottom = '5px'; // Reduced from 10px

            // Clone the entire section to catch multiple paragraphs
            const qBody = questionSectionElement.cloneNode(true);

            // Remove the existing header from the clone to avoid duplication
            const existingHeader = qBody.querySelector('.section-title');
            if (existingHeader) {
                existingHeader.remove();
            }

            // Remove the image from the clone (User request)
            const existingImage = qBody.querySelector('.question-image');
            if (existingImage) {
                existingImage.remove();
            }

            qBody.style.margin = '0';
            qBody.style.padding = '0';
            qBody.style.border = 'none';
            qBody.style.fontSize = '10pt';
            qBody.style.lineHeight = '1.6';
            qBody.style.letterSpacing = 'normal';

            // Reset margins for paragraphs inside
            const paragraphs = qBody.querySelectorAll('p, .question-text');
            paragraphs.forEach(p => {
                p.style.margin = '0 0 5px 0'; // Tight margins
                p.style.whiteSpace = 'pre-wrap'; // Apply pre-wrap specifically to text containers
            });

            // Clean up empty text nodes from cloning (source code indentation)
            Array.from(qBody.childNodes).forEach(node => {
                if (node.nodeType === Node.TEXT_NODE && !node.textContent.trim()) {
                    node.remove();
                }
            });

            questionDiv.appendChild(qHeader);
            questionDiv.appendChild(qBody);
            content.appendChild(questionDiv);
        }

        // 3. Append User Answer (if found)
        const richTextEditor = document.getElementById('richTextEditor');
        if (richTextEditor) {
            const userAnswerDiv = document.createElement('div');
            userAnswerDiv.className = 'user-answer-container';
            userAnswerDiv.style.marginBottom = '20px';
            userAnswerDiv.style.borderBottom = '2px dashed #bdc3c7';
            userAnswerDiv.style.paddingBottom = '15px';

            const header = document.createElement('h3');
            header.textContent = '【あなたの解答】';
            header.style.color = '#2c3e50';
            header.style.borderLeft = '4px solid #ff9800'; // Orange for answer
            header.style.paddingLeft = '10px';
            header.style.marginBottom = '10px';

            const body = document.createElement('div');
            body.innerHTML = richTextEditor.innerHTML;
            body.style.padding = '10px';
            body.style.backgroundColor = 'rgba(255, 248, 225, 0.5)'; // Light orange bg
            body.style.border = '1px solid #ffe0b2';
            body.style.borderRadius = '5px';

            userAnswerDiv.appendChild(header);
            userAnswerDiv.appendChild(body);
            content.appendChild(userAnswerDiv);
        }

        // 4. Append Grading Result (Original content)
        const bodyContent = document.createElement('div');
        bodyContent.innerHTML = element.innerHTML;
        content.appendChild(bodyContent);

        // 5. Apply styles to content wrapper
        content.style.padding = '20px';
        content.style.width = '210mm';
        content.style.maxWidth = '100%';
        content.style.margin = '0 auto';

        // 6. Remove buttons and controls
        const buttons = content.querySelectorAll('button');
        buttons.forEach(btn => btn.remove());

        // Remove the download button container (includes checkbox)
        const downloadContainer = content.querySelector('#downloadBtnContainer');
        if (downloadContainer) {
            downloadContainer.remove();
        }

        // Add Footer with Copyright
        let appName = 'SSWordbook';
        if (window.appInfoFromFlask && window.appInfoFromFlask.appName) {
            appName = window.appInfoFromFlask.appName;
        }

        const footer = document.createElement('div');
        footer.className = 'pdf-footer';
        footer.innerHTML = `<small>©︎ ${appName}</small>`;
        footer.style.textAlign = 'right';
        footer.style.marginTop = '20px';
        footer.style.color = '#7f8c8d';
        footer.style.fontSize = '10pt';
        footer.style.borderTop = '1px solid #e5e5e5';
        footer.style.paddingTop = '10px';
        footer.style.paddingBottom = '10px'; // Prevent cut-off
        content.appendChild(footer);

        // Global text normalization for the entire PDF content
        // This fixes NFD issues (detached dakuten) across problem, answer, and grading
        const normalizeAllText = (node) => {
            if (node.nodeType === Node.TEXT_NODE) {
                node.nodeValue = node.nodeValue.normalize('NFC');
            } else {
                node.childNodes.forEach(normalizeAllText);
            }
        };
        normalizeAllText(content);

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
                line-height: 2.2 !important; /* Increased line-height to prevent underline overlap */
            }
            #pdf-content-wrapper u {
                text-decoration: underline !important;
                text-decoration-color: #2c3e50 !important;
                text-underline-offset: 4px !important; /* Increased offset */
                text-decoration-skip-ink: none !important;
                border-bottom: none !important;
                padding-bottom: 2px; /* Add padding for safety */
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
                page-break-inside: avoid !important; /* Keep content intact to prevent text chopping */
                break-inside: avoid !important;
                margin-bottom: 0.8em;
                display: block; 
                position: relative;
            }

            #pdf-content-wrapper ul, 
            #pdf-content-wrapper ol {
                page-break-inside: auto; 
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
                /* Use simple background color instead of gradient to avoid html2canvas wrapping glitches */
                background-color: rgba(255, 235, 59, 0.4) !important;
                background-image: none !important;
                font-weight: 700 !important;
                display: inline;
                -webkit-box-decoration-break: clone;
                box-decoration-break: clone;
                padding: 0 2px;
                border-radius: 2px;
            }
        `;

        overlay.appendChild(style);
        overlay.appendChild(content);
        document.body.appendChild(overlay);

        // Update options
        const updatedOpt = {
            ...opt,
            html2canvas: {
                scale: 3,
                useCORS: true,
                letterRendering: false, // Disabled to prevent text artifacts
                scrollY: 0
            },
            pagebreak: {
                mode: ['css', 'legacy'],
                // Avoid breaking atoms AND containers to strictly prevent cutting
                avoid: ['h1', 'h2', 'h3', 'tr', 'p', 'li', '.grading-block', 'blockquote']
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
