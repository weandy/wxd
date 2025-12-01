/**
 * 数据库操作模块
 * 使用SQLite存储信号报告数据
 */

const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

// 确保data目录存在
const dataDir = path.join(__dirname, 'data');
if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
}

const dbPath = path.join(dataDir, 'reports.db');
const db = new Database(dbPath);

// 创建表
function initDatabase() {
    db.exec(`
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            callsign TEXT NOT NULL,
            grid_locator TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            distance REAL NOT NULL,
            signal_strength INTEGER DEFAULT 0,
            notes TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_session_id ON reports(session_id);
        CREATE INDEX IF NOT EXISTS idx_timestamp ON reports(timestamp DESC);
    `);

    console.log('✅ 数据库初始化完成');
}

/**
 * 获取所有报告（公开数据，不包含精确坐标）
 */
function getAllReports() {
    const stmt = db.prepare(`
        SELECT 
            id,
            callsign,
            grid_locator,
            distance,
            signal_strength,
            notes,
            timestamp
        FROM reports
        ORDER BY timestamp DESC
    `);

    return stmt.all();
}

/**
 * 获取所有报告（包含坐标，用于地图显示）
 */
function getAllReportsWithCoords() {
    const stmt = db.prepare(`
        SELECT * FROM reports ORDER BY timestamp DESC
    `);

    return stmt.all();
}

/**
 * 创建新报告
 */
function createReport(data) {
    const stmt = db.prepare(`
        INSERT INTO reports (
            session_id, callsign, grid_locator, 
            latitude, longitude, distance, 
            signal_strength, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `);

    const result = stmt.run(
        data.sessionId,
        data.callsign,
        data.gridLocator,
        data.latitude,
        data.longitude,
        data.distance,
        data.signalStrength || 0,
        data.notes || ''
    );

    // 返回新创建的报告
    const selectStmt = db.prepare('SELECT * FROM reports WHERE id = ?');
    return selectStmt.get(result.lastInsertRowid);
}

/**
 * 根据ID和会话ID获取报告（验证权限）
 */
function getReportByIdAndSession(id, sessionId) {
    const stmt = db.prepare(`
        SELECT * FROM reports 
        WHERE id = ? AND session_id = ?
    `);

    return stmt.get(id, sessionId);
}

/**
 * 更新报告（只能更新信号强度和备注）
 */
function updateReport(id, sessionId, data) {
    const stmt = db.prepare(`
        UPDATE reports 
        SET signal_strength = ?, notes = ?
        WHERE id = ? AND session_id = ?
    `);

    const result = stmt.run(
        data.signalStrength,
        data.notes,
        id,
        sessionId
    );

    if (result.changes > 0) {
        const selectStmt = db.prepare('SELECT * FROM reports WHERE id = ?');
        return selectStmt.get(id);
    }

    return null;
}

/**
 * 删除报告
 */
function deleteReport(id, sessionId) {
    const stmt = db.prepare(`
        DELETE FROM reports 
        WHERE id = ? AND session_id = ?
    `);

    const result = stmt.run(id, sessionId);
    return result.changes > 0;
}

/**
 * 管理员删除报告（无视session_id）
 */
function adminDeleteReport(id) {
    const stmt = db.prepare('DELETE FROM reports WHERE id = ?');
    const result = stmt.run(id);
    return result.changes > 0;
}


/**
 * 获取统计信息
 */
function getStats() {
    const countStmt = db.prepare('SELECT COUNT(*) as count FROM reports');
    const maxDistStmt = db.prepare('SELECT MAX(distance) as maxDistance FROM reports');

    const count = countStmt.get().count;
    const maxDistance = maxDistStmt.get().maxDistance || 0;

    return {
        totalReports: count,
        maxDistance: maxDistance
    };
}

// 初始化数据库
initDatabase();

module.exports = {
    getAllReports,
    getAllReportsWithCoords,
    createReport,
    getReportByIdAndSession,
    updateReport,
    deleteReport,
    adminDeleteReport,
    getStats
};
