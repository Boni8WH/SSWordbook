import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import json

# Add the project directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, cleanup_caches, _kks_instance, WORD_DATA_CACHE, get_kks

class TestAggressiveCleanup(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()
        
    def tearDown(self):
        self.app_context.pop()

    @patch('ctypes.CDLL')
    def test_cleanup_calls_malloc_trim(self, mock_cdll):
        """Test that cleanup_caches attempts to call malloc_trim"""
        # Mock libc instance
        mock_libc = MagicMock()
        mock_cdll.return_value = mock_libc
        
        # Trigger cleanup
        cleanup_caches()
        
        # Verify malloc_trim was called with 0
        mock_libc.malloc_trim.assert_called_with(0)

    def test_debug_endpoint_requires_auth(self):
        """Test that /api/debug/cleanup requires login"""
        response = self.app.get('/api/debug/cleanup')
        self.assertEqual(response.status_code, 401)

    def test_debug_endpoint_execution(self):
        """Test that /api/debug/cleanup runs when authenticated"""
        with self.app.session_transaction() as sess:
            sess['user_id'] = 1  # Simulate login
            
        # Patch cleanup_caches to avoid actual cleanup during this specific test (optional, but good for isolation)
        with patch('app.cleanup_caches') as mock_cleanup:
            response = self.app.get('/api/debug/cleanup')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'success')
            self.assertIn('freed_mb', data)
            mock_cleanup.assert_called_once()

if __name__ == '__main__':
    unittest.main()
