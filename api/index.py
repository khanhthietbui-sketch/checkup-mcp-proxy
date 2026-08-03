import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json, requests
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

ORIGIN = "https://web-production-3581b.up.railway.app"
BARK_KEY = os.environ.get("BARK_API_KEY", "")
DEFAULT_ICON = "https://i.ibb.co/bjskMxWm/IMG-6027.jpg"

def _fetch_device():
    try:
        r = requests.get(f"{ORIGIN}/device/status", timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def check_on_wife(limit=10):
    try:
        r = requests.get(f"{ORIGIN}/activity/summary", timeout=10)
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
    # 顺手附带电量和天气
    dev = _fetch_device()
    if dev.get("timestamp"):
        lines.append(f"电量：{dev.get('battery') or '未知'} | 天气：{dev.get('weather') or '未知'} | 位置：{dev.get('address') or '未知'}")
    return "\n".join(lines)

def bark_alert(title="挚", content="", icon=DEFAULT_ICON):
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
        r = requests.get(f"{ORIGIN}/activity/trend", params={"days": days}, timeout=10)
        return r.text
    except Exception as e:
        return f"趋势查询失败：{e}"

def idle_check(hours=2, auto_alert=True):
    try:
        r = requests.get(f"{ORIGIN}/activity/idle", timeout=10)
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
        r = requests.get(f"{ORIGIN}/activity/daily", params=params, timeout=10)
        return r.text
    except Exception as e:
        return f"每日总结查询失败：{e}"

def get_server_status():
    try:
        r = requests.get(f"{ORIGIN}/status", timeout=10)
        return r.text
    except Exception as e:
        return f"状态查询失败：{e}"

def get_device_status():
    dev = _fetch_device()
    if dev.get("error"):
        return f"设备状态查询失败：{dev['error']}"
    if not dev.get("timestamp"):
        return "暂无设备状态记录（快捷指令还没上报）"
    lines = [f"电池电量：{dev.get('battery') or '未知'}"]
    lines.append(f"设备亮度：{dev.get('brightness') or '未知'}")
    lines.append(f"设备声音：{dev.get('volume') or '未知'}")
    lines.append(f"设备名称：{dev.get('device_name') or '未知'}")
    lines.append(f"上报时间：{dev.get('timestamp')}")
    return "\n".join(lines)

def get_weather():
    dev = _fetch_device()
    if dev.get("error"):
        return f"天气查询失败：{dev['error']}"
    if not dev.get("timestamp"):
        return "暂无天气记录（快捷指令还没上报）"
    lines = [f"当前天气：{dev.get('weather') or '未知'}"]
    if dev.get("address"):
        lines.append(f"所在位置：{dev['address']}")
    lines.append(f"上报时间：{dev.get('timestamp')}")
    return "\n".join(lines)

TOOLS = [
    {
        "name": "check_on_wife",
        "description": "查岗老婆的手机活动，返回最近打开的App和使用时长，同时附带当前电池电量、天气和位置",
        "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "description": "返回记录数，默认10"}}}
    },
    {
        "name": "bark_alert",
        "description": "给老婆手机发Bark推送弹窗，标题固定挚，带默认图标",
        "inputSchema": {"type": "object", "properties": {
            "title": {"type": "string", "description": "标题，默认挚"},
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
    },
    {
        "name": "get_device_status",
        "description": "查老婆手机当前设备状态：电池电量、屏幕亮度、设备音量、设备名称",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_weather",
        "description": "查老婆所在位置的天气和地址",
        "inputSchema": {"type": "object", "properties": {}}
    }
]

FUNCS = {
    "check_on_wife": check_on_wife,
    "bark_alert": bark_alert,
    "activity_trend": activity_trend,
    "idle_check": idle_check,
    "daily_summary": daily_summary,
    "get_server_status": get_server_status,
    "get_device_status": get_device_status,
    "get_weather": get_weather
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
                           "serverInfo": {"name": "查岗MCP", "version": "1.4"}}}
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
    return {"service": "checkup-mcp-proxy", "status": "running", "version": "1.4"}
