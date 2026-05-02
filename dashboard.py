"""TaskEngine 监控面板 — 终端表格渲染、颜色、格式化"""
from history import get_latest_per_task, get_task_history, is_running

# ─── ANSI 颜色 ───

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
GRAY = "\033[90m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def colorize(text, color):
    """给文本添加 ANSI 颜色"""
    if color is None:
        return text
    return f"{color}{text}{RESET}"


# ─── 格式化辅助 ───

def format_duration(seconds):
    """将秒数格式化为可读的时间字符串"""
    if seconds < 0:
        seconds = 0
    total = int(seconds)
    if total >= 3600:
        hours = total // 3600
        minutes = (total % 3600) // 60
        return f"{hours}h {minutes}m"
    elif total >= 60:
        minutes = total // 60
        secs = total % 60
        return f"{minutes}m {secs}s"
    else:
        return f"{total}s"


def _step_progress(step_results):
    """计算 step 成功数/总数"""
    if not step_results:
        return "0/0", False
    total = len(step_results)
    succeeded = sum(1 for s in step_results if s.get("status") == "success")
    return f"{succeeded}/{total}", succeeded == total


def _status_display(status, running_info):
    """返回 (显示文本, 颜色)"""
    if running_info:
        return "Running", YELLOW
    if status == "success":
        return "Success", GREEN
    if status == "failure":
        return "Failure", RED
    return "Never", GRAY


# ─── 全部任务表格 ───

def render_summary(config, history_file, state_dir=None):
    """渲染全部任务的状态表格"""
    tasks = config.get("tasks", {})
    if not tasks:
        return "0 tasks | No tasks configured"

    latest = get_latest_per_task(history_file)

    lines = []
    # 表头
    header = f"{'Task':<18} {'Schedule':<14} {'Status':<12} {'Last Run':<22} {'Duration':<10} {'Steps':<8}"
    lines.append(header)
    lines.append("─" * 18 + " " + "─" * 14 + " " + "─" * 12 + " " + "─" * 22 + " " + "─" * 10 + " " + "─" * 8)

    for task_name, task_config in tasks.items():
        schedule = task_config.get("schedule", "")
        total_steps = len(task_config.get("steps", []))

        # 检查是否正在运行
        running_info = is_running(state_dir, task_name) if state_dir else False

        # 获取最近执行记录
        record = latest.get(task_name)
        if record:
            status = record.get("status", "")
            finished = record.get("finished_at", "—")
            duration = format_duration(record.get("duration", 0))
            step_info, _ = _step_progress(record.get("step_results"))
            step_display = f"{step_info} {'✓' if status == 'success' else '✗'}"
        else:
            status = None
            finished = "—"
            duration = "—"
            step_display = "—"

        status_text, color = _status_display(status, running_info)
        status_colored = colorize(status_text, color)

        lines.append(
            f"{task_name:<18} {schedule:<14} {status_colored:<12} {finished:<22} {duration:<10} {step_display:<8}"
        )

    # 汇总行
    total = len(tasks)
    success_count = sum(1 for t in tasks if latest.get(t, {}).get("status") == "success")
    failure_count = sum(1 for t in tasks if latest.get(t, {}).get("status") == "failure")
    never_count = total - success_count - failure_count

    summary = f"{total} tasks | {success_count} success, {failure_count} failure, {never_count} never run"
    lines.append("")
    lines.append(summary)

    return "\n".join(lines)


# ─── 单任务详情 ───

def render_task_detail(task_config, history_file, task_name, limit=5):
    """渲染单个任务的 Step 级执行历史"""
    schedule = task_config.get("schedule", "")
    steps = task_config.get("steps", [])
    timeout = task_config.get("timeout", "—")
    retry = task_config.get("retry", 0)

    lines = []
    lines.append(f"Task: {task_name}")
    lines.append(f"Schedule: {schedule}  |  Timeout: {timeout}s  |  Retry: {retry}")
    lines.append("")

    records = get_task_history(history_file, task_name, limit=limit)

    if not records:
        lines.append("No run history")
        return "\n".join(lines)

    lines.append(f"Last {len(records)} runs:")
    for rec in reversed(records):
        started = rec.get("started_at", "—")
        status = rec.get("status", "")
        duration = format_duration(rec.get("duration", 0))
        status_text, color = _status_display(status, None)
        status_colored = colorize(status_text, color)

        # Step 摘要
        step_results = rec.get("step_results", [])
        step_parts = []
        for s in step_results:
            name = s.get("name", "?")
            if s.get("status") == "success":
                step_parts.append(f"{name} {colorize('✓', GREEN)}")
            elif s.get("status") == "failure":
                step_parts.append(f"{name} {colorize('✗', RED)}")
            else:
                step_parts.append(f"{name} (skipped)")

        step_chain = " → ".join(step_parts)
        fail_reason = rec.get("fail_reason")
        reason_str = f" ({fail_reason})" if fail_reason else ""

        lines.append(f"  {started}  {status_colored}  {duration}{reason_str}  Steps: {step_chain}")

    # 最新一次的 Step 详情
    latest = records[-1]
    lines.append("")
    lines.append(f"Step details (latest run):")
    for s in latest.get("step_results", []):
        name = s.get("name", "?")
        s_status = s.get("status", "")
        exit_code = s.get("exit_code", "—")
        s_duration = format_duration(s.get("duration", 0))
        retries = s.get("retries", 0)

        s_text, s_color = _status_display(s_status, None)
        lines.append(f"  {name:<15} {colorize(s_text, s_color):<12} exit={exit_code}  {s_duration}  retries={retries}")

    return "\n".join(lines)
