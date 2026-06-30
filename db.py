"""数据库层 — SQLite 任务存储 + AI 调度查询"""

import sqlite3
import os
from datetime import datetime, timedelta
from config import DB_PATH

# 字段常量（硬约束）
VALID_STATUSES = ['待开始', '进行中', '已完成', '阻塞延期']
VALID_PRIORITIES = ['P0紧急', 'P1高', 'P2中', 'P3低']
STATUS_ACTIVE = ['待开始', '进行中', '阻塞延期']
PRIORITY_ORDER = {'P0紧急': 1, 'P1高': 2, 'P2中': 3, 'P3低': 4}


def get_connection():
    """获取数据库连接，自动启用 WAL 模式"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name    TEXT    NOT NULL DEFAULT '',
            task_detail     TEXT    NOT NULL DEFAULT '',
            responsible     TEXT    NOT NULL DEFAULT '',
            start_date      TEXT    DEFAULT '',
            deadline        TEXT    DEFAULT '',
            status          TEXT    NOT NULL DEFAULT '待开始',
            priority        TEXT    NOT NULL DEFAULT 'P2中',
            notes           TEXT    DEFAULT '',
            created_at      TEXT    DEFAULT (datetime('now','localtime')),
            updated_at      TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()
    conn.close()


# ─── 基础 CRUD ───

def query_tasks(project=None, responsible=None, status=None, include_done=False):
    """
    查询任务列表
    """
    conn = get_connection()
    conditions = []
    params = []

    if project:
        conditions.append("project_name LIKE ?")
        params.append(f"%{project}%")
    if responsible:
        conditions.append("responsible LIKE ?")
        params.append(f"%{responsible}%")
    if status:
        conditions.append("status = ?")
        params.append(status)
    if not include_done:
        conditions.append("status IN ('待开始', '进行中', '阻塞延期')")

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"""
        SELECT * FROM tasks
        {where}
        ORDER BY
            CASE priority WHEN 'P0紧急' THEN 1 WHEN 'P1高' THEN 2 WHEN 'P2中' THEN 3 WHEN 'P3低' THEN 4 END,
            deadline ASC,
            id DESC
    """
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_task(project_name="", task_detail="", responsible="",
             deadline="", priority="P2中", start_date="", notes=""):
    """添加任务，返回新任务的 id"""
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO tasks (project_name, task_detail, responsible,
                           start_date, deadline, priority, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (project_name, task_detail, responsible, start_date, deadline, priority, notes))
    conn.commit()
    task_id = cur.lastrowid
    conn.close()
    return task_id


def update_task(task_id, **kwargs):
    """更新任务字段"""
    if not kwargs:
        return False
    allowed = {'project_name', 'task_detail', 'responsible', 'start_date',
               'deadline', 'status', 'priority', 'notes'}
    set_parts = []
    values = []
    for k, v in kwargs.items():
        if k not in allowed:
            continue
        set_parts.append(f"{k} = ?")
        values.append(v)
    set_parts.append("updated_at = datetime('now','localtime')")
    if not values:
        return False

    conn = get_connection()
    cur = conn.execute(f"UPDATE tasks SET {', '.join(set_parts)} WHERE id = ?",
                       values + [task_id])
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return changed > 0


def delete_task(task_id):
    """删除任务"""
    conn = get_connection()
    cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


def get_task(task_id):
    """获取单条任务"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_stats():
    """返回统计信息"""
    conn = get_connection()
    by_status = [dict(r) for r in conn.execute(
        "SELECT status, COUNT(*) as count FROM tasks GROUP BY status"
    ).fetchall()]
    by_project = [dict(r) for r in conn.execute(
        "SELECT project_name, COUNT(*) as count FROM tasks GROUP BY project_name"
    ).fetchall()]
    by_person = [dict(r) for r in conn.execute(
        "SELECT responsible, COUNT(*) as count FROM tasks "
        "WHERE status IN ('待开始','进行中','阻塞延期') GROUP BY responsible"
    ).fetchall()]
    by_priority = [dict(r) for r in conn.execute(
        "SELECT priority, COUNT(*) as count FROM tasks "
        "WHERE status IN ('待开始','进行中','阻塞延期') GROUP BY priority "
        "ORDER BY CASE priority "
        "WHEN 'P0紧急' THEN 1 WHEN 'P1高' THEN 2 WHEN 'P2中' THEN 3 WHEN 'P3低' THEN 4 END"
    ).fetchall()]
    conn.close()
    return {
        "by_status": by_status,
        "by_project": by_project,
        "by_person": by_person,
        "by_priority": by_priority,
    }


