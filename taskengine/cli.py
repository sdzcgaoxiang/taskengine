"""TaskEngine CLI — command-line entry point (serve / trigger / dashboard / help / version / list)"""

import os
import sys
import time
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from taskengine import __version__
from taskengine.engine import load_config, Logger, run_task, TaskQueue, parse_trigger_args
from taskengine.dashboard import render_summary, render_task_detail


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python engine.py <command> [args]")
        print()
        print("Commands:")
        print("  serve                              Start the scheduler")
        print("  trigger <task> [--params '{...}']  Manually trigger a task")
        print("  dashboard [options]                Monitoring dashboard")
        print("  list                               List all configured tasks")
        print("  version                            Show version number")
        print("  help                               Show help information")
        sys.exit(1)

    command = sys.argv[1]

    # Determine base directory: prefer tasks.yaml in the current working directory
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    pkg_parent = os.path.dirname(pkg_dir)
    cwd = os.getcwd()
    # If tasks.yaml exists in current dir → use current dir (e.g. cd examples/)
    # Otherwise → use the package's parent directory (project root)
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
    """Handle the trigger subcommand"""
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
    """Handle the serve subcommand"""
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
    """Handle the dashboard subcommand"""
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
    """List all configured tasks"""
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
    """Show version number"""
    print(f"TaskEngine v{__version__}")


def _cmd_help():
    """Show help information"""
    print("TaskEngine — Lightweight Scheduled Task Engine")
    print()
    print("Usage: python engine.py <command> [args]")
    print()
    print("Commands:")
    print()
    print("  serve")
    print("      Start the scheduler; executes tasks based on cron expressions.")
    print("      Blocks until Ctrl+C is pressed.")
    print()
    print("  trigger <task_name> [--params '{\"key\":\"value\"}']")
    print("      Manually trigger the specified task, then exit.")
    print("      --params  Pass runtime parameters (JSON format)")
    print()
    print("  dashboard [options]")
    print("      Monitoring dashboard; view task execution status.")
    print("      --task <name>       View step-level details for a single task")
    print("      --watch [N]         Auto-refresh (default 3 seconds), Ctrl+C to exit")
    print("      --config <path>     Specify config file path")
    print("      --history <path>    Specify history file path")
    print("      --state-dir <path>  Specify state directory path")
    print()
    print("  list")
    print("      List all configured tasks and their basic information.")
    print()
    print("  version")
    print("      Show version number.")
    print()
    print("  help")
    print("      Show this help message.")
