# File: tests/test_openviking_client.py
import unittest
from unittest.mock import patch, Mock, MagicMock
import urllib.error
from openviking_client import is_http_server_alive, OpenVikingClient


class TestIsHttpServerAlive(unittest.TestCase):
    @patch('urllib.request.urlopen')
    def test_returns_true_on_successful_connection(self, mock_urlopen):
        # Arrange
        mock_response = Mock()
        mock_response.getcode.return_value = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Act
        result = is_http_server_alive()

        # Assert
        self.assertTrue(result)
        mock_urlopen.assert_called_once()

    @patch('urllib.request.urlopen')
    def test_returns_false_on_urlerror(self, mock_urlopen):
        # Arrange
        mock_urlopen.side_effect = urllib.error.URLError('Connection refused')

        # Act
        result = is_http_server_alive()

        # Assert
        self.assertFalse(result)
        mock_urlopen.assert_called_once()

    @patch('urllib.request.urlopen')
    def test_returns_false_on_timeout(self, mock_urlopen):
        # Arrange
        mock_urlopen.side_effect = urllib.error.URLError('timeout')

        # Act
        result = is_http_server_alive()

        # Assert
        self.assertFalse(result)
        mock_urlopen.assert_called_once()


class TestOpenVikingClientInit(unittest.TestCase):
    @patch("openviking_client.is_http_server_alive")
    @patch("openviking_client.SyncHTTPClient")
    @patch("openviking_client.SyncOpenViking")
    def test_init_with_http_server_alive(self, mock_sync_openviking, mock_sync_http_client, mock_is_http_alive):
        # Arrange
        mock_is_http_alive.return_value = True
        mock_http_instance = MagicMock()
        mock_sync_http_client.return_value = mock_http_instance

        # Act
        client = OpenVikingClient()

        # Assert
        self.assertTrue(client._is_http_client)
        self.assertEqual(client._client, mock_http_instance)
        mock_sync_http_client.assert_called_once()
        mock_sync_openviking.assert_not_called()

    @patch("openviking_client.is_http_server_alive")
    @patch("openviking_client.SyncHTTPClient")
    @patch("openviking_client.SyncOpenViking")
    def test_init_with_http_server_dead(self, mock_sync_openviking, mock_sync_http_client, mock_is_http_alive):
        # Arrange
        mock_is_http_alive.return_value = False
        mock_sync_instance = MagicMock()
        mock_sync_openviking.return_value = mock_sync_instance

        # Act
        client = OpenVikingClient()

        # Assert
        self.assertFalse(client._is_http_client)
        self.assertEqual(client._client, mock_sync_instance)
        mock_sync_openviking.assert_called_once()
        mock_sync_http_client.assert_not_called()


class TestOpenVikingClientAddResource(unittest.TestCase):
    def test_add_resource_http_mode_calls_without_build_index(self):
        mock_client = MagicMock()
        mock_client.add_resource.return_value = {"id": "mock_id"}
        
        # Instantiate in degraded mode (client=None) then inject mock client
        with patch("openviking_client._SYNC_OPENVIKING_AVAILABLE", False):
            client = OpenVikingClient()
        
        client._client = mock_client
        client._is_http_client = True
        
        result = client.add_resource("test_file.py")
        
        self.assertEqual(result, "mock_id")
        mock_client.add_resource.assert_called_once_with("test_file.py")

    def test_add_resource_native_mode_calls_with_build_index_false(self):
        mock_client = MagicMock()
        mock_client.add_resource.return_value = {"id": "mock_id"}
        
        # Instantiate in degraded mode then inject mock client
        with patch("openviking_client._SYNC_OPENVIKING_AVAILABLE", False):
            client = OpenVikingClient()
            
        client._client = mock_client
        client._is_http_client = False
        
        result = client.add_resource("test_file.py")
        
        self.assertEqual(result, "mock_id")
        mock_client.add_resource.assert_called_once_with("test_file.py", build_index=False)


if __name__ == '__main__':
    unittest.main()