# ─── AI 调度分析 ───

def inspect_tasks():
    """部门任务巡检 — 五维扫描 + 调度建议"""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()

    overdue = [dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE deadline != '' AND deadline < ? "
        "AND status != '已完成' ORDER BY deadline ASC",
        (today,)
    ).fetchall()]

    due_today = [dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE deadline = ? AND status != '已完成' "
        "ORDER BY CASE priority "
        "WHEN 'P0紧急' THEN 1 WHEN 'P1高' THEN 2 WHEN 'P2中' THEN 3 WHEN 'P3低' THEN 4 END",
        (today,)
    ).fetchall()]

    high_prio_idle = [dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE priority IN ('P0紧急','P1高') "
        "AND status = '待开始' "
        "ORDER BY CASE priority "
        "WHEN 'P0紧急' THEN 1 WHEN 'P1高' THEN 2 END, deadline"
    ).fetchall()]

    blocked = [dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE status = '阻塞延期' ORDER BY updated_at ASC"
    ).fetchall()]

    no_deadline = [dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE deadline = '' "
        "AND status IN ('待开始','进行中') "
        "ORDER BY CASE priority "
        "WHEN 'P0紧急' THEN 1 WHEN 'P1高' THEN 2 WHEN 'P2中' THEN 3 WHEN 'P3低' THEN 4 END"
    ).fetchall()]

    conn.close()

    suggestions = []
    if high_prio_idle:
        suggestions.append(
            f"🔴 P0/P1 任务 {len(high_prio_idle)} 条未启动，建议今日启动")
    if due_today:
        suggestions.append(
            f"🟡 {len(due_today)} 条任务今日到期，请确认进度")
    if overdue:
        suggestions.append(
            f"🔴 {len(overdue)} 条任务已延期，需重新评估截止日期或加速推进")
    if blocked:
        three_days_ago = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        old_blocked = [t for t in blocked
                       if (t.get('updated_at', '') or '')[:10] < three_days_ago]
        if old_blocked:
            suggestions.append(
                f"🔴 {len(old_blocked)} 条阻塞任务超过 3 天，建议协调解除阻塞")
    if no_deadline:
        suggestions.append(
            f"⚪ {len(no_deadline)} 条活跃任务缺少截止日期，建议补充")

    return {
        "overdue": overdue,
        "due_today": due_today,
        "high_prio_idle": high_prio_idle,
        "blocked": blocked,
        "no_deadline": no_deadline,
        "suggestions": suggestions,
    }


