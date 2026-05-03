"""TaskEngine 测试共享 fixtures"""
import os
from pathlib import Path

import pytest
import yaml

# 项目根目录（tests/ 的上级）
PROJECT_ROOT = str(Path(__file__).parent.parent)


@pytest.fixture
def make_config(tmp_path):
    """创建临时 tasks.yaml 配置文件，返回文件路径"""
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
    """快速创建单任务配置（test_task），支持 timeout/retry/params 等关键字参数"""
    def _make(steps, **overrides):
        task = {"schedule": "0 3 * * *", "steps": steps}
        task.update(overrides)
        return make_config({"tasks": {"test_task": task}})
    return _make
