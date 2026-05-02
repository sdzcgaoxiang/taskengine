# TaskEngine 功能规格说明

## 概述

Windows Server 2016 桌面会话上运行的轻量定时任务引擎，调度多步脚本任务。

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
