// ================================
// Configuration
// ================================
const CONFIG = {
    // 台站位置 - 请修改为您的实际位置
    stationLocation: {
        lat: 39.9042,  // 北京天安门示例
        lng: 116.4074,
        callsign: 'BD6KFP',  // 您的呼号
        band: 'UHF/VHF'       // 工作频段
    },
    // API地址
    apiBase: '',  // 空字符串表示当前域名
    // 地图设置
    map: {
        defaultZoom: 10,
        minZoom: 3,
        maxZoom: 18,
        distanceCircles: [50, 100, 200, 300]  // 距离圈 (km)
    }
};

// ================================
// Global Variables
// ================================
let map;
let stationMarker;
let reportMarkers = [];
let distanceCircles = [];
let reports = [];
let myReportIds = [];  // 我提交的报告ID列表

// ================================
// API Functions
// ================================

/**
 * 从API获取所有报告
 */
async function fetchReports() {
    try {
        const response = await fetch(`${CONFIG.apiBase}/api/reports`);
        const data = await response.json();
        if (data.success) {
            reports = data.reports;
            updateUI();
        }
    } catch (error) {
        console.error('获取报告失败:', error);
        showToast('获取报告失败', 'error');
    }
}

/**
 * 提交新报告
 */
async function submitReport(reportData) {
    try {
        const response = await fetch(`${CONFIG.apiBase}/api/reports`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(reportData),
            credentials: 'include'  // 包含cookie
        });

        const data = await response.json();
        if (data.success) {
            // 添加到我的报告列表
            myReportIds.push(data.report.id);
            // 刷新报告列表
            await fetchReports();
            showToast('✅ 报告提交成功！', 'success');
            return true;
        } else {
            showToast(data.error || '提交失败', 'error');
            return false;
        }
    } catch (error) {
        console.error('提交报告失败:', error);
        showToast('提交报告失败', 'error');
        return false;
    }
}

/**
 * 删除报告
 */
async function deleteReport(reportId) {
    try {
        const response = await fetch(`${CONFIG.apiBase}/api/reports/${reportId}`, {
            method: 'DELETE',
            credentials: 'include'
        });

        const data = await response.json();
        if (data.success) {
            // 从我的报告列表中移除
            myReportIds = myReportIds.filter(id => id !== reportId);
            // 刷新报告列表
            await fetchReports();
            showToast('✅ 删除成功', 'success');
            return true;
        } else {
            showToast(data.error || '删除失败', 'error');
            return false;
        }
    } catch (error) {
        console.error('删除报告失败:', error);
        showToast('删除失败', 'error');
        return false;
    }
}

/**
 * 获取我的报告ID列表
 */
