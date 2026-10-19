# Windows API配置

## 首次配置

在项目目录打开自己的PowerShell，运行以下命令。需要现有虚拟环境；新克隆先执行`uv sync --locked`。

```powershell
.\.venv\Scripts\python.exe -m scripts.configure_api set
```

程序先隐藏输入API Key，再询问账户可用的模型ID。成功显示Saved with Windows current-user DPAPI。重新运行set可替换已保存配置，不需要将密钥写入命令行、.env或源码。

若之前在同一个终端配置过OPENAI_API_KEY和AGENT_MODEL，则执行：

```powershell
.\.venv\Scripts\python.exe -m scripts.configure_api set --from-env
```

该命令要求两个环境变量均有效且非空，不打印它们。只设置过Key但尚未选择模型时，请用交互式set。模型ID是否可用需要后续实际调用验证；本配置程序不验证账户或余额。

## 检查与重启后使用

```powershell
.\.venv\Scripts\python.exe -m scripts.configure_api status
```

status解密检查本地文件，只报告是否存在、能否读取，不显示密钥或模型值。关闭终端或重启电脑后，无需重新设置环境变量，真实模型入口自动加载：

```powershell
$env:CAMPUS_NOW = '2026-10-20T09:00:00+08:00'
.\.venv\Scripts\python.exe -m agent_layer.read_agent "2026-10-23，6人，15:30至19:30使用120分钟，需要投影，偏好C栋。"
```

上面的模型命令会调用API，可能产生费用；保存、status及删除配置不调用API。没有可用额度时继续使用`Run-Demo.ps1`离线表单即可。

读取顺序按字段分别为：当前进程环境变量 → 本机DPAPI保存值。环境变量都齐全时不读文件；缺少字段时才使用保存值补齐。如需本终端完全使用加密配置，可先清理临时覆盖：

```powershell
Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:AGENT_MODEL -ErrorAction SilentlyContinue
```

## 保存位置与保护边界

加密文件：`%LOCALAPPDATA%\CampusVenueAssistant\credentials.dpapi`。保存整个配置的DPAPI密文，使用当前用户范围，未使用LOCAL_MACHINE标志。临时文件也只写密文，设置当前用户专用DACL后原子替换目标文件；失败时保留原文件。

程序不向环境变量回写解密后的Key，而是将它直接交给内存中的OpenAI客户端；不把Key传给模型提示词或MCP工具。离线表单和MCP服务器不会主动读取此文件。文件位于仓库之外，`.gitignore`也额外排除`*.dpapi`；每位组员使用自己的Key。

DPAPI通常绑定Windows用户与电脑。换用户/电脑、用户配置损坏或某些密码恢复操作后可能需要重新保存。它保护静态文件，不防同一账户下的恶意程序或管理员，也不能保证Python内存中的明文被彻底擦除。文件损坏或不能解密时明确报错，不回退到明文存储。

## 删除或更换

```powershell
.\.venv\Scripts\python.exe -m scripts.configure_api delete
```

delete只删除本地加密文件，不撤销OpenAI密钥，不清除现有进程环境变量。更换密钥直接重新运行set；若密钥泄露，应在OpenAI平台撤销后重新生成。

## 实现与验证

`app/credentials.py`封装CurrentUser DPAPI和文件访问；`scripts/configure_api.py`提供隐藏输入和管理命令；`agent_layer/read_agent.py`在创建OpenAI客户端前加载配置。pywin32作为Windows条件依赖显式声明，非Windows仍可使用环境变量。

2026-10-20本机执行：

- `uv run --locked python -m pytest -q --tb=short`：59 passed in 8.01s。
- `uv pip check`：81个包兼容。
- `uv run --locked python -m compileall -q app agent_layer scripts`：成功。
- `uv export --frozen --no-hashes --format requirements-txt --output-file requirements.lock.txt`：重新导出锁文件。

新增测试全部使用临时目录与假密钥；覆盖真实DPAPI往返、当前用户DACL、更新/删除、密文破坏、原子保存失败、无Key环境变量的新进程读取、环境覆盖优先级、Linux回退、输入与文件格式校验、隐藏输入失败拒绝以及模型启动参数接线。未使用真实API Key、未调用付费API、未实际重启Windows或切换Windows账户。首次参数化测试的超长自动ID触发Windows路径错误，已改为短ID后全套重跑通过。

来源：[Microsoft CryptProtectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)、[Microsoft CryptUnprotectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptunprotectdata)、[OpenAI密钥管理建议](https://developers.openai.com/api/docs/guides/production-best-practices)。
