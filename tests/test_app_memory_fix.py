import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add the project directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, cleanup_caches, _kks_instance, WORD_DATA_CACHE, get_kks

class TestMemoryCleanup(unittest.TestCase):
    def setUp(self):
        # Initialize app context
        self.app_context = app.app_context()
        self.app_context.push()
        
    def tearDown(self):
        self.app_context.pop()

    def test_cleanup_caches_clears_pykakasi(self):
        """Test that cleanup_caches clears the pykakasi instance"""
        # 1. Initialize pykakasi
        kks = get_kks()
        self.assertIsNotNone(kks, "pykakasi should be initialized")
        
        # Access the global variable directly to verify it's set
        import app as app_module
        self.assertIsNotNone(app_module._kks_instance, "_kks_instance global should be set")

        # 2. Add some dummy data to WORD_DATA_CACHE to verify it gets cleared too
        app_module.WORD_DATA_CACHE['dummy_file.csv'] = {'data': [], 'timestamp': 1234567890}
        self.assertIn('dummy_file.csv', app_module.WORD_DATA_CACHE)

        # 3. Call cleanup_caches
        cleanup_caches()
        
        # 4. Verify _kks_instance is None
        self.assertIsNone(app_module._kks_instance, "_kks_instance should be None after cleanup")
        
        # 5. Verify caches are cleared
        self.assertEqual(len(app_module.WORD_DATA_CACHE), 0, "WORD_DATA_CACHE should be empty")

    def test_pykakasi_reinitializes_after_cleanup(self):
        """Test that pykakasi can be re-initialized after cleanup"""
        # 1. Cleanup first to ensure clean state
        cleanup_caches()
        
        import app as app_module
        self.assertIsNone(app_module._kks_instance)

        # 2. Call get_kks() again
        kks = get_kks()
        
        # 3. Verify it's initialized again
        self.assertIsNotNone(kks, "pykakasi should be re-initialized")
        self.assertIsNotNone(app_module._kks_instance)

if __name__ == '__main__':
    unittest.main()
