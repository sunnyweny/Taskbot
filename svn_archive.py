"""SVN 周报归档 — 将系统生成的周报导出为 Markdown 文件并提交到公司 SVN"""

import os
import subprocess
import textwrap
from datetime import datetime, timedelta
from db import weekly_report
from config import (
    SVN_ENABLED, SVN_REPO_URL, SVN_WEEKLY_PATH,
    SVN_USERNAME, SVN_PASSWORD, SVN_WORK_COPY,
)


def generate_weekly_markdown() -> str:
    """从 dB 生成周报 Markdown 文本"""
    data = weekly_report()
    week_label = data["week_label"]
    today = datetime.now().strftime("%Y-%m-%d")

    md = f"""# 产品部周报 {week_label}

> 自动生成于 {today}

## 📊 概览

| 指标 | 数值 |
|------|------|
| 本周完成 | {len(data['completed_this_week'])} 项 |
| 本周新增 | {len(data['created_this_week'])} 项 |
| 剩余活跃 | {len(data['active_tasks'])} 项 |
| 阻塞延期 | {len(data['blocked'])} 项 |

"""

    # 按项目
    projects = data.get("projects", {})
    if projects:
        md += "## 📂 按项目\n\n"
        md += "| 项目 | 总数 | 进行中 | 待开始 | 阻塞 |\n"
        md += "|------|------|--------|--------|------|\n"
        for pn, stats in sorted(projects.items()):
            md += f"| {pn} | {stats['total']} | {stats.get('进行中',0)} | {stats.get('待开始',0)} | {stats.get('阻塞延期',0)} |\n"
        md += "\n"

    # 本周完成
    completed = data["completed_this_week"]
    if completed:
        md += f"## ✅ 本周完成（{len(completed)} 项）\n\n"
        for t in completed:
            md += f"- #{t['id']} {t['task_detail']} (@{t['responsible']})\n"
        md += "\n"
    else:
        md += "## ✅ 本周完成: 0\n\n"

    # 阻塞项
    blocked = data["blocked"]
    if blocked:
        md += f"## 🚫 阻塞项（{len(blocked)} 项）\n\n"
        for t in blocked:
            notes = t.get('notes', '')
            md += f"- #{t['id']} {t['task_detail']} (@{t['responsible']})"
            if notes:
                md += f" — {notes[:60]}"
            md += "\n"
        md += "\n"

    # 下周重点（P0/P1活跃）
    high = data["high_prio_active"]
    if high:
        md += "## 🎯 下周重点（P0/P1）\n\n"
        for t in high:
            dl = f" 截止 {t['deadline']}" if t.get('deadline') else ""
            md += f"- #{t['id']} {t['task_detail']} (@{t['responsible']}) [{t['priority']}]{dl}\n"
        md += "\n"

    # 本周新增任务
    created = data["created_this_week"]
    if created:
        md += f"## 🆕 本周新增（{len(created)} 项）\n\n"
        for t in created:
            dl = f" 截止 {t['deadline']}" if t.get('deadline') else ""
            md += f"- #{t['id']} {t['task_detail']} (@{t['responsible']}) [{t['priority']}]{dl}\n"

    return md


def export_weekly_to_file(output_dir: str = "") -> str:
    """导出周报到本地文件，返回文件路径"""
    md = generate_weekly_markdown()
    data = weekly_report()
    week_label = data["week_label"]

    if not output_dir:
        output_dir = SVN_WORK_COPY if SVN_ENABLED and SVN_WORK_COPY else "."

    os.makedirs(output_dir, exist_ok=True)
    filename = f"weekly_report_{week_label}.md"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"[INFO] 周报已导出: {filepath}")
    return filepath


def _run_svn(args: list, cwd: str = "") -> tuple[bool, str]:
    """执行 svn 命令，返回 (success, output)"""
    if not cwd:
        cwd = SVN_WORK_COPY
    cmd = ["svn"] + args
    if SVN_USERNAME and SVN_PASSWORD:
        cmd.extend(["--username", SVN_USERNAME, "--password", SVN_PASSWORD, "--non-interactive"])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=cwd)
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


def checkout_or_update() -> bool:
    """确保 SVN 工作副本存在并更新到最新"""
    if not SVN_ENABLED or not SVN_REPO_URL or not SVN_WEEKLY_PATH:
        print("[INFO] SVN 未启用或配置不完整，跳过")
        return False

    if not os.path.exists(SVN_WORK_COPY):
        os.makedirs(SVN_WORK_COPY, exist_ok=True)
        full_url = SVN_REPO_URL.rstrip("/") + "/" + SVN_WEEKLY_PATH.lstrip("/")
        ok, out = _run_svn(["checkout", full_url, SVN_WORK_COPY], cwd=os.path.dirname(SVN_WORK_COPY))
        if ok:
            print(f"[INFO] SVN checkout 成功: {SVN_WORK_COPY}")
        else:
            print(f"[ERROR] SVN checkout 失败: {out}")
        return ok
    else:
        ok, out = _run_svn(["update"])
        if ok:
            print(f"[INFO] SVN update 成功")
        else:
            print(f"[WARN] SVN update 失败: {out}")
        return ok


def commit_weekly() -> bool:
    """提交周报到 SVN"""
    if not SVN_ENABLED:
        print("[INFO] SVN 未启用，仅导出本地文件")
        export_weekly_to_file()
        return True

    if not checkout_or_update():
        print("[WARN] SVN 工作副本不可用，回退为本地导出")
        return False

    filepath = export_weekly_to_file(SVN_WORK_COPY)

    data = weekly_report()
    week_label = data["week_label"]

    ok, _ = _run_svn(["add", "--force", os.path.basename(filepath)])
    if ok:
        ok, out = _run_svn(["commit", "-m", f"周报 {week_label} 自动归档"])
        if ok:
            print(f"[INFO] SVN 提交成功: {week_label}")
            return True
        else:
            print(f"[ERROR] SVN 提交失败: {out}")
    else:
        print(f"[WARN] SVN add 失败，可能文件无变更")

    return False


if __name__ == "__main__":
    # 直接运行时导出本地文件
    path = export_weekly_to_file(".")
    print(f"\n📄 周报文件: {path}")