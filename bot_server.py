"""主服务入口 — 企微机器人消息处理 + markdown 渲染"""

from datetime import datetime
from wecom_bot_svr import WecomBotServer, RspTextMsg
from wecom_bot_svr.rsp_msg import RspMsg
from wecom_bot_svr.req_msg import ReqMsg

from db import init_db, add_task as db_add, update_task as db_update
from db import delete_task as db_delete, get_task as db_get, query_tasks, get_stats
from db import inspect_tasks, daily_report, weekly_report
from commands import parse_command, parse_add_task, normalize_field
from config import TOKEN, AES_KEY, CORP_ID, BOT_KEY, HOST, PORT, BOT_PATH, BOT_NAME


# ═══════════════════════════════════════════
#  自定义 MarkdownV2 消息类型（支持表格）
# ═══════════════════════════════════════════

class RspMarkdownV2Msg(RspMsg):
    def __init__(self, content=""):
        super().__init__()
        self.msg_type = 'markdown_v2'
        self.content = content

    def update_xml(self):
        super().update_xml()
        self.insert_elem('MarkdownV2/Content', self.content)


# ═══════════════════════════════════════════
#  渲染函数
# ═══════════════════════════════════════════

def render_kanban(tasks: list, title: str = "📋 任务看板") -> str:
    """将任务列表渲染为企微 markdown_v2 表格"""
    if not tasks:
        return f"# {title}\n\n> 暂无匹配任务"

    def p_icon(p):
        return {"P0紧急": "🔴", "P1高": "🟠", "P2中": "🟡", "P3低": "🟢"}.get(p, "⚪")

    rows = []
    rows.append("| # | 详细任务 | 责任人 | 开始 | 截止 | 状态 | 优先级 | 备注 |")
    rows.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")

    for t in tasks:
        tid = t['id']
        detail = (t["task_detail"] or "-")[:25]
        resp = t["responsible"] or "-"
        start = t.get("start_date") or "-"
        deadline = t.get("deadline") or "-"
        status = t["status"]
        prio = f"{p_icon(t['priority'])}{t['priority']}"
        notes = (t.get("notes") or "-")[:15]
        rows.append(
            f"| {tid} | {detail} | {resp} "
            f"| {start} | {deadline} | {status} "
            f"| {prio} | {notes} |"
        )

    total = len(tasks)
    p0 = sum(1 for t in tasks if t['priority'] == 'P0紧急')
    p1 = sum(1 for t in tasks if t['priority'] == 'P1高')
    p2 = sum(1 for t in tasks if t['priority'] == 'P2中')
    p3 = sum(1 for t in tasks if t['priority'] == 'P3低')
    blocked = sum(1 for t in tasks if t['status'] == '阻塞延期')
    stats_line = f"> 共 {total} 条 | P0:{p0} P1:{p1} P2:{p2} P3:{p3}"
    if blocked:
        stats_line += f" | ⚠️阻塞:{blocked}"

    return f"# {title}\n\n" + "\n".join(rows) + "\n\n" + stats_line


def render_stats(stats: dict) -> str:
    """渲染统计信息"""
    lines = ["# 📊 任务统计\n"]

    lines.append("## 按状态")
    for item in stats["by_status"]:
        lines.append(f"- {item['status']}: {item['count']} 条")

    lines.append("")
    lines.append("## 按优先级（活跃任务）")
    for item in stats.get("by_priority", []):
        lines.append(f"- {item['priority']}: {item['count']} 条")

    if stats.get("by_project"):
        lines.append("")
        lines.append("## 按项目")
        for item in stats["by_project"]:
            name = item["project_name"] or "(未分类)"
            lines.append(f"- {name}: {item['count']} 条")

    if stats.get("by_person"):
        lines.append("")
        lines.append("## 按责任人（活跃任务）")
        for item in stats["by_person"]:
            lines.append(f"- {item['responsible']}: {item['count']} 条")

    return "\n".join(lines)


