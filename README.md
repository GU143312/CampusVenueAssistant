# 校园场地查询助手

[![CI](https://github.com/GU143312/CampusVenueAssistant/actions/workflows/ci.yml/badge.svg)](https://github.com/GU143312/CampusVenueAssistant/actions/workflows/ci.yml)

BSAI408 课程项目，OpenAI Agents SDK + MCP 小组的前期原型。全部场地、预约和政策均为模拟数据，不连接学校系统。

当前实现：结构化表单 → Agents SDK 的 MCPServerStdio → 本地 FastMCP → SQLite 只读查询 → 候选与条款展示。此路径不调用语言模型，也不需要 API Key。可用于 2026-10-23 proposal 演示技术可行性。

## 本机启动

在此目录打开 PowerShell：

```powershell
.\Run-Demo.ps1
```

如果本机执行策略禁止脚本，可运行同等命令，无需修改系统执行策略：

```powershell
$env:PYTHONUTF8 = '1'
$env:CAMPUS_NOW = '2026-10-20T09:00:00+08:00'
.\.venv\Scripts\python.exe -m app.ui
```

打开终端打印的本地地址（通常为 http://127.0.0.1:7860）。Ctrl+C 停止。服务仅监听本机，share=False。

固定演示时间是 2026-10-20 09:00 UTC+08，不是电脑当前时间。默认查询 2026-10-23。固定时钟可避免汇报当天演示数据失效。

## 新机器安装

先安装 Git、Python 3.12 和 uv，再克隆私有仓库（需要仓库访问权限）：

```powershell
git clone https://github.com/GU143312/CampusVenueAssistant.git
cd CampusVenueAssistant
```

当前实测环境 Python 3.12.7、uv；依赖精确锁定于 uv.lock。技术方案建议 3.11，本次沿用本机已安装的 3.12，并将兼容范围暂时限制为 3.12。

```powershell
uv sync --locked
uv run --locked python -m scripts.seed --base-date 2026-10-20
.\Run-Demo.ps1
```

已存在的演示库不会自动被覆盖。需要重置时显式执行：

```powershell
.\.venv\Scripts\python.exe -m scripts.seed --base-date 2026-10-20 --reset
```

这只适用于本项目模拟库；种子工具不会通过 MCP 提供。切换到当前日期时，重新生成对应日期的种子库并清除 CAMPUS_NOW。日期范围为今天至今天+6天，按本地日期计算。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q
$env:CAMPUS_NOW = '2026-10-20T09:00:00+08:00'
.\.venv\Scripts\python.exe -m scripts.smoke
```

smoke 固定使用 2026-10-23 的演示场景。测试使用临时库，检查硬约束、排序、相邻和重叠时段、取消记录、资格、隐私、错误分类和真实 MCP 往返。结果见 docs/VERIFICATION.md。

## 演示步骤

1. 保持默认条件：10月23日、15:30–19:30、6人、120分钟、投影、偏好C栋。应找到16个房间时段，展示前5个，首选C301 17:30–19:30。
2. 将“必须楼栋”改为C，“最晚结束”改为17:30。应显示无解，而不擅自换到B栋。
3. 把“必须楼栋”改回不限。此时B201、B203、B204满足条件。
4. 展开MCP返回，展示 searched_scope、truncated、排除原因和条款ID；检索“时长”，展示P001。
5. 说明查询不创建预约；写入事务、多Agent和记忆属于后续里程碑。

## 后续真实模型联调

agent_layer/read_agent.py 是可选单Agent入口。必须由开发者在本地环境设置 OPENAI_API_KEY 与 AGENT_MODEL；.env.example 不会自动加载，密钥不要加入仓库或截图。当前未进行真实模型调用，不能据此宣称自然语言成功率。

```powershell
.\.venv\Scripts\python.exe -m agent_layer.read_agent "2026-10-23，6人，15:30至19:30之间使用120分钟，必须有投影，偏好C座。请查可用场地和规则。"
```

该入口设置90秒整轮超时、8轮上限，默认关闭云端Trace；将模型说明与工具回执分别输出。它目前没有跨轮对话记忆或输出事实复核控制器，不用于自动确认业务事实。模型ID待账户验证，不硬编码或臆测。

## 项目结构

| 路径 | 用途 |
|---|---|
| app/ | Gradio表单、SDK MCP连接与信封解析 |
| agent_layer/ | 可选真实模型单Agent入口 |
| mcp_server/ | 三个只读工具，stdio传输 |
| domain/ | 请求校验、排序、时段冲突和政策关键词检索 |
| storage/ | SQLite只读连接 |
| data/policies.json | 模拟政策文本和版本 |
| scripts/ | 可复现种子与MCP冒烟检查 |
| tests/ | 自动化业务和MCP测试 |
| docs/ | 范围、契约、proposal计划和验证记录 |

数据库、虚拟环境、密钥、运行日志不入版本控制。GitHub仓库为 [GU143312/CampusVenueAssistant](https://github.com/GU143312/CampusVenueAssistant)，默认分支main。

## GitHub配置与协作

每次推送main、向main提交PR或手动触发CI，GitHub Actions都会在Windows与Ubuntu安装锁定依赖，运行测试、生成模拟库、执行真实MCP往返检查和编译检查。CI不调用语言模型，不需要任何GitHub Secrets；运行令牌仅有代码读取权限。

GitHub托管代码和自动测试，不会部署本机Gradio服务。组员获得私有仓库权限后，按上方步骤在各自电脑运行。成员名单尚未提供，因此未自动邀请协作者。

建议功能开发使用独立分支和PR，检查CI后由成员审阅合并。当前没有配置自动合并。uv.lock是依赖更新的主依据；修改依赖后重新导出requirements.lock.txt：

```powershell
uv export --frozen --no-hashes --format requirements-txt --output-file requirements.lock.txt
```

Linux启动命令：

```bash
uv sync --locked
uv run --locked python -m scripts.seed --base-date 2026-10-20
CAMPUS_NOW=2026-10-20T09:00:00+08:00 GRADIO_ANALYTICS_ENABLED=False uv run --locked python -m app.ui
```
