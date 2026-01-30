// Map Quiz Admin Logic

// Global State
let currentMap = null;
let currentPins = [];
let showPinNames = true;
const API_BASE = '/admin/api/map_quiz';

// Zoom/Pan State
let editorScale = 1;
let editorPanX = 0;
let editorPanY = 0;
let isDependingPan = false;
let startPanX = 0;
let startPanY = 0;

// Drag State
let isDraggingPin = false;
let draggedPinId = null;
let dragStartX = 0;
let dragStartY = 0; // Mouse screen coords
let initialPinX = 0; // %
let initialPinY = 0; // %

// Edit Problem State
let editingProblemId = null;

// Drawing State
let currentDrawMode = 'point'; // 'point' or 'circle'
let isDrawingCircle = false;
let drawCenterX = 0;
let drawCenterY = 0;
let drawRadius = 0;
let tempCircleEl = null;

let selectedPinId = null;
// Resize/Rotate State
let isRotating = false;
let isResizing = false;
let resizeAxis = null; // 'x', 'y'
let dragStartAngle = 0;

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

    // Init Zoom/Pan Events
    const container = document.getElementById('adminMapContainer');
    if (container) {
        container.addEventListener('wheel', onEditorWheel, { passive: false });

        // Map Image Pan (Middle click or Space+Drag could be added, but standard is Drag Pins)
        // For now, let's keep it simple: Drag map image to pan? 
        // Or drag background to pan. 
        // User request focuses on "Drag adjustment of PIN position", so panning map is secondary but helpful if zoomed in.
        // Let's allow panning by dragging empty space on map image
        const imgWrapper = document.getElementById('mapImageWrapper');
        imgWrapper.addEventListener('mousedown', onMapMouseDown);
        window.addEventListener('mousemove', onGlobalMouseMove);
        window.addEventListener('mouseup', onGlobalMouseUp);

        // Click on map image is already handled by onclick="onMapClick" BUT
        // we need to distinguish between click and drag
        const img = document.getElementById('editorMapImage');
        if (img) img.addEventListener('click', onMapClick);
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

async function editMapName(mapId, currentName) {
    const newName = prompt("新しい地図名を入力してください:", currentName);
    if (newName && newName !== currentName) {
        try {
            const response = await fetch(`${API_BASE}/map/edit`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                body: JSON.stringify({ id: mapId, name: newName })
            });
            const res = await response.json();
            if (res.status === 'success') {
                // Update UI immediately
                if (currentMap && currentMap.id === mapId) {
                    currentMap.name = newName;
                    // Re-render header
                    document.getElementById('currentMapName').innerHTML =
                        `${newName} <i class="fas fa-edit ms-2 text-muted pointer" onclick="editMapName(${mapId}, '${newName}')" style="cursor: pointer; font-size: 0.8em;" title="地図名を編集"></i>`;
                }

                loadSortableMapList(); // Reload list to reflect changes
            } else {
                alert('Error: ' + res.message);
            }
        } catch (e) {
            alert('Error: ' + e.message);
        }
    }
}


// --- Map Interaction Logic ---

// Deprecated loader (kept for compatibility in case of shared calls)
async function loadMapList() {
    loadSortableMapList();
}

