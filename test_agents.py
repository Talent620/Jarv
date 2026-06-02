import unittest
import sys
import os

# Dodaj repo do PATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from orchestrator import Orchestrator

class TestAgents(unittest.TestCase):
    def test_orchestrator(self):
        orch = Orchestrator(None)
        res = orch.dispatch("test")
        self.assertEqual(res, "Przetworzono przez system agentów")

if __name__ == '__main__':
    unittest.main()
