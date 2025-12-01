// ================================
// Configuration
// ================================
const CONFIG = {
    // 台站位置 - 请修改为您的实际位置
    stationLocation: {
        lat: 35.29776,  // 北京天安门示例
        lng: 114.069038,
        callsign: 'BD6KFP',  // 您的呼号
        band: 'UHF/VHF'       // 工作频段
    },
    // 地图设置
    map: {
        defaultZoom: 10,
        minZoom: 3,
        maxZoom: 18,
        distanceCircles: [50, 100, 200, 300]  // 距离圈 (km)
    },
    // 本地存储键名
    storageKey: 'hamRadioReports'
};

// ================================
// Global Variables
// ================================
let map;
let stationMarker;
let reportMarkers = [];
let distanceCircles = [];
let reports = [];

// ================================
// Utility Functions
// ================================

/**
 * 计算两点间的距离 (Haversine公式)
 * @param {number} lat1 - 第一个点的纬度
 * @param {number} lon1 - 第一个点的经度
 * @param {number} lat2 - 第二个点的纬度
 * @param {number} lon2 - 第二个点的经度
 * @returns {number} 距离 (公里)
 */
function calculateDistance(lat1, lon1, lat2, lon2) {
    const R = 6371; // 地球半径 (km)
    const dLat = toRadians(lat2 - lat1);
    const dLon = toRadians(lon2 - lon1);

    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(toRadians(lat1)) * Math.cos(toRadians(lat2)) *
        Math.sin(dLon / 2) * Math.sin(dLon / 2);

    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    const distance = R * c;

    return Math.round(distance * 10) / 10; // 保留1位小数
}

function toRadians(degrees) {
    return degrees * (Math.PI / 180);
}

/**
 * 格式化日期时间
 */
function formatDateTime(date) {
    const now = new Date(date);
    return now.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

/**
 * 从localStorage加载报告
 */
function loadReports() {
    const stored = localStorage.getItem(CONFIG.storageKey);
    if (stored) {
        try {
            reports = JSON.parse(stored);
        } catch (e) {
            console.error('加载报告数据失败:', e);
            reports = [];
        }
    }
}

/**
 * 保存报告到localStorage
 */
function saveReports() {
    try {
        localStorage.setItem(CONFIG.storageKey, JSON.stringify(reports));
    } catch (e) {
        console.error('保存报告数据失败:', e);
        alert('保存失败，可能是存储空间已满');
    }
}

// ================================
// Map Functions
// ================================

/**
 * 初始化地图
 */
function initMap() {
    // 创建地图
    map = L.map('map').setView(
        [CONFIG.stationLocation.lat, CONFIG.stationLocation.lng],
        CONFIG.map.defaultZoom
    );

    // 添加地图瓦片层
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        minZoom: CONFIG.map.minZoom,
        maxZoom: CONFIG.map.maxZoom
    }).addTo(map);

    // 添加台站标记
    const stationIcon = L.divIcon({
        className: 'station-marker',
        html: '<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); width: 30px; height: 30px; border-radius: 50%; border: 3px solid white; box-shadow: 0 4px 6px rgba(0,0,0,0.3);"></div>',
        iconSize: [30, 30],
        iconAnchor: [15, 15]
    });

    stationMarker = L.marker(
        [CONFIG.stationLocation.lat, CONFIG.stationLocation.lng],
        { icon: stationIcon }
    ).addTo(map);

    stationMarker.bindPopup(`
        <div style="font-family: 'Inter', sans-serif; padding: 5px;">
            <strong style="font-size: 1.1em; color: #667eea;">📡 台站位置</strong><br>
            <span style="color: #666;">呼号: ${CONFIG.stationLocation.callsign}</span><br>
            <span style="color: #666;">频段: ${CONFIG.stationLocation.band}</span>
        </div>
    `);

    // 绘制距离圈
    drawDistanceCircles();

    // 加载已有的报告标记
    displayReportsOnMap();
}

/**
 * 绘制距离圈
 */