async function selectMap(mapId) {
    // Clean highlight
    document.querySelectorAll('.list-group-item').forEach(el => el.classList.remove('active'));

    try {
        const listRes = await fetch(`${API_BASE}/maps`);
        if (!listRes.ok) throw new Error(`Fetch maps failed: ${listRes.status}`);
        const listData = await listRes.json();
        currentMap = listData.maps.find(m => m.id === mapId);

        if (!currentMap) return alert('Map not found');

        // UI Updates
        document.getElementById('mapEditorPlaceholder').style.display = 'none';
        document.getElementById('mapEditorContainer').style.display = 'block';
        document.getElementById('currentMapName').innerHTML =
            `${currentMap.name} <i class="fas fa-edit ms-2 text-muted pointer" onclick="editMapName(${currentMap.id}, '${currentMap.name}')" style="cursor: pointer; font-size: 0.8em;" title="地図名を編集"></i>`;
        document.getElementById('currentMapId').value = mapId;

        const img = document.getElementById('editorMapImage');
        img.src = `/serve_map_image/${currentMap.filename}`;

        // Reset Zoom
        resetEditorZoom();

        // Load Pins
        const pinRes = await fetch(`${API_BASE}/map/${mapId}/locations`);
        if (!pinRes.ok) throw new Error(`HTTP ${pinRes.status}`);
        const pinData = await pinRes.json();

        if (pinData.status === 'error') throw new Error(pinData.message);

        currentPins = pinData.locations || [];
        renderEditorPins();

    } catch (e) {
        console.error(e);
        alert("Map Load Error: " + e.message);
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
        pinEl.style.cursor = 'grab'; // Indicate draggable

        // Store ID for retrieval
        pinEl.dataset.pinId = pin.id;

        if (pin.shape_type !== 'circle' && pin.shape_type !== 'ellipse') {
            const icon = document.createElement('i');
            icon.className = 'fas fa-map-marker-alt fa-2x text-danger';
            icon.style.filter = 'drop-shadow(2px 2px 2px rgba(0,0,0,0.5))';
            icon.style.position = 'absolute';
            icon.style.left = '0';
            icon.style.top = '0';
            icon.style.transformOrigin = '50% 100%';
            icon.style.transform = 'translate(-50%, -100%)';
            icon.style.display = 'block';
            icon.style.pointerEvents = 'auto';
            pinEl.appendChild(icon);
        } else {
            // For circle/ellipse, add a tiny center dot for dragging
            const centerDot = document.createElement('div');
            centerDot.style.width = '10px';
            centerDot.style.height = '10px';
            centerDot.style.borderRadius = '50%';
            centerDot.style.backgroundColor = 'rgba(220, 53, 69, 0.8)';
            centerDot.style.position = 'absolute';
            centerDot.style.left = '50%';
            centerDot.style.top = '50%';
            centerDot.style.transform = 'translate(-50%, -50%)';
            centerDot.style.pointerEvents = 'auto'; // Drag handle
            pinEl.appendChild(centerDot);
        }

        if (showPinNames && pin.name) {
            const label = document.createElement('span');
            label.className = 'badge bg-light text-dark border ms-1';
            label.style.position = 'absolute';
            label.style.left = '10px';
            label.style.top = '-30px';
            label.style.whiteSpace = 'nowrap';
            label.style.zIndex = '100';
            label.textContent = pin.name;
            pinEl.appendChild(label);
        }

        // Render Circle/Ellipse Region if applicable
        if (pin.shape_type === 'circle' || pin.shape_type === 'ellipse' || (pin.shape_type === 'point' && pin.radius > 0)) {
            let rx = pin.radius_x || pin.radius || 0;
            let ry = pin.radius_y || pin.radius || 0;
            let rot = pin.rotation || 0;

            if (rx > 0 || ry > 0) {
                if (rx === 0) rx = ry;
                if (ry === 0) ry = rx;

                const ellipse = document.createElement('div');
                ellipse.className = 'pin-region-shape';
                ellipse.style.position = 'absolute';
                ellipse.style.left = '50%';
                ellipse.style.top = '50%';
                ellipse.style.borderRadius = '50%';
                ellipse.style.border = '2px solid rgba(13, 110, 253, 0.7)';
                ellipse.style.backgroundColor = 'rgba(13, 110, 253, 0.2)';
                ellipse.style.pointerEvents = 'none';

                const img = document.getElementById('editorMapImage');
                if (img) {
                    const w = img.clientWidth;
                    const pxRx = (rx / 100) * w;
                    const pxRy = (ry / 100) * w;
                    ellipse.style.width = (pxRx * 2) + 'px';
                    ellipse.style.height = (pxRy * 2) + 'px';
                    ellipse.style.transform = `translate(-50%, -50%) rotate(${rot}deg)`;
                }

                pinEl.appendChild(ellipse);

                if (selectedPinId === pin.id) {
                    ellipse.style.border = '2px dashed #ffc107';
                    ellipse.style.boxShadow = '0 0 5px rgba(255, 193, 7, 0.8)';

                    const rotHandle = document.createElement('div');
                    rotHandle.className = 'editor-handle rotate-handle';
                    rotHandle.style.position = 'absolute';
                    rotHandle.style.left = '50%';
                    rotHandle.style.top = '-20px';
                    rotHandle.style.width = '2px';
                    rotHandle.style.height = '20px';
                    rotHandle.style.backgroundColor = '#ffc107';
                    rotHandle.style.cursor = 'grab';
                    rotHandle.style.pointerEvents = 'auto';
                    const rotKnob = document.createElement('div');
                    rotKnob.style.position = 'absolute';
                    rotKnob.style.top = '-5px';
                    rotKnob.style.left = '-4px';
                    rotKnob.style.width = '10px';
                    rotKnob.style.height = '10px';
                    rotKnob.style.borderRadius = '50%';
                    rotKnob.style.backgroundColor = '#ffc107';
                    rotHandle.appendChild(rotKnob);
                    rotHandle.onmousedown = (e) => startRotateDrag(e, pin);
                    ellipse.appendChild(rotHandle);

                    const resR = document.createElement('div');
                    resR.className = 'editor-handle resize-r';
                    resR.style.position = 'absolute';
                    resR.style.right = '-6px';
                    resR.style.top = '50%';
                    resR.style.marginTop = '-6px';
                    resR.style.width = '12px';
                    resR.style.height = '12px';
                    resR.style.backgroundColor = '#0d6efd';
                    resR.style.border = '1px solid white';
                    resR.style.cursor = 'ew-resize';
                    resR.style.pointerEvents = 'auto';
                    resR.onmousedown = (e) => startResizeDrag(e, pin, 'x');
                    ellipse.appendChild(resR);

                    const resB = document.createElement('div');
                    resB.className = 'editor-handle resize-b';
                    resB.style.position = 'absolute';
                    resB.style.bottom = '-6px';
                    resB.style.left = '50%';
                    resB.style.marginLeft = '-6px';
                    resB.style.width = '12px';
                    resB.style.height = '12px';
                    resB.style.backgroundColor = '#0d6efd';
                    resB.style.border = '1px solid white';
                    resB.style.cursor = 'ns-resize';
                    resB.style.pointerEvents = 'auto';
                    resB.onmousedown = (e) => startResizeDrag(e, pin, 'y');
                    ellipse.appendChild(resB);
                }
            }
        }

        // --- Drag Events ---
        pinEl.onmousedown = (e) => {
            e.stopPropagation(); // Don't trigger map pan or new pin
            startPinDrag(e, pin.id, pin.x, pin.y);
        };

        // --- Click (Edit) ---
        pinEl.onclick = (e) => {
            e.stopPropagation();
        };

        container.appendChild(pinEl);
    });
}

