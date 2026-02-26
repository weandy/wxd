"""审计日志路由"""

from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from web.middleware.auth import admin_required
from web.models.database import get_db

audit_logs_bp = Blueprint('audit_logs', __name__, url_prefix='/api/audit-logs')


@audit_logs_bp.route('', methods=['GET'])
@admin_required
def list_logs():
    """获取审计日志列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    action = request.args.get('action')
    user_id = request.args.get('user_id', type=int)
    days = request.args.get('days', 7, type=int)

    conn = get_db()
    cursor = conn.cursor()

    # 构建查询条件
    where_clauses = []
    params = []

    if action:
        where_clauses.append("action = ?")
        params.append(action)

    if user_id:
        where_clauses.append("user_id = ?")
        params.append(user_id)

    # 时间范围
    if days > 0:
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        where_clauses.append("timestamp > ?")
        params.append(cutoff)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    # 获取总数
    cursor.execute(f"SELECT COUNT(*) FROM audit_log WHERE {where_sql}", params)
    total = cursor.fetchone()[0]

    # 获取分页数据
    offset = (page - 1) * per_page
    cursor.execute(f"""
        SELECT * FROM audit_log WHERE {where_sql}
        ORDER BY timestamp DESC LIMIT ? OFFSET ?
    """, params + [per_page, offset])
    rows = cursor.fetchall()
    conn.close()

    return jsonify({
        'items': [dict(row) for row in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page
    })


@audit_logs_bp.route('/actions', methods=['GET'])
@admin_required
def list_actions():
    """获取所有操作类型"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT action FROM audit_log ORDER BY action")
    actions = [row[0] for row in cursor.fetchall()]
    conn.close()
    return jsonify({'actions': actions})


@audit_logs_bp.route('/stats', methods=['GET'])
@admin_required
def get_stats():
    """获取审计统计"""
    days = request.args.get('days', 7, type=int)
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

    conn = get_db()
    cursor = conn.cursor()

    # 每日统计
    cursor.execute("""
        SELECT DATE(timestamp) as date, COUNT(*) as count
        FROM audit_log
        WHERE timestamp > ?
        GROUP BY DATE(timestamp)
        ORDER BY date DESC
    """, (cutoff,))
    daily = [{'date': row[0], 'count': row[1]} for row in cursor.fetchall()]

    # 操作类型统计
    cursor.execute("""
        SELECT action, COUNT(*) as count
        FROM audit_log
        WHERE timestamp > ?
        GROUP BY action
        ORDER BY count DESC
    """, (cutoff,))
    by_action = [{'action': row[0], 'count': row[1]} for row in cursor.fetchall()]

    conn.close()

    return jsonify({
        'daily': daily,
        'by_action': by_action
    })


@audit_logs_bp.route('/clear', methods=['POST'])
@admin_required
def clear_logs():
    """清理历史日志"""
    data = request.get_json() or {}
    days = data.get('days', 90)  # 保留天数

    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM audit_log WHERE timestamp < ?", (cutoff,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'deleted': deleted})
