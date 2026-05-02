# TaskEngine 监控面板 Implementation Plan

> **For Hermes:** Use TDD skill — write test first, verify RED, implement, verify GREEN.

**Goal:** 为 TaskEngine 新增 `status` 子命令，在命令行实时查看所有任务的调度状态和最近执行结果。

**Architecture:** 新增 history 模块记录运行历史（JSON 文件），新增 running lock 标记运行中状态，新增 dashboard 模块渲染终端面板。零新依赖。

**Tech Stack:** Python stdlib（json, os, datetime, textwrap），ANSI 转义序列着色

---

## 变更范围

| 文件 | 类型 | 说明 |
|------|------|------|
| `history.py` | 新建 | 运行历史记录的读写、清理 |
| `dashboard.py` | 新建 | 终端面板渲染（表格、颜色、watch 模式） |
| `engine.py` | 修改 | run_task 写 history + running lock；main 新增 status 子命令 |
| `tests/test_history.py` | 新建 | history 模块测试 |
| `tests/test_dashboard.py` | 新建 | dashboard 模块测试 |
| `SPEC.md` | 修改 | 新增监控面板章节 |
| `README.md` | 修改 | 更新项目结构、用法说明 |

---

## Task 1: History 写入

**Objective:** 实现运行历史记录的追加写入和读取

**Files:**
- Create: `history.py`
- Create: `tests/test_history.py`

### Step 1: 写失败测试 — append_history + load_history

```python
# tests/test_history.py
def test_append_and_load(tmp_path):
    from history import append_history, load_history
    history_file = str(tmp_path / "history.json")
    entry = {
        "task": "daily_report",
        "run_id": "daily_report_20260503_030000",
        "status": "success",
        "started_at": "2026-05-03T03:00:00",
        "finished_at": "2026-05-03T03:05:32",
        "duration": 332.1,
        "step_results": [
            {"name": "prepare", "status": "success", "exit_code": 0, "duration": 12.3, "retries": 0}
        ],
        "failed_step": None,
        "fail_reason": None,
    }
    append_history(history_file, entry)
    records = load_history(history_file)
    assert len(records) == 1
    assert records[0]["task"] == "daily_report"
    assert records[0]["status"] == "success"
```

Run: `cd /home/admin/taskengine && python -m pytest tests/test_history.py::test_append_and_load -v`
Expected: FAIL — ModuleNotFoundError: history

### Step 2: 实现 history.py 的 append_history + load_history

```python
# history.py — minimal to pass
import json, os

def load_history(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def append_history(path, entry):
    records = load_history(path)
    records.append(entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
```

Run: `cd /home/admin/taskengine && python -m pytest tests/test_history.py::test_append_and_load -v`
Expected: PASS

---

## Task 2: History 清理（保留策略）

**Objective:** 每个 Task 只保留最近 N 条记录

### Step 1: 写失败测试 — cleanup_history

```python
def test_cleanup_keeps_latest_n(tmp_path):
    from history import append_history, cleanup_history, load_history
    history_file = str(tmp_path / "history.json")
    for i in range(10):
        append_history(history_file, {"task": "t1", "run_id": f"r{i}", "status": "success"})
        append_history(history_file, {"task": "t2", "run_id": f"r{i}", "status": "failure"})
    cleanup_history(history_file, keep=3)
    records = load_history(history_file)
    t1_records = [r for r in records if r["task"] == "t1"]
    t2_records = [r for r in records if r["task"] == "t2"]
    assert len(t1_records) == 3
    assert len(t2_records) == 3
    assert t1_records[0]["run_id"] == "r7"  # 保留最新的 3 条
```

### Step 2: 实现 cleanup_history

---

## Task 3: History 查询 — get_latest + get_task_history

**Objective:** 查询某 Task 最近 N 条记录、所有 Task 的最新一条

### Step 1: 写失败测试

```python
def test_get_latest_per_task(tmp_path):
    from history import append_history, get_latest_per_task
    history_file = str(tmp_path / "history.json")
    append_history(history_file, {"task": "t1", "run_id": "r1", "status": "success", "started_at": "10:00"})
    append_history(history_file, {"task": "t2", "run_id": "r1", "status": "failure", "started_at": "10:01"})
    append_history(history_file, {"task": "t1", "run_id": "r2", "status": "failure", "started_at": "11:00"})
    latest = get_latest_per_task(history_file)
    assert latest["t1"]["run_id"] == "r2"
    assert latest["t2"]["run_id"] == "r1"

def test_get_task_history(tmp_path):
    from history import append_history, get_task_history
    history_file = str(tmp_path / "history.json")
    for i in range(5):
        append_history(history_file, {"task": "t1", "run_id": f"r{i}", "status": "success"})
    records = get_task_history(history_file, "t1", limit=3)
    assert len(records) == 3
    assert records[0]["run_id"] == "r2"  # 最新的 3 条
```

### Step 2: 实现 get_latest_per_task + get_task_history

---

## Task 4: Running Lock（运行状态标记）

