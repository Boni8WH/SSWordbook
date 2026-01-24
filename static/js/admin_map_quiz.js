// Map Quiz Admin Logic

// Global State
let currentMap = null;
let currentPins = [];
let showPinNames = true;
const API_BASE = '/admin/api/map_quiz';

document.addEventListener('DOMContentLoaded', function () {
    // Determine if we need to load map list
    const tabLink = document.getElementById('tab-link-map-quiz');
    if (tabLink) {
        tabLink.addEventListener('shown.bs.tab', function () {
            loadSortableMapList();
        });
        if (tabLink.classList.contains('active')) {
            loadSortableMapList();
        }
    } else {
        // Fallback for direct page access if no tabs or different structure
        loadSortableMapList();
    }
});

// --- Sortable & Hierarchy Management ---

async function loadSortableMapList() {
    const listEl = document.getElementById('genreSortableList');
    if (!listEl) return; // Guard if element missing

    listEl.innerHTML = '<div class="text-center p-3 text-muted"><i class="fas fa-sync fa-spin"></i> Loading...</div>';

    try {
        const response = await fetch(`${API_BASE}/genres`);
        const data = await response.json();

        listEl.innerHTML = '';

        // 1. Render Genres
        data.genres.forEach(genre => {
            const genreItem = createGenreItem(genre);
            listEl.appendChild(genreItem);

            // Init Sortable for Maps inside Genre
            const mapListContainer = genreItem.querySelector('.map-sortable-list');
            new Sortable(mapListContainer, {
                group: 'maps',
                animation: 150,
                handle: '.map-handle',
                onEnd: function (evt) {
                    const mapIds = Array.from(mapListContainer.children).map(el => el.dataset.mapId);
                    updateMapOrder(mapIds);
                }
            });
        });

        // 2. Init Sortable for Genres
        new Sortable(listEl, {
            animation: 150,
            handle: '.genre-handle',
            onEnd: function (evt) {
                const genreIds = Array.from(listEl.children)
                    .map(el => el.dataset.genreId)
                    .filter(id => id !== 'others');
                updateGenreOrder(genreIds);
            }
        });

    } catch (error) {
        listEl.innerHTML = `<div class="text-danger p-2">Error: ${error.message}</div>`;
    }
}

function createGenreItem(genre) {
    const isOthers = genre.id === 'others';
    const div = document.createElement('div');
    div.className = 'accordion-item border mb-2';
    div.dataset.genreId = genre.id;

    const headerId = `heading-${genre.id}`;
    const collapseId = `collapse-${genre.id}`;

    let actionsHtml = '';
    if (!isOthers) {
        actionsHtml = `
            <div class="ms-auto d-flex align-items-center gap-2">
                <i class="fas fa-edit text-muted pointer" onclick="editGenre(${genre.id}, '${genre.name}')" title="名前変更"></i>
                <i class="fas fa-trash text-muted pointer" onclick="deleteGenre(${genre.id})" title="削除"></i>
                <i class="fas fa-grip-lines text-secondary genre-handle pointer ms-2" title="並び替え"></i>
            </div>
        `;
    } else {
        actionsHtml = `<div class="ms-auto text-muted small">ー</div>`;
    }

    div.innerHTML = `
        <div class="accordion-header p-2 bg-light d-flex align-items-center justify-content-between" id="${headerId}">
            <div class="d-flex align-items-center flex-grow-1 overflow-hidden me-2" type="button" 
                data-bs-toggle="collapse" data-bs-target="#${collapseId}" aria-expanded="false" style="cursor: pointer;">
                <i class="fas fa-folder me-2 text-warning"></i>
                <span class="fw-bold text-dark text-nowrap text-truncate me-2" title="${genre.name}">${genre.name}</span>
                <span class="badge bg-secondary rounded-pill small">${genre.maps.length}</span>
                <i class="fas fa-chevron-down ms-2 text-muted small"></i>
            </div>
            ${actionsHtml}
        </div>
        <div id="${collapseId}" class="accordion-collapse collapse" aria-labelledby="${headerId}" data-bs-parent="#genreSortableList">
            <div class="accordion-body p-0">
                <div class="list-group map-sortable-list list-group-flush" data-genre-id="${genre.id}">
                    <!-- Maps loop -->
                </div>
            </div>
        </div>
    `;

    const mapList = div.querySelector('.map-sortable-list');
    if (genre.maps.length === 0) {
        mapList.innerHTML = '<div class="p-2 text-muted small ps-4">地図なし</div>';
    } else {
        genre.maps.forEach(map => {
            const mapEl = document.createElement('div');
            mapEl.className = 'list-group-item list-group-item-action d-flex align-items-center p-2 ps-4';
            mapEl.dataset.mapId = map.id;

            const isChecked = map.is_active ? 'checked' : '';
            const statusLabel = map.is_active ? '公開' : '非公開';
            const statusClass = map.is_active ? 'text-primary' : 'text-muted';

            mapEl.innerHTML = `
                <i class="fas fa-grip-vertical map-handle text-muted me-3 pointer" style="cursor: grab;"></i>
                <div class="flex-grow-1 pointer overflow-hidden" onclick="selectMap(${map.id})">
                    <span class="text-truncate d-block" title="${map.name}">${map.name}</span>
                </div>
                <div class="form-check form-switch ms-2 me-2">
                    <input class="form-check-input pointer" type="checkbox" role="switch" 
                        onchange="toggleMapVisibility(${map.id}, this.checked, this)" ${isChecked}>
                    <label class="form-check-label small ${statusClass}" style="min-width: 40px; font-size: 0.75rem;">${statusLabel}</label>
                </div>
            `;
            mapList.appendChild(mapEl);
        });
    }

    return div;
}

