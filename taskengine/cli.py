"""TaskEngine CLI — 命令行入口（serve / trigger / dashboard / help / version / list）"""

import os
import sys
import time
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from taskengine import __version__
from taskengine.engine import load_config, Logger, run_task, TaskQueue, parse_trigger_args
from taskengine.dashboard import render_summary, render_task_detail


def main():
    """主入口"""
    if len(sys.argv) < 2:
        print("Usage: python engine.py <command> [args]")
        print()
        print("Commands:")
        print("  serve                              启动调度器")
        print("  trigger <task> [--params '{...}']  手动触发任务")
        print("  dashboard [options]                监控面板")
        print("  list                               列出所有配置的任务")
        print("  version                            显示版本号")
        print("  help                               显示帮助信息")
        sys.exit(1)

    command = sys.argv[1]

    # 确定基础目录：优先使用当前工作目录的 tasks.yaml
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    pkg_parent = os.path.dirname(pkg_dir)
    cwd = os.getcwd()
    # 当前目录有 tasks.yaml → 用当前目录（如 cd examples/）
    # 否则 → 用包的父目录（项目根）
    base_dir = cwd if os.path.exists(os.path.join(cwd, "tasks.yaml")) else pkg_parent
    config_path = os.path.join(base_dir, "tasks.yaml")
    log_dir = os.path.join(base_dir, "logs")
    state_dir = os.path.join(base_dir, "state")
    history_file = os.path.join(base_dir, "history.json")

    if command == "trigger":
        _cmd_trigger(sys.argv[1:], config_path, log_dir, state_dir, history_file)

    elif command == "serve":
        _cmd_serve(config_path, log_dir, state_dir, history_file)

    elif command == "dashboard":
        _cmd_dashboard(sys.argv[2:], config_path, history_file, state_dir)

    elif command == "list":
        _cmd_list(sys.argv[2:], config_path)

    elif command == "version":
        _cmd_version()

    elif command == "help":
        _cmd_help()

    else:
        print(f"Unknown command: {command}")
        print("Run 'python engine.py help' for usage.")
        sys.exit(1)


def _cmd_trigger(args, config_path, log_dir, state_dir, history_file):
    """处理 trigger 子命令"""
    parsed = parse_trigger_args(args)
    config = load_config(config_path)
    task_name = parsed["task_name"]
    if task_name not in config["tasks"]:
        print(f"Task not found: {task_name}")
        sys.exit(1)
    task = config["tasks"][task_name]
    logger = Logger(log_dir)
    result = run_task(task, task_name, parsed["params"], logger,
                      state_dir=state_dir, history_file=history_file,
                      http_notify_config=task.get("http_notify"),
                      email_notify_config=task.get("email_notify"))
    print(f"Task {task_name}: {'SUCCESS' if result['success'] else 'FAILURE'}")
    sys.exit(0 if result["success"] else 1)


def _cmd_serve(config_path, log_dir, state_dir, history_file):
    """处理 serve 子命令"""
    config = load_config(config_path)
    scheduler = BlockingScheduler()
    logger = Logger(log_dir)

    def queued_runner(task_name, params):
        task = config["tasks"][task_name]
        run_task(task, task_name, params, logger, state_dir=state_dir,
                 http_notify_config=task.get("http_notify"),
                 email_notify_config=task.get("email_notify"),
                 history_file=history_file)

    queue = TaskQueue(runner=queued_runner)

    for task_name, task in config["tasks"].items():
        cron_parts = task["schedule"].split()
        scheduler.add_job(
            queue.submit,
            "cron",
            args=[task_name, {}],
            minute=cron_parts[0] if len(cron_parts) > 0 else None,
            hour=cron_parts[1] if len(cron_parts) > 1 else None,
            day=cron_parts[2] if len(cron_parts) > 2 else None,
            month=cron_parts[3] if len(cron_parts) > 3 else None,
            day_of_week=cron_parts[4] if len(cron_parts) > 4 else None,
        )
        print(f"Scheduled: {task_name} ({task['schedule']})")

    print("TaskEngine serving...")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass


