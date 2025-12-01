/**
 * Express服务器主文件
 * 业余无线电信号反馈系统后端
 */

const express = require('express');
const session = require('express-session');
const cookieParser = require('cookie-parser');
const cors = require('cors');
const path = require('path');
const { v4: uuidv4 } = require('uuid');
const db = require('./database');
const { toMaidenhead } = require('../public/maidenhead');

const app = express();
const PORT = process.env.PORT || 3000;

// 中间件配置
app.use(cors({
    origin: true,
    credentials: true
}));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(cookieParser());

// Session配置
app.use(session({
    secret: 'ham-radio-secret-key-' + uuidv4(),
    resave: false,
    saveUninitialized: false,
    cookie: {
        maxAge: 24 * 60 * 60 * 1000, // 24小时
        httpOnly: true,
        sameSite: 'lax'
    }
}));

// 静态文件服务
app.use(express.static(path.join(__dirname, '../public')));

// ==================== API路由 ====================

/**
 * 获取所有报告（用于地图显示，包含坐标）
 */
app.get('/api/reports', (req, res) => {
    try {
        const reports = db.getAllReportsWithCoords();
        res.json({
            success: true,
            reports: reports
        });
    } catch (error) {
        console.error('获取报告失败:', error);
        res.status(500).json({
            success: false,
            error: '获取报告失败'
        });
    }
});

/**
 * 获取统计信息
 */
app.get('/api/stats', (req, res) => {
    try {
        const stats = db.getStats();
        res.json({
            success: true,
            stats: stats
        });
    } catch (error) {
        console.error('获取统计失败:', error);
        res.status(500).json({
            success: false,
            error: '获取统计失败'
        });
    }
});

/**
 * 提交新报告
 */
app.post('/api/reports', (req, res) => {
    try {
        const { callsign, latitude, longitude, signalStrength, notes } = req.body;

        // 验证必填字段
        if (!callsign || !latitude || !longitude) {
            return res.status(400).json({
                success: false,
                error: '缺少必填字段'
            });
        }

        // 生成或获取session ID
        if (!req.session.reportSessionId) {
            req.session.reportSessionId = uuidv4();
        }

        // 转换为Maidenhead网格
        const gridLocator = toMaidenhead(parseFloat(latitude), parseFloat(longitude));

        // 计算距离（假设台站位置在配置中）
        const stationLat = 39.9042; // 从前端配置读取
        const stationLon = 116.4074;
        const distance = calculateDistance(stationLat, stationLon, parseFloat(latitude), parseFloat(longitude));

        // 创建报告
        const reportData = {
            sessionId: req.session.reportSessionId,
            callsign: callsign.toUpperCase(),
            gridLocator: gridLocator,
            latitude: parseFloat(latitude),
            longitude: parseFloat(longitude),
            distance: distance,
            signalStrength: parseInt(signalStrength) || 0,
            notes: notes || ''
        };

        const report = db.createReport(reportData);

        res.json({
            success: true,
            report: report,
            sessionId: req.session.reportSessionId
        });

    } catch (error) {
        console.error('创建报告失败:', error);
        res.status(500).json({
            success: false,
            error: '创建报告失败'
        });
    }
});

/**
 * 更新报告（只能更新自己的）
 */
app.put('/api/reports/:id', (req, res) => {
    try {
        const reportId = parseInt(req.params.id);
        const { signalStrength, notes } = req.body;

        if (!req.session.reportSessionId) {
            return res.status(403).json({
                success: false,
                error: '无权限修改'
            });
        }

        // 验证是否是自己的报告
        const existingReport = db.getReportByIdAndSession(reportId, req.session.reportSessionId);
        if (!existingReport) {
            return res.status(403).json({
                success: false,
                error: '您只能修改自己提交的报告'
            });
        }

        const updatedReport = db.updateReport(reportId, req.session.reportSessionId, {
            signalStrength: parseInt(signalStrength) || 0,
            notes: notes || ''
        });

        res.json({
            success: true,
            report: updatedReport
        });

    } catch (error) {
        console.error('更新报告失败:', error);
        res.status(500).json({
            success: false,
            error: '更新报告失败'
        });
    }
});

/**
 * 删除报告（只能删除自己的）
 */
app.delete('/api/reports/:id', (req, res) => {
    try {
        const reportId = parseInt(req.params.id);

        if (!req.session.reportSessionId) {
            return res.status(403).json({
                success: false,
                error: '无权限删除'
            });
        }

        const deleted = db.deleteReport(reportId, req.session.reportSessionId);

        if (deleted) {
            res.json({
                success: true,
                message: '删除成功'
            });
        } else {
            res.status(403).json({
                success: false,
                error: '您只能删除自己提交的报告'
            });
        }

    } catch (error) {
        console.error('删除报告失败:', error);
        res.status(500).json({
            success: false,
            error: '删除报告失败'
        });
    }
});

/**
 * 获取当前用户的报告ID列表
 */
app.get('/api/my-reports', (req, res) => {
    try {
        if (!req.session.reportSessionId) {
            return res.json({
                success: true,
                reportIds: []
            });
        }

        const allReports = db.getAllReportsWithCoords();
        const myReportIds = allReports
            .filter(r => r.session_id === req.session.reportSessionId)
            .map(r => r.id);

        res.json({
            success: true,
            reportIds: myReportIds
        });

    } catch (error) {
        console.error('获取用户报告失败:', error);
        res.status(500).json({
            success: false,
            error: '获取用户报告失败'
        });
    }
});

