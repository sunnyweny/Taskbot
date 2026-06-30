"""
SVN 集成 Dry-Run 测试
模拟完整流程: 生成数据 → 推送SVN → 从SVN取回 → 加工输出
无需安装 SVN 命令行，mock 所有 subprocess 调用
"""
import os
import sys
import subprocess
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

# 设置 SVN 环境变量（模拟已配置）
os.environ["SVN_ENABLED"] = "true"
os.environ["SVN_REPO_URL"] = "https://svn.company.com/产品部"
os.environ["SVN_WEEKLY_PATH"] = "/weekly_reports/"
os.environ["SVN_USERNAME"] = "testuser"
os.environ["SVN_PASSWORD"] = "testpass123"
os.environ["SVN_WORK_COPY"] = os.path.join(os.path.dirname(__file__), "svn_work_copy_test")

# 重新加载 config 和 svn_archive（因为环境变量在 import 之后设置，需要 reload）
import config
import svn_archive
import importlib
importlib.reload(config)
importlib.reload(svn_archive)

from db import add_task, update_task, weekly_report, init_db

# ─── Phase 0: 灌入测试数据 ───
print("=" * 60)
print("Phase 0: 准备测试数据")
print("=" * 60)

# 确保数据库已初始化
init_db()

test_tasks = [
    ("NEW9830产品", "需求文档评审 — 接口定义章节", "熊和云", "2026-06-25", "2026-07-03", "进行中", "P0紧急", ""),
    ("MDP820", "UI 设计稿定稿", "吕梓铭", "2026-06-26", "2026-07-01", "进行中", "P1高", ""),
    ("NEW9220S", "竞品分析报告", "梁镇延", "2026-06-24", "2026-06-30", "已完成", "P2中", ""),
    ("NEW6260(P)", "BOM 表整理", "商文渊", "2026-06-28", "2026-07-05", "待开始", "P1高", ""),
    ("N98", "模具开模进度跟进", "商文渊", "2026-06-20", "2026-06-28", "阻塞延期", "P0紧急", "等待供应商回复"),
    ("NEW9810", "结构设计评审", "梁镇延", "2026-06-29", "2026-07-10", "待开始", "P2中", ""),
    ("MDP910", "硬件测试计划", "吕梓铭", "2026-06-27", "2026-07-02", "进行中", "P1高", ""),
    ("OM-CS280Pro", "包装设计确认", "吕梓铭", "2026-07-01", "2026-07-08", "待开始", "P3低", ""),
]

from db import update_task as db_update_task

task_ids = []
for pn, detail, person, start, deadline, status, prio, notes in test_tasks:
    tid = add_task(project_name=pn, task_detail=detail, responsible=person,
                   start_date=start, deadline=deadline, priority=prio, notes=notes)
    db_update_task(tid, status=status)
    task_ids.append(tid)

# 把竞品分析任务完成时间设为本周（模拟本周完成）
import sqlite3
from config import DB_PATH
conn = sqlite3.connect(DB_PATH)
today = datetime.now().strftime("%Y-%m-%d")
conn.execute("UPDATE tasks SET updated_at=? WHERE task_detail LIKE '%竞品分析报告%'", (today,))
conn.commit()
conn.close()

count = sqlite3.connect(DB_PATH).execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
print(f"已灌入 {count} 条测试任务")
for t in weekly_report().get("completed_this_week", []):
    print(f"  已完成: #{t['id']} {t['task_detail'][:30]}")

# ─── Phase 1: 生成周报 Markdown ───
print()
print("=" * 60)
print("Phase 1: 从数据库生成周报 Markdown")
print("=" * 60)

md = svn_archive.generate_weekly_markdown()
print("生成成功! 内容预览 (前 500 字符):")
print(md[:500])
print(f"... 总长度: {len(md)} 字符")

# ─── Phase 2: 模拟 SVN checkout + commit ───
print()
print("=" * 60)
print("Phase 2: 模拟 SVN 推送 (checkout → add → commit)")
print("=" * 60)

