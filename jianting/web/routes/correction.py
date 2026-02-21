"""纠错规则管理路由"""
import json
import sqlite3
from flask import Blueprint, render_template, request, jsonify
from web.middleware.auth import token_required, admin_required
from web.models.database import get_db_path

correction_bp = Blueprint('correction', __name__, url_prefix='/correction')


def get_db():
    """获取数据库连接"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@correction_bp.route('/')
@token_required
def index():
    """纠错规则管理页面"""
    return render_template('correction.html')


@correction_bp.route('/api/rules', methods=['GET'])
@token_required
def get_rules():
    """获取所有纠错规则"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, wrong_text, correct_text, category, enabled, priority, updated_at
            FROM correction_rules
            ORDER BY priority DESC, id ASC
        """)
        rules = [dict(row) for row in cursor.fetchall()]
        return jsonify({'success': True, 'rules': rules})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()


@correction_bp.route('/api/rules', methods=['POST'])
@admin_required
def add_rule():
    """添加纠错规则"""
    data = request.get_json()
    wrong_text = data.get('wrong_text', '').strip()
    correct_text = data.get('correct_text', '').strip()
    category = data.get('category', 'general')
    priority = int(data.get('priority', 0))

    if not wrong_text or not correct_text:
        return jsonify({'success': False, 'error': '源文本和目标文本不能为空'})

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO correction_rules (wrong_text, correct_text, category, priority)
            VALUES (?, ?, ?, ?)
        """, (wrong_text, correct_text, category, priority))
        conn.commit()
        rule_id = cursor.lastrowid
        return jsonify({'success': True, 'id': rule_id})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'error': '该规则已存在'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()


@correction_bp.route('/api/rules/<int:rule_id>', methods=['PUT'])
@admin_required
def update_rule(rule_id):
    """更新纠错规则"""
    data = request.get_json()
    wrong_text = data.get('wrong_text', '').strip()
    correct_text = data.get('correct_text', '').strip()
    category = data.get('category', 'general')
    priority = int(data.get('priority', 0))
    enabled = 1 if data.get('enabled', True) else 0

    if not wrong_text or not correct_text:
        return jsonify({'success': False, 'error': '源文本和目标文本不能为空'})

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE correction_rules
            SET wrong_text = ?, correct_text = ?, category = ?, priority = ?, enabled = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (wrong_text, correct_text, category, priority, enabled, rule_id))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': '规则不存在'})
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'error': '该规则已存在'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()


@correction_bp.route('/api/rules/<int:rule_id>', methods=['DELETE'])
@admin_required
def delete_rule(rule_id):
    """删除纠错规则"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM correction_rules WHERE id = ?", (rule_id,))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': '规则不存在'})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()


@correction_bp.route('/api/rules/toggle/<int:rule_id>', methods=['POST'])
@admin_required
def toggle_rule(rule_id):
    """启用/禁用纠错规则"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE correction_rules
            SET enabled = CASE WHEN enabled = 1 THEN 0 ELSE 1 END, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (rule_id,))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': '规则不存在'})
        # 获取最新状态
        cursor.execute("SELECT enabled FROM correction_rules WHERE id = ?", (rule_id,))
        enabled = cursor.fetchone()['enabled']
        return jsonify({'success': True, 'enabled': enabled})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()


@correction_bp.route('/api/rules/import', methods=['POST'])
@admin_required
def import_rules():
    """批量导入纠错规则"""
    data = request.get_json()
    rules = data.get('rules', [])

    if not rules:
        return jsonify({'success': False, 'error': '没有要导入的规则'})

    conn = get_db()
    imported = 0
    skipped = 0
    errors = []
    try:
        cursor = conn.cursor()
        for rule in rules:
            wrong_text = rule.get('wrong_text', '').strip()
            correct_text = rule.get('correct_text', '').strip()
            category = rule.get('category', 'general')
            priority = int(rule.get('priority', 0))

            if not wrong_text or not correct_text:
                skipped += 1
                continue

            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO correction_rules (wrong_text, correct_text, category, priority)
                    VALUES (?, ?, ?, ?)
                """, (wrong_text, correct_text, category, priority))
                if cursor.rowcount > 0:
                    imported += 1
                else:
                    skipped += 1
            except Exception as e:
                errors.append(f"{wrong_text}: {str(e)}")

        conn.commit()
        return jsonify({
            'success': True,
            'imported': imported,
            'skipped': skipped,
            'errors': errors[:10]  # 只返回前10个错误
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()


@correction_bp.route('/api/rules/export', methods=['GET'])
@token_required
def export_rules():
    """导出所有纠错规则"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT wrong_text, correct_text, category, priority
            FROM correction_rules
            ORDER BY priority DESC, id ASC
        """)
        rules = [dict(row) for row in cursor.fetchall()]
        return jsonify({'success': True, 'rules': rules})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()


# 全局函数：获取纠错规则（供 smart_processor 调用）
def get_correction_rules() -> dict:
    """获取所有启用的纠错规则"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT wrong_text, correct_text
            FROM correction_rules
            WHERE enabled = 1
            ORDER BY priority DESC
        """)
        rules = {row['wrong_text']: row['correct_text'] for row in cursor.fetchall()}
        return rules
    except Exception:
        return {}
    finally:
        conn.close()
