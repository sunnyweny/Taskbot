# 产品部动态任务看板 · SVN 周报归档操作手册

> 版本: v2.0 | 更新日期: 2026-06-30

---

## 一、你需要准备什么

联系 SVN 管理员获取以下 5 项信息：

| # | 配置项 | 说明 | 示例 |
|---|--------|------|------|
| 1 | **SVN 仓库地址** | 公司 SVN 服务器地址+仓库路径 | `https://svn.company.com/产品部` |
| 2 | **周报存放路径** | 仓库里已有的目录路径 | `/weekly_reports/` 或 `/reports/` |
| 3 | **SVN 账号** | 你的 SVN 登录用户名 | `zhangsan` |
| 4 | **SVN 密码** | 你的 SVN 登录密码 | `********` |
| 5 | **SVN 命令行** | 确认本地已安装 `svn` 命令 | 终端运行 `svn --version` |

> **提示**：如果公司 SVN 使用 TortoiseSVN（图形界面），也需要先安装命令行版本。下载地址：https://www.visualsvn.com/downloads/ 或联系 IT 统一安装。

---

## 二、配置步骤

### 2.1 确认 SVN 命令行可用

打开终端（Git Bash 或 cmd），运行：

```bash
svn --version
```

预期输出类似：

```
svn, version 1.14.0 (r1876290)
   compiled Feb 20 2023, 12:34:56
```

如果提示 `command not found`，说明没有安装，联系 IT。

### 2.2 编辑环境变量

打开文件 `D:\ProductBoardDemo\.env`（没有则新建），添加：

```
# ─── SVN 配置 ───
SVN_ENABLED=true
SVN_REPO_URL=https://svn.你的公司.com/产品部
SVN_WEEKLY_PATH=/weekly_reports/
SVN_USERNAME=你的SVN账号
SVN_PASSWORD=你的SVN密码
```

> ⚠️ 密码明文存储，请确保 `.env` 文件不被分享到 Git。`.env` 已在 `.gitignore` 中。

### 2.3 验证配置

```bash
cd D:\ProductBoardDemo
python -c "from config import SVN_ENABLED; print('SVN已启用' if SVN_ENABLED else 'SVN未启用')"
```

---

## 三、第一次使用

### 3.1 手动生成一份周报到本地

```bash
cd D:\ProductBoardDemo
python svn_archive.py
```

这会在当前目录生成 `weekly_report_2026-W27.md` 文件。打开确认内容正确。

### 3.2 测试 SVN 提交

```bash
cd D:\ProductBoardDemo
python -c "from svn_archive import commit_weekly; commit_weekly()"
```

第一次运行时会自动：

1. 从 SVN checkout 周报目录到 `svn_work_copy/`（本地）
2. 生成周报 Markdown 文件
3. 用 `svn add` + `svn commit` 提交到 SVN

成功输出示例：

```
[INFO] SVN checkout 成功: D:\ProductBoardDemo\svn_work_copy
[INFO] 周报已导出: D:\ProductBoardDemo\svn_work_copy\weekly_report_2026-W27.md
[INFO] SVN 提交成功: 2026-W27
```

---

## 四、自动化（Hermes Cron 定时任务）

配置完成后，在 Hermes 里执行：

```
发消息给 Leilah:
配置 Hermes 定时任务：
1. 每周五 17:00 运行 `cd D:\ProductBoardDemo && python svn_archive.py && python -c "from svn_archive import commit_weekly; commit_weekly()"` 提交周报到 SVN
2. 同时推送周报到企业微信群
```

或者让我（Hermes Agent）帮你创建 cron job。

---

## 五、故障排查

| 问题 | 可能原因 | 解决方法 |
|------|----------|----------|
| `svn: E170013` | 用户名/密码错误 | 检查 `.env` 中的 `SVN_USERNAME` / `SVN_PASSWORD` |
| `svn: E175002` | 路径不存在 | 确认 `SVN_WEEKLY_PATH` 在仓库中已创建 |
| `svn: E731001` | 网络不通 | 检查是否能访问公司 SVN 服务器 |
| `checkout 失败` | SVN 仓库地址拼写错误 | 复制浏览器里访问 SVN 的 URL |
| `未找到 svn 命令` | 没有安装命令行工具 | 安装 VisualSVN 或联系 IT |

---

## 六、文件结构

```
D:\ProductBoardDemo\
├── config.py              ← SVN 配置读取入口
├── svn_archive.py         ← 周报生成+SVN提交脚本
├── svn_work_copy/         ← SVN 本地工作副本（自动创建）
│   └── weekly_report_*.md ← 归档的周报文件
└── .env                   ← SVN 账号密码（不提交 Git）
```

---

## 七、扩展：手动从 SVN 读取历史周报

```bash
# 更新本地副本
cd D:\ProductBoardDemo
python -c "from svn_archive import checkout_or_update; checkout_or_update()"

# 查看所有历史周报
ls svn_work_copy/
```

Web 后台后续将支持从 `svn_work_copy/` 读取历史周报表。
