import unittest
from src.main import main

class TestMain(unittest.TestCase):
    def test_main(self):
        with self.assertLogs(level='INFO') as caplog:
            main()
        self.assertIn('Ciao, questo è il programma principale!', caplog.output)

if __name__ == "__main__":
    unittest.main()

# Ensure the test directory is importable
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
