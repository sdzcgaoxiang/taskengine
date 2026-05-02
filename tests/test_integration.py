"""集成测试 — engine.py 集成 history + running lock + status CLI"""
import json
import os
import subprocess
import sys
import time

import pytest
import yaml


class TestRunTaskWritesHistory:
    """测试 run_task 执行后写入 history.json"""

    def test_success_writes_history(self, tmp_path, make_task_config):
        from engine import run_task, load_config, Logger
        from history import load_history
        config_path = make_task_config([
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
        assert records[0]["step_results"][0]["name"] == "step1"

    def test_failure_writes_history(self, tmp_path, make_task_config):
        from engine import run_task, load_config, Logger
        from history import load_history
        config_path = make_task_config([
            {"name": "step1", "command": "exit 1", "shell": "bash"},
        ])
        config = load_config(config_path)
        task = config["tasks"]["test_task"]
        logger = Logger(str(tmp_path / "logs"))
        state_dir = str(tmp_path / "state")
        history_file = str(tmp_path / "history.json")
        os.makedirs(state_dir, exist_ok=True)
        result = run_task(task, "test_task", {}, logger, state_dir=state_dir, history_file=history_file)
        assert result["success"] is False
        records = load_history(history_file)
        assert len(records) == 1
        assert records[0]["status"] == "failure"
        assert records[0]["failed_step"] == "step1"

    def test_running_lock_lifecycle(self, tmp_path, make_task_config):
        """测试运行中锁的标记和清除"""
        from engine import run_task, load_config, Logger
        from history import is_running
        config_path = make_task_config([
            {"name": "step1", "command": "echo ok", "shell": "bash", "timeout": 10},
        ])
        config = load_config(config_path)
        task = config["tasks"]["test_task"]
        logger = Logger(str(tmp_path / "logs"))
        state_dir = str(tmp_path / "state")
        history_file = str(tmp_path / "history.json")
        os.makedirs(state_dir, exist_ok=True)
        result = run_task(task, "test_task", {}, logger, state_dir=state_dir, history_file=history_file)
        # 完成后 running lock 应该被清除
        assert is_running(state_dir, "test_task") is False

    def test_history_cleanup_after_write(self, tmp_path, make_task_config):
        """测试写入后自动清理"""
        from engine import run_task, load_config, Logger
        from history import load_history
        config_path = make_task_config([
            {"name": "step1", "command": "echo ok", "shell": "bash"},
        ])
        config = load_config(config_path)
        task = config["tasks"]["test_task"]
        state_dir = str(tmp_path / "state")
        history_file = str(tmp_path / "history.json")
        os.makedirs(state_dir, exist_ok=True)
        # 写 60 条记录
        for _ in range(60):
            logger = Logger(str(tmp_path / "logs"))
            run_task(task, "test_task", {}, logger, state_dir=state_dir, history_file=history_file, history_keep=50)
        records = load_history(history_file)
        assert len(records) <= 50


class TestStatusCLI:
    """测试 status 子命令"""

    def test_status_with_history(self, tmp_path):
        from history import append_history
        history_file = str(tmp_path / "history.json")
        append_history(history_file, {
            "task": "test_task", "status": "success",
            "started_at": "2026-05-03T03:00:00", "finished_at": "2026-05-03T03:05:32",
            "duration": 332.1, "step_results": [{"name": "step1", "status": "success"}],
            "failed_step": None, "fail_reason": None,
        })
        # 创建临时 tasks.yaml
        config_path = tmp_path / "tasks.yaml"
        config_path.write_text(yaml.dump({
            "tasks": {
                "test_task": {
                    "schedule": "0 3 * * *",
                    "steps": [{"name": "step1", "command": "echo hi"}],
                }
            }
        }, allow_unicode=True), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "engine.py", "status",
             "--config", str(config_path),
             "--history", history_file,
             "--state-dir", str(tmp_path / "state")],
            capture_output=True, text=True,
            cwd="/home/admin/taskengine",
            timeout=10,
        )
        assert result.returncode == 0
        assert "test_task" in result.stdout
        assert "Success" in result.stdout

    def test_status_empty(self, tmp_path):
        config_path = tmp_path / "tasks.yaml"
        config_path.write_text(yaml.dump({"tasks": {}}, allow_unicode=True), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "engine.py", "status",
             "--config", str(config_path),
             "--history", str(tmp_path / "history.json"),
             "--state-dir", str(tmp_path / "state")],
            capture_output=True, text=True,
            cwd="/home/admin/taskengine",
            timeout=10,
        )
        assert result.returncode == 0

    def test_status_single_task(self, tmp_path):
        from history import append_history
        history_file = str(tmp_path / "history.json")
        append_history(history_file, {
            "task": "test_task", "status": "success",
            "started_at": "2026-05-03T03:00:00", "finished_at": "2026-05-03T03:00:12",
            "duration": 12.3, "step_results": [
                {"name": "step1", "status": "success", "exit_code": 0, "duration": 12.3, "retries": 0}
            ],
            "failed_step": None, "fail_reason": None,
        })
        config_path = tmp_path / "tasks.yaml"
        config_path.write_text(yaml.dump({
            "tasks": {
                "test_task": {
                    "schedule": "0 3 * * *",
                    "steps": [{"name": "step1", "command": "echo hi"}],
                }
            }
        }, allow_unicode=True), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "engine.py", "status",
             "--task", "test_task",
             "--config", str(config_path),
             "--history", history_file,
             "--state-dir", str(tmp_path / "state")],
            capture_output=True, text=True,
            cwd="/home/admin/taskengine",
            timeout=10,
        )
        assert result.returncode == 0
        assert "test_task" in result.stdout
        assert "step1" in result.stdout
