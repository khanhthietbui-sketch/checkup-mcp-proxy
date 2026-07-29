import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json, requests
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

ORIGIN = os.environ.get("ORIGIN_API", "")
BARK_KEY = os.environ.get("BARK_API_KEY", "")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "")
DEFAULT_ICON = "https://i.ibb.co/bjskMxWm/IMG-6027.jpg"

def _headers():
    h = {}
    if AUTH_TOKEN:
        h["Authorization"] = f"Bearer {AUTH_TOKEN}"
    return h

def check_on_wife(limit=10):
    try:
        r = requests.get(f"{ORIGIN}/activity/summary", headers=_headers(), timeout=10)
        data = r.json()
    except Exception as e:
        return f"查岗失败：{e}"
    apps = data.get("recent_apps", [])
    ses = data.get("sessions", {})
    lines = [f"最近打开：{', '.join(apps)}" if apps else "暂无记录"]
    if ses:
        for app, secs in sorted(ses.items(), key=lambda x: x[1], reverse=True):
            m, s = divmod(secs, 60)
            lines.append(f"  {app}: {m}分{s}秒")
    return "\n".join(lines)

def bark_alert(title="墨言", content="", icon=DEFAULT_ICON):
    if not content:
        return "内容不能为空"
    url = f"https://api.day.app/{BARK_KEY}/{title}/{content}"
    if icon:
        url += f"?icon={icon}"
    try:
        r = requests.get(url, timeout=10)
        return "推送成功" if r.status_code == 200 else "推送失败"
    except Exception as e:
        return f"推送异常：{e}"

def activity_trend(days=3):
    try:
        r = requests.get(f"{ORIGIN}/activity/trend", params={"days": days}, headers=_headers(), timeout=10)
        return r.text
    except Exception as e:
        return f"趋势查询失败：{e}"

def idle_check(hours=2, auto_alert=True):
    try:
        r = requests.get(f"{ORIGIN}/activity/idle", headers=_headers(), timeout=10)
        data = r.json()
        idle = data.get("idle_hours")
        if idle is None:
            return "暂无活动记录"
        msg = f"已空闲 {idle} 小时，最后活动于 {data.get('last_activity')}"
        if auto_alert and idle > hours:
            bark_alert(content=f"宝宝已经 {idle:.1f} 小时没玩手机了，查查是不是在睡觉！")
            msg += "\n已推送超时空闲提醒"
        return msg
    except Exception as e:
        return f"空闲检测失败：{e}"

def daily_summary(date_str=None):
    try:
        params = {}
        if date_str:
            params["date_str"] = date_str
        r = requests.get(f"{ORIGIN}/activity/daily", params=params, headers=_headers(), timeout=10)
        return r.text
    except Exception as e:
        return f"每日总结查询失败：{e}"

def get_server_status():
    try:
        r = requests.get(f"{ORIGIN}/status", headers=_headers(), timeout=10)
        return r.text
    except Exception as e:
        return f"状态查询失败：{e}"

TOOLS = [
    {
        "name": "check_on_wife",
        "description": "查岗老婆的手机活动，返回最近打开的App和使用时长",
        "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "description": "返回记录数，默认10"}}}
    },
    {
        "name": "bark_alert",
        "description": "给老婆手机发Bark推送弹窗，标题固定墨言，带默认图标",
        "inputSchema": {"type": "object", "properties": {
            "title": {"type": "string", "description": "标题，默认墨言"},
            "content": {"type": "string", "description": "推送正文"},
            "icon": {"type": "string", "description": "自定义图标URL，不传则用默认"}},
            "required": ["content"]}
    },
    {
        "name": "activity_trend",
        "description": "分析最近几天手机活动趋势，返回各时间段使用频率和常用App变化",
        "inputSchema": {"type": "object", "properties": {"days": {"type": "integer", "description": "回溯天数，默认3"}}}
    },
    {
        "name": "idle_check",
        "description": "检测是否超过指定时间没有手机活动，超时可自动推送Bark提醒",
        "inputSchema": {"type": "object", "properties": {
            "hours": {"type": "number", "description": "空闲阈值小时数，默认2"},
            "auto_alert": {"type": "boolean", "description": "超时后是否自动推送Bark提醒，默认true"}}}
    },
    {
        "name": "daily_summary",
        "description": "获取某天手机活动总结，包括常用App、使用时长分布",
        "inputSchema": {"type": "object", "properties": {"date_str": {"type": "string", "description": "日期如 2026-07-28，可选，默认今天"}}}
    },
    {
        "name": "get_server_status",
        "description": "检测查岗后端服务运行状态，返回各模块健康情况",
        "inputSchema": {"type": "object", "properties": {}}
    }
]

FUNCS = {
    "check_on_wife": check_on_wife,
    "bark_alert": bark_alert,
    "activity_trend": activity_trend,
    "idle_check": idle_check,
    "daily_summary": daily_summary,
    "get_server_status": get_server_status
}

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/mcp")
async def mcp(req: Request):
    body = await req.json()
    method, params = body.get("method"), body.get("params") or {}
    rid = body.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"protocolVersion": "2024-11-05",
                           "capabilities": {"tools": {}},
                           "serverInfo": {"name": "查岗MCP", "version": "1.2"}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name not in FUNCS:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32601, "message": "未知工具"}}
        result = FUNCS[name](**args)
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"content": [{"type": "text", "text": str(result)}]}}
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"未知方法: {method}"}}

@app.get("/")
async def root():
    return {"service": "checkup-mcp-proxy", "status": "running", "version": "1.2"}
