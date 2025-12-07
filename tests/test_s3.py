"""Tests for S3 storage adapter."""

import pytest
from unittest.mock import patch, MagicMock
import os


class TestS3Adapter:
    """Test S3 adapter functions."""

    def test_get_download_url_no_client(self):
        """Test get_download_url returns placeholder when no client."""
        from src.api.storage import s3

        # Reset client
        s3._s3_client = None

        with patch.dict(os.environ, {}, clear=True):
            with patch('src.api.storage.s3.get_s3_client', return_value=None):
                url = s3.get_download_url("test/key")
                assert "test/key" in url
                assert "s3" in url

    def test_check_health_no_client(self):
        """Test check_health returns False when no client."""
        from src.api.storage import s3

        with patch('src.api.storage.s3.get_s3_client', return_value=None):
            result = s3.check_health()
            assert result is False

    def test_delete_object_no_client(self):
        """Test delete_object returns False when no client."""
        from src.api.storage import s3

        with patch('src.api.storage.s3.get_s3_client', return_value=None):
            result = s3.delete_object("test/key")
            assert result is False

    def test_upload_object_no_client_raises(self):
        """Test upload_object raises when no client."""
        from src.api.storage import s3

        with patch('src.api.storage.s3.get_s3_client', return_value=None):
            with pytest.raises(RuntimeError, match="not configured"):
                s3.upload_object("test/key", b"data")

    @patch('src.api.storage.s3.get_s3_client')
    def test_upload_object_success(self, mock_get_client):
        """Test successful upload."""
        from src.api.storage import s3

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        result = s3.upload_object("test/key", b"test data")

        assert result == "test/key"
        mock_client.put_object.assert_called_once()

    @patch('src.api.storage.s3.get_s3_client')
    def test_check_health_success(self, mock_get_client):
        """Test health check success."""
        from src.api.storage import s3

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        result = s3.check_health()

        assert result is True
        mock_client.head_bucket.assert_called_once()

    @patch('src.api.storage.s3.get_s3_client')
    def test_get_download_url_presigned(self, mock_get_client):
        """Test presigned URL generation."""
        from src.api.storage import s3

        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "https://presigned.url/test"
        mock_get_client.return_value = mock_client

        result = s3.get_download_url("test/key")

        assert result == "https://presigned.url/test"
        mock_client.generate_presigned_url.assert_called_once()