// Reorder & Status API Calls
async function toggleMapVisibility(mapId, isActive, el) {
    try {
        const response = await fetch(`${API_BASE}/map/${mapId}/toggle_status`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ is_active: isActive })
        });
        const res = await response.json();
        if (res.status === 'success') {
            // Success: Update label in place instead of full reload to preserve accordion state
            if (el) {
                const label = el.nextElementSibling;
                if (label) {
                    label.innerText = isActive ? '公開' : '非公開';
                    label.className = `form-check-label small ${isActive ? 'text-primary' : 'text-muted'}`;
                }
            }
        } else {
            alert('Error: ' + res.message);
            // Revert checkbox state on error
            if (el) el.checked = !isActive;
        }
    } catch (e) {
        alert('通信エラー');
        if (el) el.checked = !isActive;
    }
}

async function updateGenreOrder(ids) {
    await fetch(`${API_BASE}/genre/reorder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
        body: JSON.stringify({ ordered_ids: ids })
    });
}

async function updateMapOrder(ids) {
    await fetch(`${API_BASE}/map/reorder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
        body: JSON.stringify({ ordered_ids: ids })
    });
}

// Genre CRUD
function showAddGenreModal() {
    const name = prompt("新しいジャンル名を入力してください:");
    if (name) addGenre(name);
}

async function addGenre(name) {
    const res = await fetch(`${API_BASE}/genre/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
        body: JSON.stringify({ name: name })
    });
    if (res.ok) loadSortableMapList();
    else alert("エラーが発生しました");
}

async function editGenre(id, oldName) {
    const name = prompt("ジャンル名を編集:", oldName);
    if (name && name !== oldName) {
        await fetch(`${API_BASE}/genre/edit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ id: id, name: name })
        });
        loadSortableMapList();
    }
}

