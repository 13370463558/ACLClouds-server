# ACLClouds 自动续期 - 修复指南

## 问题诊断

你遇到的 401 错误原因：**Cookie 域名不匹配**

| 项目 | 值 |
|------|-----|
| 你使用的脚本 | `aclclouds.com` (远程版) |
| 你的 Cookie 来源 | 可能是 `dash.aclclouds.com` |
| 结果 | 域名不匹配 → 401 |

## 解决方案

### 方案 1: 使用修复版脚本（推荐）

已创建 `renew_fixed.py`，自动处理域名问题：

```bash
# 设置 Cookie
export ACL_COOKIES="XSRF-TOKEN=xxx; __Host-aclclouds_session=xxx"

# 运行修复版
cd /run/csi/mount-root/nas/4079184d856ecc166ed19d4887083405/workspaces/QwenPaw_QA_Agent_0.2/checkin-xuqi/ACLClouds-server
python3 renew_fixed.py
```

### 方案 2: 从正确域名获取 Cookie

1. 打开 **https://dash.aclclouds.com**（不是 aclclouds.com）
2. 登录后按 F12 → Application → Cookies
3. 复制完整的 Cookie 字符串

### 方案 3: 指定 BASE_URL

```bash
# 使用 dash.aclclouds.com
export ACL_BASE_URL="https://dash.aclclouds.com"
python3 renew_fixed.py

# 或使用 aclclouds.com
export ACL_BASE_URL="https://aclclouds.com"
python3 renew_fixed.py
```

## Cookie 格式验证

运行以下命令检查 Cookie：

```bash
echo "$ACL_COOKIES" | tr ';' '\n' | grep -E "(XSRF|session)" | head -5
```

应该看到：
```
XSRF-TOKEN=xxx
__Host-aclclouds_session=xxx
```

## 常见问题

### Q: 仍然 401？
**A**: Cookie 已过期，需要重新登录获取新 Cookie。

### Q: captcha_required？
**A**: 某些操作需要 Turnstile 验证，需要：
1. 安装浏览器依赖：`pip install seleniumbase`
2. 使用浏览器版脚本（需要 Chrome）

### Q: 多账号如何配置？
**A**:
```bash
export ACL_ACCOUNTS="账号1名|||cookie1
账号2名|||cookie2"
```

## 快速测试

```bash
# 测试 Cookie 是否有效
curl -s -H "Cookie: $ACL_COOKIES" \
     -H "X-XSRF-TOKEN: $(echo $ACL_COOKIES | grep -oP 'XSRF-TOKEN=\K[^;]+')" \
     "https://dash.aclclouds.com/api/client" | head -c 200
```

预期返回 JSON 数据（不是 401）。

