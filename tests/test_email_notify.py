"""notify_email 模块测试 — TDD 先写测试"""

import smtplib
from unittest.mock import patch, MagicMock
import pytest

# ─── 单元测试：build_email_message ───

def test_build_email_message_basic():
    """基本邮件内容构建：包含任务名、状态、时间、耗时"""
    from notify_email import build_email_message

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
    assert "失败" in msg
    assert "prepare" in msg
    assert "process" in msg
    assert "12.5" in msg
    assert "Error: file not found" in msg


def test_build_email_message_success():
    """成功任务邮件：所有步骤都成功"""
    from notify_email import build_email_message

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
    assert "成功" in msg
    assert "sync" in msg


def test_build_email_message_truncates_long_output():
    """失败步骤输出过长时截断到 500 字符"""
    from notify_email import build_email_message

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
    # 输出被截断，不包含完整的 2000 个 x
    assert msg.count("x") < 600


# ─── 单元测试：send_email ───

def test_send_email_smtp_without_ssl():
    """无 SSL 连接 SMTP（默认行为）"""
    from notify_email import send_email

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
    """SSL 连接 SMTP"""
    from notify_email import send_email

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
    """带用户名密码认证"""
    from notify_email import send_email

    config = {
        "host": "smtp.example.com",
        "port": 587,
        "ssl": False,
        "username": "user@example.com",
        "password": "secret",
        "from": "bot@example.com",
        "to": ["admin@example.com"],
    }
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_email(config, "Test Subject", "Test Body")

        mock_smtp.login.assert_called_once_with("user@example.com", "secret")


def test_send_email_no_auth():
    """无认证时不调用 login"""
    from notify_email import send_email

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
    """多个收件人"""
    from notify_email import send_email

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

        # 检查邮件对象的收件人
        call_args = mock_smtp.send_message.call_args
        sent_msg = call_args[0][0]
        assert "a@example.com" in sent_msg["To"]
        assert "b@example.com" in sent_msg["To"]


def test_send_email_smtp_error_returns_false():
    """SMTP 连接失败时返回 False，不抛异常"""
    from notify_email import send_email

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


# ─── 单元测试：notify_email（完整流程）───

def test_notify_email_skips_when_no_config():
    """无 email_notify_config 时不做任何事"""
    from notify_email import notify_email

    # 应该直接返回，不报错
    notify_email(None, "task", {"success": True}, "2026-01-01", "2026-01-01", 1.0)


def test_notify_email_skips_when_no_recipients():
    """没有 to 字段时不发邮件"""
    from notify_email import notify_email

    config = {"host": "smtp.example.com", "port": 25, "from": "bot@example.com"}
    with patch("notify_email.send_email") as mock_send:
        notify_email(config, "task", {"success": True}, "2026-01-01", "2026-01-01", 1.0)
        mock_send.assert_not_called()


def test_notify_email_calls_send_on_failure():
    """on=failure 且任务失败时发送邮件"""
    from notify_email import notify_email

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
    with patch("notify_email.send_email", return_value=True) as mock_send:
        notify_email(config, "my_task", task_result, "2026-01-01T00:00:00",
                     "2026-01-01T00:00:05", 5.0)
        mock_send.assert_called_once()
        # 检查 subject
        args = mock_send.call_args
        assert "my_task" in args[0][1]
        assert "失败" in args[0][1]


def test_notify_email_skips_on_failure_when_task_succeeded():
    """on=failure 但任务成功时不发送"""
    from notify_email import notify_email

    config = {
        "host": "smtp.example.com", "port": 25,
        "from": "bot@example.com", "to": ["admin@example.com"],
        "on": "failure",
    }
    with patch("notify_email.send_email") as mock_send:
        notify_email(config, "task", {"success": True, "steps": []},
                     "2026-01-01", "2026-01-01", 1.0)
        mock_send.assert_not_called()


def test_notify_email_sends_on_success():
    """on=success 且任务成功时发送"""
    from notify_email import notify_email

    config = {
        "host": "smtp.example.com", "port": 25,
        "from": "bot@example.com", "to": ["admin@example.com"],
        "on": "success",
    }
    with patch("notify_email.send_email", return_value=True) as mock_send:
        notify_email(config, "task", {"success": True, "steps": []},
                     "2026-01-01", "2026-01-01", 1.0)
        mock_send.assert_called_once()


def test_notify_email_sends_on_always():
    """on=always 时不论成败都发送"""
    from notify_email import notify_email

    config = {
        "host": "smtp.example.com", "port": 25,
        "from": "bot@example.com", "to": ["admin@example.com"],
        "on": "always",
    }
    with patch("notify_email.send_email", return_value=True) as mock_send:
        # 成功
        notify_email(config, "task", {"success": True, "steps": []},
                     "2026-01-01", "2026-01-01", 1.0)
        # 失败
        notify_email(config, "task",
                     {"success": False, "steps": [{"name": "s1", "success": False}]},
                     "2026-01-01", "2026-01-01", 1.0)
        assert mock_send.call_count == 2


def test_notify_email_default_on_is_failure():
    """不指定 on 字段时默认为 failure"""
    from notify_email import notify_email

    config = {
        "host": "smtp.example.com", "port": 25,
        "from": "bot@example.com", "to": ["admin@example.com"],
    }
    # 成功时不发送
    with patch("notify_email.send_email") as mock_send:
        notify_email(config, "task", {"success": True, "steps": []},
                     "2026-01-01", "2026-01-01", 1.0)
        mock_send.assert_not_called()


# ─── 抄送 (CC) 测试 ───

def test_send_email_with_cc():
    """cc 字段设置邮件头 Cc，收件人包含 to + cc"""
    from notify_email import send_email

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
        # To 头包含主送
        assert "admin@example.com" in sent_msg["To"]
        # Cc 头包含两个抄送人
        cc_header = sent_msg["Cc"]
        assert "ops@example.com" in cc_header
        assert "dev@example.com" in cc_header


def test_send_email_cc_empty_list():
    """cc 为空列表时不设置 Cc 头"""
    from notify_email import send_email

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
    """不设置 cc 字段时不设置 Cc 头（向后兼容）"""
    from notify_email import send_email

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
    """主送多人 + 抄送多人，邮件头都正确"""
    from notify_email import send_email

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
