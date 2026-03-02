function showChronoToast(message, type = 'danger') {
    const toastHtml = `
        <div class="toast align-items-center text-white bg-${type} border-0" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;
    const toastContainer = document.getElementById('toast-container') || createToastContainer();
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    const toastEl = toastContainer.lastElementChild;
    const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
    toast.show();
    toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
}

function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
    container.style.zIndex = '1080';
    document.body.appendChild(container);
    return container;
}

// 項目追加用
function addChronoItem(containerId = 'chrono_items_container') {
    const container = document.getElementById(containerId);
    if (!container) return;
    const currentCount = container.querySelectorAll('.chrono-item').length;
    const newIndex = currentCount + 1;

    const div = document.createElement('div');
    div.className = 'input-group mb-2 chrono-item';
    div.innerHTML = `
        <span class="input-group-text">${newIndex}</span>
        <input type="text" class="form-control item-text" name="items" placeholder="${newIndex}番目に古い項目" required>
        <button class="btn btn-outline-danger" type="button" onclick="this.parentElement.remove(); updateChronoItemNumbers('${containerId}')"><i class="fas fa-times"></i></button>
    `;
    container.appendChild(div);
}

function addEditChronoItem() {
    addChronoItem('edit_chrono_items_container');
}

function updateChronoItemNumbers(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const items = container.querySelectorAll('.chrono-item');
    items.forEach((item, index) => {
        item.querySelector('.input-group-text').textContent = index + 1;
    });
}

function getChronoItemsData(containerId) {
    const container = document.getElementById(containerId);
    const inputs = container.querySelectorAll('.item-text');
    const items = [];
    inputs.forEach((input, index) => {
        if (input.value.trim()) {
            items.push({
                id: index + 1,
                order: index + 1,
                text: input.value.trim()
            });
        }
    });
    return items;
}

function addChronoProblem() {
    const form = document.getElementById('newChronoProblemForm');
    if (!form.checkValidity()) {
        form.reportValidity();
        return;
    }

    const chapter = document.getElementById('new_chrono_chapter').value.trim();
    const university = document.getElementById('new_chrono_university').value.trim();
    const year = document.getElementById('new_chrono_year').value.trim();
    const difficulty = document.getElementById('new_chrono_difficulty').value;
    const question = document.getElementById('new_chrono_question').value.trim();
    const explanation = document.getElementById('new_chrono_explanation').value.trim();
    const items = getChronoItemsData('chrono_items_container');

    if (items.length < 2) {
        showChronoToast('最低でも2つの項目を入力してください', 'warning');
        return;
    }

    const data = {
        chapter: chapter,
        university: university,
        year: year ? parseInt(year) : null,
        difficulty: parseInt(difficulty),
        question: question,
        explanation: explanation,
        items: items
    };

    fetch('/admin/chrono/add_problem', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
        .then(response => response.json())
        .then(result => {
            if (result.status === 'success') {
                showChronoToast('問題を追加しました', 'success');
                form.reset();
                // Reset to 4 items initially
                document.getElementById('chrono_items_container').innerHTML = `
                <div class="input-group mb-2 chrono-item">
                    <span class="input-group-text">1</span>
                    <input type="text" class="form-control item-text" name="items" placeholder="一番古い項目 (例: 大化の改新)" required>
                </div>
                <div class="input-group mb-2 chrono-item">
                    <span class="input-group-text">2</span>
                    <input type="text" class="form-control item-text" name="items" placeholder="2番目に古い項目" required>
                </div>
                <div class="input-group mb-2 chrono-item">
                    <span class="input-group-text">3</span>
                    <input type="text" class="form-control item-text" name="items" placeholder="3番目に古い項目" required>
                </div>
                <div class="input-group mb-2 chrono-item">
                    <span class="input-group-text">4</span>
                    <input type="text" class="form-control item-text" name="items" placeholder="一番新しい項目" required>
                </div>
            `;
                loadChronoProblems(1);
            } else {
                showChronoToast(result.message || '追加に失敗しました', 'danger');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showChronoToast('通信エラーが発生しました', 'danger');
        });
}

function loadChronoProblems(page = 1) {
    const chapter = document.getElementById('chrono_filter_chapter') ? document.getElementById('chrono_filter_chapter').value : '';
    const search = document.getElementById('chrono_search_query') ? document.getElementById('chrono_search_query').value : '';
    const tbody = document.getElementById('chronoProblemListBody');

    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="8" class="text-center py-4"><div class="spinner-border text-primary"></div></td></tr>';

    fetch(`/admin/chrono/problems?page=${page}&chapter=${encodeURIComponent(chapter)}&search=${encodeURIComponent(search)}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                renderChronoProblems(data.problems);
                renderChronoPagination(data.pagination);
                updateChronoChapterFilter(data.chapters, chapter);
                updateChronoReorderList(data.chapters);
            } else {
                tbody.innerHTML = `<tr><td colspan="8" class="text-center text-danger">${data.message || '問題の取得に失敗しました'}</td></tr>`;
            }
        })
        .catch(error => {
            console.error('Error:', error);
            tbody.innerHTML = '<tr><td colspan="8" class="text-center text-danger">通信エラーが発生しました</td></tr>';
        });
}

