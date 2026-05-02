# TaskEngine

轻量定时任务引擎，运行在 Windows Server 2016 桌面会话上，调度多步脚本任务。

## 特性

- 🕐 **Cron 调度** — 每小时 / 每天 / 每周 / 每月，支持完整 Cron 表达式
- 🔗 **线性依赖链** — 多步串行执行，失败即停
- ✅ **自定义成功条件** — 多规则 OR，规则内 AND（`exit_code` + `output_contains` + `output_not_contains`）
- 🔄 **智能重试** — Step 级 + Task 级重试，Task 重试从失败的 Step 继续
- ⏱ **超时控制** — Step 级 + Task 级超时
- 📢 **HTTP 通知** — 失败时 POST 到可配置 URL，通知本身可失败
- 📝 **文件日志** — 每次运行一个日志文件
- 🚀 **手动触发** — 命令行即时执行
- 🔄 **崩溃重启** — 自启脚本，进程挂掉自动拉起
- 📊 **监控面板** — 命令行实时查看任务状态和执行历史

## 快速开始

### 安装

```bash
pip install -r requirements.txt
```

> Python 3.8+（Win2016 兼容）

### 配置任务

编辑 `tasks.yaml`：

```yaml
defaults:
  timeout: 300
  retry: 0
  retry_delay: 60
  http_notify:
    url: "http://your-server/api/alert"
    on: failure

tasks:
  daily_report:
    description: "每日数据报表"
    schedule: "0 3 * * *"
    timeout: 3600
    retry: 2
    retry_delay: 120
    params:
      - name: date
        default: "today"
    steps:
      - name: prepare
        command: "python D:/scripts/prepare.py --date={{date}}"
        timeout: 300

      - name: process
        command: "D:/tools/process.exe -i D:/data/input.csv"
        timeout: 600
        retry: 1
        retry_delay: 30

      - name: verify
        command: "powershell D:/scripts/verify.ps1"
        timeout: 120
        success_conditions:
          - exit_code: 0
          - exit_code: 1
            output_contains: "OK"
```

### 启动引擎

```bash
python engine.py serve
```

### 手动触发

```bash
python engine.py trigger daily_report --params '{"date":"2025-01-01"}'
```

### 查看状态

```bash
python engine.py status                      # 一次性快照
python engine.py status --watch              # 持续刷新（默认 3 秒）
python engine.py status --task daily_report  # 单任务详情
```

### 开机自启

双击 `start.bat`，或将其放到 Windows 启动目录（`shell:startup`）。

## 成功条件

多规则 **OR**，规则内 **AND**：

```yaml
# 返回0 或 返回1且含OK = 成功
success_conditions:
  - exit_code: 0
  - exit_code: 1
    output_contains: "OK"

# 输出不含ERROR = 成功
success_conditions:
  - output_not_contains: "ERROR"

# 返回0且含SUCCESS 且 不含WARN = 成功
success_conditions:
  - exit_code: 0
    output_contains: "SUCCESS"
    output_not_contains: "WARN"
```

| 维度 | 键 | 含义 | 默认值 |
|------|-----|------|--------|
| 返回码 | `exit_code` | 必须等于此值 | `0` |
| 包含 | `output_contains` | 输出必须包含 | 不检查 |
| 不包含 | `output_not_contains` | 输出不能包含 | 不检查 |

## 重试策略

- **Step 重试**：单步失败后在原步重试指定次数
- **Task 重试**：从失败的 Step 开始重跑，已成功的 Step 跳过

## 运行测试

```bash
pip install pytest
pytest tests/ -v
```

## 项目结构

```
taskengine/
├── engine.py          # 核心引擎
├── history.py         # 运行历史记录（读写、清理、查询）
├── dashboard.py       # 监控面板（终端表格渲染）
├── tasks.yaml         # 任务配置
├── start.bat          # Windows 自启脚本
├── requirements.txt   # Python 依赖
├── SPEC.md            # 功能规格说明
├── tests/
│   ├── test_engine.py       # 核心逻辑测试（37 个）
│   ├── test_history.py      # 历史记录测试（12 个）
│   ├── test_dashboard.py    # 面板渲染测试（15 个）
│   └── test_integration.py  # 集成测试（7 个）
├── logs/              # 运行日志（自动创建）
├── state/             # 执行状态（自动创建）
└── history.json       # 运行历史（自动创建）
```

## License

MIT
