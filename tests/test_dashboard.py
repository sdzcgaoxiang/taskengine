"""Dashboard 模块测试 — 面板渲染、格式化辅助"""
import os

import pytest


class TestFormatDuration:
    """测试时间格式化"""

    def test_seconds_only(self):
        from taskengine.dashboard import format_duration
        assert format_duration(45.0) == "45s"

    def test_minutes_and_seconds(self):
        from taskengine.dashboard import format_duration
        assert format_duration(332.1) == "5m 32s"

    def test_hours(self):
        from taskengine.dashboard import format_duration
        assert format_duration(3661.5) == "1h 1m"

    def test_zero(self):
        from taskengine.dashboard import format_duration
        assert format_duration(0) == "0s"

    def test_exact_minute(self):
        from taskengine.dashboard import format_duration
        assert format_duration(60.0) == "1m 0s"

    def test_large_hours(self):
        from taskengine.dashboard import format_duration
        assert format_duration(7384.0) == "2h 3m"


class TestColorize:
    """测试 ANSI 颜色"""

    def test_with_color(self):
        from taskengine.dashboard import colorize, GREEN, RESET
        result = colorize("Success", GREEN)
        assert result == f"{GREEN}Success{RESET}"

    def test_no_color(self):
        from taskengine.dashboard import colorize
        assert colorize("test", None) == "test"


class TestRenderSummary:
    """测试全部任务表格渲染"""

    def test_basic_table(self, tmp_path):
        from taskengine.dashboard import render_summary
        from taskengine.history import append_history
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

    def test_shows_failure_status(self, tmp_path):
        from taskengine.dashboard import render_summary
        from taskengine.history import append_history
        history_file = str(tmp_path / "history.json")
        append_history(history_file, {
            "task": "data_sync", "status": "failure",
            "started_at": "2026-05-03T08:00:00", "finished_at": "2026-05-03T08:12:03",
            "duration": 723.0, "step_results": [
                {"name": "sync", "status": "failure"},
            ],
            "failed_step": "sync", "fail_reason": "exit_code=1",
        })
        config = {
            "tasks": {
                "data_sync": {"schedule": "0 * * * *", "steps": [{"name": "sync"}]},
            }
        }
        output = render_summary(config, history_file, state_dir=str(tmp_path / "state"))
        assert "Failure" in output
        assert "0/1" in output

    def test_shows_running_status(self, tmp_path):
        from taskengine.dashboard import render_summary
        from taskengine.history import mark_running
        state_dir = str(tmp_path / "state")
        os.makedirs(state_dir, exist_ok=True)
        mark_running(state_dir, "data_sync", pid=12345)
        config = {
            "tasks": {
                "data_sync": {"schedule": "0 * * * *", "steps": [{"name": "sync"}]},
            }
        }
        output = render_summary(config, str(tmp_path / "history.json"), state_dir=state_dir)
        assert "Running" in output

    def test_empty_config(self, tmp_path):
        from taskengine.dashboard import render_summary
        output = render_summary({"tasks": {}}, str(tmp_path / "history.json"), state_dir=str(tmp_path / "state"))
        assert "0 tasks" in output


class TestRenderTaskDetail:
    """测试单任务详情渲染"""

    def test_basic_detail(self, tmp_path):
        from taskengine.dashboard import render_task_detail
        from taskengine.history import append_history
        history_file = str(tmp_path / "history.json")
        append_history(history_file, {
            "task": "daily_report", "run_id": "r1", "status": "success",
            "started_at": "2026-05-03T03:00:00", "finished_at": "2026-05-03T03:05:32",
            "duration": 332.1, "step_results": [
                {"name": "prepare", "status": "success", "exit_code": 0, "duration": 12.3, "retries": 0},
                {"name": "process", "status": "success", "exit_code": 0, "duration": 280.5, "retries": 0},
                {"name": "verify", "status": "success", "exit_code": 0, "duration": 39.3, "retries": 0},
            ],
            "failed_step": None, "fail_reason": None,
        })
        task_config = {
            "schedule": "0 3 * * *",
            "steps": [{"name": "prepare"}, {"name": "process"}, {"name": "verify"}],
        }
        output = render_task_detail(task_config, history_file, task_name="daily_report", limit=5)
        assert "daily_report" in output
        assert "prepare" in output
        assert "process" in output
        assert "verify" in output
        assert "Success" in output

    def test_detail_with_failure(self, tmp_path):
        from taskengine.dashboard import render_task_detail
        from taskengine.history import append_history
        history_file = str(tmp_path / "history.json")
        append_history(history_file, {
            "task": "daily_report", "run_id": "r1", "status": "failure",
            "started_at": "2026-05-03T03:00:00", "finished_at": "2026-05-03T03:12:45",
            "duration": 765.0, "step_results": [
                {"name": "prepare", "status": "success", "exit_code": 0, "duration": 12.3, "retries": 0},
                {"name": "process", "status": "failure", "exit_code": 1, "duration": 753.0, "retries": 0},
            ],
            "failed_step": "process", "fail_reason": "timeout",
        })
        task_config = {
            "schedule": "0 3 * * *",
            "steps": [{"name": "prepare"}, {"name": "process"}],
        }
        output = render_task_detail(task_config, history_file, task_name="daily_report", limit=5)
        assert "Failure" in output
        assert "timeout" in output

    def test_detail_no_history(self, tmp_path):
        from taskengine.dashboard import render_task_detail
        task_config = {"schedule": "0 3 * * *", "steps": [{"name": "step1"}]}
        output = render_task_detail(task_config, str(tmp_path / "nope.json"), task_name="t1", limit=5)
        assert "t1" in output
        assert "No run history" in output