function drawDistanceCircles() {
    // 清除旧的圈
    distanceCircles.forEach(circle => map.removeLayer(circle));
    distanceCircles = [];

    // 绘制新的圈
    CONFIG.map.distanceCircles.forEach((radius, index) => {
        const circle = L.circle(
            [CONFIG.stationLocation.lat, CONFIG.stationLocation.lng],
            {
                radius: radius * 1000, // 转换为米
                color: `rgba(59, 130, 246, ${0.6 - index * 0.1})`,
                fillColor: `rgba(59, 130, 246, ${0.1 - index * 0.02})`,
                fillOpacity: 0.1,
                weight: 1
            }
        ).addTo(map);

        circle.bindTooltip(`${radius} km`, {
            permanent: false,
            direction: 'center'
        });

        distanceCircles.push(circle);
    });
}

/**
 * 在地图上显示所有报告
 */
function displayReportsOnMap() {
    // 清除旧标记
    reportMarkers.forEach(marker => map.removeLayer(marker));
    reportMarkers = [];

    // 添加新标记
    reports.forEach((report, index) => {
        const reportIcon = L.divIcon({
            className: 'report-marker',
            html: '<div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); width: 20px; height: 20px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>',
            iconSize: [20, 20],
            iconAnchor: [10, 10]
        });

        const marker = L.marker([report.latitude, report.longitude], {
            icon: reportIcon
        }).addTo(map);

        const stars = '★'.repeat(report.signalStrength) + '☆'.repeat(5 - report.signalStrength);

        marker.bindPopup(`
            <div style="font-family: 'Inter', sans-serif; padding: 5px; min-width: 200px;">
                <strong style="font-size: 1.1em; color: #f5576c;">📍 ${report.callsign}</strong><br>
                <span style="color: #666;">距离: <strong>${report.distance} km</strong></span><br>
                <span style="color: #f59e0b;">${stars}</span><br>
                <span style="color: #888; font-size: 0.9em;">${formatDateTime(report.timestamp)}</span>
                ${report.notes ? `<br><p style="margin-top: 5px; color: #555; font-size: 0.9em;">${report.notes}</p>` : ''}
            </div>
        `);

        reportMarkers.push(marker);
    });

    // 自动调整地图视图以显示所有标记
    if (reports.length > 0) {
        const bounds = L.latLngBounds([
            [CONFIG.stationLocation.lat, CONFIG.stationLocation.lng],
            ...reports.map(r => [r.latitude, r.longitude])
        ]);
        map.fitBounds(bounds, { padding: [50, 50] });
    }
}

// ================================
// Form Functions
// ================================

/**
 * 获取用户位置
 */
function getUserLocation() {
    const statusEl = document.getElementById('locationStatus');
    const latInput = document.getElementById('latitude');
    const lngInput = document.getElementById('longitude');

    if (!navigator.geolocation) {
        statusEl.textContent = '❌ 您的浏览器不支持定位';
        statusEl.style.color = 'var(--danger-color)';
        return;
    }

    statusEl.textContent = '🔍 正在获取位置...';
    statusEl.style.color = 'var(--warning-color)';

    navigator.geolocation.getCurrentPosition(
        (position) => {
            latInput.value = position.coords.latitude.toFixed(6);
            lngInput.value = position.coords.longitude.toFixed(6);
            statusEl.textContent = '✅ 位置获取成功';
            statusEl.style.color = 'var(--success-color)';

            setTimeout(() => {
                statusEl.textContent = '';
            }, 3000);
        },
        (error) => {
            let message = '❌ 获取位置失败';
            switch (error.code) {
                case error.PERMISSION_DENIED:
                    message = '❌ 您拒绝了位置权限';
                    break;
                case error.POSITION_UNAVAILABLE:
                    message = '❌ 位置信息不可用';
                    break;
                case error.TIMEOUT:
                    message = '❌ 获取位置超时';
                    break;
            }
            statusEl.textContent = message;
            statusEl.style.color = 'var(--danger-color)';
        }
    );
}

/**
 * 处理表单提交
 */
function handleFormSubmit(e) {
    e.preventDefault();

    const formData = new FormData(e.target);
    const report = {
        callsign: formData.get('callsign').toUpperCase(),
        latitude: parseFloat(formData.get('latitude')),
        longitude: parseFloat(formData.get('longitude')),
        signalStrength: parseInt(formData.get('signalStrength')) || 0,
        notes: formData.get('notes') || '',
        timestamp: new Date().toISOString()
    };

    // 计算距离
    report.distance = calculateDistance(
        CONFIG.stationLocation.lat,
        CONFIG.stationLocation.lng,
        report.latitude,
        report.longitude
    );

    // 添加到报告列表
    reports.unshift(report); // 添加到开头

    // 保存到localStorage
    saveReports();

    // 更新界面
    updateUI();

    // 重置表单
    e.target.reset();
    document.getElementById('signalStrength').value = '0';
    updateStarRating(0);

    // 显示成功消息
    alert(`✅ 报告提交成功！\n距离台站 ${report.distance} km`);
}