async function fetchMyReports() {
    try {
        const response = await fetch(`${CONFIG.apiBase}/api/my-reports`, {
            credentials: 'include'
        });
        const data = await response.json();
        if (data.success) {
            myReportIds = data.reportIds;
        }
    } catch (error) {
        console.error('获取我的报告失败:', error);
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

    const stationGrid = Maidenhead.toMaidenhead(CONFIG.stationLocation.lat, CONFIG.stationLocation.lng);

    stationMarker.bindPopup(`
        <div style="font-family: 'Inter', sans-serif; padding: 5px;">
            <strong style="font-size: 1.1em; color: #667eea;">📡 台站位置</strong><br>
            <span style="color: #666;">呼号: ${CONFIG.stationLocation.callsign}</span><br>
            <span style="color: #666;">频段: ${CONFIG.stationLocation.band}</span><br>
            <span style="color: #999; font-size: 0.9em;">网格: ${stationGrid}</span>
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
                radius: radius * 1000,
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

    // 添加新标记 - 使用网格矩形显示
    reports.forEach((report) => {
        // 获取网格边界
        const bounds = Maidenhead.getMaidenheadBounds(report.grid_locator);

        // 绘制网格矩形
        const rectangle = L.rectangle([
            [bounds.minLat, bounds.minLon],
            [bounds.maxLat, bounds.maxLon]
        ], {
            color: '#f5576c',
            fillColor: '#f093fb',
            fillOpacity: 0.3,
            weight: 2
        }).addTo(map);

        const stars = '★'.repeat(report.signal_strength) + '☆'.repeat(5 - report.signal_strength);

        rectangle.bindPopup(`
            <div style="font-family: 'Inter', sans-serif; padding: 5px; min-width: 200px;">
                <strong style="font-size: 1.1em; color: #f5576c;">📍 ${report.callsign}</strong><br>
                <span style="color: #666;">网格: <strong>${report.grid_locator}</strong></span><br>
                <span style="color: #666;">距离: <strong>${report.distance} km</strong></span><br>
                ${report.signal_strength > 0 ? `<span style="color: #f59e0b;">${stars}</span><br>` : ''}
                <span style="color: #888; font-size: 0.9em;">${formatDateTime(report.timestamp)}</span>
                ${report.notes ? `<br><p style="margin-top: 5px; color: #555; font-size: 0.9em;">${report.notes}</p>` : ''}
            </div>
        `);

        reportMarkers.push(rectangle);
    });

    // 自动调整地图视图以显示所有标记
    if (reports.length > 0) {
        const bounds = L.latLngBounds([
            [CONFIG.stationLocation.lat, CONFIG.stationLocation.lng],
            ...reports.map(r => {
                const gridBounds = Maidenhead.getMaidenheadBounds(r.grid_locator);
                return [(gridBounds.minLat + gridBounds.maxLat) / 2, (gridBounds.minLon + gridBounds.maxLon) / 2];
            })
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
    const gridInput = document.getElementById('gridLocator');

    if (!navigator.geolocation) {
        statusEl.textContent = '❌ 您的浏览器不支持定位';
        statusEl.style.color = 'var(--danger-color)';
        return;
    }

    statusEl.textContent = '🔍 正在获取位置...';
    statusEl.style.color = 'var(--warning-color)';

    navigator.geolocation.getCurrentPosition(
        (position) => {
            const lat = position.coords.latitude.toFixed(6);
            const lng = position.coords.longitude.toFixed(6);

            latInput.value = lat;
            lngInput.value = lng;

            // 计算Maidenhead网格
            const grid = Maidenhead.toMaidenhead(parseFloat(lat), parseFloat(lng));
            gridInput.value = grid;

            statusEl.textContent = `✅ 位置获取成功 (网格: ${grid})`;
            statusEl.style.color = 'var(--success-color)';

            setTimeout(() => {
                statusEl.textContent = '';
            }, 5000);
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
async function handleFormSubmit(e) {
    e.preventDefault();

    const formData = new FormData(e.target);
    const reportData = {
        callsign: formData.get('callsign').toUpperCase(),
        latitude: parseFloat(formData.get('latitude')),
        longitude: parseFloat(formData.get('longitude')),
        signalStrength: parseInt(formData.get('signalStrength')) || 0,
        notes: formData.get('notes') || ''
    };

    const success = await submitReport(reportData);

    if (success) {
        // 重置表单
        e.target.reset();
        document.getElementById('signalStrength').value = '0';
        document.getElementById('gridLocator').value = '';
        updateStarRating(0);
    }
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

    // 添加null检查
    if (!listEl) {
        console.warn('reportsList element not found');
        return;
    }

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
        const stars = '★'.repeat(report.signal_strength);
        const emptyStars = '☆'.repeat(5 - report.signal_strength);
        const isMine = myReportIds.includes(report.id);

        return `
            <div class="report-item ${isMine ? 'my-report' : ''}">
                <div class="report-header">
                    <span class="report-callsign">${report.callsign}</span>
                    <span class="report-distance">${report.distance} km</span>
                </div>
                <div class="report-meta">
                    <span>📍 ${report.grid_locator}</span>
                    <span>🕐 ${formatDateTime(report.timestamp)}</span>
                    ${report.signal_strength > 0 ? `<span class="report-signal">${stars}${emptyStars}</span>` : ''}
                </div>
                ${report.notes ? `<div class="report-notes">${report.notes}</div>` : ''}
                ${isMine ? `
                    <div class="report-actions">
                        <button class="btn-small btn-danger" onclick="confirmDelete(${report.id})">
                            🗑️ 删除
                        </button>
                        <span class="my-badge">我的报告</span>
                    </div>
                ` : ''}
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
 * 确认删除
 */
function confirmDelete(reportId) {
    if (confirm('确定要删除这条报告吗？删除后无法恢复！')) {
        deleteReport(reportId);
    }
}

/**
 * 显示Toast通知
 */
function showToast(message, type = 'info') {
    // 创建toast元素
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    // 添加到body
    document.body.appendChild(toast);

    // 显示动画
    setTimeout(() => toast.classList.add('show'), 100);

    // 3秒后移除
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ================================
// Utility Functions
// ================================

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

// ================================
// Event Listeners
// ================================

document.addEventListener('DOMContentLoaded', async () => {
    // 更新台站信息显示
    document.getElementById('stationCallsign').textContent = CONFIG.stationLocation.callsign;
    document.getElementById('stationBand').textContent = CONFIG.stationLocation.band;

    // 初始化地图
    initMap();

    // 获取我的报告列表
    await fetchMyReports();

    // 加载报告数据
    await fetchReports();

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

    // 自动刷新（每30秒）
    setInterval(fetchReports, 30000);
});
