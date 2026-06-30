"""Web 管理后台 — Flask REST API + 看板页面"""

import json
import os
from datetime import datetime
from flask import Flask, jsonify, request, render_template

from db import (
    init_db, add_task as db_add, update_task as db_update,
    delete_task as db_delete, get_task as db_get, query_tasks, get_stats,
    inspect_tasks, daily_report, weekly_report,
    get_member_workload, get_kanban_data, get_due_tasks,
    get_risk_tasks, search_tasks, get_completion_trend,
)
from config import TEAM_MEMBERS, HOST, WEB_PORT, DB_PATH, SVN_ENABLED

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "templates"))


# ═══════════════════════════════════════════
#  页面路由
# ═══════════════════════════════════════════

@app.route("/")
def index():
    """首页 — 渲染动态看板"""
    from db import get_kanban_data, weekly_report, get_member_workload
    from config import TEAM_MEMBERS

    kanban = get_kanban_data()
    weekly = weekly_report()

    # 融合 TEAM_MEMBERS 配置 + 负载数据
    workloads = {w["responsible"]: w for w in get_member_workload()}
    members = []
    for name, info in TEAM_MEMBERS.items():
        w = workloads.get(name, {})
        members.append({
            "name": name,
            "role": info["role"],
            "products": info["products"],
            "avatar_color": info["avatar_color"],
            "total_active": w.get("total_active", 0),
            "weighted_load": w.get("weighted_load", 0),
            "blocked_count": w.get("blocked_count", 0),
            "load_pct": min(100, round((w.get("weighted_load", 0) / 10) * 100)),
            "nearest_deadline": w.get("nearest_deadline", ""),
        })

    return render_template("index.html",
                           kanban=kanban,
                           weekly=weekly,
                           members=members,
                           risks=get_risk_tasks(),
                           total_tasks=sum(len(v) for v in kanban.values()))


# ═══════════════════════════════════════════
#  看板 / 数据 API
# ═══════════════════════════════════════════

@app.route("/api/kanban")
def api_kanban():
    """看板数据 — 按状态分组的任务"""
    project = request.args.get("project")
    responsible = request.args.get("responsible")
    data = get_kanban_data(project=project or None, responsible=responsible or None)
    return jsonify({"ok": True, "data": data})


@app.route("/api/tasks")
def api_tasks():
    """任务列表（支持过滤）"""
    params = {}
    for key in ("project", "responsible", "status"):
        val = request.args.get(key)
        if val:
            params[key] = val
    if request.args.get("include_done") == "true":
        params["include_done"] = True
    tasks = query_tasks(**params)
    return jsonify({"ok": True, "data": tasks, "count": len(tasks)})


@app.route("/api/tasks/<int:task_id>")
def api_get_task(task_id):
    """获取单条任务"""
    task = db_get(task_id)
    if not task:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    return jsonify({"ok": True, "data": task})


@app.route("/api/tasks", methods=["POST"])
def api_create_task():
    """创建任务"""
    data = request.get_json(force=True)
    if not data.get("task_detail"):
        return jsonify({"ok": False, "error": "task_detail 不能为空"}), 400

    tid = db_add(
        project_name=data.get("project_name", ""),
        task_detail=data["task_detail"],
        responsible=data.get("responsible", ""),
        deadline=data.get("deadline", ""),
        priority=data.get("priority", "P2中"),
        start_date=data.get("start_date", ""),
        notes=data.get("notes", ""),
    )
    task = db_get(tid)
    return jsonify({"ok": True, "data": task}), 201