function startPinDrag(e, pinId, startXPercent, startYPercent) {
    if (e.button !== 0) return; // Left click only
    isDraggingPin = true;
    draggedPinId = pinId;
    dragStartX = e.clientX;
    dragStartY = e.clientY;
    initialPinX = parseFloat(startXPercent);
    initialPinY = parseFloat(startYPercent);
}

function startRotateDrag(e, pin) {
    e.stopPropagation(); // Don't drag pin
    e.preventDefault();
    isRotating = true;
    selectedPinId = pin.id;
    dragStartAngle = pin.rotation || 0;
}

function startResizeDrag(e, pin, axis) {
    e.stopPropagation();
    e.preventDefault();
    isResizing = true;
    resizeAxis = axis;
    selectedPinId = pin.id;
}

function onMapMouseDown(e) {
    if (e.button !== 0) return;
    // Assume start panning if not on pin
    if (e.target.closest('.map-pin')) return;

    // Distinguish click from pan:
    // We'll record start Pos. If moved > threshold, it's a pan.
    // BUT if in CIRCLE DRAW mode, start drawing circle.
    if (currentDrawMode === 'circle') {
        const img = document.getElementById('editorMapImage');
        const rect = img.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        drawCenterX = (x / rect.width) * 100;
        drawCenterY = (y / rect.height) * 100;

        // Start dragging
        isDrawingCircle = true;
        dragStartX = e.clientX;
        dragStartY = e.clientY;

        // Create Temp Visual
        createTempCircle(x, y, rect.width);

        return; // Consumption
    }

    isDependingPan = true;
    startPanX = e.clientX - editorPanX;
    startPanY = e.clientY - editorPanY;

    // Also record raw click for "Click vs Drag" check in onMapClick
    dragStartX = e.clientX;
    dragStartY = e.clientY;
}

