import json, os, requests
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

JST = timedelta(hours=9)
ORIGIN = os.environ.get("ORIGIN_API", "你的Railway域名")
BARK_KEY = os.environ.get("BARK_API_KEY", "")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "")

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
    return "\n".join(lines)

def bark_alert(title="墨言", content=""):
    if not content: return "内容不能为空"
    url = f"https://api.day.app/{BARK_KEY}/{title}/{content}"
    try:
        r = requests.get(url, timeout=10)
        return "推送成功" if r.status_code == 200 else "推送失败"
    except Exception as e:
        return f"推送异常：{e}"

def clean_records():
    """清理后端数据库中所有空名字的记录"""
    try:
        headers = {}
        if AUTH_TOKEN:
            headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
        r = requests.post(f"{ORIGIN}/activity/clean", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "ok":
                return f"清理完成，删除了 {data.get('deleted', 0)} 条空记录"
        return f"清理失败：{r.status_code} {r.text}"
    except Exception as e:
        return f"清理异常：{e}"

TOOLS = [
    {"name": "check_on_wife", "description": "查岗老婆的手机活动",
     "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
    {"name": "bark_alert", "description": "给老婆手机发推送弹窗",
     "inputSchema": {"type": "object", "properties": {
         "title": {"type": "string"}, "content": {"type": "string"}},
         "required": ["content"]}},
    {"name": "clean_records", "description": "清理后端数据库中所有空名字的旧记录",
     "inputSchema": {"type": "object", "properties": {}}}
]

FUNCS = {"check_on_wife": check_on_wife, "bark_alert": bark_alert, "clean_records": clean_records}

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"],
    allow_methods=["*"], allow_headers=["*"])

@app.post("/mcp")
async def mcp(req: Request):
    body = await req.json()
    method, params = body.get("method"), body.get("params") or {}
    rid = body.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"protocolVersion": "2024-11-05",
                           "capabilities": {"tools": {}},
                           "serverInfo": {"name": "查岗MCP", "version": "1.0"}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"tools": TOOLS}}
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