function renderChronoProblems(problems) {
    const tbody = document.getElementById('chronoProblemListBody');
    if (problems.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center py-4 text-muted">📭 問題が見つかりませんでした</td></tr>';
        return;
    }

    tbody.innerHTML = '';
    problems.forEach(p => {
        const itemTexts = p.items.map((item, i) => `${i + 1}. ${item.text}`).join('<br>');

        const tr = document.createElement('tr');
        tr.className = p.enabled ? '' : 'table-secondary text-muted';
        tr.innerHTML = `
            <td><input type="checkbox" class="chrono-checkbox" value="${p.id}"></td>
            <td>${p.id}</td>
            <td><span class="badge bg-secondary">${p.chapter}</span></td>
            <td>
                <div class="fw-bold">${p.university || '-'}</div>
                <small class="text-muted">${p.year || '-'}</small>
            </td>
            <td>
                <div class="text-truncate" style="max-width: 200px;" title="${p.display_question}">${p.display_question}</div>
            </td>
            <td>
                <span class="badge bg-info">${p.items.length} 項目</span>
                <button type="button" class="btn btn-sm btn-link p-0 ms-1" onclick="alert('${itemTexts.replace(/'/g, "\\'")}')"><i class="fas fa-info-circle"></i></button>
            </td>
            <td>
                <div class="form-check form-switch cursor-pointer">
                    <input class="form-check-input" type="checkbox" id="chrono_enable_${p.id}" 
                        ${p.enabled ? 'checked' : ''} onchange="toggleChronoProblem(${p.id})">
                </div>
            </td>
            <td>
                <button class="btn btn-sm btn-outline-primary" onclick="openEditChronoModal(${p.id})">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn btn-sm btn-outline-danger" onclick="deleteChronoProblem(${p.id})">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function renderChronoPagination(pagination) {
    const ul = document.getElementById('chronoPagination');
    if (!ul) return;

    ul.innerHTML = '';

    // Prev
    ul.innerHTML += `
        <li class="page-item ${!pagination.has_prev ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="event.preventDefault(); ${pagination.has_prev ? `loadChronoProblems(${pagination.page - 1})` : ''}">前へ</a>
        </li>
    `;

    // Pages
    for (let p of pagination.iter_pages) {
        if (p) {
            ul.innerHTML += `
                <li class="page-item ${p === pagination.page ? 'active' : ''}">
                    <a class="page-link" href="#" onclick="event.preventDefault(); loadChronoProblems(${p})">${p}</a>
                </li>
            `;
        } else {
            ul.innerHTML += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
    }

    // Next
    ul.innerHTML += `
        <li class="page-item ${!pagination.has_next ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="event.preventDefault(); ${pagination.has_next ? `loadChronoProblems(${pagination.page + 1})` : ''}">次へ</a>
        </li>
    `;
}

function updateChronoChapterFilter(chapters, selectedChapter) {
    const select = document.getElementById('chrono_filter_chapter');
    if (!select) return;

    let html = '<option value="">すべて</option>';
    chapters.forEach(ch => {
        html += `<option value="${ch}" ${ch === selectedChapter ? 'selected' : ''}>${ch}</option>`;
    });
    select.innerHTML = html;
}

let chronoSortable = null;

function updateChronoReorderList(chapters) {
    const list = document.getElementById('chrono_chapter_reorder_list');
    if (!list) return;

    if (chapters.length === 0) {
        list.innerHTML = '<li class="list-group-item text-center text-muted">セクションがありません</li>';
        return;
    }

    list.innerHTML = '';
    chapters.forEach((ch, index) => {
        const li = document.createElement('li');
        li.className = 'list-group-item d-flex justify-content-between align-items-center';
        li.style.cursor = 'grab';
        li.dataset.id = ch;
        li.innerHTML = `
            <span><i class="fas fa-grip-vertical text-muted me-3"></i> ${ch}</span>
            <span class="badge bg-light text-dark border order-badge">${index + 1}</span>
        `;
        list.appendChild(li);
    });

    if (chronoSortable) {
        chronoSortable.destroy();
    }

    chronoSortable = Sortable.create(list, {
        animation: 150,
        ghostClass: 'bg-light',
        onEnd: function () {
            // Update badges after reorder
            const items = list.querySelectorAll('.list-group-item');
            items.forEach((item, idx) => {
                const badge = item.querySelector('.order-badge');
                if (badge) badge.textContent = idx + 1;
            });
        }
    });
}

function saveChronoChapterOrder() {
    const list = document.getElementById('chrono_chapter_reorder_list');
    if (!list) return;

    const items = list.querySelectorAll('.list-group-item');
    const orders = [];
    items.forEach((item, index) => {
        if (item.dataset.id) {
            orders.push({
                chapter_name: item.dataset.id,
                display_order: index + 1
            });
        }
    });

    if (orders.length === 0) {
        showChronoToast('保存するセクションがありません', 'warning');
        return;
    }

    fetch('/admin/api/chronological/reorder_chapters', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ orders: orders })
    })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showChronoToast('セクションの表示順を保存しました', 'success');
                loadChronoProblems(1);
            } else {
                showChronoToast(data.message || '保存に失敗しました', 'danger');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showChronoToast('通信エラーが発生しました', 'danger');
        });
}

function toggleAllChronoCheckboxes() {
    const checkAll = document.getElementById('selectAllChrono');
    const checkboxes = document.querySelectorAll('.chrono-checkbox');
    checkboxes.forEach(cb => cb.checked = checkAll.checked);
}

function deleteChronoProblem(id) {
    if (!confirm('この問題を削除してもよろしいですか？')) return;

    fetch('/admin/chrono/delete_problem', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ ids: [id] })
    })
        .then(response => response.json())
        .then(result => {
            if (result.status === 'success') {
                showChronoToast('問題を削除しました', 'success');
                loadChronoProblems(1);
            } else {
                showChronoToast(result.message || '削除に失敗しました', 'danger');
            }
        });
}

function bulkDeleteChronoProblems() {
    const checked = document.querySelectorAll('.chrono-checkbox:checked');
    if (checked.length === 0) {
        showChronoToast('削除する問題を選択してください', 'warning');
        return;
    }

    if (!confirm(`選択した ${checked.length} 件の問題を削除してもよろしいですか？`)) return;

    const ids = Array.from(checked).map(cb => parseInt(cb.value));

    fetch('/admin/chrono/delete_problem', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ ids: ids })
    })
        .then(response => response.json())
        .then(result => {
            if (result.status === 'success') {
                showChronoToast(`${result.deleted_count}件の問題を削除しました`, 'success');
                loadChronoProblems(1);
                document.getElementById('selectAllChrono').checked = false;
            } else {
                showChronoToast(result.message || '削除に失敗しました', 'danger');
            }
        });
}

function toggleChronoProblem(id) {
    fetch('/admin/chrono/toggle_enabled', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ id: id })
    })
        .then(response => response.json())
        .then(result => {
            if (result.status !== 'success') {
                showChronoToast('状態の変更に失敗しました', 'danger');
                // Revert checkbox
                const cb = document.getElementById(`chrono_enable_${id}`);
                if (cb) cb.checked = !cb.checked;
            }
        });
}

function openEditChronoModal(id) {
    fetch(`/admin/chrono/problem/${id}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                const p = data.problem;
                document.getElementById('edit_chrono_id').value = p.id;
                document.getElementById('edit_chrono_chapter').value = p.chapter || '';
                document.getElementById('edit_chrono_university').value = p.university || '';
                document.getElementById('edit_chrono_year').value = p.year || '';
                document.getElementById('edit_chrono_difficulty').value = p.difficulty || '2';
                document.getElementById('edit_chrono_question').value = p.question || '';
                document.getElementById('edit_chrono_explanation').value = p.explanation || '';

                const container = document.getElementById('edit_chrono_items_container');
                container.innerHTML = '';

                p.items.forEach((item, index) => {
                    const div = document.createElement('div');
                    div.className = 'input-group mb-2 chrono-item';
                    div.innerHTML = `
                    <span class="input-group-text">${index + 1}</span>
                    <input type="text" class="form-control item-text" name="items" value="${item.text.replace(/"/g, '&quot;')}" required>
                    <button class="btn btn-outline-danger" type="button" onclick="this.parentElement.remove(); updateChronoItemNumbers('edit_chrono_items_container')"><i class="fas fa-times"></i></button>
                `;
                    container.appendChild(div);
                });

                const modal = new bootstrap.Modal(document.getElementById('chronoEditModal'));
                modal.show();
            } else {
                showChronoToast('問題データの取得に失敗しました', 'danger');
            }
        });
}

