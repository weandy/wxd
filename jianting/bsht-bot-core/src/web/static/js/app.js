/**
 * BSHT Bot Web 平台 - 公共 JavaScript
 */

// 全局状态
const AppState = {
    currentUser: null,
    isLoading: false
};

// 工具函数
const Utils = {
    /**
     * 格式化日期时间
     */
    formatDateTime(dateStr) {
        if (!dateStr) return '-';
        const date = new Date(dateStr);
        return date.toLocaleString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    },

    /**
     * 格式化时长
     */
    formatDuration(seconds) {
        if (!seconds) return '-';
        if (seconds < 60) {
            return `${seconds.toFixed(1)}秒`;
        }
        const minutes = Math.floor(seconds / 60);
        const secs = (seconds % 60).toFixed(0);
        return `${minutes}分${secs}秒`;
    },

    /**
     * 格式化文件大小
     */
    formatFileSize(bytes) {
        if (!bytes) return '-';
        const units = ['B', 'KB', 'MB', 'GB'];
        let size = bytes;
        let unitIndex = 0;
        while (size >= 1024 && unitIndex < units.length - 1) {
            size /= 1024;
            unitIndex++;
        }
        return `${size.toFixed(1)} ${units[unitIndex]}`;
    },

    /**
     * 防抖函数
     */
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    /**
     * 节流函数
     */
    throttle(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }
};

// 初始化应用
document.addEventListener('DOMContentLoaded', () => {
    console.log('BSHT Bot Web 平台已加载');

    // 检查登录状态
    checkLoginStatus();
});

/**
 * 检查登录状态
 */
async function checkLoginStatus() {
    try {
        const response = await fetchAPI('/auth/me');
        if (response.code === 0 && response.data) {
            AppState.currentUser = response.data;
        }
    } catch (error) {
        // 未登录或 API 未实现
        console.log('未登录或 API 未就绪');
    }
}

/**
 * 确认对话框
 */
function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

/**
 * 渲染分页控件
 */
function renderPagination(page, totalPages, onPageChange) {
    if (totalPages <= 1) return '';

    let html = '<div class="flex items-center justify-center space-x-2 mt-6">';

    // 上一页
    html += `<button
        onclick="window.goToPage(${page - 1})"
        class="px-4 py-2 rounded border ${page === 1 ? 'text-gray-400 cursor-not-allowed' : 'hover:bg-gray-100'}"
        ${page === 1 ? 'disabled' : ''}
    >上一页</button>`;

    // 页码
    for (let i = 1; i <= totalPages; i++) {
        if (i === 1 || i === totalPages || (i >= page - 2 && i <= page + 2)) {
            html += `<button
                onclick="window.goToPage(${i})"
                class="px-4 py-2 rounded border ${i === page ? 'bg-blue-600 text-white' : 'hover:bg-gray-100'}"
            >${i}</button>`;
        } else if (i === page - 3 || i === page + 3) {
            html += '<span class="px-2">...</span>';
        }
    }

    // 下一页
    html += `<button
        onclick="window.goToPage(${page + 1})"
        class="px-4 py-2 rounded border ${page === totalPages ? 'text-gray-400 cursor-not-allowed' : 'hover:bg-gray-100'}"
        ${page === totalPages ? 'disabled' : ''}
    >下一页</button>`;

    html += '</div>';
    html += `<p class="text-center text-gray-500 text-sm mt-2">第 ${page}/${totalPages} 页</p>`;

    return html;
}
