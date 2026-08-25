# ACLClouds 自动续期

为(https://aclclouds.com/dashboard/projects) 上的免费 Minecraft / VPS 服务器自动续期。

## 工作原理

- 直接调用 Pelican 风格 API: `POST /api/client/servers/{id}/upgrade/renew`
- 通过 Cookie 注入保持登录态 (无需浏览器 / 无需代理 / 不触发 Turnstile)
- 默认剩余时间 < 48h 自动续期
- 每天 UTC 03:00 / 15:00 跑两次 (Actions 自带 cron)

## 部署步骤

### 1. Fork / Clone 本仓库到你的 GitHub

### 2. 获取 Cookie

1. 用浏览器登录 <https://dash.aclclouds.com>
2. 按 `F12` 打开开发者工具 → `Application` (或 `存储` / `Storage`) → `Cookies` → `https://dash.aclclouds.com`
3. 复制全部 Cookie 为一个字符串 (格式: `key1=value1; key2=value2; ...`)

> 必须包含这两个关键 Cookie: `XSRF-TOKEN` 和 `aclclouds_session` (或类似 session 名)
>
> 推荐用浏览器扩展 **EditThisCookie** / **Cookie-Editor** 一键导出 → "导出为 Header 字符串"

### 3. 配置 GitHub Secrets

进入仓库 → `Settings` → `Secrets and variables` → `Actions` → `New repository secret`:

| Secret 名称 | 必填 | 说明 |
| --- | --- | --- |
| `ACL_COOKIES` | ✅ | 单账号 Cookie 字符串 |
| `ACL_ACCOUNTS` | 多账号 | 格式: `name1\|\|\|cookie1\nname2\|\|\|cookie2` (每行一个) |
| `TG_BOT_TOKEN` | TG 通知 | Telegram Bot Token |
| `TG_CHAT_ID` | TG 通知 | 接收通知的 Chat ID |

> `ACL_ACCOUNTS` 和 `ACL_COOKIES` 二选一, 同时配置时 `ACL_ACCOUNTS` 优先

### 4. 手动测试

进入仓库 → `Actions` → `ACLClouds-Renew` → `Run workflow`

## 续期规则 (面板内置)

| 服务类型 | 可续期阈值 |
| --- | --- |
| 免费服务 (普通) | 到期前 2 天 |
| 免费 Minecraft | 到期前 2 小时 |
| 付费服务 | 4 天前 |

脚本默认 `< 48h` 就尝试续期, 后端会返回 `renewNotAvailableYet` 错误并跳过, 不影响其他服务器。

## 本地调试

```bash
pip install -r requirements.txt
export ACL_COOKIES="XSRF-TOKEN=...; aclclouds_session=..."
export TG_BOT_TOKEN="可选"
export TG_CHAT_ID="可选"
python renew.py
```

## TG 通知示例

```
🎮 ACLClouds 自动续期
⏰ 2026-07-16 03:00:00 UTC

📊 总服务器: 3 | ✅ 2 | ⏭️ 1 | ❌ 0

👤 main (✅2 ⏭️1 ❌0)
  ✅ MyServer1: 12h 30m → 60h 30m
  ✅ MyServer2: 6h 0m → 54h 0m
  ⏭️ MyServer3: 剩 3d 0h, 未到阈值 48h
```

## 维护

- Cookie 有效期约 7-30 天, 过期后重新登录复制即可
- 后端接口变更: 修改 `renew.py` 中的 `renew_server()` 函数
- 想改阈值: 修改 `RENEW_THRESHOLD_HOURS` 环境变量 (workflow_dispatch 输入框可临时覆盖)

