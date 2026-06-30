"""企微智能机器人 API 封装 — botID + BotSecret 纯 API 模式

仅通过智能机器人 API 推送消息。
"""

import json
import time
import urllib.request
from config import WECOM_BOT_ID, WECOM_BOT_SECRET, WECOM_CORP_ID, WECOM_CHAT_ID

# ─── Access Token 缓存 ───
_token_cache: dict = {"token": "", "expires_at": 0}


def get_access_token() -> str:
    """获取企微 access_token（自动缓存，过期刷新）"""
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    if not WECOM_BOT_ID or not WECOM_BOT_SECRET or not WECOM_CORP_ID:
        print("[WARN] WECOM_BOT_ID / WECOM_BOT_SECRET / WECOM_CORP_ID 未配置")
        return ""

    url = (
        f"https://qyapi.weixin.qq.com/cgi-bin/gettoken"
        f"?corpid={WECOM_CORP_ID}&corpsecret={WECOM_BOT_SECRET}"
    )
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if data.get("errcode") == 0:
                _token_cache["token"] = data["access_token"]
                _token_cache["expires_at"] = time.time() + data.get("expires_in", 7200)
                return _token_cache["token"]
            print(f"[ERROR] 获取 access_token 失败: {data}")
    except Exception as e:
        print(f"[ERROR] 获取 access_token 网络异常: {e}")
    return ""


# ═══════════════════════════════════════════
#  通用 API 调用
# ═══════════════════════════════════════════

def _api_post(endpoint: str, payload: dict) -> bool:
    """通用 API POST（带 access_token）"""
    token = get_access_token()
    if not token:
        return False
    url = (
        f"https://qyapi.weixin.qq.com/cgi-bin/tencent/chat/{endpoint}"
        f"?access_token={token}"
    )
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            ok = result.get("errcode") == 0
            if not ok:
                print(f"[WARN] API 推送失败: {result}")
            return ok
    except Exception as e:
        print(f"[ERROR] API 推送异常: {e}")
        return False


def _resolve_chat(chat_id: str = "") -> str:
    """解析目标 chat_id"""
    return chat_id or WECOM_CHAT_ID


# ═══════════════════════════════════════════
#  基础消息推送
# ═══════════════════════════════════════════

def send_text(content: str, chat_id: str = "", mentioned_list: list = None) -> bool:
    """推送文本消息（支持 @人）"""
    payload = {
        "chatid": _resolve_chat(chat_id),
        "msgtype": "text",
        "text": {"content": content},
    }
    if mentioned_list:
        payload["text"]["mentioned_list"] = mentioned_list
    return _api_post("send_text", payload)


def send_markdown(content: str, chat_id: str = "") -> bool:
    """推送 markdown 消息"""
    return _api_post("send_markdown", {
        "chatid": _resolve_chat(chat_id),
        "msgtype": "markdown",
        "markdown": {"content": content},
    })


# ═══════════════════════════════════════════
#  模板卡片
# ═══════════════════════════════════════════

def send_template_card(chat_id: str, card: dict) -> bool:
    """推送模板卡片消息

    完整字段参考: https://developer.work.weixin.qq.com/document/path/96553
    """
    card.setdefault("chat_id", chat_id)
    return _api_post("send_template_card", {
        "chatid": _resolve_chat(chat_id),
        "msgtype": "template_card",
        "template_card": card,
    })


def send_daily_report_card(chat_id: str = "",
                            date_str: str = "",
                            completed: int = 0,
                            in_progress: int = 0,
                            risks: int = 0,
                            p0: int = 0, p1: int = 0, p2: int = 0, p3: int = 0,
                            detail_url: str = "") -> bool:
    """发送日报模板卡片"""
    card = {
        "card_type": "text_notice",
        "source": {"icon_url": "", "desc": "产品部助手", "desc_color": 1},
        "main_title": {
            "title": f"📋 产品部日报 ({date_str})",
            "desc": f"完成 {completed} · 进行中 {in_progress} · 风险 {risks}",
        },
        "emphasis_content": {"title": f"{completed} 项", "desc": "今日完成"},
        "sub_title_text": f"优先级: P0:{p0} | P1:{p1} | P2:{p2} | P3:{p3}",
        "horizontal_content_list": [
            {"keyname": "进行中", "value": f"{in_progress} 项"},
            {"keyname": "风险项", "value": f"{risks} 项"},
        ],
    }
    if detail_url:
        card["jump_list"] = [{"type": 1, "title": "查看完整看板", "url": detail_url}]
        card["card_action"] = {"type": 1, "url": detail_url}
    return _api_post("send_template_card", {
        "chatid": _resolve_chat(chat_id),
        "msgtype": "template_card",
        "template_card": card,
    })


def send_weekly_report_card(chat_id: str = "",
                             week_label: str = "",
                             completed: int = 0,
                             created: int = 0,
                             active: int = 0,
                             blocked: int = 0,
                             detail_url: str = "") -> bool:
    """发送周报模板卡片"""
    card = {
        "card_type": "text_notice",
        "source": {"icon_url": "", "desc": "产品部助手", "desc_color": 3},
        "main_title": {
            "title": f"📊 产品部周报 {week_label}",
            "desc": f"完成 {completed} · 新增 {created} · 进行中 {active}",
        },
        "emphasis_content": {"title": f"{completed} 项", "desc": "本周完成"},
        "sub_title_text": f"阻塞: {blocked} 项",
        "horizontal_content_list": [
            {"keyname": "本周新增", "value": f"{created} 项"},
            {"keyname": "进行中", "value": f"{active} 项"},
        ],
    }
    if detail_url:
        card["jump_list"] = [{"type": 1, "title": "查看完整周报", "url": detail_url}]
        card["card_action"] = {"type": 1, "url": detail_url}
    return _api_post("send_template_card", {
        "chatid": _resolve_chat(chat_id),
        "msgtype": "template_card",
        "template_card": card,
    })


def send_alert_card(chat_id: str = "",
                     alert_type: str = "风险预警",
                     title: str = "",
                     description: str = "",
                     detail_url: str = "") -> bool:
    """发送预警卡片"""
    card = {
        "card_type": "text_notice",
        "source": {"icon_url": "", "desc": "⚠️ 风险预警", "desc_color": 2},
        "main_title": {"title": title, "desc": description},
        "emphasis_content": {"title": alert_type, "desc": "请关注"},
    }
    if detail_url:
        card["jump_list"] = [{"type": 1, "title": "查看详情", "url": detail_url}]
        card["card_action"] = {"type": 1, "url": detail_url}
    return _api_post("send_template_card", {
        "chatid": _resolve_chat(chat_id),
        "msgtype": "template_card",
        "template_card": card,
    })