def daily_report():
    """生成部门日报数据"""
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    conn = get_connection()

    completed_today = [dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE status = '已完成' AND date(updated_at) = ? "
        "ORDER BY updated_at DESC", (today,)
    ).fetchall()]

    created_today = [dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE date(created_at) = ? "
        "ORDER BY created_at DESC", (today,)
    ).fetchall()]

    in_progress = [dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE status IN ('待开始','进行中') "
        "ORDER BY CASE priority "
        "WHEN 'P0紧急' THEN 1 WHEN 'P1高' THEN 2 WHEN 'P2中' THEN 3 WHEN 'P3低' THEN 4 END, deadline"
    ).fetchall()]

    due_tomorrow = [dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE deadline = ? AND status != '已完成' "
        "ORDER BY CASE priority "
        "WHEN 'P0紧急' THEN 1 WHEN 'P1高' THEN 2 WHEN 'P2中' THEN 3 WHEN 'P3低' THEN 4 END",
        (tomorrow,)
    ).fetchall()]

    blocked_tasks = [dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE status = '阻塞延期' ORDER BY updated_at"
    ).fetchall()]

    due_today_unfinished = [dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE deadline = ? AND status NOT IN ('已完成')",
        (today,)
    ).fetchall()]

    conn.close()
    return {
        "completed_today": completed_today,
        "created_today": created_today,
        "in_progress": in_progress,
        "due_tomorrow": due_tomorrow,
        "blocked_tasks": blocked_tasks,
        "due_today_unfinished": due_today_unfinished,
    }


def weekly_report():
    """生成部门周报数据"""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    monday_str = monday.strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")
    week_label = f"{monday.year}-W{monday.isocalendar()[1]:02d}"

    conn = get_connection()

    completed_this_week = [dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE status = '已完成' "
        "AND date(updated_at) BETWEEN ? AND ? ORDER BY updated_at DESC",
        (monday_str, today_str)
    ).fetchall()]

    created_this_week = [dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE date(created_at) BETWEEN ? AND ? "
        "ORDER BY created_at DESC",
        (monday_str, today_str)
    ).fetchall()]

    active_tasks = [dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE status IN ('待开始','进行中','阻塞延期') "
        "ORDER BY CASE priority "
        "WHEN 'P0紧急' THEN 1 WHEN 'P1高' THEN 2 WHEN 'P2中' THEN 3 WHEN 'P3低' THEN 4 END, deadline"
    ).fetchall()]

    blocked = [dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE status = '阻塞延期' ORDER BY updated_at"
    ).fetchall()]

    high_prio_active = [dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE priority IN ('P0紧急','P1高') "
        "AND status IN ('待开始','进行中') "
        "ORDER BY CASE priority "
        "WHEN 'P0紧急' THEN 1 WHEN 'P1高' THEN 2 END, deadline"
    ).fetchall()]

    projects = {}
    for t in active_tasks:
        pn = t['project_name'] or '(未分类)'
        if pn not in projects:
            projects[pn] = {'total': 0, '进行中': 0, '待开始': 0, '阻塞延期': 0}
        projects[pn]['total'] += 1
        st = t['status']
        if st in projects[pn]:
            projects[pn][st] += 1

    conn.close()
    return {
        "week_label": week_label,
        "completed_this_week": completed_this_week,
        "created_this_week": created_this_week,
        "active_tasks": active_tasks,
        "blocked": blocked,
        "high_prio_active": high_prio_active,
        "projects": projects,
    }


# ─── Web 后台扩展查询 ───

