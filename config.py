"""配置文件 — 通过环境变量注入敏感信息"""

import os

# ═══════════════════════════════════════════
#  企微群机器人回调配置
# ═══════════════════════════════════════════
TOKEN = os.environ.get("WX_BOT_TOKEN", "")
AES_KEY = os.environ.get("WX_BOT_AES_KEY", "")
CORP_ID = os.environ.get("WX_BOT_CORP_ID", "")

# 智能机器人 API 配置（botID + BotSecret）
WECOM_BOT_ID = os.environ.get("WECOM_BOT_ID", "")
WECOM_BOT_SECRET = os.environ.get("WECOM_BOT_SECRET", "")
WECOM_CORP_ID = os.environ.get("WECOM_CORP_ID", CORP_ID)
# 群聊 chat_id（用于主动推送）
WECOM_CHAT_ID = os.environ.get("WECOM_CHAT_ID", "")

# ═══════════════════════════════════════════
#  服务配置
# ═══════════════════════════════════════════
HOST = "0.0.0.0"
BOT_PORT = 5001          # 企微回调端口
WEB_PORT = 5000          # Web 管理后台端口
BOT_NAME = "产品部小助手"
BOT_PATH = "/wecom_bot"

# ═══════════════════════════════════════════
#  数据库路径
# ═══════════════════════════════════════════
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tasks.db")

# ═══════════════════════════════════════════
#  SVN 配置
# ═══════════════════════════════════════════
SVN_ENABLED = os.environ.get("SVN_ENABLED", "false").lower() == "true"
SVN_REPO_URL = os.environ.get("SVN_REPO_URL", "")        # e.g. https://svn.company.com/repo
SVN_WEEKLY_PATH = os.environ.get("SVN_WEEKLY_PATH", "")  # e.g. /weekly_reports/
SVN_USERNAME = os.environ.get("SVN_USERNAME", "")
SVN_PASSWORD = os.environ.get("SVN_PASSWORD", "")
SVN_WORK_COPY = os.path.join(BASE_DIR, "svn_work_copy")  # 本地 checkout 目录

# ═══════════════════════════════════════════
#  团队配置
# ═══════════════════════════════════════════
TEAM_MEMBERS = {
    "王艺超": {"role": "产品部经理", "products": [], "avatar_color": "indigo"},
    "熊和云": {"role": "产品经理", "products": ["NEW9830","NEW6220Y","NEW6200Y","P3000","NEW9010","NEW3500A","NEW7220D","MDP860","MDP810A","NEW5320","NEW5010"], "avatar_color": "red"},
    "吕梓铭": {"role": "产品经理", "products": ["NEW9310","MDP910","MDP810K","NEW9310Pro","MDP820","NEW9228","NEW9850","NEW9800","OM-CS280Pro","OM-CS280"], "avatar_color": "green"},
    "梁镇延": {"role": "产品经理", "products": ["NEW9220S","NEW9220U(L)","NEW9810","NEW9810P","NEW2010","NEW2020","NEW20230","NOP-210","NOP-608T"], "avatar_color": "sky"},
    "商文渊": {"role": "产品助理", "products": ["NEW6260(P)","MDP810A","MDP726A(830)","NEW7220I","NEW7220K","N98"], "avatar_color": "purple"},
    "罗时勇": {"role": "产品助理", "products": [], "avatar_color": "amber"},
    "龙园": {"role": "企划组", "products": [], "avatar_color": "indigo"},
    "韩文博": {"role": "企划组", "products": [], "avatar_color": "cyan"},
    "罗康": {"role": "企划组", "products": [], "avatar_color": "orange"},
}

# AI 调度阈值
AI_HIGH_LOAD_THRESHOLD = 75    # 负载超过此值触发预警 (百分比)
AI_OVERDUE_WARN_DAYS = 1       # 到期前 N 天开始预警
AI_BLOCKED_STALE_DAYS = 3      # 阻塞超过 N 天自动升级