function onGlobalMouseMove(e) {
    if (isDraggingPin && draggedPinId) {
        // Dragging Pin
        e.preventDefault();

        const img = document.getElementById('editorMapImage');
        const rect = img.getBoundingClientRect();

        // Calculate delta in pixels (screen)
        const deltaX = e.clientX - dragStartX;
        const deltaY = e.clientY - dragStartY;

        // Convert screen delta to map percentage delta
        // rect.width is the CURRENT rendered width (including zoom)
        const percentDeltaX = (deltaX / rect.width) * 100;
        const percentDeltaY = (deltaY / rect.height) * 100;

        let newX = initialPinX + percentDeltaX;
        let newY = initialPinY + percentDeltaY;

        // Clamp 0-100
        newX = Math.max(0, Math.min(100, newX));
        newY = Math.max(0, Math.min(100, newY));

        // Update local state and visual
        const pin = currentPins.find(p => p.id === draggedPinId);
        if (pin) {
            pin.x = newX;
            pin.y = newY;
            updatePinPositionVisual(draggedPinId, newX, newY);
        }
    } else if (isRotating && selectedPinId) {
        e.preventDefault();
        const pin = currentPins.find(p => p.id === selectedPinId);
        if (pin) {
            const pinEl = document.querySelector(`.map-pin[data-pin-id="${pin.id}"]`);
            if (pinEl) {
                const pinRect = pinEl.getBoundingClientRect();
                const centerX = pinRect.left + pinRect.width / 2;
                const centerY = pinRect.top + pinRect.height / 2;
                const dx = e.clientX - centerX;
                const dy = e.clientY - centerY;
                let angle = Math.atan2(dy, dx) * (180 / Math.PI);
                let rot = angle + 90;
                pin.rotation = rot;
                renderEditorPins();
            }
        }
    } else if (isResizing && selectedPinId) {
        e.preventDefault();
        const pin = currentPins.find(p => p.id === selectedPinId);
        if (pin) {
            const img = document.getElementById('editorMapImage');
            const rect = img.getBoundingClientRect();
            const pinEl = document.querySelector(`.map-pin[data-pin-id="${pin.id}"]`);
            if (pinEl) {
                const pinRect = pinEl.getBoundingClientRect();
                const centerX = pinRect.left + pinRect.width / 2;
                const centerY = pinRect.top + pinRect.height / 2;
                const dist = Math.sqrt(Math.pow(e.clientX - centerX, 2) + Math.pow(e.clientY - centerY, 2));
                const radiusP = (dist / rect.width) * 100;
                if (resizeAxis === 'x') pin.radius_x = radiusP;
                if (resizeAxis === 'y') pin.radius_y = radiusP;
                renderEditorPins();
            }
        }
    } else if (isDrawingCircle) {
        e.preventDefault();
        const img = document.getElementById('editorMapImage');
        const rect = img.getBoundingClientRect();

        const deltaX = e.clientX - dragStartX;
        const deltaY = e.clientY - dragStartY;
        // Radius = distance in pixels / width * 100
        const distPx = Math.sqrt(deltaX * deltaX + deltaY * deltaY);
        const radiusPercent = (distPx / rect.width) * 100;

        drawRadius = radiusPercent;
        updateTempCircle(distPx);

    } else if (isDependingPan) {
        // Panning map
        e.preventDefault();
        editorPanX = e.clientX - startPanX;
        editorPanY = e.clientY - startPanY;
        setEditorTransform();
    }
}

function onGlobalMouseUp(e) {
    if (isDraggingPin) {
        isDraggingPin = false;
        const delta = Math.sqrt(Math.pow(e.clientX - dragStartX, 2) + Math.pow(e.clientY - dragStartY, 2));
        if (delta < 5) {
            // Clicked Pin -> Select it AND open edit modal
            const pin = currentPins.find(p => p.id === draggedPinId);
            if (pin) {
                selectedPinId = pin.id;
                renderEditorPins();
                openPinEdit(pin); // Added call to open edit modal
            }
        }
        else {
            // Dragged -> Save
            const pin = currentPins.find(p => p.id === draggedPinId);
            if (pin) savePinCoordinates(pin);
        }
        draggedPinId = null;
    }

    if (isRotating || isResizing) {
        // Finished transforming
        isRotating = false;
        isResizing = false;
        if (selectedPinId) {
            const pin = currentPins.find(p => p.id === selectedPinId);
            if (pin) savePinCoordinates(pin);
        }
    }

    if (isDrawingCircle) {
        isDrawingCircle = false;
        if (tempCircleEl) {
            tempCircleEl.remove();
            tempCircleEl = null;
        }
        if (drawRadius < 0.5) { }
        openPinCreate({
            x: drawCenterX.toFixed(2),
            y: drawCenterY.toFixed(2),
            radius: drawRadius.toFixed(2),
            radius_x: drawRadius.toFixed(2),
            radius_y: drawRadius.toFixed(2),
            shape: 'circle'
        });
        return;
    }

    if (isDependingPan) {
        isDependingPan = false;
    }
}

function updatePinPositionVisual(id, x, y) {
    const el = document.querySelector(`.map-pin[data-pin-id="${id}"]`);
    if (el) {
        el.style.left = `${x}%`;
        el.style.top = `${y}%`;
    }
}

async function savePinCoordinates(pin) {
    // Only update coords
    try {
        const payload = {
            map_id: currentMap.id,
            name: pin.name,
            x: pin.x,
            y: pin.y,
            shape_type: pin.shape_type,
            radius: pin.radius,
            radius_x: pin.radius_x,
            radius_y: pin.radius_y,
            rotation: pin.rotation
        };
        const response = await fetch(`${API_BASE}/location/${pin.id}/update`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify(payload)
        });
        // Silent update
    } catch (e) {
        console.error("Auto-save failed", e);
    }
}


