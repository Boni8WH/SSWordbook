// static/map.js

document.addEventListener('DOMContentLoaded', () => {
    // 地図の初期化 (ローマを中心)
    const map = L.map('map').setView([41.9028, 12.4964], 5);

    // タイルレイヤーの追加 (OpenStreetMap)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    // データの読み込み
    loadGeoData(map);

    // 管理者モードの場合、編集コントロールを追加
    if (typeof window.isAdmin !== 'undefined' && window.isAdmin) {
        initDrawControl(map);
    }
});

function loadGeoData(map) {
    // APIからデータを取得
    fetch('/api/geo_data')
        .then(response => response.json())
        .then(data => {
            // 既存のレイヤーをクリアしたい場合はここで処理が必要だが、
            // 今回は追記のみ考慮
            L.geoJSON(data, {
                onEachFeature: function (feature, layer) {
                    if (feature.properties && feature.properties.name) {
                        let popupContent = `<strong>${feature.properties.name}</strong>`;
                        if (feature.properties.description) {
                            popupContent += `<br>${feature.properties.description}`;
                        }
                        if (feature.properties.type) {
                            popupContent += `<br><small>(${feature.properties.type})</small>`;
                        }
                        layer.bindPopup(popupContent);
                    }
                }
            }).addTo(map);
        })
        .catch(error => console.error('Error loading geo data:', error));
}

function initDrawControl(map) {
    // Leaflet.draw の初期化
    const drawnItems = new L.FeatureGroup();
    map.addLayer(drawnItems);

    const drawControl = new L.Control.Draw({
        edit: {
            featureGroup: drawnItems
        },
        draw: {
            polygon: true,
            polyline: true,
            rectangle: true,
            circle: false,
            marker: true,
            circlemarker: false
        }
    });
    map.addControl(drawControl);

    map.on(L.Draw.Event.CREATED, function (e) {
        const type = e.layerType;
        const layer = e.layer;

        // 入力プロンプト（簡易的）
        const name = prompt("場所の名前を入力してください:", "");
        if (name === null) return; // キャンセル

        const description = prompt("説明を入力してください:", "");
        const featureType = prompt("種類を入力してください (city, river, mountain, etc.):", "city");

        if (!name) {
            alert("名前は必須です。");
            return;
        }

        // GeoJSONに変換
        const geoJson = layer.toGeoJSON();
        const geometry = geoJson.geometry;

        // サーバーに保存
        saveGeoData(name, featureType || 'other', description || '', geometry, layer, map);

        drawnItems.addLayer(layer);
    });
}

function saveGeoData(name, type, description, geometry, layer, map) {
    const data = {
        name: name,
        type: type,
        description: description,
        geometry: geometry
    };

    fetch('/api/geo_data', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
        .then(response => response.json())
        .then(result => {
            if (result.status === 'success') {
                alert(`保存しました (ID: ${result.id})`);
                layer.bindPopup(`<strong>${name}</strong><br>${description}<br><small>(${type})</small>`);
            } else {
                alert(`保存エラー: ${result.error}`);
                map.removeLayer(layer);
            }
        })
        .catch(error => {
            console.error('Error saving geo data:', error);
            alert('保存中にエラーが発生しました。');
            map.removeLayer(layer);
        });
}
