"""Tests for API email sending script."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from gishant_scripts.postal.send_api import APIError, send_email_via_api


class TestSendEmailViaAPI:
    """Test send_email_via_api function."""

    @patch("gishant_scripts.postal.send_api.requests.post")
    def test_send_basic_email(self, mock_post):
        """Test sending a basic email."""
        # Setup mock response
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "message_id": "123",
                "messages": {
                    "recipient@example.com": {"id": 456, "token": "abc123"},
                },
            },
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        # Call function
        result = send_email_via_api(
            api_url="https://postal.example.com",
            api_key="test-api-key",
            from_email="sender@example.com",
            to_emails=["recipient@example.com"],
            subject="Test Subject",
            plain_body="Test Body",
        )

        # Verify
        assert result["status"] == "success"
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://postal.example.com/api/v1/messages/send"
        assert call_args[1]["headers"]["X-Server-API-Key"] == "test-api-key"
        assert call_args[1]["json"]["to"] == "recipient@example.com"
        assert call_args[1]["json"]["from"] == "sender@example.com"
        assert call_args[1]["json"]["subject"] == "Test Subject"

    @patch("gishant_scripts.postal.send_api.requests.post")
    def test_send_email_with_html(self, mock_post):
        """Test sending email with HTML body."""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "success", "data": {"message_id": "123", "messages": {}}}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = send_email_via_api(
            api_url="https://postal.example.com",
            api_key="test-api-key",
            from_email="sender@example.com",
            to_emails=["recipient@example.com"],
            subject="Test Subject",
            plain_body="Plain text",
            html_body="<p>HTML text</p>",
        )

        assert result["status"] == "success"
        call_args = mock_post.call_args
        assert call_args[1]["json"]["html_body"] == "<p>HTML text</p>"

    @patch("gishant_scripts.postal.send_api.requests.post")
    def test_send_email_with_cc_bcc(self, mock_post):
        """Test sending email with CC and BCC."""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "success", "data": {"message_id": "123", "messages": {}}}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = send_email_via_api(
            api_url="https://postal.example.com",
            api_key="test-api-key",
            from_email="sender@example.com",
            to_emails=["recipient@example.com"],
            subject="Test Subject",
            plain_body="Test Body",
            cc_emails=["cc@example.com"],
            bcc_emails=["bcc@example.com"],
        )

        assert result["status"] == "success"
        call_args = mock_post.call_args
        assert call_args[1]["json"]["cc"] == "cc@example.com"
        assert call_args[1]["json"]["bcc"] == "bcc@example.com"

    @patch("gishant_scripts.postal.send_api.requests.post")
    def test_send_email_with_attachments(self, mock_post, tmp_path):
        """Test sending email with attachments."""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "success", "data": {"message_id": "123", "messages": {}}}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        result = send_email_via_api(
            api_url="https://postal.example.com",
            api_key="test-api-key",
            from_email="sender@example.com",
            to_emails=["recipient@example.com"],
            subject="Test Subject",
            plain_body="Test Body",
            attachments=[test_file],
        )

        assert result["status"] == "success"
        call_args = mock_post.call_args
        attachments = call_args[1]["json"]["attachments"]
        assert len(attachments) == 1
        assert attachments[0]["name"] == "test.txt"
        assert attachments[0]["content_type"] == "text/plain"
        assert "data" in attachments[0]  # Base64 encoded

    @patch("gishant_scripts.postal.send_api.requests.post")
    def test_send_email_with_custom_headers(self, mock_post):
        """Test sending email with custom headers."""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "success", "data": {"message_id": "123", "messages": {}}}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = send_email_via_api(
            api_url="https://postal.example.com",
            api_key="test-api-key",
            from_email="sender@example.com",
            to_emails=["recipient@example.com"],
            subject="Test Subject",
            plain_body="Test Body",
            headers={"X-Custom-Header": "CustomValue"},
        )

        assert result["status"] == "success"
        call_args = mock_post.call_args
        assert call_args[1]["json"]["headers"]["X-Custom-Header"] == "CustomValue"

    @patch("gishant_scripts.postal.send_api.requests.post")
    def test_send_email_multiple_recipients(self, mock_post):
        """Test sending email to multiple recipients."""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "success", "data": {"message_id": "123", "messages": {}}}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = send_email_via_api(
            api_url="https://postal.example.com",
            api_key="test-api-key",
            from_email="sender@example.com",
            to_emails=["recipient1@example.com", "recipient2@example.com"],
            subject="Test Subject",
            plain_body="Test Body",
        )

        assert result["status"] == "success"
        call_args = mock_post.call_args
        assert call_args[1]["json"]["to"] == ["recipient1@example.com", "recipient2@example.com"]

    @patch("gishant_scripts.postal.send_api.requests.post")
    def test_send_email_with_reply_to(self, mock_post):
        """Test sending email with reply-to."""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "success", "data": {"message_id": "123", "messages": {}}}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = send_email_via_api(
            api_url="https://postal.example.com",
            api_key="test-api-key",
            from_email="sender@example.com",
            to_emails=["recipient@example.com"],
            subject="Test Subject",
            plain_body="Test Body",
            reply_to="reply@example.com",
        )

        assert result["status"] == "success"
        call_args = mock_post.call_args
        assert call_args[1]["json"]["reply_to"] == "reply@example.com"

    @patch("gishant_scripts.postal.send_api.requests.post")
    def test_send_email_attachment_not_found(self, mock_post):
        """Test sending email with non-existent attachment."""
        with pytest.raises(APIError, match="Attachment file not found"):
            send_email_via_api(
                api_url="https://postal.example.com",
                api_key="test-api-key",
                from_email="sender@example.com",
                to_emails=["recipient@example.com"],
                subject="Test Subject",
                plain_body="Test Body",
                attachments=[Path("/nonexistent/file.txt")],
            )

    @patch("gishant_scripts.postal.send_api.requests.post")
    def test_send_email_api_error_response(self, mock_post):
        """Test handling API error responses."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "error",
            "data": {"message": "Invalid API key"},
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        with pytest.raises(APIError, match="API returned error"):
            send_email_via_api(
                api_url="https://postal.example.com",
                api_key="invalid-key",
                from_email="sender@example.com",
                to_emails=["recipient@example.com"],
                subject="Test Subject",
                plain_body="Test Body",
            )

    @patch("gishant_scripts.postal.send_api.requests.post")
    def test_send_email_http_error(self, mock_post):
        """Test handling HTTP errors."""
        mock_post.side_effect = requests.exceptions.HTTPError("404 Not Found")

        with pytest.raises(APIError, match="HTTP request failed"):
            send_email_via_api(
                api_url="https://postal.example.com",
                api_key="test-api-key",
                from_email="sender@example.com",
                to_emails=["recipient@example.com"],
                subject="Test Subject",
                plain_body="Test Body",
            )

    @patch("gishant_scripts.postal.send_api.requests.post")
    def test_send_email_connection_error(self, mock_post):
        """Test handling connection errors."""
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")

        with pytest.raises(APIError, match="HTTP request failed"):
            send_email_via_api(
                api_url="https://postal.example.com",
                api_key="test-api-key",
                from_email="sender@example.com",
                to_emails=["recipient@example.com"],
                subject="Test Subject",
                plain_body="Test Body",
            )

    @patch("gishant_scripts.postal.send_api.requests.post")
    def test_send_email_invalid_json(self, mock_post):
        """Test handling invalid JSON responses."""
        mock_response = Mock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        with pytest.raises(APIError, match="Invalid JSON response"):
            send_email_via_api(
                api_url="https://postal.example.com",
                api_key="test-api-key",
                from_email="sender@example.com",
                to_emails=["recipient@example.com"],
                subject="Test Subject",
                plain_body="Test Body",
            )

    @patch("gishant_scripts.postal.send_api.requests.post")
    def test_send_email_url_trailing_slash(self, mock_post):
        """Test that URL trailing slashes are handled correctly."""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "success", "data": {"message_id": "123", "messages": {}}}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        send_email_via_api(
            api_url="https://postal.example.com/",
            api_key="test-api-key",
            from_email="sender@example.com",
            to_emails=["recipient@example.com"],
            subject="Test Subject",
            plain_body="Test Body",
        )

        call_args = mock_post.call_args
        # Should not have double slashes
        assert call_args[0][0] == "https://postal.example.com/api/v1/messages/send"

    @patch("gishant_scripts.postal.send_api.requests.post")
    def test_send_email_content_type_detection(self, mock_post, tmp_path):
        """Test content type detection for different file types."""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "success", "data": {"message_id": "123", "messages": {}}}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        # Test different file types
        test_files = {
            "test.txt": "text/plain",
            "test.html": "text/html",
            "test.pdf": "application/pdf",
            "test.jpg": "image/jpeg",
            "test.png": "image/png",
            "test.json": "application/json",
        }

        for filename, expected_type in test_files.items():
            test_file = tmp_path / filename
            test_file.write_text("test content")

            send_email_via_api(
                api_url="https://postal.example.com",
                api_key="test-api-key",
                from_email="sender@example.com",
                to_emails=["recipient@example.com"],
                subject="Test Subject",
                plain_body="Test Body",
                attachments=[test_file],
            )

            call_args = mock_post.call_args
            attachments = call_args[1]["json"]["attachments"]
            assert attachments[0]["content_type"] == expected_type