def render_inspect(result: dict) -> str:
    """渲染巡检报告"""
    lines = ["# 🔍 部门任务巡检报告", ""]

    sections = [
        ("❌ 延期任务", "overdue"),
        ("⏰ 今日到期", "due_today"),
        ("🔴 P0/P1 未启动", "high_prio_idle"),
        ("🚫 阻塞任务", "blocked"),
        ("⚪ 无截止日期", "no_deadline"),
    ]

    for label, key in sections:
        items = result[key]
        if items:
            lines.append(f"## {label} ({len(items)} 条)")
            limit = 5 if key != "no_deadline" else 3
            for t in items[:limit]:
                dl = f" | 截止 {t['deadline']}" if t.get('deadline') else ""
                note = f" | {t.get('notes','')[:30]}" if t.get('notes') else ""
                lines.append(
                    f"- #{t['id']} {t['task_detail']} "
                    f"| {t['responsible']}"
                    f"{dl}"
                    f"{note}"
                )
            if len(items) > limit:
                lines.append(f"  > 还有 {len(items) - limit} 条...")
            lines.append("")
        else:
            lines.append(f"## ✅ {label}: 0")
            lines.append("")

    suggestions = result["suggestions"]
    if suggestions:
        lines.append("---")
        lines.append("## ⚠️ 调度提醒")
        for s in suggestions:
            lines.append(f"- {s}")
    else:
        lines.append("> ✅ 一切正常，无需调度干预")

    return "\n".join(lines)


def render_daily_report(data: dict) -> str:
    """渲染日报"""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"# 📋 部门日报 ({today})", ""]

    lines.append("## 今日概览")
    lines.append(f"- 完成: {len(data['completed_today'])} 条")
    lines.append(f"- 新增: {len(data['created_today'])} 条")
    lines.append(f"- 进行中: {len(data['in_progress'])} 条")
    lines.append("")

    completed = data["completed_today"]
    if completed:
        lines.append(f"## ✅ 今日完成 ({len(completed)} 条)")
        for t in completed:
            lines.append(f"- #{t['id']} {t['task_detail']} ({t['responsible']})")
        lines.append("")
    else:
        lines.append("## ✅ 今日完成: 0")
        lines.append("")

    due_tom = data["due_tomorrow"]
    if due_tom:
        lines.append("## 📅 明日计划")
        for t in due_tom[:10]:
            lines.append(
                f"- #{t['id']} {t['task_detail']} ({t['responsible']}) "
                f"截止 {t['deadline']} [{t['priority']}]")
        lines.append("")

    # 风险项
    risks = []
    for t in data["blocked_tasks"]:
        risks.append(
            f"- #{t['id']} {t['task_detail']} ({t['responsible']}) "
            f"阻塞延期: {t.get('notes','')[:30]}")
    for t in data["due_today_unfinished"]:
        risks.append(
            f"- #{t['id']} {t['task_detail']} ({t['responsible']}) "
            f"今日到期未完成")
    if risks:
        lines.append("## ⚠️ 风险项")
        lines.extend(risks)
        lines.append("")

    return "\n".join(lines)


def render_weekly_report(data: dict) -> str:
    """渲染周报"""
    lines = [f"# 📊 部门周报 {data['week_label']}", ""]

    lines.append(
        f"完成 {len(data['completed_this_week'])} 条 "
        f"| 新增 {len(data['created_this_week'])} 条 "
        f"| 剩余活跃 {len(data['active_tasks'])} 条")
    lines.append("")

    projects = data["projects"]
    if projects:
        lines.append("## 按项目")
        for pn, stats in sorted(projects.items()):
            detail = " / ".join(
                f"{k}:{v}" for k, v in stats.items() if k != 'total' and v > 0)
            lines.append(f"- **{pn}** ({stats['total']}条): {detail}")
        lines.append("")

    completed = data["completed_this_week"]
    if completed:
        lines.append(f"## ✅ 本周完成 ({len(completed)} 条)")
        for t in completed:
            lines.append(f"- #{t['id']} {t['task_detail']} ({t['responsible']})")
        lines.append("")

    blocked = data["blocked"]
    if blocked:
        lines.append(f"## 🚫 阻塞项 ({len(blocked)} 条)")
        for t in blocked:
            lines.append(
                f"- #{t['id']} {t['task_detail']} ({t['responsible']}): "
                f"{t.get('notes','')[:40]}")
        lines.append("")

    high = data["high_prio_active"]
    if high:
        lines.append("## 🎯 下周重点 (P0/P1)")
        for t in high:
            dl = f" 截止 {t['deadline']}" if t.get('deadline') else ""
            lines.append(
                f"- #{t['id']} {t['task_detail']} ({t['responsible']}) "
                f"[{t['priority']}]{dl}")
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════
#  帮助文本
# ═══════════════════════════════════════════

