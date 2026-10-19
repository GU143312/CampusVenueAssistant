# 前期开发与可行性验证记录

首次原型验证：2026-10-20 01:04 UTC+08。项目：CampusVenueAssistant；分支main。GitHub配置与后续检查记录见GITHUB_SETUP.md。

## 结论

已验证本地只读查询方案可运行：Gradio表单 → OpenAI Agents SDK MCP客户端 → stdio子进程 → FastMCP → SQLite只读业务查询。无需API Key。真实语言模型、自然语言追问、多Agent和最终预约闭环未验证。

## 环境与依赖

Windows，本机Python 3.12.7，uv 0.12.23。实测版本：openai-agents 0.24.0、mcp 1.30.0、pydantic 2.14.1、gradio 6.30.0、pytest 9.1.1。uv.lock为主要精确锁文件，requirements.lock.txt为导出副本。

初次安装无上限的mcp得到2.3.0，实际启动报mcp.server.fastmcp已移除，MCP测试失败；修复为pyproject.toml中mcp>=1.26,<2并重锁到1.30.0。不要直接照方案示例安装无限制最新版。初次测试还发现测试文件装饰器语法错误，已修复并重跑。

## 实际执行与观察

命令均在项目根目录PowerShell执行。

| 命令或操作 | 观察结果 |
|---|---|
| uv venv --python C:/ProgramData/anaconda3/python.exe .venv | 建立独立虚拟环境 |
| uv lock；uv sync --locked | 初次解析/安装成功，但后续发现MCP 2.x不兼容示例 |
| uv add 'mcp>=1.26,<2' | 改为mcp 1.30.0并更新锁文件 |
| .venv/Scripts/python.exe -m scripts.seed --base-date 2026-10-20 | 10房间、28条模拟预约记录、一周数据 |
| .venv/Scripts/python.exe -m pytest -q --junitxml=work/pytest.xml | 最终40 passed in 22.74s，无失败 |
| .venv/Scripts/python.exe -m scripts.smoke，先设CAMPUS_NOW=2026-10-20T09:00:00+08:00 | 成功发现3个只读工具；规则和空位工具真实往返成功；16个候选，首项C301 17:30–19:30；数据库SHA256前后相同 |
| .venv/Scripts/python.exe -m compileall -q app agent_layer domain mcp_server storage scripts | exit 0 |
| uv pip check | 82个已安装包检查通过，无依赖冲突 |
| .venv/Scripts/python.exe -m agent_layer.read_agent 'test'，未配置Key/模型 | 预期exit 1，明确提示缺少OPENAI_API_KEY/AGENT_MODEL，未调用模型 |
| uv export --frozen --no-hashes --format requirements-txt --output-file requirements.lock.txt | 导出锁定依赖 |
| 浏览器打开127.0.0.1:7860并点击默认查询 | 页面显示16个时段、前5项，首项C301；MCP真实回执可展开 |
| 浏览器设必须C栋、15:30–17:30、6人、120分钟、投影 | 页面显示没有满足全部硬约束的时段，清空候选，没有自动放宽 |

测试总数40包含参数化实例，不是40个独立用户任务，更不是LLM评估成功率。单次运行耗时受冷启动影响，不能据此报告产品延迟P95。

## 验证覆盖

- 硬约束：人数、设备、楼栋、时长、日期、时间边界；非法类型、额外字段、缺失字段被拒。
- 时段：重叠排除、边界相邻允许、取消记录不占用、过去时段排除。
- 资格：禁用房间/实验室过滤；日程不暴露用户身份。
- 排序：软偏好、时间、房间编号；limit、总数、截断标记和稳定候选ID。
- 错误：缺库、过期数据、规则版本不一致与无候选明确区分。
- 只读：数据库DELETE被拒；直接服务及MCP调用前后文件哈希不变；create_booking工具不存在。
- 协议：SDK真实stdio子进程发现/调用3工具；结构化和文本信封解析；isError处理。
- UI回调：正常、无解、非整数输入、后台缺库路径；浏览器验证正常和无解。

## 未验证和已知限制

真实模型调用、模型可用性/费用/延迟、自然语言成功率、长期多轮会话、Coordinator→Search.as_tool、注入防御模型效果、云端Trace、另一台机器重装、macOS/Linux均未验证。当前测试保证确定性层和接口行为，不能证明模型永远不幻觉。

当前规则检索是关键词基线；不是完整Agentic RAG。规则JSON与校验器阈值仍有重复，测试固定检查版本内参数，后续应集中配置。每次表单查询都会启动MCP子进程，尚未做性能优化。库结构是只读子集，没有原方案的tasks/proposals/approvals/operations/preferences等表。

下一步优先：A接入模型参数提取、追问和状态；B/C对齐另一组契约并完成12例自然语言评估；10月22日冻结演示、整理PPT和排练。当前12例保存在evals/readonly_cases.json，状态明确标注为未执行。