def _cmd_dashboard(args, default_config_path, default_history_file, default_state_dir):
    """处理 dashboard 子命令"""
    task_filter = None
    watch = False
    watch_interval = 3
    cli_config_path = default_config_path
    cli_history_file = default_history_file
    cli_state_dir = default_state_dir

    i = 0
    while i < len(args):
        if args[i] == "--task" and i + 1 < len(args):
            task_filter = args[i + 1]
            i += 2
        elif args[i] == "--watch":
            watch = True
            if i + 1 < len(args) and args[i + 1].isdigit():
                watch_interval = int(args[i + 1])
                i += 2
            else:
                i += 1
        elif args[i] == "--config" and i + 1 < len(args):
            cli_config_path = args[i + 1]
            i += 2
        elif args[i] == "--history" and i + 1 < len(args):
            cli_history_file = args[i + 1]
            i += 2
        elif args[i] == "--state-dir" and i + 1 < len(args):
            cli_state_dir = args[i + 1]
            i += 2
        else:
            i += 1

    config = load_config(cli_config_path)

    def show():
        if watch:
            print("\033[H\033[2J", end="")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"TaskEngine Dashboard — {now}")
        print()
        if task_filter:
            if task_filter not in config["tasks"]:
                print(f"Task not found: {task_filter}")
                return
            task_config = config["tasks"][task_filter]
            desc = task_config.get("description", "")
            if desc:
                print(f'Description: "{desc}"')
            print(render_task_detail(task_config, cli_history_file, task_name=task_filter, limit=5))
        else:
            print(render_summary(config, cli_history_file, state_dir=cli_state_dir))

    if watch:
        try:
            while True:
                show()
                time.sleep(watch_interval)
        except KeyboardInterrupt:
            pass
    else:
        show()


def _cmd_list(args, default_config_path):
    """列出所有配置的任务"""
    config_path = default_config_path
    i = 0
    while i < len(args):
        if args[i] == "--config" and i + 1 < len(args):
            config_path = args[i + 1]
            i += 2
        else:
            i += 1

    config = load_config(config_path)
    tasks = config.get("tasks", {})
    if not tasks:
        print("No tasks configured.")
        return

    print(f"{'Task':<20} {'Schedule':<16} {'Steps':<7} {'Timeout':<10} {'Retry':<6} {'Description'}")
    print("─" * 20 + " " + "─" * 16 + " " + "─" * 7 + " " + "─" * 10 + " " + "─" * 6 + " " + "─" * 20)
    for name, task in tasks.items():
        schedule = task.get("schedule", "—")
        steps = len(task.get("steps", []))
        timeout = f"{task.get('timeout', '—')}s"
        retry = task.get("retry", 0)
        desc = task.get("description", "")
        print(f"{name:<20} {schedule:<16} {steps:<7} {timeout:<10} {retry:<6} {desc}")

    print()
    print(f"{len(tasks)} tasks configured.")


def _cmd_version():
    """显示版本号"""
    print(f"TaskEngine v{__version__}")


def _cmd_help():
    """显示帮助信息"""
    print("TaskEngine — 轻量定时任务引擎")
    print()
    print("Usage: python engine.py <command> [args]")
    print()
    print("Commands:")
    print()
    print("  serve")
    print("      启动调度器，按 Cron 表达式定时执行任务。阻塞运行，Ctrl+C 退出。")
    print()
    print("  trigger <task_name> [--params '{\"key\":\"value\"}']")
    print("      手动触发指定任务，执行完毕后退出。")
    print("      --params  传递运行参数（JSON 格式）")
    print()
    print("  dashboard [options]")
    print("      监控面板，查看任务运行状态。")
    print("      --task <name>       查看单个任务的 Step 级详情")
    print("      --watch [N]         持续刷新（默认 3 秒），Ctrl+C 退出")
    print("      --config <path>     指定配置文件路径")
    print("      --history <path>    指定历史记录文件路径")
    print("      --state-dir <path>  指定状态目录路径")
    print()
    print("  list")
    print("      列出所有已配置的任务及其基本信息。")
    print()
    print("  version")
    print("      显示版本号。")
    print()
    print("  help")
    print("      显示本帮助信息。")
