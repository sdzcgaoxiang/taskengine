"""History 模块测试 — 运行历史记录的读写、清理、查询"""
import json
import os

import pytest


class TestAppendAndLoad:
    """测试历史记录的追加写入和读取"""

    def test_append_creates_file_and_loads(self, tmp_path):
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

    def test_append_multiple_entries(self, tmp_path):
        from history import append_history, load_history
        history_file = str(tmp_path / "history.json")
        for i in range(3):
            append_history(history_file, {"task": "t1", "run_id": f"r{i}", "status": "success"})
        records = load_history(history_file)
        assert len(records) == 3

    def test_load_nonexistent_returns_empty(self, tmp_path):
        from history import load_history
        records = load_history(str(tmp_path / "no_such_file.json"))
        assert records == []


class TestCleanup:
    """测试历史记录清理 — 每个 Task 保留最近 N 条"""

    def test_cleanup_keeps_latest_n(self, tmp_path):
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
        assert t1_records[0]["run_id"] == "r7"
        assert t1_records[2]["run_id"] == "r9"

    def test_cleanup_noop_when_under_limit(self, tmp_path):
        from history import append_history, cleanup_history, load_history
        history_file = str(tmp_path / "history.json")
        append_history(history_file, {"task": "t1", "run_id": "r0", "status": "success"})
        cleanup_history(history_file, keep=50)
        records = load_history(history_file)
        assert len(records) == 1


class TestQuery:
    """测试历史记录查询"""

    def test_get_latest_per_task(self, tmp_path):
        from history import append_history, get_latest_per_task
        history_file = str(tmp_path / "history.json")
        append_history(history_file, {"task": "t1", "run_id": "r1", "status": "success", "started_at": "10:00"})
        append_history(history_file, {"task": "t2", "run_id": "r1", "status": "failure", "started_at": "10:01"})
        append_history(history_file, {"task": "t1", "run_id": "r2", "status": "failure", "started_at": "11:00"})
        latest = get_latest_per_task(history_file)
        assert latest["t1"]["run_id"] == "r2"
        assert latest["t2"]["run_id"] == "r1"

    def test_get_latest_empty_file(self, tmp_path):
        from history import get_latest_per_task
        latest = get_latest_per_task(str(tmp_path / "nope.json"))
        assert latest == {}

    def test_get_task_history(self, tmp_path):
        from history import append_history, get_task_history
        history_file = str(tmp_path / "history.json")
        for i in range(5):
            append_history(history_file, {"task": "t1", "run_id": f"r{i}", "status": "success"})
        records = get_task_history(history_file, "t1", limit=3)
        assert len(records) == 3
        assert records[0]["run_id"] == "r2"
        assert records[2]["run_id"] == "r4"

    def test_get_task_history_no_records(self, tmp_path):
        from history import get_task_history
        records = get_task_history(str(tmp_path / "nope.json"), "t1", limit=5)
        assert records == []


class TestRunningLock:
    """测试运行状态锁文件"""

    def test_mark_and_check_running(self, tmp_path):
        from history import mark_running, clear_running, is_running
        state_dir = str(tmp_path / "state")
        os.makedirs(state_dir, exist_ok=True)
        assert is_running(state_dir, "t1") is False
        mark_running(state_dir, "t1", pid=12345)
        running = is_running(state_dir, "t1")
        assert running is not False
        assert running["pid"] == 12345

    def test_clear_running(self, tmp_path):
        from history import mark_running, clear_running, is_running
        state_dir = str(tmp_path / "state")
        os.makedirs(state_dir, exist_ok=True)
        mark_running(state_dir, "t1", pid=12345)
        assert is_running(state_dir, "t1") is not False
        clear_running(state_dir, "t1")
        assert is_running(state_dir, "t1") is False

    def test_clear_nonexistent_is_safe(self, tmp_path):
        from history import clear_running, is_running
        state_dir = str(tmp_path / "state")
        os.makedirs(state_dir, exist_ok=True)
        clear_running(state_dir, "nonexistent")
        assert is_running(state_dir, "nonexistent") is False
