// 管理员后台逻辑

const API_BASE = '';

// DOM元素
const loginSection = document.getElementById('loginSection');
const dashboardSection = document.getElementById('dashboardSection');
const loginForm = document.getElementById('loginForm');
const reportsTableBody = document.getElementById('reportsTableBody');
const totalCountEl = document.getElementById('totalCount');

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    checkLoginStatus();

    // 绑定事件
    loginForm.addEventListener('submit', handleLogin);
    document.getElementById('logoutBtn').addEventListener('click', handleLogout);
    document.getElementById('refreshBtn').addEventListener('click', fetchReports);
    document.getElementById('exportCsvBtn').addEventListener('click', () => {
        window.location.href = `${API_BASE}/api/reports/export/csv`;
    });
});

/**
 * 检查登录状态
 */
async function checkLoginStatus() {
    try {
        const response = await fetch(`${API_BASE}/api/admin/check`);
        const data = await response.json();

        if (data.isAdmin) {
            showDashboard();
        } else {
            showLogin();
        }
    } catch (error) {
        console.error('检查登录状态失败:', error);
        showLogin();
    }
}

/**
 * 处理登录
 */
async function handleLogin(e) {
    e.preventDefault();
    const password = document.getElementById('password').value;

    try {
        const response = await fetch(`${API_BASE}/api/admin/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        });

        const data = await response.json();

        if (data.success) {
            showDashboard();
        } else {
            alert('密码错误');
        }
    } catch (error) {
        console.error('登录失败:', error);
        alert('登录请求失败');
    }
}

/**
 * 处理登出
 */
async function handleLogout() {
    try {
        await fetch(`${API_BASE}/api/admin/logout`, { method: 'POST' });
        showLogin();
    } catch (error) {
        console.error('登出失败:', error);
    }
}

/**
 * 显示仪表板
 */
function showDashboard() {
    loginSection.style.display = 'none';
    dashboardSection.style.display = 'block';
    fetchReports();
}

/**
 * 显示登录页
 */
function showLogin() {
    loginSection.style.display = 'block';
    dashboardSection.style.display = 'none';
    document.getElementById('password').value = '';
}

/**
 * 获取所有报告
 */
async function fetchReports() {
    try {
        const response = await fetch(`${API_BASE}/api/admin/reports`);
        const data = await response.json();

        if (data.success) {
            renderReports(data.reports);
        } else {
            if (data.error === '未授权') {
                showLogin();
            } else {
                alert('获取数据失败: ' + data.error);
            }
        }
    } catch (error) {
        console.error('获取报告失败:', error);
    }
}

/**
 * 渲染报告表格
 */
function renderReports(reports) {
    totalCountEl.textContent = `共 ${reports.length} 条`;
    reportsTableBody.innerHTML = '';

    if (reports.length === 0) {
        reportsTableBody.innerHTML = '<tr><td colspan="7" style="text-align:center;">暂无数据</td></tr>';
        return;
    }

    reports.forEach(report => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${report.id}</td>
            <td><strong>${report.callsign}</strong></td>
            <td>${report.grid_locator}</td>
            <td>${report.distance} km</td>
            <td>${'★'.repeat(report.signal_strength)}</td>
            <td>${new Date(report.timestamp).toLocaleString()}</td>
            <td>
                <button class="btn btn-danger action-btn" onclick="deleteReport(${report.id})">删除</button>
            </td>
        `;
        reportsTableBody.appendChild(tr);
    });
}

/**
 * 删除报告
 */
window.deleteReport = async function (id) {
    if (!confirm('确定要删除这条报告吗？此操作不可恢复。')) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/api/admin/reports/${id}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (data.success) {
            fetchReports(); // 刷新列表
        } else {
            alert('删除失败: ' + data.error);
        }
    } catch (error) {
        console.error('删除请求失败:', error);
        alert('删除请求失败');
    }
};
