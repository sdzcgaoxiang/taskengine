"""Tests for the notify_email module — TDD style"""

import smtplib
from unittest.mock import patch, MagicMock
import pytest

# ─── Unit tests: build_email_message ───

def test_build_email_message_basic():
    """Basic email content build: includes task name, status, time, duration"""
    from taskengine.notify_email import build_email_message

    task_result = {
        "success": False,
        "steps": [
            {"name": "prepare", "success": True},
            {"name": "process", "success": False, "exit_code": 1,
             "output": "Error: file not found", "duration": 5.2},
        ],
    }
    msg = build_email_message(
        task_name="daily_report",
        result=task_result,
        started_at="2026-05-03T14:00:00",
        finished_at="2026-05-03T14:00:12",
        duration=12.5,
    )
    assert "daily_report" in msg
    assert "Failed" in msg
    assert "prepare" in msg
    assert "process" in msg
    assert "12.5" in msg
    assert "Error: file not found" in msg


def test_build_email_message_success():
    """Successful task email: all steps succeeded"""
    from taskengine.notify_email import build_email_message

    task_result = {
        "success": True,
        "steps": [
            {"name": "sync", "success": True, "duration": 3.0},
        ],
    }
    msg = build_email_message(
        task_name="data_sync",
        result=task_result,
        started_at="2026-05-03T14:00:00",
        finished_at="2026-05-03T14:00:03",
        duration=3.0,
    )
    assert "data_sync" in msg
    assert "Succeeded" in msg
    assert "sync" in msg


def test_build_email_message_truncates_long_output():
    """Truncates failed step output to 500 characters when too long"""
    from taskengine.notify_email import build_email_message

    long_output = "x" * 2000
    task_result = {
        "success": False,
        "steps": [
            {"name": "big_task", "success": False, "exit_code": 1,
             "output": long_output, "duration": 1.0},
        ],
    }
    msg = build_email_message(
        task_name="big_task",
        result=task_result,
        started_at="2026-05-03T14:00:00",
        finished_at="2026-05-03T14:00:01",
        duration=1.0,
    )
    # Output is truncated, should not contain all 2000 x's
    assert msg.count("x") < 600


# ─── Unit tests: send_email ───

def test_send_email_smtp_without_ssl():
    """SMTP connection without SSL (default behavior)"""
    from taskengine.notify_email import send_email

    config = {
        "host": "smtp.example.com",
        "port": 587,
        "ssl": False,
        "from": "bot@example.com",
        "to": ["admin@example.com"],
    }
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_email(config, "Test Subject", "Test Body")

        mock_smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=10)
        mock_smtp.send_message.assert_called_once()


def test_send_email_smtp_with_ssl():
    """SMTP connection with SSL"""
    from taskengine.notify_email import send_email

    config = {
        "host": "smtp.example.com",
        "port": 465,
        "ssl": True,
        "from": "bot@example.com",
        "to": ["admin@example.com"],
    }
    with patch("smtplib.SMTP_SSL") as mock_smtp_ssl_cls:
        mock_smtp = MagicMock()
        mock_smtp_ssl_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_ssl_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_email(config, "Test Subject", "Test Body")

        mock_smtp_ssl_cls.assert_called_once_with("smtp.example.com", 465, timeout=10)
        mock_smtp.send_message.assert_called_once()


def test_send_email_with_auth():
    """SMTP with username/password authentication"""
    from taskengine.notify_email import send_email

    config = {
        "host": "smtp.example.com",
        "port": 587,
        "ssl": False,
        "username": "user@example.com",
        "password": "***",
        "from": "bot@example.com",
        "to": ["admin@example.com"],
    }
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_email(config, "Test Subject", "Test Body")

        mock_smtp.login.assert_called_once_with("user@example.com", "***")


def test_send_email_no_auth():
    """Without auth credentials, login is not called"""
    from taskengine.notify_email import send_email

    config = {
        "host": "smtp.example.com",
        "port": 25,
        "ssl": False,
        "from": "bot@example.com",
        "to": ["admin@example.com"],
    }
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_email(config, "Subject", "Body")

        mock_smtp.login.assert_not_called()


def test_send_email_multiple_recipients():
    """Multiple recipients"""
    from taskengine.notify_email import send_email

    config = {
        "host": "smtp.example.com",
        "port": 25,
        "ssl": False,
        "from": "bot@example.com",
        "to": ["a@example.com", "b@example.com"],
    }
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_email(config, "Subject", "Body")

        # Check the recipients in the email message
        call_args = mock_smtp.send_message.call_args
        sent_msg = call_args[0][0]
        assert "a@example.com" in sent_msg["To"]
        assert "b@example.com" in sent_msg["To"]


def test_send_email_smtp_error_returns_false():
    """Returns False on SMTP connection failure, without raising exceptions"""
    from taskengine.notify_email import send_email

    config = {
        "host": "bad.smtp.com",
        "port": 25,
        "ssl": False,
        "from": "bot@example.com",
        "to": ["admin@example.com"],
    }
    with patch("smtplib.SMTP", side_effect=smtplib.SMTPException("Connection refused")):
        result = send_email(config, "Subject", "Body")
        assert result is False


# ─── Unit tests: notify_email (full workflow) ───

def test_notify_email_skips_when_no_config():
    """Does nothing when email_notify_config is not provided"""
    from taskengine.notify_email import notify_email

    # Should return directly without error
    notify_email(None, "task", {"success": True}, "2026-01-01", "2026-01-01", 1.0)


def test_notify_email_skips_when_no_recipients():
    """Does not send email when 'to' field is missing"""
    from taskengine.notify_email import notify_email

    config = {"host": "smtp.example.com", "port": 25, "from": "bot@example.com"}
    with patch("taskengine.notify_email.send_email") as mock_send:
        notify_email(config, "task", {"success": True}, "2026-01-01", "2026-01-01", 1.0)
        mock_send.assert_not_called()


