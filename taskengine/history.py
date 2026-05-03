"""TaskEngine 运行历史记录 — 读写、清理、查询、运行锁"""
import json
import os
from datetime import datetime


# ─── 基础读写 ───

def load_history(path):
    """加载历史记录，文件不存在返回空列表"""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def append_history(path, entry):
    """追加一条历史记录"""
    records = load_history(path)
    records.append(entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


# ─── 清理 ───

def cleanup_history(path, keep=50):
    """每个 Task 只保留最近 keep 条记录"""
    records = load_history(path)
    if not records:
        return

    # 按 task 分组
    by_task = {}
    for r in records:
        task = r.get("task", "")
        by_task.setdefault(task, []).append(r)

    # 每个 task 截取最后 keep 条
    trimmed = []
    for task, entries in by_task.items():
        trimmed.extend(entries[-keep:])

    with open(path, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)


# ─── 查询 ───

def get_latest_per_task(path):
    """返回每个 Task 的最新一条记录 {task_name: record}"""
    records = load_history(path)
    latest = {}
    for r in records:
        task = r.get("task", "")
        latest[task] = r  # 后出现的覆盖前面的（即最新的）
    return latest


def get_task_history(path, task_name, limit=20):
    """返回某 Task 最近 limit 条记录（按时间正序）"""
    records = load_history(path)
    task_records = [r for r in records if r.get("task") == task_name]
    return task_records[-limit:]


# ─── 运行锁 ───

def mark_running(state_dir, task_name, pid=None):
    """标记任务正在运行"""
    os.makedirs(state_dir, exist_ok=True)
    lock_path = os.path.join(state_dir, f"{task_name}.running")
    data = {
        "pid": pid or os.getpid(),
        "started_at": datetime.now().isoformat(),
    }
    with open(lock_path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def clear_running(state_dir, task_name):
    """清除运行标记"""
    lock_path = os.path.join(state_dir, f"{task_name}.running")
    if os.path.exists(lock_path):
        os.remove(lock_path)


def is_running(state_dir, task_name):
    """检查任务是否正在运行，返回 False 或运行信息 dict"""
    lock_path = os.path.join(state_dir, f"{task_name}.running")
    if not os.path.exists(lock_path):
        return False
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return False