// --- Zoom & Pan Logic ---

function onEditorWheel(e) {
    e.preventDefault();
    const wrapper = document.getElementById('mapImageWrapper');
    const rect = wrapper.getBoundingClientRect();

    // Mouse relative to wrapper (taking into account current transform)
    // Actually, simple zoom centered on mouse:
    const offsetX = e.clientX - rect.left;
    const offsetY = e.clientY - rect.top;

    const delta = -Math.sign(e.deltaY) * 0.1;
    const newScale = Math.max(0.5, Math.min(5, editorScale + delta));

    // Calculate pan adjustment to zoom towards mouse
    // This is complex with CSS transform.
    // Simplified: Just center zoom or standard zoom.

    editorScale = newScale;
    setEditorTransform();
}

function zoomEditorMap(targetScale) {
    if (targetScale === 1.2) editorScale *= 1.2;
    else if (targetScale === 0.8) editorScale /= 1.2;
    // Limits
    editorScale = Math.max(0.2, Math.min(10, editorScale));
    setEditorTransform();
}

function resetEditorZoom() {
    editorScale = 1;
    editorPanX = 0;
    editorPanY = 0;
    setEditorTransform();
}

function setEditorTransform() {
    const wrapper = document.getElementById('mapImageWrapper');
    if (wrapper) {
        wrapper.style.transform = `translate(${editorPanX}px, ${editorPanY}px) scale(${editorScale})`;
        // Counter-scale pins to keep them same size visually?
        // In Play mode we do it. In editor it's nice too.
        const invScale = 1 / editorScale;
        document.querySelectorAll('.map-pin i').forEach(icon => {
            icon.style.transform = `translate(-50%, -100%) scale(${invScale})`;
            // Note: original transform was translate(-50%, -100%)
        });
    }
}


function togglePinNames() {
    const toggle = document.getElementById('showPinNamesToggle');
    showPinNames = toggle.checked;
    renderEditorPins();
}

function onMapClick(event) {
    if (!currentMap) return;

    // Check if we just finished a drag/pan
    // The browser might fire click after mouseup.
    // We used dragStartX/Y in mousedown.
    const dist = Math.sqrt(Math.pow(event.clientX - dragStartX, 2) + Math.pow(event.clientY - dragStartY, 2));
    if (dist > 5) return; // Allow small jitter, but ignore drags

    const img = document.getElementById('editorMapImage');
    const rect = img.getBoundingClientRect();
    const x = event.clientX - rect.left; // x in screen pixels within the image box
    const y = event.clientY - rect.top;

    // x, y are scaled.
    // real width = rect.width.
    const xPercent = (x / rect.width) * 100;
    const yPercent = (y / rect.height) * 100;

    openPinCreate({
        x: xPercent.toFixed(2),
        y: yPercent.toFixed(2)
    });
}

// Crop State
let cropper = null;

async function toggleCropMode() {
    const img = document.getElementById('editorMapImage');
    const startBtn = document.getElementById('startCropBtn');
    const controls = document.getElementById('cropControls');

    if (!cropper) {
        // Init Crop
        // CRITICAL: Reset zoom/pan transform BEFORE init Cropper
        // Otherwise cropper coordinates will be skewed by the CSS transform
        resetEditorZoom();

        startBtn.style.display = 'none';
        controls.style.display = 'inline-block';

        // Disable Zoom/Pan/Drag interactions
        // (Cropper.js takes over interactions)

        cropper = new Cropper(img, {
            viewMode: 1, // Restrict crop box to canvas
            zoomable: true,
            movable: true,
            rotatable: false,
            scalable: false,
            ready() {
                // Adjust cropper container z-index to be above pins?
                // Actually pins might obscure crop box. 
                // We should probably hide pins or make them pass-through?
                // Let's hide pins during crop for clarity.
                document.getElementById('editorPinsContainer').style.display = 'none';
            }
        });
    }
}

async function cancelCrop() {
    if (cropper) {
        cropper.destroy();
        cropper = null;
    }
    document.getElementById('startCropBtn').style.display = 'inline-block';
    document.getElementById('cropControls').style.display = 'none';
    document.getElementById('editorPinsContainer').style.display = 'block';
    resetEditorZoom(); // Restore normal zoom state
}

