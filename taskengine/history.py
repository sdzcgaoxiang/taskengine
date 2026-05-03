"""TaskEngine run history — read/write, cleanup, queries, run locks"""
import json
import os
from datetime import datetime


# ─── Basic read/write ───

def load_history(path):
    """Load history records; return empty list if file does not exist"""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def append_history(path, entry):
    """Append a single history record"""
    records = load_history(path)
    records.append(entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


# ─── Cleanup ───

def cleanup_history(path, keep=50):
    """Keep only the most recent `keep` records per task"""
    records = load_history(path)
    if not records:
        return

    # Group by task
    by_task = {}
    for r in records:
        task = r.get("task", "")
        by_task.setdefault(task, []).append(r)

    # Keep the last `keep` entries for each task
    trimmed = []
    for task, entries in by_task.items():
        trimmed.extend(entries[-keep:])

    with open(path, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)


# ─── Queries ───

def get_latest_per_task(path):
    """Return the latest record per task {task_name: record}"""
    records = load_history(path)
    latest = {}
    for r in records:
        task = r.get("task", "")
        latest[task] = r  # Later entries overwrite earlier ones (i.e. keep the latest)
    return latest


def get_task_history(path, task_name, limit=20):
    """Return the most recent `limit` records for a task (in chronological order)"""
    records = load_history(path)
    task_records = [r for r in records if r.get("task") == task_name]
    return task_records[-limit:]


# ─── Run locks ───

def mark_running(state_dir, task_name, pid=None):
    """Mark a task as currently running"""
    os.makedirs(state_dir, exist_ok=True)
    lock_path = os.path.join(state_dir, f"{task_name}.running")
    data = {
        "pid": pid or os.getpid(),
        "started_at": datetime.now().isoformat(),
    }
    with open(lock_path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def clear_running(state_dir, task_name):
    """Clear the running marker"""
    lock_path = os.path.join(state_dir, f"{task_name}.running")
    if os.path.exists(lock_path):
        os.remove(lock_path)


def is_running(state_dir, task_name):
    """Check if a task is running; returns False or the run-info dict"""
    lock_path = os.path.join(state_dir, f"{task_name}.running")
    if not os.path.exists(lock_path):
        return False
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return False