// ==================== 管理员 API ====================

const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin123'; // 默认密码

/**
 * 管理员登录
 */
app.post('/api/admin/login', (req, res) => {
    const { password } = req.body;
    if (password === ADMIN_PASSWORD) {
        req.session.isAdmin = true;
        res.json({ success: true });
    } else {
        res.status(401).json({ success: false, error: '密码错误' });
    }
});

/**
 * 检查管理员状态
 */
app.get('/api/admin/check', (req, res) => {
    res.json({ isAdmin: !!req.session.isAdmin });
});

/**
 * 管理员登出
 */
app.post('/api/admin/logout', (req, res) => {
    req.session.isAdmin = false;
    res.json({ success: true });
});

/**
 * 管理员获取所有报告（包含详细信息）
 */
app.get('/api/admin/reports', (req, res) => {
    if (!req.session.isAdmin) {
        return res.status(403).json({ success: false, error: '未授权' });
    }
    try {
        const reports = db.getAllReportsWithCoords();
        res.json({ success: true, reports });
    } catch (error) {
        res.status(500).json({ success: false, error: '获取失败' });
    }
});

/**
 * 管理员删除报告
 */
app.delete('/api/admin/reports/:id', (req, res) => {
    if (!req.session.isAdmin) {
        return res.status(403).json({ success: false, error: '未授权' });
    }
    try {
        const reportId = parseInt(req.params.id);
        // 管理员可以删除任何报告，这里我们需要修改 database.js 或者添加一个新的删除方法
        // 为了简单，我们直接调用 db.deleteReport，但需要绕过 session 检查
        // 让我们在 database.js 中添加一个 adminDeleteReport 方法

        // 临时解决方案：直接操作数据库（不建议，最好封装在 database.js）
        // 或者修改 database.js 添加 adminDeleteReport
        // 这里我们先假设 database.js 有个 adminDeleteReport 方法，稍后添加
        const deleted = db.adminDeleteReport(reportId);

        if (deleted) {
            res.json({ success: true });
        } else {
            res.status(404).json({ success: false, error: '报告不存在' });
        }
    } catch (error) {
        console.error('管理员删除失败:', error);
        res.status(500).json({ success: false, error: '删除失败' });
    }
});


/**
 * 导出所有报告为CSV格式
 */
app.get('/api/reports/export/csv', (req, res) => {
    try {
        const reports = db.getAllReportsWithCoords();

        // CSV表头
        const headers = [
            'ID',
            '呼号',
            'Maidenhead网格',
            '纬度',
            '经度',
            '距离(km)',
            '信号强度',
            '备注',
            '提交时间'
        ];

        // CSV行数据
        const rows = reports.map(report => [
            report.id,
            report.callsign,
            report.grid_locator,
            report.latitude.toFixed(6),
            report.longitude.toFixed(6),
            report.distance,
            report.signal_strength,
            `"${(report.notes || '').replace(/"/g, '""')}"`, // 转义双引号
            formatDateTimeForCSV(report.timestamp)
        ]);

        // 组合CSV内容
        const csvContent = [
            headers.join(','),
            ...rows.map(row => row.join(','))
        ].join('\r\n');

        // 生成文件名（包含当前日期）
        const now = new Date();
        const dateStr = now.toISOString().split('T')[0];
        const filename = `ham_radio_reports_${dateStr}.csv`;

        // 设置响应头
        res.setHeader('Content-Type', 'text/csv; charset=utf-8');
        res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);

        // 添加BOM以支持Excel正确显示中文
        res.write('\uFEFF');
        res.end(csvContent);

        console.log(`✅ CSV导出成功: ${reports.length} 条报告`);

    } catch (error) {
        console.error('CSV导出失败:', error);
        res.status(500).json({
            success: false,
            error: 'CSV导出失败'
        });
    }
});


// ==================== 辅助函数 ====================

/**
 * 计算两点间距离 (Haversine公式)
 */
function calculateDistance(lat1, lon1, lat2, lon2) {
    const R = 6371;
    const dLat = toRadians(lat2 - lat1);
    const dLon = toRadians(lon2 - lon1);

    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(toRadians(lat1)) * Math.cos(toRadians(lat2)) *
        Math.sin(dLon / 2) * Math.sin(dLon / 2);

    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    const distance = R * c;

    return Math.round(distance * 10) / 10;
}

function toRadians(degrees) {
    return degrees * (Math.PI / 180);
}

/**
 * 格式化日期时间用于CSV
 */
function formatDateTimeForCSV(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    }).replace(/\//g, '-');
}


// ==================== 启动服务器 ====================

app.listen(PORT, () => {
    console.log(`
╔════════════════════════════════════════════════╗
║  📡 业余无线电信号反馈系统 - 服务器已启动      ║
╠════════════════════════════════════════════════╣
║  🌐 访问地址: http://localhost:${PORT}           ║
║  📊 API地址:  http://localhost:${PORT}/api      ║
║  ⏰ Session有效期: 24小时                       ║
╚════════════════════════════════════════════════╝
    `);
});

// 优雅退出
process.on('SIGINT', () => {
    console.log('\n👋 服务器正在关闭...');
    process.exit(0);
});
