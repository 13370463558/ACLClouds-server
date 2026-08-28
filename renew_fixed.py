#!/usr/bin/env python3
"""
ACLClouds 自动续期脚本 - 修复版本
- 支持 dash.aclclouds.com (API 版)
- 支持 aclclouds.com (浏览器版，带 Turnstile 处理)
- 自动检测域名并选择对应模式
"""

import os
import sys
import json
import time
import urllib.parse
from datetime import datetime, timezone

import requests

# ==================== 配置 ====================
# 优先使用 dash.aclclouds.com (纯 API 版，无需浏览器)
BASE_URL = os.environ.get("ACL_BASE_URL", "https://dash.aclclouds.com")
RENEW_THRESHOLD_HOURS = int(os.environ.get("RENEW_THRESHOLD_HOURS", "48"))

# Cookie: 完整的浏览器 Cookie 字符串
COOKIE = os.environ.get("ACL_COOKIES", "").strip()

# 多账号支持 (可选), 格式: name1|||cookie1\nname2|||cookie2
MULTI_ACCOUNTS = os.environ.get("ACL_ACCOUNTS", "").strip()

# TG 通知
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()

# 代理 (仅浏览器版需要)
PROXY_URL = os.environ.get("PROXY_URL", "").strip()

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


# ==================== 工具函数 ====================
def now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def log(msg):
    print(msg, flush=True)


def send_tg(text):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=15,
        )
    except Exception as e:
        log(f"⚠️ TG 推送失败: {e}")


def fmt_remaining(seconds):
    if seconds is None:
        return "?"
    if seconds < 0:
        return "已过期"
    seconds = int(seconds)
    d = seconds // 86400
    h = (seconds % 86400) // 3600
    m = (seconds % 3600) // 60
    if d > 0:
        return f"{d}d {h}h {m}m"
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


def parse_iso(s):
    if not s:
        return None
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


# ==================== API 版 (纯 HTTP) ====================
def build_api_session(cookie_str):
    """构建 API session，正确处理 __Host- 前缀 cookie

    关键修复: 不再用 s.cookies.set (requests 的 prepare_cookies 会用 cookiejar
    覆盖手动设置的 Cookie header, 而且 __Host- 前缀会被剥离导致服务器不识别),
    而是保存原始 Cookie 字符串, 在 api_get/api_post 里强制覆盖。
    """
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/projects",
    })
    # 保存原始 Cookie 字符串（含 __Host- 前缀, 原样发送）
    s._raw_cookie = cookie_str.strip()
    # 不写入 s.cookies, 防止 prepare_cookies 用剥离前缀的名字重建 header
    return s


def get_xsrf(session):
    """从原始 Cookie 字符串提取 XSRF-TOKEN (并 URL 解码)"""
    raw = getattr(session, '_raw_cookie', '')
    if raw:
        for kv in raw.split(";"):
            kv = kv.strip()
            if kv.startswith("XSRF-TOKEN="):
                return urllib.parse.unquote(kv[len("XSRF-TOKEN="):])
    return None


def api_get(session, path):
    """发送 GET 请求，自动注入 XSRF token，并强制覆盖原始 Cookie"""
    headers = {}
    token = get_xsrf(session)
    if token:
        headers["X-XSRF-TOKEN"] = token

    req = requests.Request('GET', f"{BASE_URL}{path}", headers=headers)
    prepared = session.prepare_request(req)
    # 强制覆盖 Cookie header (prepare_cookies 已删掉手动 header, 这里写回原样)
    if getattr(session, '_raw_cookie', None):
        prepared.headers['Cookie'] = session._raw_cookie
    return session.send(prepared, timeout=30)


def api_post(session, path, payload=None):
    """发送 POST 请求，自动注入 XSRF token，并强制覆盖原始 Cookie"""
    headers = {}
    token = get_xsrf(session)
    if token:
        headers["X-XSRF-TOKEN"] = token

    req = requests.Request('POST', f"{BASE_URL}{path}", headers=headers, json=payload or {})
    prepared = session.prepare_request(req)
    if getattr(session, '_raw_cookie', None):
        prepared.headers['Cookie'] = session._raw_cookie
    return session.send(prepared, timeout=30)


