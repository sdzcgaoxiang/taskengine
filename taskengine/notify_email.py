"""TaskEngine Email Notification Module — SMTP email sending

Configuration example (tasks.yaml):
  email_notify:
    host: smtp.example.com
    port: 25
    ssl: false            # default false
    username: user        # optional
    password: pass        # optional
    from: bot@example.com
    to:
      - admin@example.com
    cc:                   # optional, CC list
      - ops@example.com
    on: failure           # failure / success / always, default failure
"""

import logging
import smtplib
from email.mime.text import MIMEText

from taskengine.engine import should_notify

logger = logging.getLogger(__name__)


def build_email_message(task_name, result, started_at, finished_at, duration):
    """Build email body (plain text)

    Returns:
        str: Email body text
    """
    status_text = "Succeeded" if result["success"] else "Failed"
    lines = [
        f"Task: {task_name}",
        f"Status: {status_text}",
        f"Started: {started_at}",
        f"Finished: {finished_at}",
        f"Duration: {duration:.1f}s",
        "",
    ]

    # Step execution details
    if result.get("steps"):
        lines.append("Step execution details:")
        for s in result["steps"]:
            name = s.get("name", "?")
            if s.get("success"):
                dur = s.get("duration", "")
                dur_text = f" ({dur:.1f}s)" if dur else ""
                lines.append(f"  ✓ {name}{dur_text}")
            else:
                lines.append(f"  ✗ {name}")
                if s.get("exit_code") is not None:
                    lines.append(f"    Exit code: {s['exit_code']}")
                output = (s.get("output") or "")[-500:]
                if output:
                    lines.append(f"    Output: {output}")
                if s.get("retry_count"):
                    lines.append(f"    Retry count: {s['retry_count']}")

    return "\n".join(lines)


def send_email(config, subject, body):
    """Send an email

    Args:
        config: SMTP configuration dict (host, port, ssl, username, password, from, to)
        subject: Email subject
        body: Email body

    Returns:
        bool: True if sent successfully, False if sending failed
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
        logger.error("Email sending failed: %s", e)
        return False
    except Exception as e:
        logger.error("Email sending error: %s", e)
        return False


def _auth_and_send(smtp, config, msg):
    """Authenticate and send the email"""
    username = config.get("username")
    password = config.get("password")
    if username and password:
        smtp.login(username, password)
    smtp.send_message(msg)


def notify_email(email_config, task_name, result, started_at, finished_at, duration):
    """Email notification entry point (called by run_task)

    Args:
        email_config: email_notify configuration dict; skipped if None
        task_name: Task name
        result: run_task return value {success, steps, ...}
        started_at: Task start time (ISO)
        finished_at: Task end time (ISO)
        duration: Total duration (seconds)
    """
    if not email_config:
        return

    to = email_config.get("to")
    if not to:
        return

    on = email_config.get("on", "failure")
    if not should_notify(on, result["success"]):
        return

    status_text = "Succeeded" if result["success"] else "Failed"
    subject = f"[TaskEngine] {task_name} {status_text}"

    body = build_email_message(task_name, result, started_at, finished_at, duration)

    ok = send_email(email_config, subject, body)
    if ok:
        logger.info("Email notification sent: %s -> %s", task_name, to)
    else:
        logger.warning("Email notification failed: %s", task_name)
