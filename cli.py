"""TaskEngine CLI — 命令行入口（serve / trigger / status）"""
import os
import sys
import time
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from engine import load_config, Logger, run_task, TaskQueue, parse_trigger_args
from dashboard import render_summary, render_task_detail


def main():
    """主入口"""
    if len(sys.argv) < 2:
        print("Usage: python engine.py serve | trigger <task_name> [--params '{...}'] | status [options]")
        sys.exit(1)

    command = sys.argv[1]

    # 确定配置文件路径（与 engine.py 同目录）
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "tasks.yaml")
    log_dir = os.path.join(base_dir, "logs")
    state_dir = os.path.join(base_dir, "state")
    history_file = os.path.join(base_dir, "history.json")

    if command == "trigger":
        _cmd_trigger(sys.argv[1:], config_path, log_dir, state_dir, history_file)

    elif command == "serve":
        _cmd_serve(config_path, log_dir, state_dir, history_file)

    elif command == "status":
        _cmd_status(sys.argv[2:], config_path, history_file, state_dir)

    else:
        print(f"Unknown command: {command}")
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
                      state_dir=state_dir, history_file=history_file)
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


def _cmd_status(args, default_config_path, default_history_file, default_state_dir):
    """处理 status 子命令"""
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
