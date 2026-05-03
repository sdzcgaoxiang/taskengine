"""TaskEngine - 轻量定时任务引擎（核心逻辑）

业务函数：check_success, replace_params, load_config, Logger,
         run_step, run_task, notify, should_notify, TaskQueue 等。
CLI 入口见 cli.py。
"""
import json
import os
import subprocess
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime

import yaml
from taskengine.history import append_history, cleanup_history, mark_running, clear_running


# ─── 成功条件判定 ───

def check_success(conditions, exit_code, output):
    """
    多规则 OR，规则内 AND。
    conditions 为空时默认 exit_code=0。
    """
    if not conditions:
        return exit_code == 0

    for rule in conditions:
        rule_exit = rule.get("exit_code")
        contains = rule.get("output_contains")
        not_contains = rule.get("output_not_contains")

        # 检查 exit_code（如果规则里没写，就不检查）
        exit_ok = True
        if rule_exit is not None:
            exit_ok = (exit_code == rule_exit)

        # 检查 output_contains
        contains_ok = True
        if contains is not None:
            contains_ok = (contains in output)

        # 检查 output_not_contains
        not_contains_ok = True
        if not_contains is not None:
            not_contains_ok = (not_contains not in output)

        # 规则内 AND
        if exit_ok and contains_ok and not_contains_ok:
            return True

    return False


# ─── 参数替换 ───

def replace_params(command, params):
    """把 {{key}} 替换为 params[key]，缺失的保持原样"""
    for key, value in params.items():
        command = command.replace("{{" + key + "}}", str(value))
    return command


# ─── 配置加载 ───

def load_config(config_path):
    """加载 YAML 配置，合并 defaults"""
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    defaults = raw.get("defaults", {})
    tasks = raw.get("tasks", {})

    for task_name, task in tasks.items():
        # 任务级默认值合并
        for key in ("timeout", "retry", "retry_delay"):
            if key not in task and key in defaults:
                task[key] = defaults[key]

        # 确保 timeout 有值
        if "timeout" not in task:
            task["timeout"] = 300

        # Step 级默认值合并
        for step in task.get("steps", []):
            if "timeout" not in step:
                step["timeout"] = task["timeout"]
            if "retry" not in step:
                step["retry"] = 0
            if "retry_delay" not in step:
                step["retry_delay"] = 60
            if "success_conditions" not in step:
                step["success_conditions"] = [{"exit_code": 0}]

        # http_notify 合并
        if "http_notify" not in task and "http_notify" in defaults:
            task["http_notify"] = defaults["http_notify"]

        # email_notify 合并
        if "email_notify" not in task and "email_notify" in defaults:
            task["email_notify"] = defaults["email_notify"]

    return {"tasks": tasks, "defaults": defaults}


# ─── 日志 ───

class Logger:
    def __init__(self, log_dir):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self._file = None
        self._path = None

    def _open(self, task_name, run_id):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{task_name}_{timestamp}_{run_id}.log"
        self._path = os.path.join(self.log_dir, filename)
        self._file = open(self._path, "a", encoding="utf-8")

    def _write(self, msg):
        ts = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        line = f"{ts} {msg}"
        if self._file:
            self._file.write(line + "\n")
            self._file.flush()

    def start_run(self, task_name, run_id):
        self._open(task_name, run_id)
        self._write(f"Task: {task_name} START")

    def step_start(self, step_name, command):
        self._write(f"Step: {step_name} START")
        self._write(f"  Command: {command}")

    def step_end(self, step_name, success, exit_code, duration, fail_reason=None, matched_rule=None):
        status = "SUCCESS" if success else "FAILURE"
        rule_info = f" (matched rule: {matched_rule})" if matched_rule else ""
        reason_info = f" ({fail_reason})" if fail_reason else ""
        self._write(f"  Exit code: {exit_code}")
        self._write(f"  Result: {status}{rule_info}{reason_info}")
        self._write(f"Step: {step_name} END ({duration:.1f}s)")

    def step_output(self, output):
        # 记录输出片段
        snippet = output[-500:] if len(output) > 500 else output
        for line in snippet.strip().split("\n"):
            self._write(f"  > {line}")

    def step_skipped(self, step_name):
        self._write(f"Step: {step_name} SKIPPED (already completed)")

    def end_run(self, task_name, success, duration):
        status = "SUCCESS" if success else "FAILURE"
        self._write(f"Task: {task_name} END ({duration:.1f}s) {status}")
        if self._file:
            self._file.close()
            self._file = None


