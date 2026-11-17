"""src/auto_jobs.py: jobs = min(cores / cores_per_job, free memory / GB per job), at least 1."""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from auto_jobs import auto_jobs


class AutoJobs(unittest.TestCase):
    def test_cores_limit(self):
        self.assertEqual(auto_jobs(cores=16, mem_gb=64, cores_per_job=4, gb_per_job=2)[0], 4)

    def test_memory_limit(self):
        jobs, why = auto_jobs(cores=16, mem_gb=5, cores_per_job=4, gb_per_job=2)
        self.assertEqual(jobs, 2)
        self.assertIn('GB', why)

    def test_at_least_one(self):
        self.assertEqual(auto_jobs(cores=1, mem_gb=0.5, cores_per_job=4, gb_per_job=2)[0], 1)

    def test_unknown_memory_uses_cores_only(self):
        self.assertEqual(auto_jobs(cores=8, mem_gb=None, cores_per_job=4, gb_per_job=2)[0], 2)

    def test_default_runs_here(self):
        self.assertGreaterEqual(auto_jobs()[0], 1)


if __name__ == '__main__':
    unittest.main()
