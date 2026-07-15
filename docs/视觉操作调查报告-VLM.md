# VLM 视觉操作方案调查报告

> 日期：2026-07-13
> 测试模型：GLM-4V-Flash、Agnes-2.0-Flash、Qwen-3.7-Plus、Qwen-VL-Max
> 结论：**VLM 直接看图方案目前不可行，建议回退到 OmniParser + 文本 LLM 方案**

---

## 一、测试历程

| 模型 | 端点 | 结果 |
|------|------|------|
| GLM-4V-Flash | 智谱 | 识别不准，坐标乱猜 |
| Agnes-2.0-Flash | Agnes | 完全不可用，乱判完成 |
| Qwen-3.7-Plus | 阿里北京 | 理解力好，端点不稳定超时 |
| Qwen-VL-Max | DashScope | 理解力最好，但仍反复失败 |

---

## 二、一次完整失败解剖（Qwen-VL-Max）

目标：打开 Chrome 进入 bilibili 主页。

```
Step 1:  operation=click, id=1     → "未知操作"   ✗ key 名是 operation 不是 action
Step 2:  click id=13               → 点中一条线     ✗ 选错元素
Step 3:  click id=13               → 又点那条线     ✗ 重复错误
Step 4:  operation=win_search      → "未知操作"    ✗ key 名又是 operation
Step 5:  win_search('chrome')      → 搜空字符串     ✗ 括号参数没提取到
Step 6:  click id=47               → 点了某个图标   ✗ 不是 Chrome
Step 7:  Chrome开了说是"股票软件"   → 重新搜索      ✗ 识别错误
Step 8:  click(element_id=47)      → id=None        ✗ 括号参数没解析
Step 9:  click(element_id=28)      → id=None        ✗ 同上
Step 10: operation=click           → "未知操作"    ✗ 回到 operation key
```

---

## 三、根本原因（按严重程度）

### 1. Qwen 输出格式极度不稳定（致命）

同一个任务里用了 **6 种不同格式**：

| 格式 | 出现步骤 |
|------|----------|
| `{"action":"click","element_id":13}` | Step 2,3 |
| `{"operation":"click","element_id":1}` | Step 1,10,11 |
| `{"action":"click(element_id=47)"}` | Step 8,9 |
| `{"action":"win_search('chrome')"}` | Step 5 |
| `{"operation":"win_search","argument":"chrome"}` | Step 4 |
| `{"action":"alt_tab()"}` | 往轮 |

每次变一种格式，解析代码追不上。**这是模型本身的问题，不是 prompt 能解决的。**

### 2. OmniParser 标签对决策无用

73% 的标签是这类：
- "a single line or bar"
- "A simple application or service icon"
- "A stylized text editing tool"
- "a black background with..."

80 个检测框里 60 个标签长得差不多，Qwen 分不出哪个是 Chrome 图标、哪个是 VS Code 按钮、哪个是文件管理器。

### 3. Qwen 具体识别不准

- Chrome 用户选择界面 → "股票软件"
- IDE 内的 Chrome 文件标签 → 没认出来
- 能判断大场景（"桌面"、"有窗口"），认不出具体应用

### 4. 网络不稳定

北京 Workspace 端连续超时。DashScope 好一些但有波动。

---

## 四、为什么会反复失败

VLM 做桌面自动化的隐含假设：

```
VLM精准理解 → 精准定位 → 一致输出 → 执行成功
```

实际每一步都断裂：

```
大概理解(60分) → 定位靠猜(20分) → 格式随机(0分) → 失败
```

**格式不稳定性**最致命——代码补逻辑追不上模型换格式。**标签无意义**第二致命——OmniParser 检测框准，但标签不够细，模型没法判断。

---

## 五、建议

### 回退到 OmniParser + DeepSeek 文本推理

```
截图 → OmniParser 检测 → 格式化文本 → DeepSeek 推理 → 操作
```

之前这个方案失败是因为 planner 逻辑太简单（一次规划全部步骤、不回头看屏幕），不是检测精度问题。改成循环（每步截屏→检测→推理→执行→验证）即可。

DeepSeek 文本输出格式比 VLM 多模态稳定得多——纯文本模型的输出一致性远好于视觉模型。

### 不推荐继续试 VLM

Qwen-VL-Max 已是阿里最强视觉模型。它还不行，其他 VLM 也没有本质区别——输出格式稳定性在 2026 年仍是行业通病。

---

*基于 20+ 次实际运行测试失败记录分析*