async function saveCrop() {
    if (!cropper) return;
    if (!confirm('画像をトリミングしますか？\\n既存のピンの位置は再計算されますが、範囲外のピンは削除されます。')) return;

    // Get Data
    // We need data relative to the *original* image natural size.
    // cropper.getData(true) returns rounded values
    const data = cropper.getData(true);

    // { x, y, width, height, rotate, scaleX, scaleY }
    const cropData = {
        x: data.x,
        y: data.y,
        width: data.width,
        height: data.height
    };

    try {
        const response = await fetch(`${API_BASE}/map/${currentMap.id}/crop`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify(cropData)
        });

        const res = await response.json();
        if (res.status === 'success') {
            alert('トリミング完了しました');
            cancelCrop();
            // Reload map to get new image and pin positions
            // Force image reload by appending query param
            const img = document.getElementById('editorMapImage');
            const newSrc = `/serve_map_image/${res.filename}?t=${new Date().getTime()}`;
            img.src = newSrc;

            // Wait for load? or just reload pins
            // Better to re-select map to ensure full refresh of state
            await loadPins(currentMap.id);
        } else {
            alert('Error: ' + res.message);
        }
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

function openPinCreate(coords) {
    document.getElementById('currentPinId').value = '';
    document.getElementById('displayPinX').value = coords.x;
    document.getElementById('displayPinY').value = coords.y;
    document.getElementById('currentPinX').value = coords.x;
    document.getElementById('currentPinY').value = coords.y;
    document.getElementById('pinNameInput').value = '';

    // Set Shape Info
    if (coords.shape === 'circle') {
        document.getElementById('shapeTypeCircle').checked = true;
        document.getElementById('pinRadiusXInput').value = coords.radius_x || coords.radius || 5.0;
        document.getElementById('pinRadiusYInput').value = coords.radius_y || coords.radius || 5.0;
        document.getElementById('pinRotationInput').value = 0;
    } else {
        document.getElementById('shapeTypePoint').checked = true;
        document.getElementById('pinRadiusXInput').value = 0;
        document.getElementById('pinRadiusYInput').value = 0;
        document.getElementById('pinRotationInput').value = 0;
    }
    toggleShapeInputs();

    document.getElementById('pinProblemsList').innerHTML = '<div class="text-muted small">保存後に問題を追加できます</div>';

    resetProblemForm();
    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('pinEditModal'));
    modal.show();
}

async function openPinEdit(pin) {
    document.getElementById('currentPinId').value = pin.id;
    document.getElementById('displayPinX').value = pin.x;
    document.getElementById('displayPinY').value = pin.y;
    document.getElementById('currentPinX').value = pin.x;
    document.getElementById('currentPinY').value = pin.y;
    document.getElementById('pinNameInput').value = pin.name;

    // Set Shape Info
    if (pin.shape_type === 'circle' || pin.shape_type === 'ellipse') {
        document.getElementById('shapeTypeCircle').checked = true;
        let rx = pin.radius_x || pin.radius || 5.0;
        let ry = pin.radius_y || pin.radius || 5.0;
        document.getElementById('pinRadiusXInput').value = rx;
        document.getElementById('pinRadiusYInput').value = ry;
        document.getElementById('pinRotationInput').value = pin.rotation || 0;
    } else {
        document.getElementById('shapeTypePoint').checked = true;
        document.getElementById('pinRadiusXInput').value = 0;
        document.getElementById('pinRadiusYInput').value = 0;
        document.getElementById('pinRotationInput').value = 0;
    }
    toggleShapeInputs();

    resetProblemForm();
    await loadPinProblems(pin.id);

    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('pinEditModal'));
    modal.show();
}

async function savePinData() {
    await _doSavePin();
}