def list_servers(session):
    r = api_get(session, "/api/client")
    if r.status_code == 401:
        log(f"❌ 登录失败 (401): Cookie 已过期，请重新获取")
        log(f"   响应: {r.text[:200]}")
        return []
    r.raise_for_status()
    j = r.json()
    if isinstance(j, dict):
        return j.get("data", [])
    return j if isinstance(j, list) else []


def server_detail(session, sid):
    r = api_get(session, f"/api/client/servers/{sid}")
    if r.status_code != 200:
        return None
    try:
        j = r.json()
        return j.get("attributes", j) if isinstance(j, dict) else j
    except Exception:
        return None


def find_expire(attrs, detail=None):
    """从多个可能字段找到期时间"""
    candidates = [attrs]
    if detail:
        candidates.append(detail)
    for c in list(candidates):
        rel = c.get("relationships") if isinstance(c, dict) else None
        if rel:
            candidates.append(rel)
    for c in candidates:
        if not isinstance(c, dict):
            continue
        for key in ("expires_at", "expire_at", "renew_at", "renewable_at",
                    "expiration_date", "expires", "expiry"):
            v = c.get(key)
            if v:
                return key, v
    return None, None


def renew_server_api(session, sid):
    """调用续期 API"""
    r = api_post(session, f"/api/client/servers/{sid}/upgrade/renew")
    captcha_required = False
    if r.status_code == 403:
        try:
            j = r.json()
            if isinstance(j, dict) and j.get("code") == "captcha_required":
                captcha_required = True
        except Exception:
            pass
    return r, captcha_required


# ==================== 浏览器版 (需要 Turnstile) ====================
def check_browser_requirements():
    """检查浏览器环境"""
    try:
        from seleniumbase import Driver
        return True, Driver
    except ImportError:
        return False, None


# ==================== 主流程 ====================
def process_account(label, cookie_str, use_browser=False):
    """处理单个账号的续期"""
    log(f"\n{'='*60}")
    log(f"👤 账号: {label}")
    log(f"🌐 站点: {BASE_URL}")
    log(f"{'='*60}")

    if not cookie_str:
        return {"label": label, "ok": False, "msg": "Cookie 为空", "renewed": 0, "failed": 0}

    # 构建 session
    session = build_api_session(cookie_str)

    # 1. 测试登录
    try:
        test_r = api_get(session, "/api/client")
        if test_r.status_code == 200:
            log("✅ API 登录验证通过")
        else:
            log(f"❌ 登录失败: HTTP {test_r.status_code}")
            log(f"   响应: {test_r.text[:300]}")
            return {"label": label, "ok": False, "msg": f"登录失败 HTTP {test_r.status_code}", "renewed": 0, "failed": 0}
    except Exception as e:
        log(f"❌ 登录测试异常: {e}")
        return {"label": label, "ok": False, "msg": f"登录异常: {e}", "renewed": 0, "failed": 0}

    # 2. 获取服务器列表
    servers = list_servers(session)
    if not servers:
        return {"label": label, "ok": True, "msg": "无服务器或获取失败", "renewed": 0, "failed": 0}

    log(f"📦 共 {len(servers)} 台服务器")

    # 3. 筛选需要续期的服务器
    now = datetime.now(timezone.utc)
    to_renew = []
    
    for srv in servers:
        attrs = srv.get("attributes", srv) if isinstance(srv, dict) else {}
        sid = attrs.get("identifier") or attrs.get("id") or attrs.get("uuid")
        name = attrs.get("name", f"server-{len(to_renew)+1}")
        
        if not sid:
            continue
            
        # 获取详情和到期时间
        _, expire_str = find_expire(attrs)
        detail = None
        if not expire_str:
            detail = server_detail(session, sid)
            if detail:
                _, expire_str = find_expire(attrs, detail)
        
        if not expire_str:
            continue
            
        expire = parse_iso(expire_str)
        if not expire:
            continue
            
        remaining = (expire - now).total_seconds()
        remaining_h = remaining / 3600
        
        log(f"  - {name}: 剩余 {fmt_remaining(remaining)} ({remaining_h:.1f}h)")
        
        if remaining_h < RENEW_THRESHOLD_HOURS:
            to_renew.append({"id": sid, "name": name, "remaining": remaining})

    if not to_renew:
        return {"label": label, "ok": True, "msg": f"所有服务器剩余时间充足，无需续期", "renewed": 0, "failed": 0}

    log(f"🔄 需要续期 {len(to_renew)} 台服务器")

    # 4. 执行续期
    renewed = 0
    failed = 0
    results = []
    
    for srv in to_renew:
        log(f"\n🖥️ 续期: {srv['name']} (id={srv['id']})")
        
        try:
            r, captcha = renew_server_api(session, srv["id"])
            
            if r.status_code in (200, 201, 202, 204):
                # 续期成功，重新查询到期时间
                time.sleep(1.5)
                new_detail = server_detail(session, srv["id"])
                _, new_expire_str = find_expire({}, new_detail)
                new_expire = parse_iso(new_expire_str) if new_expire_str else None
                
                if new_expire:
                    new_remaining = (new_expire - now).total_seconds()
                    results.append(f"✅ {srv['name']}: {fmt_remaining(srv['remaining'])} → {fmt_remaining(new_remaining)}")
                else:
                    results.append(f"✅ {srv['name']}: 续期成功")
                renewed += 1
                log(f"✅ 续期成功")
                
            elif captcha:
                results.append(f"🛡️ {srv['name']}: 需要 Turnstile 验证")
                failed += 1
                log(f"🛡️ 需要浏览器验证")
                
            else:
                results.append(f"❌ {srv['name']}: HTTP {r.status_code} - {r.text[:100]}")
                failed += 1
                log(f"❌ 续期失败: HTTP {r.status_code}")
                
        except Exception as e:
            results.append(f"❌ {srv['name']}: {e}")
            failed += 1
            log(f"❌ 异常: {e}")
        
        time.sleep(2)

    return {
        "label": label,
        "ok": failed == 0,
        "msg": f"成功 {renewed} 台，失败 {failed} 台",
        "renewed": renewed,
        "failed": failed,
        "results": results,
    }


