# ACLClouds 自动续期 - 修复指南 (2026-09 改版)

## 改版后 401 的根本原因

**站点改版**: `dash.aclclouds.com` 已废弃, 所有请求 302 到 `aclclouds.com`。

| 项目 | 改版前 | 改版后 |
|------|--------|--------|
| 面板域名 | `dash.aclclouds.com` | `aclclouds.com/dashboard` |
| Cookie 来源 | 可以是 dash | **必须从 aclclouds.com 复制** |
| API 基址 | dash.aclclouds.com | `aclclouds.com/api/...` (dash 会 302) |

**为什么脚本会 401**:
1. 旧脚本 `BASE_URL` 指向 `dash.aclclouds.com`
2. dash 对所有 API 请求返回 302 → `aclclouds.com`
3. Python `requests` 在**跨域重定向时自动丢弃 Cookie 头**
4. 到 `aclclouds.com` 时没有会话 → `401 Unauthenticated`
5. 脚本未检测到失败 (exit 0) → Actions 显示"假成功"

## 解决方案 (已写入 renew_fixed.py)

### 1. BASE_URL 必须指向 aclclouds.com

```bash
# 正确 (默认值, 无需设置)
export ACL_BASE_URL="https://aclclouds.com"

# 错误
export ACL_BASE_URL="https://dash.aclclouds.com"   # 会 302 + 丢 Cookie -> 401
```

### 2. Cookie 从 aclclouds.com 复制

1. 打开 **https://aclclouds.com/dashboard** (不是 dash.aclclouds.com)
2. 登录后 F12 → Application → Cookies → `https://aclclouds.com`
3. 复制完整的 Cookie 字符串, 必须包含:
   - `XSRF-TOKEN=...`
   - `__Host-aclclouds_session=...`

### 3. 更新 GitHub Secret

仓库 → Settings → Secrets and variables → Actions → 更新 `ACL_COOKIES` 为新 Cookie。

## 常见错误对照

| 错误 | 含义 | 处理 |
|------|------|------|
| **401** | 会话无效/过期/域名不匹配 | 按上面第 2 步重新复制 Cookie; 确认 BASE_URL 是 aclclouds.com |
| **403** | Cloudflare 风控 / Turnstile | 换网络重试; 数据中心 IP 易被风控; 面板续期接口一般不强制验证 |
| **404** | 服务器 id 类型不对或已删除 | 脚本已自动用短标识 (uuid 前 8 位); 仍 404 检查该服务器是否还存在 |

## 本地快速验证

```bash
export ACL_COOKIES="XSRF-TOKEN=xxx; __Host-aclclouds_session=xxx"
export DEBUG=1
python renew_fixed.py
```

看到 `✅ API 登录验证通过` 即 Cookie 有效。

## 排查脚本

```bash
# 检查 Cookie 是否包含关键项
echo "$ACL_COOKIES" | tr ';' '\n' | grep -E "(XSRF|session)" | head -5

# 不带 Cookie 直连 API, 应返回 401 (而非 404/302)
curl -s -H "Accept: application/json" https://aclclouds.com/api/client
```
