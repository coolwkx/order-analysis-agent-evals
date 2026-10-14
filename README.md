# 订单分析 Agent 与评测实验

Python + DeepSeek + MySQL 学习项目：模型自主选择查询年月，通过只读工具获取数据，并输出月消费变化的结构化结果。包含工具保护、注入故障、边界任务配置和规则评测。

## 架构

用户任务 → 模型提出工具调用 → 程序白名单及参数校验 → 查询/注入工具 → 返回关联调用结果 → 模型继续或结束 → 独立评测。

模型请求最多六轮，工具请求最多四次。同一任务内相同参数的查询只尝试一次；失败后也不自动重试。

## 快速开始

在仓库根目录执行。已验证的本机 Python 为 3.13.5，推荐使用独立环境。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Linux/macOS 对应使用 `.venv/bin/python`。无需激活环境。

仅用注入数据实验时，不需要 MySQL，但仍需安装依赖。

```powershell
$env:DEEPSEEK_BASE_URL = "https://api.deepseek.com"
$env:DEEPSEEK_MODEL = "deepseek-flash"
$key = Read-Host "输入 API Key" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($key)
try { $env:DEEPSEEK_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr); Remove-Variable key,ptr }
.\.venv\Scripts\python.exe src/run_comparison_cases.py --check-only
.\.venv\Scripts\python.exe src/run_comparison_cases.py
```

最后一条命令使用真实模型，产生 API 费用。`.env.example` 仅作配置参考，程序不会自动读取 `.env`。

## 真实数据库运行

1. 用管理账号在数据库客户端执行 `sql/init.sql`。已有五条数据时不要重复执行 INSERT；不删除已有数据。
2. 单独创建 `agent_reader` 账号，设置自己的密码，并授予练习订单表 SELECT 权限。
3. 在同一 PowerShell 设置配置，再运行：

```powershell
$env:MYSQL_HOST = "127.0.0.1"
$env:MYSQL_PORT = "3306"
$env:MYSQL_DATABASE = "agent_eval_lab"
$env:MYSQL_USER = "agent_reader"
$password = Read-Host "输入数据库密码" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($password)
try { $env:MYSQL_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr); Remove-Variable password,ptr }
.\.venv\Scripts\python.exe src/check_mysql.py
.\.venv\Scripts\python.exe src/agent_demo.py
```

只读账号配置与远程主机匹配需依据自己的服务器设置。管理员账号不用作 Agent 查询账号。

## 路径

运行记录默认写入仓库 `work/`，报告写入 `outputs/`；均不提交 Git。

已有 D 盘环境可以继续使用原解释器，并设置：

```powershell
$env:AGENT_WORK_DIR = "D:\Codex\work\agent-eval-lab"
$env:AGENT_OUTPUT_DIR = "D:\Codex\outputs\agent-eval-lab"
```

## 验证入口

无需模型、无需数据库：

```powershell
python src/test_tool_guard.py
python src/test_agent_duplicate.py
python src/validate_case_answers.py
```

需要真实数据库：`python src/test_db_tools.py`。

需要真实模型：`run_live_suite.py`、`run_injected_suite.py`、`run_comparison_cases.py`。

`run_evaluation_suite.py` 与 `summarize_live_runs.py` 是历史记录复评工具，依赖原记录存在；新克隆不能直接复现历史记录评分。`test_evaluator.py` 需要通过参数提供正常/失败记录路径。

## 文件与文档

- `src/agent_demo.py`：模型接口与执行循环。
- `src/db_tools.py`：参数化 SQL、连接与业务工具。
- `src/tool_guard.py`：重复调用保护。
- `cases/comparison_cases.json`：四个边界场景及参考答案。
- `sql/init.sql`：五条练习订单初始化。
- [项目与面试详细问答](docs/interview_qa.md)：原理、设计取舍、评测、Python/SQL 与面试表达。
- [实验报告](docs/experiment_report.md)：已观察结果与证据限制。
- [发布验证](docs/release_validation.md)：本次整理所运行的检查。

## 结果与限制

学习阶段：正常/澄清/非法月份三个开发任务各运行三次，通过当前检查；部分失败/空月份两场景通过；无下降/并列下降/两月为空/用户并集四场景通过。这些来自不同阶段，不能合并为生产成功率。

JSON 格式主要依赖提示词；Agent 正常结束不等于业务成功。评分器限定场景，语义澄清仍需人工检查。无独立保留测试集、无真实故障恢复和工作流对照实验。公开整理后的路径调整不会被旧实验结果覆盖，请区分历史结果与发布验证。

这是学习项目，适合展示工具调用与评测闭环，不宣称生产可靠性。
