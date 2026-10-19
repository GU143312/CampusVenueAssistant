# GitHub配置记录

日期：2026-10-20，UTC+08。

目标仓库：https://github.com/GU143312/CampusVenueAssistant ，私有仓库，默认分支main。当前任务包含首次提交与推送，不部署公网服务。

## 配置

- `.python-version`固定Python 3.12系列；uv.lock精确锁定项目依赖。
- `.github/workflows/ci.yml`在Windows/Ubuntu执行离线测试、种子生成和SDK MCP往返检查；uv版本0.12.23；第三方Action固定到已核对的提交SHA。
- Workflow仅申请contents:read，checkout不持久化凭据，不读取或配置API密钥。
- `.gitignore`排除所有环境密钥文件（保留空模板.env.example）、证书、虚拟环境、运行数据和日志。
- `.gitattributes`及`.editorconfig`统一编码与换行；PR模板提示验证及共享接口契约。
- 本仓库Git提交邮箱使用GitHub noreply地址，只修改仓库级配置，不修改全局Git身份。
- 未配置自动合并，未邀请未指定的协作者；未发布学校资料或本地数据库。

## 检查记录

首次推送前检查：

- `uv sync --locked --dev`：成功，同时清理初次MCP 2.x安装遗留的mcp-types包。
- `uv run --locked python -m pytest -q`：40 passed in 8.44s。
- `uv run --locked python -m scripts.smoke`：真实MCP往返通过，数据库哈希不变。
- `uv run --locked python -m compileall -q app agent_layer domain mcp_server storage scripts`：exit 0。
- `uv pip check`：81个包兼容。
- `git diff --cached --check`：通过；37个待上传文件检查，未发现疑似密钥或应排除的文件；CI YAML结构校验通过。

远端运行结果将在首次CI完成后追加。

## 维护约定

新功能在分支开发并通过PR审阅。模型API Key仍需开发者在本机配置；不应为离线CI添加密钥。若将来增加真实模型评估，需另行配置限定触发条件与预算。

依据：[uv GitHub Actions官方集成文档](https://docs.astral.sh/uv/guides/integration/github/)。Action版本与SHA通过各自官方GitHub仓库API核对。
