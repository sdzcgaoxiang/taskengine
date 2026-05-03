"""TaskEngine shared test fixtures"""
import os
from pathlib import Path

import pytest
import yaml

# Project root directory (parent of tests/)
PROJECT_ROOT = str(Path(__file__).parent.parent)


@pytest.fixture
def make_config(tmp_path):
    """Create a temporary tasks.yaml config file and return its path"""
    def _make(tasks_yaml):
        config_path = tmp_path / "tasks.yaml"
        config_path.write_text(
            yaml.dump(tasks_yaml, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        return str(config_path)
    return _make


@pytest.fixture
def make_task_config(make_config):
    """Quickly create a single-task config (test_task), supporting timeout/retry/params keyword arguments"""
    def _make(steps, **overrides):
        task = {"schedule": "0 3 * * *", "steps": steps}
        task.update(overrides)
        return make_config({"tasks": {"test_task": task}})
    return _make