svn_log = []

def mock_svn_run(args, **kwargs):
    """Mock subprocess.run, 记录所有 SVN 操作"""
    cmd_str = " ".join(args) if isinstance(args, list) else args
    svn_log.append(cmd_str)
    print(f"  [MOCK SVN] {cmd_str}")

    if "checkout" in args:
        # 模拟 checkout 成功，创建目标目录
        target = args[-1] if len(args) > 1 else "."
        os.makedirs(target, exist_ok=True)
        return subprocess.CompletedProcess(args, 0, stdout="Checked out revision 42.\n", stderr="")

    elif "update" in args:
        return subprocess.CompletedProcess(args, 0, stdout="Updating '.'\nAt revision 42.\n", stderr="")

    elif "add" in args:
        return subprocess.CompletedProcess(args, 0, stdout="A         weekly_report_2026-W27.md\n", stderr="")

    elif "commit" in args:
        return subprocess.CompletedProcess(args, 0,
            stdout="Committing...\nCommitted revision 43.\n", stderr="")

    else:
        return subprocess.CompletedProcess(args, 0, stdout="OK\n", stderr="")

with patch.object(subprocess, "run", side_effect=mock_svn_run):
    os.environ["SVN_ENABLED"] = "true"
    importlib.reload(config)
    importlib.reload(svn_archive)

    result = svn_archive.commit_weekly()

print(f"\nSVN 推送结果: {'✓ 成功' if result else '✗ 失败'}")
print(f"\n共执行 {len(svn_log)} 次 SVN 操作:")
for i, cmd in enumerate(svn_log, 1):
    print(f"  {i}. {cmd}")

# ─── Phase 3: 模拟从 SVN 拉取数据并加工 ───
print()
print("=" * 60)
print("Phase 3: 从 SVN 取历史周报并加工分析")
print("=" * 60)

# 创建模拟的 svn 工作副本目录和文件
work_copy = os.environ["SVN_WORK_COPY"]
os.makedirs(work_copy, exist_ok=True)

# 模拟之前几周的周报文件
sample_reports = {
    "weekly_report_2026-W24.md": """# 产品部周报 2026-W24
## ✅ 本周完成（3 项）
- #1 接口文档 v1 评审 (@熊和云)
- #2 UI 初稿完成 (@吕梓铭)
- #3 BOM 初版整理 (@商文渊)
## 🚫 阻塞项（1 项）
- #5 模具开模 — 等待供应商报价""",
    "weekly_report_2026-W25.md": """# 产品部周报 2026-W25
## ✅ 本周完成（2 项）
- #4 竞品分析初稿 (@梁镇延)
- #6 结构设计启动 (@梁镇延)
## 🎯 下周重点（P0/P1）
- #7 需求文档评审 v2 (@熊和云) [P0紧急]""",
}

