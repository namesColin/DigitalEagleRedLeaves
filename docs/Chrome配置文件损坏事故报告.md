# 事故报告：Chrome Profile Cookie 加密密钥被覆盖

日期：2026-07-14
分支：experiment/three-layer-perception
影响：默认 Chrome Profile 的 `Local State` 加密密钥被覆盖，全部网站登录态丢失

---

## 1. 事件时序

| 步骤 | 操作 | 结果 |
|------|------|------|
| 1 | 启用 `chrome://inspect/#remote-debugging`（Chrome 150） | CDP 端口 9222 打开 |
| 2 | Agent 通过 `DevToolsActivePort` 文件连接 | WebSocket 握手成功 |
| 3 | Page 级 CDP 命令返回空 | `Target.attachToTarget` 的 flatten 模式路由失败 |
| 4 | 每次新连接弹出权限对话框 | 用户问能否永久绕过（答案：不能） |
| 5 | 决定从 inspect 模式切换到 `--remote-debugging-port` 方案 | 架构方向变更 |
| 6 | 查资料：Chrome 136+ 要求非默认 `--user-data-dir` 才能远程调试 | 提出联结方案 |
| 7 | `mklink /J C:\chrome-agent-junction` 指向默认 Profile | 联结创建成功 |
| 8 | `taskkill /f /im chrome.exe` | Chrome 强制终止 |
| 9 | `chrome --remote-debugging-port=9222 --user-data-dir=C:\chrome-agent-junction` | Chrome 以联结路径启动 |
| 10 | Chrome 读取 `Local State` 中 `encrypted_key`，用 DPAPI 尝试解密 | 路径字符串不匹配，解密失败 |
| 11 | Chrome 生成新 `encrypted_key`，写回 `Local State` | 原始密钥被静默覆盖 |
| 12 | `Network/Cookies`（1.9MB）用旧密钥加密 | 数据不可读，全部登录态丢失 |

---

## 2. 根因分析

### 2.1 技术机制

Chrome 的 Cookie 加密使用两级密钥体系：

```
DPAPI (Windows) + 数据目录路径作为熵
    ↓ 解密
encrypted_key（在 Local State 中）
    ↓ 解密
Cookie 数据（在 Default/Network/Cookies 中）
```

`encrypted_key` 本身由 Windows DPAPI 加密。Chrome 调用 DPAPI 时将 `--user-data-dir` 的路径字符串作为额外熵参数传入。

当 `--user-data-dir` 参数变化时——即使底层是同一个物理目录（通过联结）——传给 DPAPI 的字符串不同，旧的 `encrypted_key` 解密失败。Chrome 不会报错，而是静默生成新密钥并写回 `Local State`。

**关键发现：Chrome 不解析联结的物理路径。只比对 `--user-data-dir` 参数的字符串值。** `C:\chrome-agent-junction` 和 `C:\Users\yin\AppData\Local\Google\Chrome\User Data` 是同一物理位置，但在 Chrome 看来是两个不同的数据目录。

这跟之前 Profile 拷贝方案（`chrome_agent_profile`）导致登录丢失的原因相同。联结没能解决它，因为路径字符串还是变了。

### 2.2 决策错误

**错误一：对 Chrome 路径判断机制的假设错误**

假设 Chrome 通过物理路径判断是否为默认数据目录。实际上 Chrome 比较的是参数字符串，不解析联结。

**错误二：在用户真实数据上直接测试**

联结方案没有先在临时 Profile 上验证加密行为。测试环境就是用户的生产数据。

**错误三：遇到障碍时改变方案而非修复问题**

`chrome://inspect` 的 websockets 超时是库兼容性问题（websockets 16.1 async 在 Python 3.13 + Windows 上握手超时），不是 inspect 方案不可行。已验证原始 TCP 握手正常，同步版客户端正常。应该修复库的调用方式，而非替换整个连接架构。

### 2.3 正确做法

```
inspect + websockets 超时
    ↓
验证：原始 TCP WebSocket 握手正常？→ 正常
验证：同步版 websockets 客户端正常？→ 正常
修复：改用 sync client + asyncio.to_thread
    ↓
完成。不涉及 Profile。
```

---

## 3. 数据影响

| 类别 | 状态 | 说明 |
|------|------|------|
| 网站 Cookie | 丢失 | `Network/Cookies`（1.9MB）新密钥无法解密 |
| Google 登录态 | 丢失 | 也是 Cookie |
| Chrome 同步数据（密码、书签、历史、扩展） | 可恢复 | 云端数据不受影响，重登 Google 后同步 |
| `Default/Preferences` | 完好 | 明文存储 |
| `Default/Login Data` | 可能丢失 | 加密数据，依赖云端同步恢复 |

---

## 4. 防护措施

### 规则 1：禁止变更 `--user-data-dir` 路径

任何对 `--user-data-dir` 的变更——拷贝、联结、符号链接——都会触发密钥轮换。用户当前运行的 Chrome 实例是唯一合法的入口。

### 规则 2：破坏性操作先在隔离环境测试

操作 Chrome Profile 前必须：
1. 创建临时 Profile 验证方案可行性
2. 确认 `Local State` 的 `encrypted_key` 未被修改
3. 确认 Cookie 可读
4. 经用户确认

### 规则 3：在问题发生层面解决问题

库兼容性问题是库层面的，用库层面的手段解决。不升级为架构替换。

### 规则 4：连接方案优先级

| 优先级 | 方案 | 数据风险 |
|--------|------|---------|
| 第一 | `chrome://inspect` 读 `DevToolsActivePort`，WebSocket 直连 | 零 |
| 第二 | 独立浏览器 + 独立 Profile | 零 |
| 禁止 | `--user-data-dir` 指向用户默认 Profile | 数据丢失 |

---

## 5. 恢复步骤

1. 正常打开 Chrome（桌面快捷方式，无命令行参数）
2. 登录 Google 账号 → Chrome 同步恢复密码、书签、历史、扩展
3. 逐个重登各网站
4. 启用 `chrome://inspect/#remote-debugging`
5. Agent 通过 `DevToolsActivePort` 连接，不再碰 Chrome Profile
