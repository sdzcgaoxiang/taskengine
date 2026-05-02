# TaskEngine 功能规格说明

## 概述

Windows Server 2016 桌面会话上运行的轻量定时任务引擎，调度多步脚本任务。

## 架构

```
engine.py    ← 纯业务逻辑（条件判断、配置加载、Step/Task 执行、状态持久化、通知）
cli.py       ← CLI 入口（serve / trigger / dashboard / list / version / help）
history.py   ← 运行历史记录（读写、清理、查询、运行锁）
dashboard.py ← 监控面板（终端表格渲染、ANSI 颜色）
tasks.yaml   ← 任务配置文件
```

**调用链：** `python engine.py` → `engine.__main__` → `cli.main()` → 根据 command 分发到 `_cmd_serve` / `_cmd_trigger` / `_cmd_dashboard` / `_cmd_list` / `_cmd_version` / `_cmd_help`。

**依赖方向：** `cli.py` → `engine.py` → `history.py`。`dashboard.py` → `history.py`。`engine.py` 不依赖 `cli.py`、`dashboard.py` 或 `apscheduler`。

## 一、任务定义（YAML）

| 项目 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| name | 是 | - | 唯一标识 |
| schedule | 是 | - | Cron 表达式 |
| timeout | 否 | 300 | 整体超时（秒） |
| retry | 否 | 0 | 失败后重试次数 |
| retry_delay | 否 | 60 | 重试间隔（秒） |
| params | 否 | [] | 参数列表，支持默认值 |
| http_notify | 否 | 全局配置 | URL + 触发条件 |
| steps | 是 | - | 有序步骤列表 |

## 二、Step 定义

| 项目 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| name | 是 | - | 步骤标识 |
| command | 是 | - | 要执行的命令，`{{参数}}` 替换 |
| workdir | 否 | 任务目录 | 工作目录 |
| timeout | 否 | 任务timeout | 步骤超时（秒） |
| retry | 否 | 0 | 步骤级重试次数 |
| retry_delay | 否 | 60 | 重试间隔（秒） |
| success_conditions | 否 | exit_code=0 | 成功判定规则列表 |

## 三、成功条件

多规则 **OR**，规则内 **AND**。

```yaml
success_conditions:
  - exit_code: 0                    # 规则1
  - exit_code: 1                    # 规则2
    output_contains: "OK"
```

含义：`exit_code==0 OR (exit_code==1 AND 输出包含"OK")`

省略 `exit_code` = 不检查返回码，省略 `output_contains` = 不检查输出。

## 四、重试策略

- **Step 重试**：单步失败后在原步重试
- **Task 重试**：从失败的 Step 开始重跑，已成功的 Step 跳过

## 五、调度

- Cron 表达式触发
- **排队制**：多 Task 同时触发时按顺序依次执行

## 六、执行方式

所有命令通过 **PowerShell** 执行。

## 七、HTTP 通知

| 项目 | 说明 |
|------|------|
| url | 可配置，每个 Task 可覆盖 |
| on | `failure` 仅失败 / `always` 每次 |
| 超时 | 5 秒，超时放弃 |
| 容忍 | 通知失败不影响任务状态 |

Payload：
```json
{
  "task": "daily_report",
  "status": "failure",
  "step_failed": "verify",
  "exit_code": 1,
  "output_snippet": "最后500字符",
  "retry_count": 2,
  "started_at": "2025-01-01T03:00:00",
  "finished_at": "2025-01-01T03:05:32"
}
```

## 八、日志

纯文件，每次运行一个文件：

```
logs/daily_report_20250101_030000.log
```

格式：
```
[时间] Task: xxx START
[时间] Params: {...}
[时间] Step: xxx START
[时间]   Command: xxx
[时间]   Exit code: 0
[时间]   Result: SUCCESS (matched rule: ...)
[时间] Step: xxx END (耗时)
...
[时间] Task: xxx END (耗时) SUCCESS/FAILURE
```

## 九、手动触发

```
python engine.py trigger <task_name> [--params '{"key":"value"}']
```

## 十、自启动 + 崩溃重启

- 开机自启
- 崩溃自动重启

## 十一、CLI 命令

### serve

启动 Cron 调度器，阻塞运行，Ctrl+C 退出。

### trigger

```bash
python engine.py trigger <task_name> [--params '{"key":"value"}']
```

手动触发指定任务，执行完毕后退出。

### dashboard

```bash
python engine.py dashboard                      # 显示一次快照，退出
python engine.py dashboard --watch              # 持续刷新（默认 3 秒），Ctrl+C 退出
python engine.py dashboard --watch 5            # 自定义刷新间隔
python engine.py dashboard --task daily_report  # 查看单个任务的 Step 级详情
```

### 数据来源

运行历史记录存储在 `history.json`（与 `engine.py` 同目录），每次任务执行完成后自动追加。

**保留策略：** 每个 Task 默认保留最近 50 条记录，超出自动清理最旧的。

### 运行状态检测

通过锁文件 `state/{task_name}.running` 标记任务正在运行。任务开始时创建，结束时删除。`dashboard` 命令检查该文件判断 Running 状态。

### 全部任务视图

```
TaskEngine Dashboard — 2026-05-03 08:15:30

Task              Schedule       Status     Last Run              Duration  Steps
───────────────── ───────────── ────────── ───────────────────── ───────── ──────
daily_report      0 3 * * *     ● Success  2026-05-03 03:05:32   5m 32s    3/3 ✓
data_sync         0 * * * *     ● Failure  2026-05-03 08:12:15   12m 03s   0/1 ✗
monthly_cleanup   0 2 1 * *     ○ Never    —                     —         —

3 tasks | 1 success, 1 failure, 1 never run
```

### 单任务详情视图（`--task`）

```
Task: daily_report
Schedule: 0 3 * * *  |  Timeout: 3600s  |  Retry: 2

Last 5 runs:
  2026-05-03T03:00:00  Success  5m 32s  Steps: prepare ✓ → process ✓ → verify ✓
  2026-05-02T03:00:00  Failure  12m 03s Steps: prepare ✓ → process ✗ (timeout)

Step details (latest run):
  prepare   Success  exit=0  12.3s  retries=0
  process   Success  exit=0  280.5s retries=0
  verify    Success  exit=0  39.3s  retries=0
```

### ANSI 颜色

- Success → 绿色
- Failure → 红色
- Running → 黄色
- Never → 灰色

Windows 10+ / Windows Server 2016+ 原生支持 ANSI 转义序列。

### 无新依赖

纯 Python stdlib 实现，不需要额外的第三方库。

### list

```bash
python engine.py list [--config <path>]
```

列出所有已配置的任务，显示名称、Cron 表达式、步骤数、超时、重试次数和描述。

无任务时输出 `No tasks configured.`。

### version

```bash
python engine.py version
```

输出 `TaskEngine vX.Y.Z`。版本号定义在 `cli.py` 的 `__version__` 常量中。

### help

```bash
python engine.py help
```

显示所有命令的用法说明，包括参数和选项。

无参数调用 `python engine.py` 也显示简版用法。