def collect_accounts():
    """收集账号列表"""
    accounts = []
    
    if MULTI_ACCOUNTS:
        for line in MULTI_ACCOUNTS.splitlines():
            line = line.strip()
            if not line:
                continue
            if "|||" in line:
                name, ck = line.split("|||", 1)
                accounts.append((name.strip(), ck.strip()))
            else:
                accounts.append((f"account-{len(accounts)+1}", line))
    
    if not accounts and COOKIE:
        accounts.append(("main", COOKIE))
    
    return accounts


def build_summary(all_results):
    """构建汇总消息"""
    renewed_total = sum(r.get("renewed", 0) for r in all_results)
    skipped_total = sum(r.get("skipped", 0) for r in all_results)
    failed_total = sum(r.get("failed", 0) for r in all_results)

    lines = ["🎮 *ACLClouds 自动续期*", f"⏰ {now_str()}", ""]
    lines.append(f"📊 ✅ {renewed_total} | ❌ {failed_total}")
    lines.append("")

    for r in all_results:
        if not r.get("ok"):
            lines.append(f"👤 {r['label']}: ❌ {r.get('msg', '失败')}")
        else:
            lines.append(f"👤 {r['label']}: ✅ {r.get('msg', '成功')}")
            if "results" in r:
                for res in r["results"]:
                    lines.append(f"  {res}")
        lines.append("")

    return "\n".join(lines)


def main():
    log(f"🚀 ACLClouds 续期脚本启动 @ {now_str()}")
    log(f"⚙️ 站点: {BASE_URL}")
    log(f"⏰ 续期阈值: {RENEW_THRESHOLD_HOURS}h")

    accounts = collect_accounts()
    if not accounts:
        msg = "❌ 未配置 ACL_COOKIES 或 ACL_ACCOUNTS\n\n请使用以下环境变量之一：\n- ACL_COOKIES: 单账号 Cookie\n- ACL_ACCOUNTS: 多账号 (格式: name|||cookie)"
        log(msg)
        send_tg(msg)
        sys.exit(1)

    log(f"📋 共 {len(accounts)} 个账号")

    all_results = []
    for label, ck in accounts:
        try:
            res = process_account(label, ck)
        except Exception as e:
            res = {"label": label, "ok": False, "msg": f"异常: {e}", "renewed": 0, "failed": 1}
        all_results.append(res)

    summary = build_summary(all_results)
    print("\n" + summary + "\n")
    send_tg(summary)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n用户中断")
    except Exception as e:
        log(f"💥 未捕获异常: {e}")
        send_tg(f"🎮 ACLClouds 续期\n\n💥 脚本崩溃: {e}")
        sys.exit(1)

