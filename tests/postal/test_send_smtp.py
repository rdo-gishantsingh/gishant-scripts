"""Tests for SMTP email sending script."""

import smtplib
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from gishant_scripts.postal.send_smtp import SMTPError, send_email


class TestSendEmail:
    """Test send_email function."""

    @patch("gishant_scripts.postal.send_smtp.smtplib.SMTP")
    def test_send_basic_email(self, mock_smtp_class):
        """Test sending a basic email."""
        # Setup mocks
        mock_server = Mock()
        mock_smtp_class.return_value = mock_server

        # Call function
        result = send_email(
            smtp_host="localhost",
            smtp_port=25,
            from_email="sender@example.com",
            to_emails=["recipient@example.com"],
            subject="Test Subject",
            body="Test Body",
        )

        # Verify
        assert result["status"] == "success"
        mock_smtp_class.assert_called_once_with("localhost", 25)
        mock_server.starttls.assert_called_once()
        mock_server.sendmail.assert_called_once()
        mock_server.quit.assert_called_once()

    @patch("gishant_scripts.postal.send_smtp.smtplib.SMTP")
    def test_send_email_with_html(self, mock_smtp_class):
        """Test sending email with HTML body."""
        mock_server = Mock()
        mock_smtp_class.return_value = mock_server

        result = send_email(
            smtp_host="localhost",
            smtp_port=25,
            from_email="sender@example.com",
            to_emails=["recipient@example.com"],
            subject="Test Subject",
            body="Plain text",
            html_body="<p>HTML text</p>",
        )

        assert result["status"] == "success"
        mock_server.sendmail.assert_called_once()

    @patch("gishant_scripts.postal.send_smtp.smtplib.SMTP")
    def test_send_email_with_cc_bcc(self, mock_smtp_class):
        """Test sending email with CC and BCC."""
        mock_server = Mock()
        mock_smtp_class.return_value = mock_server

        result = send_email(
            smtp_host="localhost",
            smtp_port=25,
            from_email="sender@example.com",
            to_emails=["recipient@example.com"],
            subject="Test Subject",
            body="Test Body",
            cc_emails=["cc@example.com"],
            bcc_emails=["bcc@example.com"],
        )

        assert result["status"] == "success"
        # Verify all recipients are included
        call_args = mock_server.sendmail.call_args
        recipients = call_args[0][1]  # Second argument is recipients list
        assert "recipient@example.com" in recipients
        assert "cc@example.com" in recipients
        assert "bcc@example.com" in recipients

    @patch("gishant_scripts.postal.send_smtp.smtplib.SMTP")
    def test_send_email_with_attachments(self, mock_smtp_class, tmp_path):
        """Test sending email with attachments."""
        mock_server = Mock()
        mock_smtp_class.return_value = mock_server

        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        result = send_email(
            smtp_host="localhost",
            smtp_port=25,
            from_email="sender@example.com",
            to_emails=["recipient@example.com"],
            subject="Test Subject",
            body="Test Body",
            attachments=[test_file],
        )

        assert result["status"] == "success"
        mock_server.sendmail.assert_called_once()

    @patch("gishant_scripts.postal.send_smtp.smtplib.SMTP")
    def test_send_email_with_authentication(self, mock_smtp_class):
        """Test sending email with SMTP authentication."""
        mock_server = Mock()
        mock_smtp_class.return_value = mock_server

        result = send_email(
            smtp_host="localhost",
            smtp_port=25,
            from_email="sender@example.com",
            to_emails=["recipient@example.com"],
            subject="Test Subject",
            body="Test Body",
            username="user",
            password="pass",
        )

        assert result["status"] == "success"
        mock_server.login.assert_called_once_with("user", "pass")

    @patch("gishant_scripts.postal.send_smtp.smtplib.SMTP")
    def test_send_email_no_tls(self, mock_smtp_class):
        """Test sending email without TLS."""
        mock_server = Mock()
        mock_smtp_class.return_value = mock_server

        result = send_email(
            smtp_host="localhost",
            smtp_port=25,
            from_email="sender@example.com",
            to_emails=["recipient@example.com"],
            subject="Test Subject",
            body="Test Body",
            use_tls=False,
        )

        assert result["status"] == "success"
        mock_server.starttls.assert_not_called()

    @patch("gishant_scripts.postal.send_smtp.smtplib.SMTP")
    def test_send_email_with_reply_to(self, mock_smtp_class):
        """Test sending email with reply-to header."""
        mock_server = Mock()
        mock_smtp_class.return_value = mock_server

        result = send_email(
            smtp_host="localhost",
            smtp_port=25,
            from_email="sender@example.com",
            to_emails=["recipient@example.com"],
            subject="Test Subject",
            body="Test Body",
            reply_to="reply@example.com",
        )

        assert result["status"] == "success"
        mock_server.sendmail.assert_called_once()

    @patch("gishant_scripts.postal.send_smtp.smtplib.SMTP")
    def test_send_email_multiple_recipients(self, mock_smtp_class):
        """Test sending email to multiple recipients."""
        mock_server = Mock()
        mock_smtp_class.return_value = mock_server

        result = send_email(
            smtp_host="localhost",
            smtp_port=25,
            from_email="sender@example.com",
            to_emails=["recipient1@example.com", "recipient2@example.com"],
            subject="Test Subject",
            body="Test Body",
        )

        assert result["status"] == "success"
        call_args = mock_server.sendmail.call_args
        recipients = call_args[0][1]
        assert len(recipients) == 2
        assert "recipient1@example.com" in recipients
        assert "recipient2@example.com" in recipients

    @patch("gishant_scripts.postal.send_smtp.smtplib.SMTP")
    def test_send_email_attachment_not_found(self, mock_smtp_class):
        """Test sending email with non-existent attachment."""
        mock_server = Mock()
        mock_smtp_class.return_value = mock_server

        with pytest.raises(SMTPError, match="Attachment file not found"):
            send_email(
                smtp_host="localhost",
                smtp_port=25,
                from_email="sender@example.com",
                to_emails=["recipient@example.com"],
                subject="Test Subject",
                body="Test Body",
                attachments=[Path("/nonexistent/file.txt")],
            )

    @patch("gishant_scripts.postal.send_smtp.smtplib.SMTP")
    def test_send_email_smtp_error(self, mock_smtp_class):
        """Test handling SMTP errors."""
        mock_server = Mock()
        mock_server.sendmail.side_effect = smtplib.SMTPException("SMTP error occurred")
        mock_smtp_class.return_value = mock_server

        with pytest.raises(SMTPError, match="SMTP error"):
            send_email(
                smtp_host="localhost",
                smtp_port=25,
                from_email="sender@example.com",
                to_emails=["recipient@example.com"],
                subject="Test Subject",
                body="Test Body",
            )

    @patch("gishant_scripts.postal.send_smtp.smtplib.SMTP")
    def test_send_email_connection_error(self, mock_smtp_class):
        """Test handling connection errors."""
        mock_smtp_class.side_effect = ConnectionError("Connection failed")

        with pytest.raises(SMTPError, match="Failed to send email"):
            send_email(
                smtp_host="localhost",
                smtp_port=25,
                from_email="sender@example.com",
                to_emails=["recipient@example.com"],
                subject="Test Subject",
                body="Test Body",
            )

    @patch("gishant_scripts.postal.send_smtp.smtplib.SMTP")
    def test_send_email_auth_error(self, mock_smtp_class):
        """Test handling authentication errors."""
        mock_server = Mock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, "Authentication failed")
        mock_smtp_class.return_value = mock_server

        with pytest.raises(SMTPError, match="SMTP error"):
            send_email(
                smtp_host="localhost",
                smtp_port=25,
                from_email="sender@example.com",
                to_emails=["recipient@example.com"],
                subject="Test Subject",
                body="Test Body",
                username="user",
                password="wrong",
            )
