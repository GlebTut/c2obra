#!/usr/bin/env python3
"""How many tasks/files to run at the same time on this machine ("--jobs auto").

jobs = min(cores // CORES_PER_JOB, available memory // GB_PER_JOB), at least 1.
Both constants are a cautious guess, NOT measured peak values: change them with the
C2OBRA_CORES_PER_JOB and C2OBRA_GB_PER_JOB environment variables (or the function arguments).
Prints one number, so a shell can use it:  C2OBRA_JOBS=$(python3 src/auto_jobs.py)
"""
import os
import sys

CORES_PER_JOB = 4       # Sikraken + compiler + the test threads of one task
GB_PER_JOB = 2.0        # large inputs (tens of MB) need more; lower the job count if memory runs out


def available_gb():
    """MemAvailable from /proc/meminfo in GB, or None where that file does not exist."""
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1]) / (1024 * 1024)
    except OSError:
        pass
    return None


def auto_jobs(cores=None, mem_gb='detect', cores_per_job=None, gb_per_job=None):
    """(jobs, reason). mem_gb None = unknown, only the cores count."""
    cores = cores or os.cpu_count() or 1
    cores_per_job = cores_per_job or float(os.environ.get('C2OBRA_CORES_PER_JOB') or CORES_PER_JOB)
    gb_per_job = gb_per_job or float(os.environ.get('C2OBRA_GB_PER_JOB') or GB_PER_JOB)
    if mem_gb == 'detect':
        mem_gb = available_gb()
    by_cores = max(1, int(cores // cores_per_job))
    jobs, limit = by_cores, f'{cores} cores / {cores_per_job:g} per job'
    if mem_gb is not None:
        by_mem = max(1, int(mem_gb // gb_per_job))
        if by_mem < by_cores:
            jobs, limit = by_mem, f'{mem_gb:.1f} GB free / {gb_per_job:g} GB per job'
    return jobs, f'{limit} -> {jobs}'


if __name__ == '__main__':
    print(auto_jobs()[0])
    print(auto_jobs()[1], file=sys.stderr)
