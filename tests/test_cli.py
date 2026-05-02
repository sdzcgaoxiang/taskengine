"""CLI 命令测试 — help / version / list / dashboard / unknown"""
import subprocess
import sys

import pytest
import yaml


class TestVersionCommand:
    """测试 version 命令"""

    def test_version_output(self):
        result = subprocess.run(
            [sys.executable, "engine.py", "version"],
            capture_output=True, text=True,
            cwd="/home/admin/taskengine",
            timeout=10,
        )
        assert result.returncode == 0
        assert "TaskEngine" in result.stdout
        assert "v" in result.stdout

    def test_version_has_semver_format(self):
        result = subprocess.run(
            [sys.executable, "engine.py", "version"],
            capture_output=True, text=True,
            cwd="/home/admin/taskengine",
            timeout=10,
        )
        # 应该匹配 vX.Y.Z 格式
        import re
        assert re.search(r"v\d+\.\d+\.\d+", result.stdout)


class TestHelpCommand:
    """测试 help 命令"""

    def test_help_output(self):
        result = subprocess.run(
            [sys.executable, "engine.py", "help"],
            capture_output=True, text=True,
            cwd="/home/admin/taskengine",
            timeout=10,
        )
        assert result.returncode == 0
        assert "serve" in result.stdout
        assert "trigger" in result.stdout
        assert "dashboard" in result.stdout
        assert "list" in result.stdout
        assert "version" in result.stdout

    def test_help_shows_usage(self):
        result = subprocess.run(
            [sys.executable, "engine.py", "help"],
            capture_output=True, text=True,
            cwd="/home/admin/taskengine",
            timeout=10,
        )
        assert "Usage" in result.stdout

    def test_no_args_shows_help_like_output(self):
        """无参数也应该显示用法"""
        result = subprocess.run(
            [sys.executable, "engine.py"],
            capture_output=True, text=True,
            cwd="/home/admin/taskengine",
            timeout=10,
        )
        assert result.returncode == 1
        assert "Commands" in result.stdout or "Usage" in result.stdout


class TestListCommand:
    """测试 list 命令"""

    def test_list_with_tasks(self, tmp_path):
        config_path = tmp_path / "tasks.yaml"
        config_path.write_text(yaml.dump({
            "tasks": {
                "daily_report": {
                    "schedule": "0 3 * * *",
                    "timeout": 3600,
                    "retry": 2,
                    "description": "每日报表",
                    "steps": [
                        {"name": "prepare", "command": "echo prep"},
                        {"name": "process", "command": "echo proc"},
                    ],
                },
                "data_sync": {
                    "schedule": "0 * * * *",
                    "steps": [{"name": "sync", "command": "echo sync"}],
                },
            }
        }, allow_unicode=True), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "engine.py", "list",
             "--config", str(config_path)],
            capture_output=True, text=True,
            cwd="/home/admin/taskengine",
            timeout=10,
        )
        assert result.returncode == 0
        assert "daily_report" in result.stdout
        assert "data_sync" in result.stdout
        assert "0 3 * * *" in result.stdout
        assert "2 tasks configured" in result.stdout

    def test_list_empty(self, tmp_path):
        config_path = tmp_path / "tasks.yaml"
        config_path.write_text(yaml.dump({"tasks": {}}, allow_unicode=True), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "engine.py", "list",
             "--config", str(config_path)],
            capture_output=True, text=True,
            cwd="/home/admin/taskengine",
            timeout=10,
        )
        assert result.returncode == 0
        assert "No tasks" in result.stdout

    def test_list_shows_step_count(self, tmp_path):
        config_path = tmp_path / "tasks.yaml"
        config_path.write_text(yaml.dump({
            "tasks": {
                "multi_step": {
                    "schedule": "0 3 * * *",
                    "steps": [
                        {"name": "step1", "command": "echo 1"},
                        {"name": "step2", "command": "echo 2"},
                        {"name": "step3", "command": "echo 3"},
                    ],
                },
            }
        }, allow_unicode=True), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "engine.py", "list",
             "--config", str(config_path)],
            capture_output=True, text=True,
            cwd="/home/admin/taskengine",
            timeout=10,
        )
        assert result.returncode == 0
        assert "3" in result.stdout  # 3 steps


class TestUnknownCommand:
    """测试未知命令"""

    def test_unknown_command_exits_with_error(self):
        result = subprocess.run(
            [sys.executable, "engine.py", "foobar"],
            capture_output=True, text=True,
            cwd="/home/admin/taskengine",
            timeout=10,
        )
        assert result.returncode == 1
        assert "Unknown command" in result.stdout

    def test_unknown_command_suggests_help(self):
        result = subprocess.run(
            [sys.executable, "engine.py", "foobar"],
            capture_output=True, text=True,
            cwd="/home/admin/taskengine",
            timeout=10,
        )
        assert "help" in result.stdout.lower()