HELP_TEXT = """# 🤖 任务看板助手

## 📋 查询
- **看板** — 查看所有活跃任务
- **看板 全部** — 查看所有任务（含已完成）
- **看板 项目名** — 按项目筛选
- **看板 @人名** — 按责任人筛选
- **我的任务** — 查看我的任务

## ✏️ 操作（操作后自动刷新看板）
- **添加 项目名 任务描述 @责任人 截止YYYY-MM-DD P1高** — 添加任务
- **更新 #编号 字段 新值** — 修改任务
- **完成 #编号** — 标记完成
- **阻塞 #编号 原因** — 标记阻塞延期 + 备注原因
- **删除 #编号** — 删除任务
- **备注 #编号 内容** — 追加备注

## 🤖 AI 调度
- **巡检** — 部门任务巡检（延期/到期/阻塞/高优未启动 + 调度建议）
- **日报** — 部门日报（今日完成/新增/风险/明日计划）
- **周报** — 部门周报（本周概览/按项目/阻塞/下周重点）
- **统计** — 统计摘要

## 📌 字段规范
- 状态: 待开始 / 进行中 / 已完成 / 阻塞延期
- 优先级: P0紧急 / P1高 / P2中 / P3低
- 日期: YYYY-MM-DD

## 其他
- **帮助** — 显示本帮助"""


# ═══════════════════════════════════════════
#  消息处理器
# ═══════════════════════════════════════════