for filename, content in sample_reports.items():
    filepath = os.path.join(work_copy, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  模拟历史文件: {filename}")

# 模拟从 SVN update 获取最新列表
print()
print("--- 模拟 SVN update (拉取最新) ---")

def mock_svn_list(args, **kwargs):
    cmd_str = " ".join(args) if isinstance(args, list) else args
    print(f"  [MOCK SVN] {cmd_str}")
    if "update" in args:
        return subprocess.CompletedProcess(args, 0,
            stdout="Updating 'weekly_report_2026-W27.md'\nAt revision 44.\n", stderr="")
    elif "list" in args:
        files = "\n".join(os.listdir(work_copy))
        return subprocess.CompletedProcess(args, 0, stdout=files + "\n", stderr="")
    return subprocess.CompletedProcess(args, 0, stdout="OK\n", stderr="")

with patch.object(subprocess, "run", side_effect=mock_svn_list):
    ok, out = svn_archive._run_svn(["update"])
    print(f"  update 结果: {'成功' if ok else '失败'}")

# 加工分析：读取所有历史周报，提取统计数据
print()
print("--- 加工分析：汇总历史周报 ---")

import re
all_files = sorted([f for f in os.listdir(work_copy) if f.endswith(".md")])

total_completed = 0
total_blocked_items = 0
weekly_summary = []

for fname in all_files:
    fpath = os.path.join(work_copy, fname)
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()

    week = fname.replace("weekly_report_", "").replace(".md", "")

    # 提取完成数
    completed_match = re.search(r"本周完成.*?（(\d+) 项）", content)
    completed_count = int(completed_match.group(1)) if completed_match else 0

    # 提取阻塞数
    blocked_match = re.search(r"阻塞项.*?（(\d+) 项）", content)
    blocked_count = int(blocked_match.group(1)) if blocked_match else 0

    total_completed += completed_count
    total_blocked_items += blocked_count

    weekly_summary.append({
        "week": week,
        "completed": completed_count,
        "blocked": blocked_count,
    })

print(f"\n  📂 历史周报文件数: {len(all_files)}")
print(f"  📊 汇总统计:")
print(f"     ┌{'─'*30}┬{'─'*8}┬{'─'*8}┐")
print(f"     │ {'周次':^28} │ {'完成':^6} │ {'阻塞':^6} │")
print(f"     ├{'─'*30}┼{'─'*8}┼{'─'*8}┤")
for s in weekly_summary:
    print(f"     │ {s['week']:<28} │ {s['completed']:>4}  │ {s['blocked']:>4}  │")
print(f"     ├{'─'*30}┼{'─'*8}┼{'─'*8}┤")
print(f"     │ {'合计':<28} │ {total_completed:>4}  │ {total_blocked_items:>4}  │")
print(f"     └{'─'*30}┴{'─'*8}┴{'─'*8}┘")
print(f"  📈 周均完成: {total_completed / len(weekly_summary):.1f} 项")
print(f"  ⚠️  累计阻塞: {total_blocked_items} 项")

# 导出汇总报告
summary_path = os.path.join(work_copy, "SVN_归档汇总报告.md")
summary_md = f"""# SVN 周报归档汇总报告
> 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}

## 数据来源
从 SVN 仓库 `{os.environ['SVN_REPO_URL']}{os.environ['SVN_WEEKLY_PATH']}` 拉取 {len(all_files)} 份历史周报。

## 汇总统计

| 周次 | 当周完成 | 阻塞项 |
|------|----------|--------|
"""
for s in weekly_summary:
    summary_md += f"| {s['week']} | {s['completed']} | {s['blocked']} |\n"

summary_md += f"""
| **合计** | **{total_completed}** | **{total_blocked_items}** |

## 关键指标
- 周均完成: {total_completed / len(weekly_summary):.1f} 项
- 累计阻塞: {total_blocked_items} 项
- 按时完成率: 待实际 SVN 数据接入后计算
"""

with open(summary_path, "w", encoding="utf-8") as f:
    f.write(summary_md)
print(f"\n  📄 汇总报告已生成: {summary_path}")

# ─── 清理测试 work copy ───
import shutil
if os.path.exists(work_copy):
    shutil.rmtree(work_copy)
    print(f"\n  已清理测试目录: {work_copy}")

print()
print("=" * 60)
print("Dry-Run 测试完成!")
print("=" * 60)
print()
print("流程总结:")
print("  1. 数据库 → 生成 Markdown 周报          ✓")
print("  2. 本地文件 → SVN checkout/add/commit   ✓ (mock)")
print("  3. SVN update → 读取历史文件 → 加工汇总  ✓ (mock)")
print()
print("正式使用步骤:")
print("  1. 安装 SVN:   winget install SlikSVN")
print("  2. 配置 .env:  SVN_ENABLED=true + 仓库地址/账号/密码")
print("  3. 首次运行:   python svn_archive.py")
print("  4. 提交 SVN:   python -c \"from svn_archive import commit_weekly; commit_weekly()\"")