function saveChronoProblem() {
    const form = document.getElementById('editChronoForm');
    if (!form.checkValidity()) {
        form.reportValidity();
        return;
    }

    const id = document.getElementById('edit_chrono_id').value;
    const chapter = document.getElementById('edit_chrono_chapter').value.trim();
    const university = document.getElementById('edit_chrono_university').value.trim();
    const year = document.getElementById('edit_chrono_year').value.trim();
    const difficulty = document.getElementById('edit_chrono_difficulty').value;
    const question = document.getElementById('edit_chrono_question').value.trim();
    const explanation = document.getElementById('edit_chrono_explanation').value.trim();
    const items = getChronoItemsData('edit_chrono_items_container');

    if (items.length < 2) {
        showChronoToast('最低でも2つの項目を入力してください', 'warning');
        return;
    }

    const data = {
        id: id,
        chapter: chapter,
        university: university,
        year: year ? parseInt(year) : null,
        difficulty: parseInt(difficulty),
        question: question,
        explanation: explanation,
        items: items
    };

    fetch('/admin/chrono/update_problem', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
        .then(response => response.json())
        .then(result => {
            if (result.status === 'success') {
                showChronoToast('問題を更新しました', 'success');
                bootstrap.Modal.getInstance(document.getElementById('chronoEditModal')).hide();
                loadChronoProblems(1);
            } else {
                showChronoToast(result.message || '更新に失敗しました', 'danger');
            }
        });
}

function downloadChronoTemplate() {
    const csvContent = "chapter,university,year,difficulty,question,explanation,item1,item2,item3,item4\n1,東大,2024,2,,,大化の改新,壬申の乱,平城京遷都,平安京遷都\n";
    const blob = new Blob([new Uint8Array([0xEF, 0xBB, 0xBF]), csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.setAttribute("href", url);
    link.setAttribute("download", "chrono_template.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// Event Listeners for file upload
document.addEventListener('DOMContentLoaded', () => {
    // When chronological tab is opened, load problems
    const chronoTab = document.getElementById('tab-link-chrono-management');
    if (chronoTab) {
        chronoTab.addEventListener('shown.bs.tab', () => {
            loadChronoProblems(1);
        });
    }

    const fileInput = document.getElementById('chrono_csv_file');
    if (fileInput) {
        fileInput.addEventListener('change', function (e) {
            const fileName = e.target.files[0]?.name || 'ファイル未選択';
            document.getElementById('chrono_filename_display').textContent = fileName;
        });
    }

    const uploadForm = document.getElementById('chronoUploadForm');
    if (uploadForm) {
        uploadForm.addEventListener('submit', function (e) {
            e.preventDefault();
            const formData = new FormData(this);

            const btn = this.querySelector('.btn-upload');
            const originalText = btn.innerHTML;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> アップロード中...';
            btn.disabled = true;

            fetch('/admin/chrono/upload_csv', {
                method: 'POST',
                body: formData
            })
                .then(response => response.json())
                .then(result => {
                    if (result.status === 'success') {
                        showChronoToast(`${result.added}件の問題をインポートしました`, 'success');
                        this.reset();
                        document.getElementById('chrono_filename_display').textContent = '';
                        loadChronoProblems(1);
                    } else {
                        showChronoToast(result.message || 'インポートに失敗しました', 'danger');
                    }
                })
                .catch(error => {
                    showChronoToast('通信エラーが発生しました', 'danger');
                })
                .finally(() => {
                    btn.innerHTML = originalText;
                    btn.disabled = false;
                });
        });
    }
});
