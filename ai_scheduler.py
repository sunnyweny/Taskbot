"""AI 调度建议 — 基于规则 + 数据库数据生成建议

无需外部 AI API 调用，纯本地计算。
需要 AI 增强时可通过 Hermes agent 或 cronjob 调用。
"""

from datetime import datetime, timedelta
from db import (
    get_member_workload, get_risk_tasks, get_due_tasks, inspect_tasks,
)
from config import (
    TEAM_MEMBERS, AI_HIGH_LOAD_THRESHOLD, AI_OVERDUE_WARN_DAYS, AI_BLOCKED_STALE_DAYS,
)


def compute_workload_suggestions() -> list:
    """负载均衡建议：当成员负载超过阈值时生成建议"""
    workloads = get_member_workload()
    suggestions = []

    # 按负载排序
    high_load = [w for w in workloads
                 if w["weighted_load"] >= 3 and w["responsible"] in TEAM_MEMBERS]
    low_load = [w for w in workloads
                if w["weighted_load"] <= 1 and w["responsible"] in TEAM_MEMBERS
                and w["responsible"] not in [hw["responsible"] for hw in high_load]]

    for member in high_load:
        load_pct = min(100, round((member["weighted_load"] / 10) * 100))
        if load_pct >= AI_HIGH_LOAD_THRESHOLD:
            name = member["responsible"]
            role = TEAM_MEMBERS.get(name, {}).get("role", "")
            # 找到负载最低的人作为建议接收方
            target = low_load[0]["responsible"] if low_load else "其他同事"
            suggestions.append({
                "type": "负载均衡",
                "confidence": min(90, load_pct + 10),
                "title": f"{name} 负载偏高",
                "description": (
                    f"{name}（{role}）当前活跃 {member['total_active']} 项任务，"
                    f"负载 {load_pct}%，建议评估是否可将非紧急任务转移至 {target}"
                ),
            })

    return suggestions


def compute_overdue_suggestions() -> list:
    """延期预警建议"""
    insp = inspect_tasks()
    suggestions = []

    for task in insp.get("overdue", []):
        if task.get("deadline"):
            days_overdue = (datetime.now() - datetime.strptime(task["deadline"], "%Y-%m-%d")).days
            if days_overdue >= AI_OVERDUE_WARN_DAYS:
                suggestions.append({
                    "type": "延期预警",
                    "confidence": min(90, 70 + days_overdue * 2),
                    "title": f"#{task['id']} {task['task_detail'][:30]} 已延期 {days_overdue} 天",
                    "description": (
                        f"责任人: {task['responsible']} | 优先级: {task['priority']} | "
                        f"原计划截止 {task['deadline']}，建议确认原因并更新截止日期"
                    ),
                })

    # 即将到期预警
    due_soon = get_due_tasks(days=AI_OVERDUE_WARN_DAYS)
    for task in due_soon:
        suggestions.append({
            "type": "到期预警",
            "confidence": 80,
            "title": f"#{task['id']} {task['task_detail'][:30]} 即将到期",
            "description": (
                f"责任人: {task['responsible']} | 优先级: {task['priority']} | "
                f"截止 {task['deadline']}，请确认进度"
            ),
        })

    return suggestions


def compute_blocked_suggestions() -> list:
    """阻塞升级建议"""
    insp = inspect_tasks()
    suggestions = []
    three_days_ago = (datetime.now() - timedelta(days=AI_BLOCKED_STALE_DAYS)).strftime("%Y-%m-%d")

    for task in insp.get("blocked", []):
        updated = task.get("updated_at", "")[:10]
        if updated and updated < three_days_ago:
            stale_days = (datetime.now() - datetime.strptime(updated, "%Y-%m-%d")).days
            suggestions.append({
                "type": "阻塞升级",
                "confidence": min(92, 75 + stale_days * 2),
                "title": f"#{task['id']} {task['task_detail'][:30]} 阻塞 {stale_days} 天未更新",
                "description": (
                    f"责任人: {task['responsible']} | 优先级: {task['priority']} | "
                    f"建议协调整合资源解除阻塞，或发起专项讨论"
                ),
            })

    return suggestions


def compute_idle_priority_suggestions() -> list:
    """高优未启动建议"""
    insp = inspect_tasks()
    suggestions = []

    for task in insp.get("high_prio_idle", []):
        suggestions.append({
            "type": "启动建议",
            "confidence": 85,
            "title": f"#{task['id']} {task['task_detail'][:30]}",
            "description": (
                f"{task['priority']} 任务尚未启动，责任人: {task['responsible']} | "
                f"{'截止 ' + task['deadline'] if task.get('deadline') else '无截止日期'}，"
                f"建议今日分配资源启动"
            ),
        })

    return suggestions


def compute_all_suggestions() -> dict:
    """汇总所有 AI 调度建议"""
    all_suggestions = (
        compute_workload_suggestions()
        + compute_overdue_suggestions()
        + compute_blocked_suggestions()
        + compute_idle_priority_suggestions()
    )

    # 按置信度降序
    all_suggestions.sort(key=lambda s: s["confidence"], reverse=True)

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(all_suggestions),
        "suggestions": all_suggestions,
        "summary": {
            "workload": len(compute_workload_suggestions()),
            "overdue": len(compute_overdue_suggestions()),
            "blocked": len(compute_blocked_suggestions()),
            "idle": len(compute_idle_priority_suggestions()),
        },
    }


def format_suggestions_markdown(suggestions: dict) -> str:
    """将建议格式化为 Markdown 文本（用于企微推送）"""
    if not suggestions.get("suggestions"):
        return "✅ 当前无调度建议，一切正常"

    lines = ["🤖 AI 调度建议\n"]
    for i, s in enumerate(suggestions["suggestions"][:8], 1):
        emoji = {
            "负载均衡": "⚖️",
            "延期预警": "🔴",
            "到期预警": "🟡",
            "阻塞升级": "🚫",
            "启动建议": "🔥",
        }.get(s["type"], "📌")
        lines.append(f"{i}. {emoji} [{s['type']}] {s['title']}")
        lines.append(f"> {s['description']}\n")
        lines.append("")

    if len(suggestions["suggestions"]) > 8:
        lines.append(f"> 还有 {len(suggestions['suggestions']) - 8} 条建议，请查看 Web 后台")

    return "\n".join(lines)
