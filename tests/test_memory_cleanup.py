
import unittest
from unittest.mock import MagicMock, patch
import sys
import gc

# Add app directory to path
sys.path.append('/Users/kitsukaasaki/Desktop/SSWordbook')

from app import app, cleanup_caches, MEMORY_THRESHOLD_MB, ROOM_SETTING_CACHE, WORD_DATA_CACHE, TextbookManager, check_memory_and_cleanup

class TestMemoryCleanup(unittest.TestCase):
    def setUp(self):
        # Populate caches with dummy data
        ROOM_SETTING_CACHE['test'] = {'data': 'dummy'}
        WORD_DATA_CACHE['test.csv'] = {'data': 'dummy'}
        
        # Ensure TextbookManager has data (mocking load)
        tm = TextbookManager.get_instance()
        tm.sections = {'Title': 'Content'}
        tm.toc = ['Title']

    def test_cleanup_function_clears_caches(self):
        """Verify cleanup_caches() clears all target caches"""
        print("\nTesting cleanup_caches function...")
        
        # Verify data exists before cleanup
        self.assertTrue(len(ROOM_SETTING_CACHE) > 0)
        self.assertTrue(len(WORD_DATA_CACHE) > 0)
        tm = TextbookManager.get_instance()
        self.assertIsNotNone(tm.sections)

        # Run cleanup
        cleanup_caches()

        # Verify data is gone
        self.assertEqual(len(ROOM_SETTING_CACHE), 0)
        self.assertEqual(len(WORD_DATA_CACHE), 0)
        self.assertIsNone(tm.sections)
        print("✅ All caches cleared successfully")

    @patch('psutil.Process')
    def test_before_request_trigger(self, mock_process_cls):
        """Verify high memory triggers cleanup in before_request"""
        print("\nTesting before_request memory check...")
        
        # Mock process.memory_info().rss to return (THRESHOLD + 100) MB
        # rss is in bytes
        high_memory_bytes = (MEMORY_THRESHOLD_MB + 100) * 1024 * 1024
        
        mock_process = MagicMock()
        mock_process.memory_info.return_value.rss = high_memory_bytes
        mock_process_cls.return_value = mock_process

        # Re-populate cache for this test
        ROOM_SETTING_CACHE['test'] = {'data': 'dummy'}

        # Manually trigger the before_request function
        # Note: We need to import the function reference from app, but since it's decorated, 
        # it's registered in app.before_request_funcs.
        # However, we defined it as 'check_memory_and_cleanup' in global scope of app.py.
        # Let's import it dynamically or reuse the one from 'from app import ...' if available.
        # But 'from app import check_memory_and_cleanup' might fail if it wasn't exported.
        # It's better to simulate a request or call the function if we can access it.
        

        with app.test_request_context('/'):
            check_memory_and_cleanup()
            
        # Verify cleanup happened
        self.assertEqual(len(ROOM_SETTING_CACHE), 0)
        print("✅ Cleanup triggered by high memory simulation")

    @patch('psutil.Process')
    def test_before_request_no_trigger(self, mock_process_cls):
        """Verify low memory does NOT trigger cleanup"""
        print("\nTesting before_request low memory ignore...")
        
        # Mock process.memory_info().rss to return (THRESHOLD - 100) MB
        low_memory_bytes = (MEMORY_THRESHOLD_MB - 100) * 1024 * 1024
        
        mock_process = MagicMock()
        mock_process.memory_info.return_value.rss = low_memory_bytes
        mock_process_cls.return_value = mock_process

        # Re-populate cache
        ROOM_SETTING_CACHE['test'] = {'data': 'dummy'}


        with app.test_request_context('/'):
            check_memory_and_cleanup()
            
        # Verify cleanup did NOT happen
        self.assertEqual(len(ROOM_SETTING_CACHE), 1)
        print("✅ Low memory ignored (no cleanup)")

if __name__ == '__main__':
    unittest.main()
