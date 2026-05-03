"""TaskEngine 邮件通知模块 — SMTP 邮件发送

配置示例 (tasks.yaml):
  email_notify:
    host: smtp.example.com
    port: 25
    ssl: false            # 默认 false
    username: user        # 可选
    password: pass        # 可选
    from: bot@example.com
    to:
      - admin@example.com
    cc:                   # 可选，抄送列表
      - ops@example.com
    on: failure           # failure / success / always，默认 failure
"""

import logging
import smtplib
from email.mime.text import MIMEText

from engine import should_notify

logger = logging.getLogger(__name__)


def build_email_message(task_name, result, started_at, finished_at, duration):
    """构建邮件正文（纯文本）

    Returns:
        str: 邮件正文
    """
    status_text = "成功" if result["success"] else "失败"
    lines = [
        f"任务: {task_name}",
        f"状态: {status_text}",
        f"开始: {started_at}",
        f"结束: {finished_at}",
        f"耗时: {duration:.1f}s",
        "",
    ]

    # 步骤执行情况
    if result.get("steps"):
        lines.append("步骤执行详情:")
        for s in result["steps"]:
            name = s.get("name", "?")
            if s.get("success"):
                dur = s.get("duration", "")
                dur_text = f" ({dur:.1f}s)" if dur else ""
                lines.append(f"  ✓ {name}{dur_text}")
            else:
                lines.append(f"  ✗ {name}")
                if s.get("exit_code") is not None:
                    lines.append(f"    退出码: {s['exit_code']}")
                output = (s.get("output") or "")[-500:]
                if output:
                    lines.append(f"    输出: {output}")
                if s.get("retry_count"):
                    lines.append(f"    重试次数: {s['retry_count']}")

    return "\n".join(lines)


def send_email(config, subject, body):
    """发送邮件

    Args:
        config: SMTP 配置字典 (host, port, ssl, username, password, from, to)
        subject: 邮件主题
        body: 邮件正文

    Returns:
        bool: True 发送成功, False 发送失败
    """
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = config["from"]
    msg["To"] = ", ".join(config["to"])

    cc = config.get("cc")
    if cc:
        msg["Cc"] = ", ".join(cc)

    use_ssl = config.get("ssl", False)
    host = config["host"]
    port = config.get("port", 25 if not use_ssl else 465)

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=10) as smtp:
                _auth_and_send(smtp, config, msg)
        else:
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                _auth_and_send(smtp, config, msg)
        return True
    except smtplib.SMTPException as e:
        logger.error("邮件发送失败: %s", e)
        return False
    except Exception as e:
        logger.error("邮件发送异常: %s", e)
        return False


def _auth_and_send(smtp, config, msg):
    """登录认证并发送邮件"""
    username = config.get("username")
    password = config.get("password")
    if username and password:
        smtp.login(username, password)
    smtp.send_message(msg)


def notify_email(email_config, task_name, result, started_at, finished_at, duration):
    """邮件通知入口（由 run_task 调用）

    Args:
        email_config: email_notify 配置字典，None 则跳过
        task_name: 任务名称
        result: run_task 返回值 {success, steps, ...}
        started_at: 任务开始时间 (ISO)
        finished_at: 任务结束时间 (ISO)
        duration: 总耗时 (秒)
    """
    if not email_config:
        return

    to = email_config.get("to")
    if not to:
        return

    on = email_config.get("on", "failure")
    if not should_notify(on, result["success"]):
        return

    status_text = "成功" if result["success"] else "失败"
    subject = f"[TaskEngine] {task_name} {status_text}"

    body = build_email_message(task_name, result, started_at, finished_at, duration)

    ok = send_email(email_config, subject, body)
    if ok:
        logger.info("邮件通知已发送: %s -> %s", task_name, to)
    else:
        logger.warning("邮件通知发送失败: %s", task_name)
