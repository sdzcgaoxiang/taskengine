"""TaskEngine 核心逻辑测试"""
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
import yaml

# 检测是否在 Windows 上
IS_WINDOWS = os.name == "nt"
SHELL = ["powershell", "-Command"] if IS_WINDOWS else ["bash", "-c"]


# ─── 辅助：创建临时配置 ───

def make_config(tmp_path, tasks_yaml):
    """把 tasks_yaml dict 写入临时目录的 tasks.yaml"""
    config_path = tmp_path / "tasks.yaml"
    config_path.write_text(yaml.dump(tasks_yaml, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    return str(config_path)


def make_task_config(tmp_path, steps, **overrides):
    """快速构造单个任务的配置，支持 timeout/retry/params 等关键字参数"""
    task = {
        "schedule": "0 3 * * *",
        "steps": steps,
    }
    task.update(overrides)
    return make_config(tmp_path, {"tasks": {"test_task": task}})


# ─── 一、成功条件判定 ───

class TestCheckSuccess:
    """测试 success_conditions 的 OR/AND 逻辑"""

    def test_default_exit_code_0_is_success(self):
        from engine import check_success
        assert check_success([{"exit_code": 0}], 0, "") is True

    def test_exit_code_0_is_failure_when_code_is_1(self):
        from engine import check_success
        assert check_success([{"exit_code": 0}], 1, "") is False

    def test_or_logic_two_rules_first_matches(self):
        from engine import check_success
        rules = [
            {"exit_code": 0},
            {"exit_code": 1, "output_contains": "OK"},
        ]
        assert check_success(rules, 0, "anything") is True

    def test_or_logic_two_rules_second_matches(self):
        from engine import check_success
        rules = [
            {"exit_code": 0},
            {"exit_code": 1, "output_contains": "OK"},
        ]
        assert check_success(rules, 1, "VERIFIED OK") is True

    def test_or_logic_no_rule_matches(self):
        from engine import check_success
        rules = [
            {"exit_code": 0},
            {"exit_code": 1, "output_contains": "OK"},
        ]
        assert check_success(rules, 2, "something") is False

    def test_and_within_rule_exit_code_matches_but_output_missing(self):
        from engine import check_success
        rules = [
            {"exit_code": 1, "output_contains": "OK"},
        ]
        assert check_success(rules, 1, "FAIL") is False

    def test_output_not_contains(self):
        from engine import check_success
        rules = [
            {"output_not_contains": "ERROR"},
        ]
        assert check_success(rules, 0, "all good") is True
        assert check_success(rules, 0, "got ERROR here") is False

    def test_output_contains_and_not_contains_together(self):
        from engine import check_success
        rules = [
            {"output_contains": "DONE", "output_not_contains": "ERROR"},
        ]
        assert check_success(rules, 0, "DONE successfully") is True
        assert check_success(rules, 0, "DONE but ERROR") is False
        assert check_success(rules, 0, "nothing") is False

    def test_empty_rules_defaults_to_exit_code_0(self):
        from engine import check_success
        assert check_success([], 0, "") is True
        assert check_success([], 1, "") is False

    def test_only_output_contains_ignores_exit_code(self):
        from engine import check_success
        rules = [{"output_contains": "DONE"}]
        assert check_success(rules, 99, "DONE") is True
        assert check_success(rules, 0, "not done") is False


# ─── 二、配置加载 ───

class TestLoadConfig:
    """测试 YAML 配置加载和默认值合并"""

    def test_load_simple_task(self, tmp_path):
        from engine import load_config
        config_path = make_task_config(tmp_path, [
            {"name": "step1", "command": "echo hello"},
        ])
        config = load_config(config_path)
        assert "test_task" in config["tasks"]
        assert config["tasks"]["test_task"]["steps"][0]["name"] == "step1"

    def test_defaults_merge(self, tmp_path):
        from engine import load_config
        config_path = make_config(tmp_path, {
            "defaults": {
                "timeout": 600,
                "retry": 1,
            },
            "tasks": {
                "test_task": {
                    "schedule": "0 3 * * *",
                    "steps": [
                        {"name": "step1", "command": "echo hi"},
                    ],
                },
            },
        })
        config = load_config(config_path)
        task = config["tasks"]["test_task"]
        assert task["timeout"] == 600
        assert task["retry"] == 1

    def test_task_overrides_defaults(self, tmp_path):
        from engine import load_config
        config_path = make_config(tmp_path, {
            "defaults": {"timeout": 600, "retry": 0},
            "tasks": {
                "test_task": {
                    "schedule": "0 3 * * *",
                    "timeout": 120,
                    "retry": 3,
                    "steps": [
                        {"name": "step1", "command": "echo hi"},
                    ],
                },
            },
        })
        config = load_config(config_path)
        task = config["tasks"]["test_task"]
        assert task["timeout"] == 120
        assert task["retry"] == 3

    def test_step_inherits_task_timeout(self, tmp_path):
        from engine import load_config
        config_path = make_task_config(tmp_path, [
            {"name": "step1", "command": "echo hi"},
        ], timeout=999)
        config = load_config(config_path)
        step = config["tasks"]["test_task"]["steps"][0]
        assert step["timeout"] == 999

    def test_params_with_default(self, tmp_path):
        from engine import load_config
        config_path = make_task_config(tmp_path, [
            {"name": "step1", "command": "python run.py --date={{date}}"},
        ], params=[{"name": "date", "default": "today"}])
        config = load_config(config_path)
        task = config["tasks"]["test_task"]
        assert task["params"][0]["name"] == "date"
        assert task["params"][0]["default"] == "today"


# ─── 三、参数替换 ───

class TestParamReplace:
    """测试 {{param}} 模板替换"""

    def test_simple_replace(self):
        from engine import replace_params
        result = replace_params("python run.py --date={{date}}", {"date": "2025-01-01"})
        assert result == "python run.py --date=2025-01-01"

    def test_multiple_params(self):
        from engine import replace_params
        result = replace_params("run --date={{date}} --mode={{mode}}", {"date": "2025-01-01", "mode": "full"})
        assert result == "run --date=2025-01-01 --mode=full"

    def test_missing_param_kept_as_is(self):
        from engine import replace_params
        result = replace_params("run --date={{date}}", {})
        assert result == "run --date={{date}}"


# ─── 四、Step 执行 ───

class TestRunStep:
    """测试单步执行：超时、重试、成功判定"""

    def test_simple_success(self, tmp_path):
        from engine import run_step, Logger
        logger = Logger(str(tmp_path / "logs"))
        step = {
            "name": "echo_step",
            "command": "echo hello",
            "timeout": 10,
            "shell": "bash",
        }
        result = run_step(step, {}, logger, run_id="test")
        assert result["success"] is True
        assert "hello" in result["output"]

    def test_step_timeout(self, tmp_path):
        from engine import run_step, Logger
        logger = Logger(str(tmp_path / "logs"))
        step = {
            "name": "slow_step",
            "command": "sleep 60",
            "timeout": 2,
            "shell": "bash",
        }
        start = time.time()
        result = run_step(step, {}, logger, run_id="test")
        elapsed = time.time() - start
        assert result["success"] is False
        assert "timeout" in result.get("fail_reason", "").lower()
        assert elapsed < 10

    def test_step_retry_then_success(self, tmp_path):
        from engine import run_step, Logger
        logger = Logger(str(tmp_path / "logs"))
        marker = tmp_path / "retry_marker.txt"
        # bash 实现：第一次创建标记文件并失败，第二次检测到就成功
        step = {
            "name": "retry_step",
            "command": f'if [ -f "{marker}" ]; then echo "OK"; else touch "{marker}"; echo "fail" >&2; exit 1; fi',
            "timeout": 10,
            "retry": 1,
            "retry_delay": 1,
            "shell": "bash",
            "success_conditions": [
                {"exit_code": 0},
                {"output_contains": "OK"},
            ],
        }
        result = run_step(step, {}, logger, run_id="test")
        assert result["success"] is True
        assert result["retry_count"] >= 1

    def test_step_all_retries_exhausted(self, tmp_path):
        from engine import run_step, Logger
        logger = Logger(str(tmp_path / "logs"))
        step = {
            "name": "always_fail",
            "command": "echo 'fail' >&2; exit 1",
            "timeout": 10,
            "retry": 2,
            "retry_delay": 1,
            "shell": "bash",
        }
        result = run_step(step, {}, logger, run_id="test")
        assert result["success"] is False
        assert result["retry_count"] == 2

    def test_custom_success_condition(self, tmp_path):
        from engine import run_step, Logger
        logger = Logger(str(tmp_path / "logs"))
        step = {
            "name": "weird_exit",
            "command": "echo 'VERIFIED OK'; exit 1",
            "timeout": 10,
            "shell": "bash",
            "success_conditions": [
                {"exit_code": 0},
                {"exit_code": 1, "output_contains": "OK"},
            ],
        }
        result = run_step(step, {}, logger, run_id="test")
        assert result["success"] is True


# ─── 五、Task 执行（多Step + 从失败Step重跑） ───

class TestRunTask:
    """测试任务级执行：Step串行、失败中断、从失败Step重跑"""

    def test_linear_steps_all_succeed(self, tmp_path):
        from engine import run_task, load_config, Logger
        config_path = make_task_config(tmp_path, [
            {"name": "step1", "command": "echo step1", "shell": "bash"},
            {"name": "step2", "command": "echo step2", "shell": "bash"},
            {"name": "step3", "command": "echo step3", "shell": "bash"},
        ])
        config = load_config(config_path)
        task = config["tasks"]["test_task"]
        logger = Logger(str(tmp_path / "logs"))
        state_dir = str(tmp_path / "state")
        os.makedirs(state_dir, exist_ok=True)
        result = run_task(task, "test_task", {}, logger, state_dir=state_dir)
        assert result["success"] is True
        assert len(result["steps"]) == 3
        assert all(s["success"] for s in result["steps"])

    def test_failure_stops_later_steps(self, tmp_path):
        from engine import run_task, load_config, Logger
        config_path = make_task_config(tmp_path, [
            {"name": "step1", "command": "echo step1", "shell": "bash"},
            {"name": "step2", "command": "exit 1", "shell": "bash"},
            {"name": "step3", "command": "echo step3", "shell": "bash"},
        ])
        config = load_config(config_path)
        task = config["tasks"]["test_task"]
        logger = Logger(str(tmp_path / "logs"))
        state_dir = str(tmp_path / "state")
        os.makedirs(state_dir, exist_ok=True)
        result = run_task(task, "test_task", {}, logger, state_dir=state_dir)
        assert result["success"] is False
        assert result["steps"][0]["success"] is True
        assert result["steps"][1]["success"] is False
        assert result["steps"][2]["success"] is None  # skipped

    def test_retry_from_failed_step(self, tmp_path):
        from engine import run_task, load_config, Logger
        marker = tmp_path / "step2_marker.txt"
        step2_cmd = f'if [ -f "{marker}" ]; then echo "step2 ok"; else touch "{marker}"; exit 1; fi'
        config_path = make_task_config(tmp_path, [
            {"name": "step1", "command": "echo step1", "shell": "bash"},
            {"name": "step2", "command": step2_cmd, "shell": "bash", "retry": 1, "retry_delay": 1},
            {"name": "step3", "command": "echo step3", "shell": "bash"},
        ])
        config = load_config(config_path)
        task = config["tasks"]["test_task"]
        logger = Logger(str(tmp_path / "logs"))
        state_dir = str(tmp_path / "state")
        os.makedirs(state_dir, exist_ok=True)
        result = run_task(task, "test_task", {}, logger, state_dir=state_dir)
        assert result["success"] is True

    def test_task_retry_from_failed_step_not_from_beginning(self, tmp_path):
        from engine import run_task, load_config, Logger
        call_count_file = tmp_path / "step1_calls.txt"
        step1_cmd = f'echo "called" >> "{call_count_file}"; echo step1'
        marker = tmp_path / "step2_marker.txt"
        step2_cmd = f'if [ -f "{marker}" ]; then echo "step2 ok"; else touch "{marker}"; exit 1; fi'

        config_path = make_task_config(tmp_path, [
            {"name": "step1", "command": step1_cmd, "shell": "bash"},
            {"name": "step2", "command": step2_cmd, "shell": "bash", "retry": 1, "retry_delay": 1},
        ], retry=1, retry_delay=1)

        config = load_config(config_path)
        task = config["tasks"]["test_task"]
        logger = Logger(str(tmp_path / "logs"))
        state_dir = str(tmp_path / "state")
        os.makedirs(state_dir, exist_ok=True)

        result = run_task(task, "test_task", {}, logger, state_dir=state_dir)
        assert result["success"] is True
        calls = call_count_file.read_text().strip().split("\n") if call_count_file.exists() else []
        assert len(calls) == 1, f"step1 should be called once, got {len(calls)}"


# ─── 六、HTTP 通知 ───

class TestNotify:
    """测试 HTTP 通知发送"""

    def test_notify_on_failure(self, tmp_path):
        from engine import notify
        import threading
        from http.server import HTTPServer, BaseHTTPRequestHandler

        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                body = self.rfile.read(length)
                received.append(json.loads(body))
                self.send_response(200)
                self.end_headers()
            def log_message(self, *a): pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        notify(
            url=f"http://127.0.0.1:{port}/alert",
            payload={"task": "test", "status": "failure"},
            timeout=5,
        )
        t.join(timeout=5)
        server.server_close()

        assert len(received) == 1
        assert received[0]["task"] == "test"

    def test_notify_failure_tolerated(self):
        from engine import notify
        notify(
            url="http://127.0.0.1:1/impossible",
            payload={"task": "test"},
            timeout=2,
        )

    def test_notify_skipped_on_success_when_config_failure_only(self):
        from engine import should_notify
        assert should_notify("failure", task_success=True) is False
        assert should_notify("failure", task_success=False) is True
        assert should_notify("always", task_success=True) is True
        assert should_notify("always", task_success=False) is True


# ─── 七、日志 ───

class TestLogger:
    """测试文件日志"""

    def test_log_creates_file(self, tmp_path):
        from engine import Logger
        logger = Logger(str(tmp_path / "logs"))
        logger.start_run("test_task", "run001")
        logger.step_start("step1", "echo hello")
        logger.step_end("step1", success=True, exit_code=0, duration=1)
        logger.end_run("test_task", success=True, duration=2)
        log_files = list(Path(str(tmp_path / "logs")).glob("*.log"))
        assert len(log_files) == 1
        content = log_files[0].read_text(encoding="utf-8")
        assert "test_task" in content
        assert "START" in content
        assert "SUCCESS" in content

    def test_log_records_failure(self, tmp_path):
        from engine import Logger
        logger = Logger(str(tmp_path / "logs"))
        logger.start_run("test_task", "run002")
        logger.step_start("step1", "exit 1")
        logger.step_end("step1", success=False, exit_code=1, duration=1, fail_reason="exit code 1")
        logger.end_run("test_task", success=False, duration=1)
        log_files = list(Path(str(tmp_path / "logs")).glob("*.log"))
        content = log_files[0].read_text(encoding="utf-8")
        assert "FAILURE" in content
        assert "exit code 1" in content


# ─── 八、排队 ───

class TestQueue:
    """测试多任务排队串行执行"""

    def test_sequential_execution(self, tmp_path):
        from engine import TaskQueue
        results = []

        def fake_runner(task_name, params):
            results.append(f"start_{task_name}")
            time.sleep(0.1)
            results.append(f"end_{task_name}")
            return {"success": True}

        q = TaskQueue(runner=fake_runner)
        q.submit("task_a", {})
        q.submit("task_b", {})
        q.wait_all()

        assert results.index("start_task_a") < results.index("start_task_b")
        assert results.index("end_task_a") < results.index("start_task_b")


# ─── 九、手动触发 ───

class TestTrigger:
    """测试手动触发 CLI"""

    def test_trigger_with_params(self, tmp_path):
        from engine import parse_trigger_args
        result = parse_trigger_args(["trigger", "daily_report", '--params', '{"date":"2025-01-01"}'])
        assert result["task_name"] == "daily_report"
        assert result["params"]["date"] == "2025-01-01"

    def test_trigger_without_params(self):
        from engine import parse_trigger_args
        result = parse_trigger_args(["trigger", "daily_report"])
        assert result["task_name"] == "daily_report"
        assert result["params"] == {}


# ─── 十、State 持久化（从失败Step重跑） ───

class TestState:
    """测试运行状态持久化"""

    def test_save_and_load_state(self, tmp_path):
        from engine import save_state, load_state
        state_dir = str(tmp_path / "state")
        os.makedirs(state_dir, exist_ok=True)
        run_id = "test_task_20250101_030000"

        save_state(state_dir, run_id, completed_steps=["step1", "step2"], failed_step="step3")
        state = load_state(state_dir, run_id)

        assert state["completed_steps"] == ["step1", "step2"]
        assert state["failed_step"] == "step3"

    def test_no_state_returns_empty(self, tmp_path):
        from engine import load_state
        state_dir = str(tmp_path / "state")
        os.makedirs(state_dir, exist_ok=True)
        state = load_state(state_dir, "nonexistent")
        assert state is None