def test_notify_email_calls_send_on_failure():
    """Sends email when on=failure and task failed"""
    from taskengine.notify_email import notify_email

    config = {
        "host": "smtp.example.com",
        "port": 25,
        "from": "bot@example.com",
        "to": ["admin@example.com"],
        "on": "failure",
    }
    task_result = {
        "success": False,
        "steps": [
            {"name": "step1", "success": False, "exit_code": 1, "output": "err"},
        ],
    }
    with patch("taskengine.notify_email.send_email", return_value=True) as mock_send:
        notify_email(config, "my_task", task_result, "2026-01-01T00:00:00",
                     "2026-01-01T00:00:05", 5.0)
        mock_send.assert_called_once()
        # Check subject
        args = mock_send.call_args
        assert "my_task" in args[0][1]
        assert "Failed" in args[0][1]


def test_notify_email_skips_on_failure_when_task_succeeded():
    """Does not send when on=failure but task succeeded"""
    from taskengine.notify_email import notify_email

    config = {
        "host": "smtp.example.com", "port": 25,
        "from": "bot@example.com", "to": ["admin@example.com"],
        "on": "failure",
    }
    with patch("taskengine.notify_email.send_email") as mock_send:
        notify_email(config, "task", {"success": True, "steps": []},
                     "2026-01-01", "2026-01-01", 1.0)
        mock_send.assert_not_called()


def test_notify_email_sends_on_success():
    """Sends email when on=success and task succeeded"""
    from taskengine.notify_email import notify_email

    config = {
        "host": "smtp.example.com", "port": 25,
        "from": "bot@example.com", "to": ["admin@example.com"],
        "on": "success",
    }
    with patch("taskengine.notify_email.send_email", return_value=True) as mock_send:
        notify_email(config, "task", {"success": True, "steps": []},
                     "2026-01-01", "2026-01-01", 1.0)
        mock_send.assert_called_once()


def test_notify_email_sends_on_always():
    """Sends email on both success and failure when on=always"""
    from taskengine.notify_email import notify_email

    config = {
        "host": "smtp.example.com", "port": 25,
        "from": "bot@example.com", "to": ["admin@example.com"],
        "on": "always",
    }
    with patch("taskengine.notify_email.send_email", return_value=True) as mock_send:
        # Success
        notify_email(config, "task", {"success": True, "steps": []},
                     "2026-01-01", "2026-01-01", 1.0)
        # Failure
        notify_email(config, "task",
                     {"success": False, "steps": [{"name": "s1", "success": False}]},
                     "2026-01-01", "2026-01-01", 1.0)
        assert mock_send.call_count == 2


def test_notify_email_default_on_is_failure():
    """Defaults to 'failure' when 'on' field is not specified"""
    from taskengine.notify_email import notify_email

    config = {
        "host": "smtp.example.com", "port": 25,
        "from": "bot@example.com", "to": ["admin@example.com"],
    }
    # Should not send on success
    with patch("taskengine.notify_email.send_email") as mock_send:
        notify_email(config, "task", {"success": True, "steps": []},
                     "2026-01-01", "2026-01-01", 1.0)
        mock_send.assert_not_called()


# ─── CC (Carbon Copy) tests ───

def test_send_email_with_cc():
    """cc field sets the Cc email header; recipients include to + cc"""
    from taskengine.notify_email import send_email

    config = {
        "host": "smtp.example.com", "port": 25,
        "from": "bot@example.com",
        "to": ["admin@example.com"],
        "cc": ["ops@example.com", "dev@example.com"],
    }
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_email(config, "Subject", "Body")

        call_args = mock_smtp.send_message.call_args
        sent_msg = call_args[0][0]
        # To header contains primary recipients
        assert "admin@example.com" in sent_msg["To"]
        # Cc header contains both CC recipients
        cc_header = sent_msg["Cc"]
        assert "ops@example.com" in cc_header
        assert "dev@example.com" in cc_header


def test_send_email_cc_empty_list():
    """Does not set Cc header when cc is an empty list"""
    from taskengine.notify_email import send_email

    config = {
        "host": "smtp.example.com", "port": 25,
        "from": "bot@example.com",
        "to": ["admin@example.com"],
        "cc": [],
    }
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_email(config, "Subject", "Body")

        call_args = mock_smtp.send_message.call_args
        sent_msg = call_args[0][0]
        assert sent_msg.get("Cc") is None


def test_send_email_no_cc_field():
    """Does not set Cc header when cc field is absent (backward compatibility)"""
    from taskengine.notify_email import send_email

    config = {
        "host": "smtp.example.com", "port": 25,
        "from": "bot@example.com",
        "to": ["admin@example.com"],
    }
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_email(config, "Subject", "Body")

        call_args = mock_smtp.send_message.call_args
        sent_msg = call_args[0][0]
        assert sent_msg.get("Cc") is None


def test_send_email_to_and_cc_multiple():
    """Multiple To + multiple CC recipients: all email headers are correct"""
    from taskengine.notify_email import send_email

    config = {
        "host": "smtp.example.com", "port": 25,
        "from": "bot@example.com",
        "to": ["a@example.com", "b@example.com"],
        "cc": ["c@example.com", "d@example.com"],
    }
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_email(config, "Subject", "Body")

        call_args = mock_smtp.send_message.call_args
        sent_msg = call_args[0][0]
        assert "a@example.com" in sent_msg["To"]
        assert "b@example.com" in sent_msg["To"]
        assert "c@example.com" in sent_msg["Cc"]
        assert "d@example.com" in sent_msg["Cc"]