async function _doSavePin() {
    const pinId = document.getElementById('currentPinId').value;
    const mapId = document.getElementById('currentMapId').value;
    const name = document.getElementById('pinNameInput').value;
    const x = document.getElementById('currentPinX').value;
    const y = document.getElementById('currentPinY').value;

    // Shape Data
    const isCircle = document.getElementById('shapeTypeCircle').checked;
    const shapeType = isCircle ? 'ellipse' : 'point'; // Default to ellipse if circle mode selected, or detect equal radii?
    // Actually backend supports 'circle' or 'ellipse'. 
    // Let's use 'ellipse' if we have independent X/Y. Or 'circle' if equal.
    // For simplicity, let's just send 'ellipse' if isCircle check matches.
    // Or check if x != y. 

    let radiusX = 0;
    let radiusY = 0;
    let rotation = 0;

    if (isCircle) {
        radiusX = parseFloat(document.getElementById('pinRadiusXInput').value) || 0;
        radiusY = parseFloat(document.getElementById('pinRadiusYInput').value) || 0;
        rotation = parseInt(document.getElementById('pinRotationInput').value) || 0;

        if (radiusX <= 0 || radiusY <= 0) {
            alert('半径は0より大きい値を設定してください');
            return null;
        }
    }

    if (!name) {
        alert('地点名を入力してください');
        return null;
    }

    const url = pinId ? `${API_BASE}/location/${pinId}/update` : `${API_BASE}/location/add`;
    const payload = {
        map_id: mapId,
        name: name,
        x: x,
        y: y,
        shape_type: isCircle ? ((radiusX === radiusY) ? 'circle' : 'ellipse') : 'point',
        radius: (radiusX === radiusY) ? radiusX : 0, // Legacy support
        radius_x: radiusX,
        radius_y: radiusY,
        rotation: rotation
    };

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify(payload)
        });

        const res = await response.json();

        if (res.status === 'success') {
            await loadPins(currentMap.id);
            if (!pinId) {
                document.getElementById('currentPinId').value = res.location.id;
                alert('地点を保存しました');
            } else {
                // If called explicitly via Save button, close modal?
                // The original code closed modal on update.
                // But since we split this for reuse, we might need a flag or caller handling.
                // For now, let's just return ID and let caller decide, OR keep side effect here if button calls this.
                // But _doSavePin is used by addProblem too. cancel modal close there.
            }
            return res.location.id;
        } else {
            alert('Error: ' + res.message);
            return null;
        }
    } catch (error) {
        alert('通信エラー: ' + error.message);
        return null;
    }
}

async function loadPins(mapId) {
    const response = await fetch(`${API_BASE}/map/${mapId}/locations`);
    const data = await response.json();
    currentPins = data.locations;
    renderEditorPins();

    // Re-apply current zoom transform to new pins
    setEditorTransform();
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


// --- Image Replace & Health Logic ---

function triggerReplaceImage() {
    if (!currentMap) return;
    document.getElementById('replaceImageInput').click();
}

async function uploadReplaceImage(input) {
    if (!input.files || !input.files[0]) return;
    const file = input.files[0];

    if (!confirm(`「${currentMap.name}」の画像を置換しますか？\nピンや問題データは維持されますが、画像サイズが変わるとピンの位置がずれる可能性があります。`)) {
        input.value = '';
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(`${API_BASE}/map/${currentMap.id}/replace_image`, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCsrfToken() },
            body: formData
        });

        const res = await response.json();
        if (res.status === 'success') {
            alert('画像を置換しました');
            // Reload map image
            const img = document.getElementById('editorMapImage');
            img.src = `/serve_map_image/${res.filename}?t=${new Date().getTime()}`;
            // Update currentMap object filename if needed
            currentMap.filename = res.filename;
        } else {
            alert('Error: ' + res.message);
        }
    } catch (e) {
        alert('Error: ' + e.message);
    } finally {
        input.value = '';
    }
}

async function checkMapHealth() {
    try {
        const response = await fetch(`${API_BASE}/health_check`);
        const res = await response.json();

        if (res.status === 'success') {
            const issues = res.issues;
            if (issues.length === 0) {
                alert('すべての地図データは正常です。\n（DB内に画像データが存在します）');
            } else {
                let msg = `【重要】${issues.length}件の地図に問題が見つかりました。\nこれらは画像ファイルが消失している可能性があります。\n\n`;
                issues.forEach(i => {
                    msg += `・ID:${i.id} ${i.name} (${i.status})\n`;
                });
                msg += '\n「画像置換」機能を使って復旧してください。';
                alert(msg);
            }
        } else {
            alert('Error: ' + res.message);
        }
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function addProblemToPin() {
    let pinId = document.getElementById('currentPinId').value;

    // Auto-save pin if new
    if (!pinId) {
        const savedId = await _doSavePin();
        if (!savedId) return; // Save failed
        pinId = savedId;
        // The _doSavePin updates currentPinId value
    }

    const question = document.getElementById('newProblemText').value;
    const explanation = document.getElementById('newProblemExplanation').value;
    const difficulty = document.getElementById('newProblemDifficulty').value;

    if (!question) {
        alert('問題文を入力してください');
        return;
    }

    const url = editingProblemId ? `${API_BASE}/problem/${editingProblemId}/update` : `${API_BASE}/problem/add`;
    const payload = {
        location_id: pinId,
        question: question,
        explanation: explanation,
        difficulty: difficulty
    };

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify(payload)
        });
        const res = await response.json();
        if (res.status === 'success') {
            resetProblemForm();
            loadPinProblems(pinId);
        } else {
            alert('Error: ' + res.message);
        }
    } catch (e) { alert('Error: ' + e.message); }
}