def get_member_workload():
    """团队成员负载分析：按责任人统计活跃任务数 + 优先级加权负载"""
    conn = get_connection()
    rows = conn.execute("""
        SELECT responsible,
               COUNT(*) as total_active,
               SUM(CASE WHEN priority = 'P0紧急' THEN 4
                        WHEN priority = 'P1高' THEN 3
                        WHEN priority = 'P2中' THEN 2
                        WHEN priority = 'P3低' THEN 1 ELSE 1 END) as weighted_load,
               SUM(CASE WHEN status = '阻塞延期' THEN 1 ELSE 0 END) as blocked_count,
               SUM(CASE WHEN status = '进行中' THEN 1 ELSE 0 END) as in_progress_count,
               SUM(CASE WHEN status = '待开始' THEN 1 ELSE 0 END) as pending_count,
               MIN(CASE WHEN deadline != '' THEN deadline END) as nearest_deadline
        FROM tasks
        WHERE status IN ('待开始', '进行中', '阻塞延期')
        GROUP BY responsible
        ORDER BY weighted_load DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_kanban_data(project=None, responsible=None):
    """按状态分组返回看板数据，供 Web 5列看板使用"""
    conn = get_connection()
    conditions = ["status IN ('待开始', '进行中', '已完成', '阻塞延期')"]
    params = []
    if project:
        conditions.append("project_name LIKE ?")
        params.append(f"%{project}%")
    if responsible:
        conditions.append("responsible LIKE ?")
        params.append(f"%{responsible}%")
    where = "WHERE " + " AND ".join(conditions)

    rows = conn.execute(f"""
        SELECT * FROM tasks {where}
        ORDER BY
            CASE priority WHEN 'P0紧急' THEN 1 WHEN 'P1高' THEN 2 WHEN 'P2中' THEN 3 WHEN 'P3低' THEN 4 END,
            deadline ASC, id DESC
    """, params).fetchall()
    conn.close()

    grouped = {"待开始": [], "进行中": [], "已完成": [], "阻塞延期": []}
    for r in rows:
        d = dict(r)
        status = d["status"]
        if status in grouped:
            grouped[status].append(d)
    return grouped


def get_due_tasks(days=7, include_done=False):
    """获取未来 N 天内到期的任务"""
    from datetime import datetime, timedelta
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    conn = get_connection()
    conditions = ["deadline != ''", "deadline >= ?", "deadline <= ?"]
    params = [today, end]
    if not include_done:
        conditions.append("status != '已完成'")
    rows = conn.execute(f"""
        SELECT * FROM tasks
        WHERE {' AND '.join(conditions)}
        ORDER BY deadline ASC,
            CASE priority WHEN 'P0紧急' THEN 1 WHEN 'P1高' THEN 2 WHEN 'P2中' THEN 3 WHEN 'P3低' THEN 4 END
    """, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_risk_tasks():
    """风险任务扫描：延期 + 高优未启动 + 阻塞超3天"""
    from datetime import datetime, timedelta
    today = datetime.now().strftime("%Y-%m-%d")
    three_days_ago = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")

    conn = get_connection()

    overdue = [dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE deadline != '' AND deadline < ? AND status != '已完成' "
        "ORDER BY deadline ASC", (today,)
    ).fetchall()]

    high_prio_idle = [dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE priority IN ('P0紧急','P1高') AND status = '待开始' "
        "ORDER BY CASE priority WHEN 'P0紧急' THEN 1 WHEN 'P1高' THEN 2 END, deadline"
    ).fetchall()]

    blocked_stale = [dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE status = '阻塞延期' AND updated_at < ? "
        "ORDER BY updated_at ASC", (three_days_ago,)
    ).fetchall()]

    conn.close()
    return {
        "overdue": overdue,
        "high_prio_idle": high_prio_idle,
        "blocked_stale": blocked_stale,
        "total_risk": len(overdue) + len(high_prio_idle) + len(blocked_stale),
    }


def get_product_tasks(product_code: str):
    """按产品编号查询关联任务（精确匹配项目名）"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM tasks WHERE project_name = ? ORDER BY id DESC", (product_code,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_tasks(keyword: str, limit: int = 50):
    """全文搜索任务（匹配描述/项目名/备注/责任人）"""
    conn = get_connection()
    kw = f"%{keyword}%"
    rows = conn.execute("""
        SELECT * FROM tasks
        WHERE task_detail LIKE ? OR project_name LIKE ? OR notes LIKE ? OR responsible LIKE ?
        ORDER BY id DESC LIMIT ?
    """, (kw, kw, kw, kw, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_completion_trend(days: int = 30):
    """过去 N 天每日完成趋势"""
    from datetime import datetime, timedelta
    conn = get_connection()
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT date(updated_at) as day, COUNT(*) as count
        FROM tasks
        WHERE status = '已完成' AND date(updated_at) >= ?
        GROUP BY day ORDER BY day
    """, (start,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]