**Objective:** 用锁文件标记任务正在运行，供 status 命令检测

### Step 1: 写失败测试

```python
# tests/test_history.py
def test_running_lock(tmp_path):
    from history import mark_running, clear_running, is_running
    state_dir = str(tmp_path / "state")
    os.makedirs(state_dir, exist_ok=True)
    assert is_running(state_dir, "t1") is False
    mark_running(state_dir, "t1", pid=12345)
    assert is_running(state_dir, "t1") is True
    info = is_running(state_dir, "t1")
    assert info["pid"] == 12345
    clear_running(state_dir, "t1")
    assert is_running(state_dir, "t1") is False
```

### Step 2: 实现 mark_running / clear_running / is_running

---

## Task 5: Dashboard 渲染 — 全部任务表格

**Objective:** 渲染所有任务的状态表格（纯文本，无颜色先）

### Step 1: 写失败测试

```python
# tests/test_dashboard.py
def test_render_summary_table(tmp_path):
    from dashboard import render_summary
    from history import append_history
    history_file = str(tmp_path / "history.json")
    append_history(history_file, {
        "task": "daily_report", "status": "success",
        "started_at": "2026-05-03T03:00:00", "finished_at": "2026-05-03T03:05:32",
        "duration": 332.1, "step_results": [
            {"name": "prepare", "status": "success"},
            {"name": "process", "status": "success"},
        ],
        "failed_step": None, "fail_reason": None,
    })
    config = {
        "tasks": {
            "daily_report": {"schedule": "0 3 * * *", "steps": [{"name": "prepare"}, {"name": "process"}]},
            "data_sync": {"schedule": "0 * * * *", "steps": [{"name": "sync"}]},
        }
    }
    output = render_summary(config, history_file, state_dir=str(tmp_path / "state"))
    assert "daily_report" in output
    assert "data_sync" in output
    assert "Success" in output
    assert "Never" in output
    assert "2/2" in output
```

### Step 2: 实现 render_summary

---

## Task 6: Dashboard 渲染 — 单任务详情

**Objective:** 渲染单个任务的 Step 级执行历史

### Step 1: 写失败测试

```python
def test_render_task_detail(tmp_path):
    from dashboard import render_task_detail
    from history import append_history
    history_file = str(tmp_path / "history.json")
    # ... append entries
    output = render_task_detail(task_config, history_file, task_name="daily_report", limit=5)
    assert "prepare" in output
    assert "process" in output
```

### Step 2: 实现 render_task_detail

---

## Task 7: Dashboard — 格式化辅助函数

**Objective:** duration 格式化、ANSI 颜色、Watch 模式

### Step 1: 写失败测试

```python
def test_format_duration():
    from dashboard import format_duration
    assert format_duration(332.1) == "5m 32s"
    assert format_duration(45.0) == "45s"
    assert format_duration(3661.5) == "1h 1m"

def test_colorize():
    from dashboard import colorize, GREEN, RED, RESET
    assert colorize("Success", GREEN) == f"{GREEN}Success{RESET}"
    assert colorize("test", None) == "test"  # 无颜色
```

### Step 2: 实现 format_duration + colorize

---

## Task 8: 集成 — engine.py 写入 history + running lock

**Objective:** run_task 结束时写 history，开始/结束时管理 running lock

### Step 1: 写失败测试

```python
def test_run_task_writes_history(tmp_path):
    from engine import run_task, load_config, Logger
    from history import load_history
    config_path = make_task_config(tmp_path, [
        {"name": "step1", "command": "echo ok", "shell": "bash"},
    ])
    config = load_config(config_path)
    task = config["tasks"]["test_task"]
    logger = Logger(str(tmp_path / "logs"))
    state_dir = str(tmp_path / "state")
    history_file = str(tmp_path / "history.json")
    os.makedirs(state_dir, exist_ok=True)
    result = run_task(task, "test_task", {}, logger, state_dir=state_dir, history_file=history_file)
    records = load_history(history_file)
    assert len(records) == 1
    assert records[0]["task"] == "test_task"
    assert records[0]["status"] == "success"
```

### Step 2: 修改 engine.py 的 run_task — 追加 history 写入 + running lock

---

## Task 9: CLI 集成 — status 子命令

**Objective:** main() 新增 status 子命令入口

### Step 1: 写失败测试

```python
def test_status_command_runs(tmp_path):
    from history import append_history
    history_file = str(tmp_path / "history.json")
    append_history(history_file, {"task": "t1", "status": "success", ...})
    result = subprocess.run(
        [sys.executable, "engine.py", "status", "--history", history_file],
        capture_output=True, text=True, cwd="/home/admin/taskengine"
    )
    assert result.returncode == 0
    assert "t1" in result.stdout
```

### Step 2: 修改 engine.py main() 新增 status 分支

---

## Task 10: 文档更新

**Objective:** 更新 SPEC.md + README.md

- SPEC.md 新增"监控面板"章节
- README.md 更新项目结构、用法示例