/**
 * 更新星级评分
 */
function updateStarRating(rating) {
    const stars = document.querySelectorAll('.star');
    const ratingText = document.getElementById('ratingText');
    const ratingInput = document.getElementById('signalStrength');

    stars.forEach((star, index) => {
        if (index < rating) {
            star.classList.add('active');
        } else {
            star.classList.remove('active');
        }
    });

    ratingInput.value = rating;

    const labels = ['未评分', '很弱', '较弱', '一般', '较强', '很强'];
    ratingText.textContent = labels[rating] || '未评分';
}

// ================================
// UI Functions
// ================================

/**
 * 更新用户界面
 */
function updateUI() {
    updateReportsList();
    updateStats();
    displayReportsOnMap();
}

/**
 * 更新报告列表
 */
function updateReportsList() {
    const listEl = document.getElementById('reportsList');

    if (reports.length === 0) {
        listEl.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📭</div>
                <p>暂无报告数据</p>
                <p class="empty-hint">等待信号反馈...</p>
            </div>
        `;
        return;
    }

    const html = reports.map(report => {
        const stars = '★'.repeat(report.signalStrength);
        const emptyStars = '☆'.repeat(5 - report.signalStrength);

        return `
            <div class="report-item">
                <div class="report-header">
                    <span class="report-callsign">${report.callsign}</span>
                    <span class="report-distance">${report.distance} km</span>
                </div>
                <div class="report-meta">
                    <span>🕐 ${formatDateTime(report.timestamp)}</span>
                    ${report.signalStrength > 0 ? `<span class="report-signal">${stars}${emptyStars}</span>` : ''}
                </div>
                ${report.notes ? `<div class="report-notes">${report.notes}</div>` : ''}
            </div>
        `;
    }).join('');

    listEl.innerHTML = html;
}

/**
 * 更新统计信息
 */
function updateStats() {
    document.getElementById('reportCount').textContent = reports.length;

    if (reports.length > 0) {
        const maxDist = Math.max(...reports.map(r => r.distance));
        document.getElementById('maxDistance').textContent = maxDist;
    } else {
        document.getElementById('maxDistance').textContent = '0';
    }
}

/**
 * 清空所有报告
 */
function clearReports() {
    if (reports.length === 0) {
        alert('没有数据需要清空');
        return;
    }

    if (confirm(`确定要清空所有 ${reports.length} 条报告吗？此操作不可恢复！`)) {
        reports = [];
        saveReports();
        updateUI();
        alert('✅ 数据已清空');
    }
}

// ================================
// Event Listeners
// ================================

document.addEventListener('DOMContentLoaded', () => {
    // 更新台站信息显示
    document.getElementById('stationCallsign').textContent = CONFIG.stationLocation.callsign;
    document.getElementById('stationBand').textContent = CONFIG.stationLocation.band;

    // 初始化地图
    initMap();

    // 加载报告数据
    loadReports();
    updateUI();

    // 表单提交事件
    document.getElementById('reportForm').addEventListener('submit', handleFormSubmit);

    // 获取位置按钮
    document.getElementById('getLocationBtn').addEventListener('click', getUserLocation);

    // 星级评分点击事件
    document.querySelectorAll('.star').forEach(star => {
        star.addEventListener('click', () => {
            const rating = parseInt(star.dataset.value);
            updateStarRating(rating);
        });

        star.addEventListener('mouseenter', () => {
            const rating = parseInt(star.dataset.value);
            const stars = document.querySelectorAll('.star');
            stars.forEach((s, index) => {
                if (index < rating) {
                    s.style.color = 'var(--warning-color)';
                } else {
                    s.style.color = 'var(--text-muted)';
                }
            });
        });
    });

    document.getElementById('starRating').addEventListener('mouseleave', () => {
        const currentRating = parseInt(document.getElementById('signalStrength').value);
        updateStarRating(currentRating);
    });

    // 清空数据按钮
    document.getElementById('clearReportsBtn').addEventListener('click', clearReports);
});