async function deleteGenre(id) {
    if (!confirm("このジャンルを削除しますか？\n含まれる地図は「その他」に移動します。")) return;
    await fetch(`${API_BASE}/genre/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
        body: JSON.stringify({ id: id })
    });
    loadSortableMapList();
}


// --- Map Interaction Logic ---

// Deprecated loader (kept for compatibility in case of shared calls)
async function loadMapList() {
    loadSortableMapList();
}

async function selectMap(mapId) {
    // Clean highlight
    document.querySelectorAll('.list-group-item').forEach(el => el.classList.remove('active'));
    // We could highlight the specific element but it's tricky with multiple lists. 
    // Just load the map data.

    // We need map details (filename, name). 
    // We can fetch just one map or find in DOM. 
    // Let's fetch the list (lightweight) or use a dedicated endpoint.
    // Re-fetching full list is inefficient but safe. 
    // Better: GET /map/<id>

    try {
        // We'll rely on the map list endpoint for metadata for now, or assume we have it.
        // Actually, let's just fetch the map list again and find it, mirroring old logic.
        const listRes = await fetch(`${API_BASE}/maps`);
        const listData = await listRes.json();
        currentMap = listData.maps.find(m => m.id === mapId);

        if (!currentMap) return alert('Map not found');

        // UI Updates
        document.getElementById('mapEditorPlaceholder').style.display = 'none';
        document.getElementById('mapEditorContainer').style.display = 'block';
        document.getElementById('currentMapName').innerText = currentMap.name;
        document.getElementById('currentMapId').value = mapId;

        const img = document.getElementById('editorMapImage');
        img.src = `/serve_map_image/${currentMap.filename}`;

        // Load Pins
        const pinRes = await fetch(`${API_BASE}/map/${mapId}/locations`);
        const pinData = await pinRes.json();
        currentPins = pinData.locations;

        renderEditorPins();

    } catch (e) {
        console.error(e);
        alert("Map Load Error");
    }
}

function renderEditorPins() {
    const container = document.getElementById('editorPinsContainer');
    container.innerHTML = '';

    currentPins.forEach(pin => {
        const pinEl = document.createElement('div');
        pinEl.className = 'map-pin';
        pinEl.style.position = 'absolute';
        pinEl.style.left = `${pin.x}%`;
        pinEl.style.top = `${pin.y}%`;
        pinEl.style.width = '0';
        pinEl.style.height = '0';
        pinEl.style.overflow = 'visible';
        pinEl.style.zIndex = '100';
        pinEl.style.cursor = 'pointer';

        const icon = document.createElement('i');
        icon.className = 'fas fa-map-marker-alt fa-2x text-danger';
        icon.style.filter = 'drop-shadow(2px 2px 2px rgba(0,0,0,0.5))';
        icon.style.position = 'absolute';
        icon.style.left = '0';
        icon.style.top = '0';
        icon.style.transform = 'translate(-50%, -100%)';
        icon.style.display = 'block';

        pinEl.appendChild(icon);

        if (showPinNames && pin.name) {
            const label = document.createElement('span');
            label.className = 'badge bg-light text-dark border ms-1';
            label.style.position = 'absolute';
            label.style.left = '10px';
            label.style.top = '-30px';
            label.style.whiteSpace = 'nowrap';
            label.textContent = pin.name;
            pinEl.appendChild(label);
        }

        pinEl.onclick = (e) => {
            e.stopPropagation();
            openPinEdit(pin);
        };

        container.appendChild(pinEl);
    });
}

function togglePinNames() {
    const toggle = document.getElementById('showPinNamesToggle');
    showPinNames = toggle.checked;
    renderEditorPins();
}

function onMapClick(event) {
    if (!currentMap) return;
    const img = event.target;
    if (img.id !== 'editorMapImage') return;

    const rect = img.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;

    const xPercent = (x / rect.width) * 100;
    const yPercent = (y / rect.height) * 100;

    openPinCreate({
        x: xPercent.toFixed(2),
        y: yPercent.toFixed(2)
    });
}

function openPinCreate(coords) {
    document.getElementById('currentPinId').value = '';
    document.getElementById('displayPinX').value = coords.x;
    document.getElementById('displayPinY').value = coords.y;
    document.getElementById('currentPinX').value = coords.x;
    document.getElementById('currentPinY').value = coords.y;
    document.getElementById('pinNameInput').value = '';
    document.getElementById('pinProblemsList').innerHTML = '<div class="text-muted small">保存後に問題を追加できます</div>';

    const modal = new bootstrap.Modal(document.getElementById('pinEditModal'));
    modal.show();
}

async function openPinEdit(pin) {
    document.getElementById('currentPinId').value = pin.id;
    document.getElementById('displayPinX').value = pin.x;
    document.getElementById('displayPinY').value = pin.y;
    document.getElementById('currentPinX').value = pin.x;
    document.getElementById('currentPinY').value = pin.y;
    document.getElementById('pinNameInput').value = pin.name;

    await loadPinProblems(pin.id);

    const modal = new bootstrap.Modal(document.getElementById('pinEditModal'));
    modal.show();
}

async function savePinData() {
    const pinId = document.getElementById('currentPinId').value;
    const mapId = document.getElementById('currentMapId').value;
    const name = document.getElementById('pinNameInput').value;
    const x = document.getElementById('currentPinX').value;
    const y = document.getElementById('currentPinY').value;

    const url = pinId ? `${API_BASE}/location/${pinId}/update` : `${API_BASE}/location/add`;
    const payload = { map_id: mapId, name: name, x: x, y: y };

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify(payload)
        });

        const res = await response.json();

        if (res.status === 'success') {
            loadPins(currentMap.id); // Reload
            if (!pinId) {
                // Was new
                document.getElementById('currentPinId').value = res.location.id;
                loadPinProblems(res.location.id);
                // Also update the pinId field so subsequent adds associate correctly immediately
                document.getElementById('currentPinId').value = res.location.id;
                alert('地点を保存しました。問題を追加できます。');
            } else {
                const modal = bootstrap.Modal.getInstance(document.getElementById('pinEditModal'));
                modal.hide();
            }
        } else {
            alert('Error: ' + res.message);
        }
    } catch (error) {
        alert('通信エラー: ' + error.message);
    }
}

async function loadPins(mapId) {
    const response = await fetch(`${API_BASE}/map/${mapId}/locations`);
    const data = await response.json();
    currentPins = data.locations;
    renderEditorPins();
}

async function deletePin() {
    const pinId = document.getElementById('currentPinId').value;
    if (!pinId) return;

    if (!confirm('この地点を削除しますか？\\n関連する問題も全て削除されます。')) return;

    try {
        const response = await fetch(`${API_BASE}/location/${pinId}/delete`, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCsrfToken() }
        });
        const res = await response.json();
        if (res.status === 'success') {
            const modal = bootstrap.Modal.getInstance(document.getElementById('pinEditModal'));
            modal.hide();
            loadPins(currentMap.id);
        } else {
            alert('Error: ' + res.message);
        }
    } catch (error) { alert('Error: ' + error.message); }
}

async function addProblemToPin() {
    const pinId = document.getElementById('currentPinId').value;
    if (!pinId) {
        alert('先に地点を保存してください');
        return;
    }

    const question = document.getElementById('newProblemText').value;
    const explanation = document.getElementById('newProblemExplanation').value;
    const difficulty = document.getElementById('newProblemDifficulty').value;

    if (!question) {
        alert('問題文を入力してください');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/problem/add`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({
                location_id: pinId,
                question: question,
                explanation: explanation,
                difficulty: difficulty
            })
        });
        const res = await response.json();
        if (res.status === 'success') {
            document.getElementById('newProblemText').value = '';
            document.getElementById('newProblemExplanation').value = '';
            document.getElementById('newProblemDifficulty').value = '2'; // Reset to standard
            loadPinProblems(pinId);
        } else {
            alert('Error: ' + res.message);
        }
    } catch (e) { alert('Error: ' + e.message); }
}