@app.route("/api/tasks/<int:task_id>", methods=["PUT"])
def api_update_task(task_id):
    """更新任务"""
    data = request.get_json(force=True)
    allowed = {"project_name", "task_detail", "responsible",
               "start_date", "deadline", "status", "priority", "notes"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({"ok": False, "error": "无可更新字段"}), 400

    ok = db_update(task_id, **updates)
    if not ok:
        return jsonify({"ok": False, "error": "任务不存在或更新失败"}), 404
    return jsonify({"ok": True, "data": db_get(task_id)})


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def api_delete_task(task_id):
    """删除任务"""
    ok = db_delete(task_id)
    if not ok:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    return jsonify({"ok": True})


@app.route("/api/tasks/search")
def api_search_tasks():
    """搜索任务"""
    q = request.args.get("q", "")
    if not q:
        return jsonify({"ok": False, "error": "缺少 q 参数"}), 400
    results = search_tasks(q)
    return jsonify({"ok": True, "data": results, "count": len(results)})


# ═══════════════════════════════════════════
#  统计 / 分析 API
# ═══════════════════════════════════════════

@app.route("/api/stats")
def api_stats():
    """统计摘要"""
    return jsonify({"ok": True, "data": get_stats()})


@app.route("/api/stats/members")
def api_members():
    """团队成员+负载+产品映射（融合 DB 数据和 TEAM_MEMBERS 配置）"""
    workloads = {w["responsible"]: w for w in get_member_workload()}
    members = []
    for name, info in TEAM_MEMBERS.items():
        w = workloads.get(name, {})
        members.append({
            "name": name,
            "role": info["role"],
            "products": info["products"],
            "avatar_color": info["avatar_color"],
            "total_active": w.get("total_active", 0),
            "weighted_load": w.get("weighted_load", 0),
            "blocked_count": w.get("blocked_count", 0),
            "in_progress_count": w.get("in_progress_count", 0),
            "pending_count": w.get("pending_count", 0),
            "nearest_deadline": w.get("nearest_deadline", ""),
            # 负载百分比（按每个人最多承担 10 个权重单位）
            "load_pct": min(100, round((w.get("weighted_load", 0) / 10) * 100)),
        })
    return jsonify({"ok": True, "data": members})


@app.route("/api/stats/risks")
def api_risks():
    """风险扫描"""
    return jsonify({"ok": True, "data": get_risk_tasks()})


@app.route("/api/stats/due")
def api_due():
    """即将到期任务"""
    days = int(request.args.get("days", 7))
    return jsonify({"ok": True, "data": get_due_tasks(days=days)})


@app.route("/api/stats/trend")
def api_trend():
    """完成趋势"""
    days = int(request.args.get("days", 30))
    return jsonify({"ok": True, "data": get_completion_trend(days=days)})


# ═══════════════════════════════════════════
#  报告 API
# ═══════════════════════════════════════════

@app.route("/api/reports/daily")
def api_daily_report():
    """日报数据"""
    return jsonify({"ok": True, "data": daily_report()})


@app.route("/api/reports/weekly")
def api_weekly_report():
    """周报数据"""
    return jsonify({"ok": True, "data": weekly_report()})


@app.route("/api/reports/inspect")
def api_inspect():
    """巡检报告"""
    return jsonify({"ok": True, "data": inspect_tasks()})


# ═══════════════════════════════════════════
#  系统 API
# ═══════════════════════════════════════════

@app.route("/api/status")
def api_status():
    """系统状态"""
    stats = get_stats()
    tasks = query_tasks()
    risks = get_risk_tasks()
    return jsonify({
        "ok": True,
        "data": {
            "db_path": DB_PATH,
            "total_tasks": len(tasks),
            "risk_count": risks["total_risk"],
            "status_dist": {s["status"]: s["count"] for s in stats["by_status"]},
            "svn_enabled": SVN_ENABLED,
            "team_size": len(TEAM_MEMBERS),
            "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    })


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# ═══════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════

def main():
    init_db()
    print(f"🌐 Web 管理后台启动: http://{HOST}:{WEB_PORT}")
    print(f"   看板 API: http://localhost:{WEB_PORT}/api/kanban")
    print(f"   健康检查: http://localhost:{WEB_PORT}/health")
    app.run(host=HOST, port=WEB_PORT, debug=True)


if __name__ == "__main__":
    main()
