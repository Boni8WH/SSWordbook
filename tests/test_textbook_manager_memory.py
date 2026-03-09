
import unittest
import sys
import os
import gc

# Add app directory to path
sys.path.append('/Users/kitsukaasaki/Desktop/SSWordbook')

from app import TextbookManager, app

class TestTextbookManagerMemory(unittest.TestCase):
    def setUp(self):
        # Reset singleton if possible (though tough with locking, we'll try to get the instance)
        self.tm = TextbookManager.get_instance()
        # Ensure clean state
        self.tm.clear_memory()

    def test_lazy_loading_initial_state(self):
        """Verify that sections and toc are None initially (after clear)"""
        print("\nTesting Lazy Loading Initial State...")
        self.assertIsNone(self.tm.sections)
        self.assertIsNone(self.tm.toc)
        print("✅ Initial state is clean (None)")

    def test_load_on_demand_via_ensure(self):
        """Verify that _ensure_textbook_loaded loads data"""
        print("\nTesting _ensure_textbook_loaded...")
        self.tm._ensure_textbook_loaded()
        self.assertIsNotNone(self.tm.sections)
        self.assertIsNotNone(self.tm.toc)
        self.assertTrue(len(self.tm.toc) > 0)
        print(f"✅ Data loaded: {len(self.tm.toc)} sections")

    def test_clear_memory(self):
        """Verify that clear_memory releases data"""
        print("\nTesting clear_memory...")
        # Ensure loaded first
        self.tm._ensure_textbook_loaded()
        self.assertIsNotNone(self.tm.sections)
        
        # Clear
        self.tm.clear_memory()
        self.assertIsNone(self.tm.sections)
        self.assertIsNone(self.tm.toc)
        self.assertIsNone(self.tm.vectors)
        print("✅ Memory cleared successfully")

    def test_get_relevant_content_triggers_load(self):
        """Verify that get_relevant_content triggers loading"""
        print("\nTesting get_relevant_content triggers load...")
        self.tm.clear_memory()
        self.assertIsNone(self.tm.sections)
        
        # Call with dummy title
        # Note: We need to mock _load_textbook if we want to be pure, but integration test is fine here
        # We expect it to load data then return empty string if not found, or content if found
        # We just check if sections became not None
        self.tm.get_relevant_content(["NonExistentTitle"])
        self.assertIsNotNone(self.tm.sections)
        print("✅ get_relevant_content triggered load")

if __name__ == '__main__':
    unittest.main()