async function loadPinProblems(pinId) {
    const list = document.getElementById('pinProblemsList');
    list.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';

    try {
        const response = await fetch(`${API_BASE}/location/${pinId}/problems`);
        const data = await response.json();

        list.innerHTML = '';
        if (data.problems.length === 0) {
            list.innerHTML = '<div class="text-muted small">登録された問題はありません</div>';
            return;
        }

        data.problems.forEach(prob => {
            const div = document.createElement('div');
            div.className = 'border rounded p-2 mb-1 bg-white';

            // Difficulty Badge
            let diffBadge = '';
            if (prob.difficulty === 1) diffBadge = '<span class="badge bg-success me-1">易</span>';
            else if (prob.difficulty === 3) diffBadge = '<span class="badge bg-danger me-1">難</span>';
            else diffBadge = '<span class="badge bg-primary me-1">標</span>';

            div.innerHTML = `
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        ${diffBadge}
                        <strong>${prob.question}</strong>
                    </div>
                    <button class="btn btn-xs btn-outline-danger" onclick="deleteProblem(${prob.id})"><i class="fas fa-trash"></i></button>
                </div>
                ${prob.explanation ? `<div class="small text-muted mt-1 ms-1">解説: ${prob.explanation}</div>` : ''}
            `;
            list.appendChild(div);
        });

    } catch (error) {
        list.innerHTML = '<div class="text-danger">読み込み失敗</div>';
    }
}

async function deleteProblem(problemId) {
    if (!confirm('この問題を削除しますか？')) return;
    try {
        const response = await fetch(`${API_BASE}/problem/${problemId}/delete`, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCsrfToken() }
        });
        const res = await response.json();
        if (res.status === 'success') {
            const pinId = document.getElementById('currentPinId').value;
            loadPinProblems(pinId);
        }
    } catch (e) { alert('Error'); }
}

async function deleteCurrentMap() {
    if (!currentMap) return;
    if (!confirm(`地図「${currentMap.name}」を削除しますか？\n登録された地点と問題も全て削除されます。`)) return;

    try {
        const response = await fetch(`${API_BASE}/map/${currentMap.id}/delete`, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCsrfToken() }
        });
        const res = await response.json();
        if (res.status === 'success') {
            currentMap = null;
            document.getElementById('mapEditorContainer').style.display = 'none';
            document.getElementById('mapEditorPlaceholder').style.display = 'block';
            loadSortableMapList();
        } else {
            alert('Error: ' + res.message);
        }
    } catch (e) { alert('Error: ' + e.message); }
}

function getCsrfToken() {
    const input = document.querySelector('input[name="csrf_token"]');
    if (input) return input.value;
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');
    return '';
}
