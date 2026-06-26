"""命令解析 — 将自然语言文本转为结构化操作"""

import re


# ─── 命令模式匹配 ───

PATTERNS = {
    "kanban": re.compile(r"^(看板|kanban|kb)\s*(全部|all|.+)?(?:$|\n)"),
    "my_tasks": re.compile(r"^(我的任务|mytasks|mt)\s*$"),
    "add": re.compile(r"^(添加|新增|add)\s+(.+)"),
    "update": re.compile(r"^(更新|修改|update)\s+#?(\d+)\s+(\S+)\s*(.*)"),
    "done": re.compile(r"^(完成|done|finish)\s+#?(\d+)"),
    "block": re.compile(r"^(阻塞|block)\s+#?(\d+)\s*(.*)"),
    "delete": re.compile(r"^(删除|del|delete|rm)\s+#?(\d+)"),
    "note": re.compile(r"^(备注|note|memo)\s+#?(\d+)\s+(.+)"),
    "stats": re.compile(r"^(统计|stats|summary)"),
    "inspect": re.compile(r"^(巡检|检查|inspect|scan)"),
    "daily": re.compile(r"^(日报|daily|今日报告)"),
    "weekly": re.compile(r"^(周报|weekly|本周报告)"),
    "help": re.compile(r"^(帮助|help|h|\?|？)"),
}


def parse_command(text: str, user_name: str = "") -> dict:
    """
    解析用户输入，返回结构化命令

    返回:
        {"action": "...", "params": {...}}
    """
    text = text.strip()

    # 看板
    m = PATTERNS["kanban"].match(text)
    if m:
        filter_arg = (m.group(2) or "").strip()
        params = {"include_done": False}
        if filter_arg in ("全部", "all"):
            params["include_done"] = True
        elif filter_arg:
            if filter_arg.startswith("@"):
                params["responsible"] = filter_arg[1:]
            else:
                params["project"] = filter_arg
        return {"action": "kanban", "params": params}

    # 我的任务
    m = PATTERNS["my_tasks"].match(text)
    if m:
        return {"action": "kanban", "params": {"responsible": user_name}}

    # 添加
    m = PATTERNS["add"].match(text)
    if m:
        return {"action": "add", "params": {"raw": m.group(2).strip()}}

    # 更新
    m = PATTERNS["update"].match(text)
    if m:
        return {"action": "update", "params": {
            "task_id": int(m.group(2)),
            "field": m.group(3),
            "value": m.group(4).strip(),
        }}

    # 完成
    m = PATTERNS["done"].match(text)
    if m:
        return {"action": "done", "params": {"task_id": int(m.group(2))}}

    # 阻塞
    m = PATTERNS["block"].match(text)
    if m:
        return {"action": "block", "params": {
            "task_id": int(m.group(2)),
            "reason": m.group(3).strip(),
        }}

    # 删除
    m = PATTERNS["delete"].match(text)
    if m:
        return {"action": "delete", "params": {"task_id": int(m.group(2))}}

    # 备注
    m = PATTERNS["note"].match(text)
    if m:
        return {"action": "note", "params": {
            "task_id": int(m.group(2)),
            "content": m.group(3).strip(),
        }}

    # 统计
    m = PATTERNS["stats"].match(text)
    if m:
        return {"action": "stats", "params": {}}

    # 巡检
    m = PATTERNS["inspect"].match(text)
    if m:
        return {"action": "inspect", "params": {}}

    # 日报
    m = PATTERNS["daily"].match(text)
    if m:
        return {"action": "daily", "params": {}}

    # 周报
    m = PATTERNS["weekly"].match(text)
    if m:
        return {"action": "weekly", "params": {}}

    # 帮助
    m = PATTERNS["help"].match(text)
    if m:
        return {"action": "help", "params": {}}

    return {"action": "unknown", "params": {}}


# ─── 添加任务的高级解析 ───

def parse_add_task(raw: str) -> dict:
    """
    从自由文本中提取任务字段
    示例: "产品A 需求评审 @张三 截止2025-06-30 P1高"
    """
    result = {
        "project_name": "",
        "task_detail": "",
        "responsible": "",
        "start_date": "",
        "deadline": "",
        "priority": "P2中",
    }

    # 提取 @责任人
    m = re.search(r"@(\S+)", raw)
    if m:
        result["responsible"] = m.group(1)
        raw = raw.replace(m.group(0), "").strip()

    # 提取优先级（P0紧急 / P1高 / P2中 / P3低）
    m = re.search(r"(P[0-3](?:紧急|高|中|低))\s*$", raw)
    if m:
        result["priority"] = m.group(1)
        raw = raw[:m.start()].strip()

    # 提取截止日期 YYYY-MM-DD
    m = re.search(r"截止[:\s]*(\d{4}-\d{2}-\d{2})", raw)
    if m:
        result["deadline"] = m.group(1)
        raw = raw.replace(m.group(0), "").strip()

    # 提取开始日期
    m = re.search(r"开始[:\s]*(\d{4}-\d{2}-\d{2})", raw)
    if m:
        result["start_date"] = m.group(1)
        raw = raw.replace(m.group(0), "").strip()

    # 剩余：项目名 + 任务描述（第一个空格分割）
    remaining = raw.strip()
    if " " in remaining or "\u3000" in remaining:
        parts = remaining.split(None, 1)
        result["project_name"] = parts[0]
        result["task_detail"] = parts[1] if len(parts) > 1 else ""
    else:
        result["task_detail"] = remaining

    return result


# ─── 字段名映射 ───

FIELD_ALIASES = {
    "状态": "status", "status": "status",
    "优先级": "priority", "priority": "priority",
    "截止": "deadline", "deadline": "deadline",
    "开始": "start_date", "start_date": "start_date",
    "责任人": "responsible", "responsible": "responsible",
    "项目": "project_name", "project": "project_name",
    "备注": "notes", "notes": "notes",
    "任务": "task_detail", "detail": "task_detail",
}


def normalize_field(field: str) -> str:
    """将中文/英文字段名标准化为数据库列名"""
    return FIELD_ALIASES.get(field, field.lower())