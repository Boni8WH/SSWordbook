import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add the project directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, cleanup_caches, WORD_DATA_CACHE

class TestMemoryCleanup(unittest.TestCase):
    def setUp(self):
        # Initialize app context
        self.app_context = app.app_context()
        self.app_context.push()
        
    def tearDown(self):
        self.app_context.pop()

    def test_cleanup_caches_clears_word_cache(self):
        """Test that cleanup_caches clears the word data cache"""
        import app as app_module
        
        # 1. Add some dummy data to WORD_DATA_CACHE
        app_module.WORD_DATA_CACHE['dummy_file.csv'] = {'data': [], 'timestamp': 1234567890}
        self.assertIn('dummy_file.csv', app_module.WORD_DATA_CACHE)

        # 2. Call cleanup_caches
        cleanup_caches()
        
        # 3. Verify caches are cleared
        self.assertEqual(len(app_module.WORD_DATA_CACHE), 0, "WORD_DATA_CACHE should be empty")

if __name__ == '__main__':
    unittest.main()