def msg_handler(req_msg: ReqMsg, server: WecomBotServer):
    """企业微信群机器人回调入口"""
    text = (req_msg.content or "").strip()
    user_name = req_msg.from_user or ""

    if not text:
        return RspMarkdownV2Msg(content=HELP_TEXT)

    cmd = parse_command(text, user_name)
    action = cmd["action"]
    params = cmd["params"]

    try:
        # ── 查询类 ──

        if action == "kanban":
            tasks = query_tasks(**params)
            title = "📋 任务看板"
            if params.get("project"):
                title = f"📋 任务看板 — {params['project']}"
            elif params.get("responsible"):
                title = f"📋 {params['responsible']} 的任务"
            if params.get("include_done"):
                title += " (全部)"
            return RspMarkdownV2Msg(content=render_kanban(tasks, title))

        # ── 操作类（generator → 确认 + 自动刷看板）──

        elif action == "add":
            info = parse_add_task(params["raw"])
            if not info["task_detail"]:
                return RspTextMsg(content=(
                    "❌ 请提供任务描述。\n"
                    "格式: 添加 项目名 任务描述 @责任人 截止YYYY-MM-DD P1高"))
            tid = db_add(**info)
            task = db_get(tid)

            def gen_add():
                yield RspMarkdownV2Msg(content=(
                    f"✅ 已添加 #{tid}: {task['task_detail']}\n"
                    f"项目: {task['project_name']} | 责任人: {task['responsible']} "
                    f"| 截止: {task['deadline'] or '-'} | {task['priority']}"))
                tasks = query_tasks()
                yield RspMarkdownV2Msg(content=render_kanban(tasks))
            return gen_add()

        elif action == "update":
            tid = params["task_id"]
            field = normalize_field(params["field"])
            value = params["value"]
            allowed = {'status', 'priority', 'deadline', 'start_date',
                       'responsible', 'project_name', 'task_detail', 'notes'}
            if field not in allowed:
                return RspTextMsg(content=(
                    f"❌ 不支持的字段: {params['field']}\n"
                    f"支持: 状态/优先级/截止/开始/责任人/项目/备注"))
            ok = db_update(tid, **{field: value})
            if ok:
                def gen_upd():
                    yield RspTextMsg(content=(
                        f"✅ 已更新 #{tid} 的 {params['field']} → {value}"))
                    tasks = query_tasks()
                    yield RspMarkdownV2Msg(content=render_kanban(tasks))
                return gen_upd()
            return RspTextMsg(content=f"❌ 未找到任务 #{tid}")

        elif action == "done":
            tid = params["task_id"]
            ok = db_update(tid, status="已完成")
            if ok:
                def gen_done():
                    yield RspTextMsg(content=f"✅ 任务 #{tid} 已标记为完成")
                    tasks = query_tasks()
                    yield RspMarkdownV2Msg(content=render_kanban(tasks))
                return gen_done()
            return RspTextMsg(content=f"❌ 未找到任务 #{tid}")

        elif action == "block":
            tid = params["task_id"]
            reason = params.get("reason", "")
            updates = {"status": "阻塞延期"}
            if reason:
                updates["notes"] = reason
            ok = db_update(tid, **updates)
            if ok:
                def gen_block():
                    yield RspTextMsg(content=f"🚫 任务 #{tid} 已标记为阻塞延期")
                    tasks = query_tasks()
                    yield RspMarkdownV2Msg(content=render_kanban(tasks))
                return gen_block()
            return RspTextMsg(content=f"❌ 未找到任务 #{tid}")

        elif action == "delete":
            tid = params["task_id"]
            task = db_get(tid)
            if not task:
                return RspTextMsg(content=f"❌ 未找到任务 #{tid}")
            db_delete(tid)

            def gen_del():
                yield RspTextMsg(
                    content=f"🗑️ 已删除 #{tid}: {task['task_detail']}")
                tasks = query_tasks()
                yield RspMarkdownV2Msg(content=render_kanban(tasks))
            return gen_del()

        elif action == "note":
            tid = params["task_id"]
            content = params["content"]
            ok = db_update(tid, notes=content)
            if ok:
                def gen_note():
                    yield RspTextMsg(content=f"✅ 已为 #{tid} 添加备注")
                    tasks = query_tasks()
                    yield RspMarkdownV2Msg(content=render_kanban(tasks))
                return gen_note()
            return RspTextMsg(content=f"❌ 未找到任务 #{tid}")

        # ── AI 调度类 ──

        elif action == "stats":
            s = get_stats()
            return RspMarkdownV2Msg(content=render_stats(s))

        elif action == "inspect":
            result = inspect_tasks()
            return RspMarkdownV2Msg(content=render_inspect(result))

        elif action == "daily":
            data = daily_report()
            return RspMarkdownV2Msg(content=render_daily_report(data))

        elif action == "weekly":
            data = weekly_report()
            return RspMarkdownV2Msg(content=render_weekly_report(data))

        elif action == "help":
            return RspMarkdownV2Msg(content=HELP_TEXT)

        else:
            return RspTextMsg(content=(
                f"🤔 未识别的命令。发送 **帮助** 查看可用命令。\n"
                f"收到: {text[:100]}"))

    except Exception as e:
        return RspTextMsg(content=f"❌ 出错了: {str(e)}")


# ═══════════════════════════════════════════
#  启动
# ═══════════════════════════════════════════

def main():
    init_db()
    server = WecomBotServer(
        BOT_NAME,
        HOST,
        PORT,
        path=BOT_PATH,
        token=TOKEN,
        aes_key=AES_KEY,
        corp_id=CORP_ID,
        bot_key=BOT_KEY,
    )
    server.set_message_handler(msg_handler)
    # 占位 handler — 企微要求必须设置
    server.set_event_handler(lambda req_msg, srv: RspTextMsg(content=""))
    print(f"🚀 任务看板机器人启动: http://{HOST}:{PORT}{BOT_PATH}")
    server.run()


if __name__ == "__main__":
    main()