# ─── 状态持久化 ───

def save_state(state_dir, run_id, completed_steps, failed_step):
    os.makedirs(state_dir, exist_ok=True)
    path = os.path.join(state_dir, f"{run_id}.json")
    data = {
        "completed_steps": completed_steps,
        "failed_step": failed_step,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def load_state(state_dir, run_id):
    path = os.path.join(state_dir, f"{run_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def clear_state(state_dir, run_id):
    path = os.path.join(state_dir, f"{run_id}.json")
    if os.path.exists(path):
        os.remove(path)


# ─── HTTP 通知 ───

def should_notify(on_config, task_success):
    """判断是否需要发送通知"""
    if on_config == "always":
        return True
    if on_config == "failure":
        return not task_success
    if on_config == "success":
        return task_success
    return False


def notify(url, payload, timeout=5):
    """发送 HTTP 通知，失败不抛异常"""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=timeout)
    except Exception:
        pass  # 通知失败不影响任务


# ─── Step 执行 ───

def run_step(step, params, logger, run_id="0"):
    """执行单个 Step，处理超时、重试、成功判定"""
    command = replace_params(step["command"], params)
    timeout = step.get("timeout", 300)
    max_retry = step.get("retry", 0)
    retry_delay = step.get("retry_delay", 60)
    conditions = step.get("success_conditions", [{"exit_code": 0}])
    workdir = step.get("workdir")
    shell_type = step.get("shell", "powershell")  # powershell 或 bash

    logger.step_start(step["name"], command)

    if shell_type == "bash":
        cmd_args = ["bash", "-c", command]
    else:
        cmd_args = ["powershell", "-Command", command]

    retry_count = 0
    step_start = time.time()
    for attempt in range(1 + max_retry):
        try:
            proc = subprocess.Popen(
                cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=workdir,
            )
            try:
                output, _ = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                if attempt < max_retry:
                    retry_count += 1
                    time.sleep(retry_delay)
                    continue
                result = {
                    "success": False,
                    "exit_code": -1,
                    "output": "",
                    "fail_reason": "timeout",
                    "retry_count": retry_count,
                    "duration": round(time.time() - step_start, 1),
                }
                logger.step_output(f"TIMEOUT after {timeout}s")
                logger.step_end(step["name"], False, -1, 0, fail_reason="timeout")
                return result

            exit_code = proc.returncode
            success = check_success(conditions, exit_code, output)

            if success:
                # 找到匹配的规则描述
                matched = _describe_matched_rule(conditions, exit_code, output)
                logger.step_output(output)
                logger.step_end(step["name"], True, exit_code, 0, matched_rule=matched)
                return {
                    "success": True,
                    "exit_code": exit_code,
                    "output": output,
                    "retry_count": retry_count,
                    "duration": round(time.time() - step_start, 1),
                }
            else:
                if attempt < max_retry:
                    retry_count += 1
                    time.sleep(retry_delay)
                    continue
                logger.step_output(output)
                logger.step_end(step["name"], False, exit_code, 0, fail_reason=f"exit_code={exit_code}, no rule matched")
                return {
                    "success": False,
                    "exit_code": exit_code,
                    "output": output,
                    "fail_reason": f"exit_code={exit_code}, no rule matched",
                    "retry_count": retry_count,
                    "duration": round(time.time() - step_start, 1),
                }

        except Exception as e:
            if attempt < max_retry:
                retry_count += 1
                time.sleep(retry_delay)
                continue
            logger.step_end(step["name"], False, -1, 0, fail_reason=str(e))
            return {
                "success": False,
                "exit_code": -1,
                "output": "",
                "fail_reason": str(e),
                "retry_count": retry_count,
                "duration": round(time.time() - step_start, 1),
            }


def _describe_matched_rule(conditions, exit_code, output):
    """描述匹配到的规则"""
    for i, rule in enumerate(conditions):
        rule_exit = rule.get("exit_code")
        contains = rule.get("output_contains")
        not_contains = rule.get("output_not_contains")

        exit_ok = rule_exit is None or exit_code == rule_exit
        contains_ok = contains is None or contains in output
        not_contains_ok = not_contains is None or not_contains not in output

        if exit_ok and contains_ok and not_contains_ok:
            parts = []
            if rule_exit is not None:
                parts.append(f"exit_code={rule_exit}")
            if contains is not None:
                parts.append(f"output_contains \"{contains}\"")
            if not_contains is not None:
                parts.append(f"output_not_contains \"{not_contains}\"")
            return " AND ".join(parts) if parts else "default"
    return None


# ─── Task 执行 ───

def run_task(task, task_name, params, logger, state_dir=None, http_notify_config=None,
             email_notify_config=None, history_file=None, history_keep=50):
    """执行整个 Task，从失败 Step 重跑"""
    steps = task["steps"]
    task_timeout = task.get("timeout", 3600)
    task_retry = task.get("retry", 0)
    task_retry_delay = task.get("retry_delay", 60)

    run_id = f"{task_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    logger.start_run(task_name, run_id)

    # 标记运行中
    if state_dir:
        mark_running(state_dir, task_name)

    # 解析参数默认值
    resolved_params = {}
    for p in task.get("params", []):
        resolved_params[p["name"]] = p.get("default", "")
    resolved_params.update(params)

    started_at = datetime.now().isoformat()
    start_time = time.time()

    # 加载已有状态（用于 Task 级重试时从失败 Step 继续）
    if state_dir:
        existing = load_state(state_dir, run_id)
        if existing:
            completed_steps = existing["completed_steps"]
        else:
            completed_steps = []
    else:
        completed_steps = []

    for task_attempt in range(1 + task_retry):
        step_results = []
        failed = False

        for i, step in enumerate(steps):
            # 跳过已成功的 Step
            if step["name"] in completed_steps:
                logger.step_skipped(step["name"])
                step_results.append({"name": step["name"], "success": True, "skipped": True})
                continue

            # 检查 Task 总超时
            elapsed = time.time() - start_time
            if elapsed > task_timeout:
                logger._write(f"Task timeout ({task_timeout}s) exceeded")
                # 未执行的 step 标记为 skipped
                for remaining_step in steps[i:]:
                    step_results.append({"name": remaining_step["name"], "success": None, "skipped": True})
                failed = True
                break

            result = run_step(step, resolved_params, logger, run_id=run_id)
            result["name"] = step["name"]
            step_results.append(result)

            if result["success"]:
                completed_steps.append(step["name"])
                # 保存状态
                if state_dir:
                    save_state(state_dir, run_id, completed_steps, None)
            else:
                failed = True
                if state_dir:
                    save_state(state_dir, run_id, completed_steps, step["name"])
                # 未执行的 step 标记为 skipped
                for remaining_step in steps[i + 1:]:
                    step_results.append({"name": remaining_step["name"], "success": None, "skipped": True})
                break

        if not failed:
            # 清理状态
            if state_dir:
                clear_state(state_dir, run_id)
            duration = time.time() - start_time
            logger.end_run(task_name, True, duration)
            result = {"success": True, "steps": step_results, "duration": duration}
            _write_history(history_file, task_name, run_id, result, started_at, duration, history_keep)
            _do_notify(task_name, result, http_notify_config)
            _do_notify_email(task_name, result, email_notify_config, started_at, duration)
            if state_dir:
                clear_running(state_dir, task_name)
            return result

        # Task 重试
        if task_attempt < task_retry:
            logger._write(f"Task retry {task_attempt + 1}/{task_retry} after {task_retry_delay}s")
            time.sleep(task_retry_delay)

    # 所有重试耗尽
    if state_dir:
        clear_state(state_dir, run_id)
    duration = time.time() - start_time
    logger.end_run(task_name, False, duration)
    result = {"success": False, "steps": step_results, "duration": duration}
    _write_history(history_file, task_name, run_id, result, started_at, duration, history_keep)
    _do_notify(task_name, result, http_notify_config)
    _do_notify_email(task_name, result, email_notify_config, started_at, duration)
    if state_dir:
        clear_running(state_dir, task_name)
    return result


def _build_step_results_for_history(step_results):
    """构建 history 记录的 step_results"""
    history_steps = []
    for s in step_results:
        entry = {"name": s.get("name", "?")}
        if s.get("skipped") and s.get("success") is None:
            entry["status"] = "skipped"
        elif s.get("success"):
            entry["status"] = "success"
        else:
            entry["status"] = "failure"
        entry["exit_code"] = s.get("exit_code")
        entry["duration"] = round(s.get("duration", 0), 1) if s.get("duration") else None
        entry["retries"] = s.get("retry_count", 0)
        history_steps.append(entry)
    return history_steps


def _write_history(history_file, task_name, run_id, result, started_at, duration, history_keep):
    """写入运行历史记录"""
    if not history_file:
        return
    # 找到失败的 step
    failed_step = None
    fail_reason = None
    for s in result.get("steps", []):
        if not s.get("success") and not s.get("skipped"):
            failed_step = s.get("name")
            fail_reason = s.get("fail_reason")
            break

    entry = {
        "task": task_name,
        "run_id": run_id,
        "status": "success" if result["success"] else "failure",
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(),
        "duration": round(duration, 1),
        "step_results": _build_step_results_for_history(result.get("steps", [])),
        "failed_step": failed_step,
        "fail_reason": fail_reason,
    }
    append_history(history_file, entry)
    cleanup_history(history_file, keep=history_keep)


def _do_notify(task_name, result, http_notify_config):
    """发送通知（如果配置了且条件满足）"""
    if not http_notify_config:
        return
    url = http_notify_config.get("url")
    on = http_notify_config.get("on", "failure")
    if not url:
        return
    if not should_notify(on, result["success"]):
        return

    failed_step = None
    exit_code = None
    output_snippet = ""
    retry_count = 0
    for s in result.get("steps", []):
        if not s.get("success"):
            failed_step = s.get("name")
            exit_code = s.get("exit_code")
            output_snippet = (s.get("output", "") or "")[-500:]
            retry_count = s.get("retry_count", 0)
            break

    payload = {
        "task": task_name,
        "status": "failure" if not result["success"] else "success",
        "step_failed": failed_step,
        "exit_code": exit_code,
        "output_snippet": output_snippet,
        "retry_count": retry_count,
        "started_at": "",  # 由 run_task 填充更精确的
        "finished_at": datetime.now().isoformat(),
    }
    notify(url, payload)


def _do_notify_email(task_name, result, email_notify_config, started_at, duration):
    """发送邮件通知（如果配置了且条件满足）"""
    if not email_notify_config:
        return
    from notify_email import notify_email
    finished_at = datetime.now().isoformat()
    notify_email(email_notify_config, task_name, result, started_at, finished_at, duration)


# ─── 排队执行 ───

class TaskQueue:
    """串行任务队列"""

    def __init__(self, runner):
        self.runner = runner
        self._queue = []
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def submit(self, task_name, params):
        with self._lock:
            self._queue.append((task_name, params))
            if not self._running:
                self._running = True
                self._thread = threading.Thread(target=self._run_loop, daemon=True)
                self._thread.start()

    def _run_loop(self):
        while True:
            with self._lock:
                if not self._queue:
                    self._running = False
                    return
                task_name, params = self._queue.pop(0)
            self.runner(task_name, params)

    def wait_all(self):
        if self._thread:
            self._thread.join()


# ─── CLI ───

def parse_trigger_args(args):
    """解析 trigger 命令参数"""
    task_name = args[1] if len(args) > 1 else None
    params = {}
    for i, a in enumerate(args):
        if a == "--params" and i + 1 < len(args):
            params = json.loads(args[i + 1])
    return {"task_name": task_name, "params": params}


if __name__ == "__main__":
    from taskengine.cli import main
    main()