function editProblem(prob) {
    editingProblemId = prob.id;
    document.getElementById('newProblemText').value = prob.question;
    document.getElementById('newProblemExplanation').value = prob.explanation || '';
    document.getElementById('newProblemDifficulty').value = prob.difficulty;

    const btn = document.querySelector('button[onclick="addProblemToPin()"]');
    if (btn) {
        btn.textContent = '更新';
        btn.classList.replace('btn-outline-primary', 'btn-primary');
    }

    // Add cancel button if not exists
    let cancelBtn = document.getElementById('cancelEditBtn');
    if (!cancelBtn) {
        cancelBtn = document.createElement('button');
        cancelBtn.id = 'cancelEditBtn';
        cancelBtn.className = 'btn btn-sm btn-outline-secondary ms-2';
        cancelBtn.textContent = 'キャンセル';
        cancelBtn.onclick = resetProblemForm;
        btn.parentNode.appendChild(cancelBtn);
    }
}

function resetProblemForm() {
    editingProblemId = null;
    document.getElementById('newProblemText').value = '';
    document.getElementById('newProblemExplanation').value = '';

    const btn = document.querySelector('button[onclick="addProblemToPin()"]');
    if (btn) {
        btn.textContent = '追加';
        btn.classList.replace('btn-primary', 'btn-outline-primary');
    }
    const cancelBtn = document.getElementById('cancelEditBtn');
    if (cancelBtn) cancelBtn.remove();
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
            // Difficulty 1: Easy (Success), 2: Std (Primary), 3: Hard (Danger)
            // 4: Most Difficult - Purple? Or Dark?
            const d = parseInt(prob.difficulty);
            if (d === 1) diffBadge = '<span class="badge bg-success me-1">易</span>';
            else if (d === 3) diffBadge = '<span class="badge bg-danger me-1">難</span>';
            else if (d === 4) diffBadge = '<span class="badge bg-dark me-1" style="background-color: #6610f2 !important;">最難</span>';
            else diffBadge = '<span class="badge bg-primary me-1">標</span>';

            div.innerHTML = `
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        ${diffBadge}
                        <strong>${prob.question}</strong>
                    </div>
                    <div>
                        <button class="btn btn-xs btn-outline-secondary me-1" onclick='editProblem(${JSON.stringify(prob)})'><i class="fas fa-edit"></i></button>
                        <button class="btn btn-xs btn-outline-danger" onclick="deleteProblem(${prob.id})"><i class="fas fa-trash"></i></button>
                    </div>
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

function getCsrfToken() {
    const input = document.querySelector('input[name="csrf_token"]');
    if (input) return input.value;
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');
    return '';
}

// --- Helper Functions for Region Support ---

function setCreateMode(mode) {
    currentDrawMode = mode;
    if (mode === 'point') {
        const rad = document.getElementById('modePoint');
        if (rad) rad.checked = true;
    } else {
        const rad = document.getElementById('modeCircle');
        if (rad) rad.checked = true;
    }
}

function toggleShapeInputs() {
    const isCircle = document.getElementById('shapeTypeCircle').checked;
    const inputs = document.getElementById('circleInputs');
    if (inputs) {
        inputs.style.display = isCircle ? 'block' : 'none';
    }
}

function createTempCircle(centerX, centerY, mapWidthPx) {
    const container = document.getElementById('editorPinsContainer');
    tempCircleEl = document.createElement('div');
    tempCircleEl.style.position = 'absolute';
    tempCircleEl.style.left = drawCenterX + '%';
    tempCircleEl.style.top = drawCenterY + '%';
    tempCircleEl.style.width = '0px';
    tempCircleEl.style.height = '0px';
    tempCircleEl.style.transform = 'translate(-50%, -50%)';
    tempCircleEl.style.borderRadius = '50%';
    tempCircleEl.style.border = '2px dashed rgba(13, 110, 253, 0.8)';
    tempCircleEl.style.backgroundColor = 'rgba(13, 110, 253, 0.3)';
    tempCircleEl.style.pointerEvents = 'none';

    container.appendChild(tempCircleEl);
}

function updateTempCircle(radiusPx) {
    if (!tempCircleEl) return;

    // Calculate size based on drawRadius (%) so it matches final render
    const img = document.getElementById('editorMapImage');
    const w = img.clientWidth;

    const px = (drawRadius / 100) * w * 2;

    tempCircleEl.style.width = px + 'px';
    tempCircleEl.style.height = px + 'px';
}
