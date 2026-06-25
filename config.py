"""配置文件 — 通过环境变量注入敏感信息"""

import os

# 企微机器人回调配置（从环境变量读取）
TOKEN = os.environ.get("WX_BOT_TOKEN", "")
AES_KEY = os.environ.get("WX_BOT_AES_KEY", "")
CORP_ID = os.environ.get("WX_BOT_CORP_ID", "")

# 机器人 webhook key（用于主动发送文件，取自 webhook URL 的 key 参数）
BOT_KEY = os.environ.get("WX_BOT_KEY", "")

# 服务配置
HOST = "0.0.0.0"
PORT = 5001
BOT_NAME = "任务看板助手"
BOT_PATH = "/wecom_bot"

# 数据库路径
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks.db")