#!/usr/bin/env python3
"""Resumable batch driver: run C²oBra (with Sikraken tests) on the tasks of sample.csv.

One task: prepare -> sikraken -> c2obra.sh (instrument, compile, run, report) -> result.json.
Statuses, stages and timeouts are in batch/stages.py and docs/mass_test.md.

  New run:   batch/mass_test.sh --name pilot --pilot 20
  Resume:    batch/mass_test.sh --run-dir ~/benchmarks/runs/2026-10-21_pilot
  Re-run:    batch/mass_test.sh --run-dir ... --retry-status sikraken_timeout,run_crash

Each task directory gets result.json last, written atomically; a directory without it is an
interrupted attempt and is moved to _incomplete/ on the next run. results.csv and summary.txt
are rebuilt from all result.json files after every task (atomic replace), so a Ctrl-C or a
killed WSL never leaves half a row. Coverage numbers come from merge_reports.compute_stats(),
which calls edges.edge_coverage().
"""
import argparse
import datetime
import glob
import hashlib
import io
import csv
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, 'src'))
import stages as S          # noqa: E402
import merge_reports as M   # noqa: E402  (load_branch_map, load_coverage, compute_stats)

SIK_PREFIX = 'c2b__'        # sikraken_output/<prefix><task id>: directories this driver owns
DM_FLAG = {'ILP32': '-m32', 'LP64': '-m64'}
TAR_SUITE_OVER = 200        # test-suite/ with more files than this is kept as test-suite.tar.gz


# ─── Processes ───────────────────────────────────────────────────────────────

MARK_LINE = re.compile(r'^(=== |✅ Done|❌ )')       # c2obra.sh step markers, get a timestamp


def stamp(t0):
    """'[HH:MM:SS.mmm +12.345s] ': wall clock and seconds since t0 (time.monotonic())."""
    now = datetime.datetime.now()
    return f"[{now:%H:%M:%S}.{now.microsecond // 1000:03d} +{time.monotonic() - t0:.3f}s] "


def run_proc(cmd, cwd, env, timeout, log, t0):
    """Run cmd in its own process group. (exit code, timed out, output, seconds, marks).

    Output is read line by line as it arrives: lines that start a c2obra.sh step get a
    timestamp in log.txt, and marks = [(stage, monotonic time)] for stages.step_seconds().
    The returned output text is unchanged (it is what stages.classify_*() parse).
    On timeout (or Ctrl-C) the whole group gets SIGTERM, then SIGKILL after 5 s: this reaches
    ECLiPSe under prlimit/bash -lc and the test binaries run_tests.py starts."""
    start = time.monotonic()
    log.write(f"{stamp(t0)}$ {' '.join(cmd)}   (cwd {cwd}, timeout {timeout:.0f} s)\n")
    log.flush()
    p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         start_new_session=True)
    chunks, marks = [], []
    names = dict(S.STAGE_MARKERS)

    def reader():
        for raw in iter(p.stdout.readline, b''):
            line = raw.decode('utf-8', errors='replace')
            chunks.append(line)
            for marker, name in names.items():
                if line.startswith(marker):
                    marks.append((name, time.monotonic()))
            log.write((stamp(t0) if MARK_LINE.match(line) else '') + line)
        p.stdout.close()

    th = threading.Thread(target=reader, daemon=True)
    th.start()
    timed_out = False
    try:
        p.wait(timeout=max(1, timeout))
    except subprocess.TimeoutExpired:
        timed_out = True
        kill_group(p, log)
    except BaseException:                       # Ctrl-C / SIGTERM: do not leave the group running
        kill_group(p, log)
        raise
    th.join(timeout=10)
    end = time.monotonic()
    if timed_out:
        log.write(f"\n{stamp(t0)}[driver] TIMEOUT after {timeout:.0f} s: process group killed\n")
    log.write(f"{stamp(t0)}[driver] exit {p.returncode} after {end - start:.1f} s\n")
    log.flush()
    return p.returncode, timed_out, ''.join(chunks), end - start, marks + [('_end', end)]


def kill_group(p, log):
    for sig, wait in ((signal.SIGTERM, 5), (signal.SIGKILL, 5)):
        try:
            os.killpg(p.pid, sig)
        except ProcessLookupError:
            break
        try:
            p.wait(timeout=wait)
            break
        except subprocess.TimeoutExpired:
            continue
    try:
        os.killpg(p.pid, 0)
        log.write(f"[driver] WARNING: process group {p.pid} still has members after SIGKILL\n")
    except ProcessLookupError:
        pass


# ─── One task ────────────────────────────────────────────────────────────────

def read_text(path):
    with open(path, 'rb') as f:
        return f.read().decode('utf-8', errors='surrogateescape')


def write_text(path, text):
    with open(path, 'wb') as f:
        f.write(text.encode('utf-8', errors='surrogateescape'))


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


class Task:
    def __init__(self, cfg, row):
        self.cfg, self.row = cfg, row
        self.dir = os.path.join(cfg.tasks_dir, row['id'])
        self.src_dir = os.path.join(self.dir, 'src')
        self.out_dir = os.path.join(self.dir, 'out')
        self.sik_name = SIK_PREFIX + row['id']
        self.sik_out = os.path.join(cfg.sikraken_dir, 'sikraken_output', self.sik_name)
        self.t0 = time.monotonic()
        self.r = {k: row.get(k, '') for k in ('id', 'category', 'yml_path', 'input_file', 'extension', 'data_model')}
        self.r.update(cleaned_markers=0, nondet=None, status=None, stage='prepare', sikraken_tests=None, decisions=None,
                      skipped_macro=None, edges_covered=None, edges_total=None, pct=None, sikraken_exit=None,
                      c2obra_exit=None, seconds_sikraken=None, seconds_c2obra=None,
                      log=os.path.relpath(os.path.join(self.dir, 'log.txt'), cfg.run_dir),
                      detail={'notes': S.notes_for(row)} if S.notes_for(row) else {})

    def left(self):
        return self.cfg.task_timeout - (time.monotonic() - self.t0)

    def fail(self, status, stage, detail=None):
        if self.r['status'] is None:
            self.r['status'], self.r['stage'] = status, stage
            self.r['detail'].update(detail or {})

    def run(self):
        os.makedirs(self.dir)
        with open(os.path.join(self.dir, 'log.txt'), 'w') as log:
            self.log = log
            log.write(f"{stamp(self.t0)}[driver] task {self.row['id']}  {self.row['yml_path']}\n")
            try:
                self._run()
            finally:
                self.r['seconds'] = round(time.monotonic() - self.t0, 2)
        S.atomic_write(os.path.join(self.dir, 'result.json'), json.dumps(self.r, indent=1, sort_keys=True))
        return self.r

    def _run(self):
        cfg, row = self.cfg, self.row
        src_in = os.path.join(cfg.sv_root, row['input_file'])
        if not os.path.isfile(src_in):
            return self.fail('input_missing', 'prepare', {'path': src_in})

        # prepare: copy (cleaning gcc line markers if line 1 is one) + same-directory headers
        self.log.write(f"{stamp(self.t0)}[driver] === prepare ===\n")
        os.makedirs(self.src_dir)
        text = read_text(src_in)
        text, n = S.strip_line_markers(text)
        self.src = os.path.join(self.src_dir, self.sik_name + row['extension'])
        write_text(self.src, text)
        self.r['cleaned_markers'] = 1 if n else 0
        self.r['detail']['input_sha256'] = sha256(src_in)
        if n:
            self.r['detail']['marker_lines_blanked'] = n
        headers = sorted(glob.glob(os.path.join(os.path.dirname(src_in), '*.h')))
        for h in headers:
            shutil.copy(h, self.src_dir)
        if headers:
            self.r['detail']['headers_copied'] = len(headers)
        nondet = S.uses_nondet(text)
        self.r['nondet'] = nondet

        # sikraken
        suite = '-'
        if nondet:
            suite = self.sikraken()
        # c2obra.sh: instrument, compile, run, report (also after a Sikraken failure, with no
        # inputs, to learn whether C²oBra itself works on the file; the status stays Sikraken's)
        self.c2obra(suite, nondet)

    def sikraken(self):
        cfg, row = self.cfg, self.row
        self.log.write(f"{stamp(self.t0)}[driver] === sikraken ===\n")
        self.r['stage'] = 'sikraken'
        shutil.rmtree(self.sik_out, ignore_errors=True)
        rel = os.path.relpath(self.src, cfg.sikraken_dir)
        cmd = ['./bin/sikraken.sh', 'release', f'budget[{cfg.budget}]', DM_FLAG[row['data_model']], rel]
        code, timed_out, out, secs, _ = run_proc(cmd, cfg.sikraken_dir, os.environ.copy(),
                                                 min(cfg.sikraken_timeout, self.left()), self.log, self.t0)
        self.r['sikraken_exit'], self.r['seconds_sikraken'] = code, round(secs, 2)
        suite_src = os.path.join(self.sik_out, 'test-suite')
        n_tests = len(glob.glob(os.path.join(suite_src, 'test_input-*.xml'))) if os.path.isdir(suite_src) else None
        self.r['sikraken_tests'] = n_tests
        status, detail = S.classify_sikraken(code, timed_out, out, n_tests)
        suite = '-'
        if status:
            self.fail(status, 'sikraken', detail)
        else:
            suite = os.path.join(self.dir, 'test-suite')
            shutil.copytree(suite_src, suite)
        shutil.rmtree(self.sik_out, ignore_errors=True)
        return suite

    def c2obra(self, suite, nondet):
        cfg, row = self.cfg, self.row
        self.log.write(f"{stamp(self.t0)}[driver] === c2obra.sh ===\n")
        if self.r['status'] is None:
            self.r['stage'] = 'instrument'
        if self.left() <= 1:
            return self.fail('tool_timeout', 'instrument', {'error': 'task time used up before c2obra.sh'})
        env = os.environ.copy()
        for k in ('CFLAGS', 'VIRTUAL_ENV'):
            env.pop(k, None)
        # -I src/: c2obra.sh compiles the instrumented copy in OUT_DIR, so a local #include "x.h"
        # of the input is not found next to it; the headers were copied to src/ in prepare.
        env.update(OUT_DIR=self.out_dir, DATA_MODEL=row['data_model'], SIKRAKEN_SUITE=suite, LDLIBS='-lm',
                   SIKRAKEN_DIR=cfg.sikraken_dir, CFLAGS=f'-DLARGE_INT=1000000 -I{self.src_dir}')
        code, timed_out, out, secs, marks = run_proc(['bash', os.path.join(REPO, 'c2obra.sh'), self.src], REPO,
                                                     env, min(cfg.c2obra_timeout, self.left()), self.log, self.t0)
        self.r['c2obra_exit'], self.r['seconds_c2obra'] = code, round(secs, 2)
        steps = S.step_seconds(marks[:-1], marks[-1][1]) if len(marks) > 1 else {}
        steps.pop('done', None)
        self.r['detail']['step_seconds'] = steps
        signals, timeouts = S.run_signals(out)
        if signals:
            self.r['detail']['run_signals'] = signals
        if timeouts:
            self.r['detail']['run_timeouts'] = timeouts
        m = re.search(r'Skipped (\d+) Clang decision\(s\): macro', out)
        self.r['skipped_macro'] = int(m.group(1)) if m else (0 if 'Done! Instrumented' in out else None)

        status, stage, detail = S.classify_c2obra(code, timed_out, out)
        if self.r['status'] is None:
            self.r['stage'] = stage
            if status:
                self.fail(status, stage, detail)
        else:
            # Sikraken failed first; record how C²oBra itself did on the file (no inputs)
            self.r['detail']['after_sikraken_failure'] = {'c2obra_status': status or 'ok', 'stage': stage, **detail}
            if detail.get('missing_symbols'):
                self.r['detail']['missing_symbols'] = detail['missing_symbols']

        base = os.path.join(self.out_dir, self.sik_name + '_inst')
        map_path, cov_path = base + '_branch_map.json', base + '_coverage.json'
        branch_map = M.load_branch_map(map_path) if os.path.exists(map_path) else {}
        if branch_map:
            self.r['decisions'] = len(branch_map.get('branches', []))
        cov_json = None
        if os.path.exists(cov_path):
            with open(cov_path) as f:
                cov_json = json.load(f)
        if self.r['status'] is None:
            status, detail = S.classify_run(cov_json, nondet, self.r['sikraken_tests'])
            self.r['detail'].update(detail)
            if status in ('ok', 'partial', 'no_tests'):
                self.r['status'], self.r['stage'] = status, 'done'
            else:
                self.fail(status, 'run')
        try:
            if branch_map:
                total, covered, pct = M.compute_stats(branch_map, M.load_coverage(cov_path))
                self.r['edges_total'] = total
                if self.r['status'] in ('ok', 'partial', 'no_tests'):
                    self.r['edges_covered'], self.r['pct'] = covered, round(pct, 2)
        except Exception as e:                     # MissingEdgesError, bad JSON
            if self.r['status'] in ('ok', 'partial', 'no_tests'):
                self.r['status'], self.r['stage'] = 'report_error', 'report'
            self.r['detail']['report_error'] = str(e)
        self.slim()

    def slim(self):
        """Delete what can be rebuilt: the binary always; for ok tasks also the instrumented
        source, HTML and an uncleaned input copy. Failed tasks keep everything."""
        for p in glob.glob(os.path.join(self.out_dir, '*_test')):
            os.remove(p)
        ok = self.r['status'] == 'ok'
        if ok:
            for pat in ('*_inst.c', '*.html'):
                for p in glob.glob(os.path.join(self.out_dir, pat)):
                    os.remove(p)
            if not self.r['cleaned_markers']:
                shutil.rmtree(self.src_dir, ignore_errors=True)
        suite = os.path.join(self.dir, 'test-suite')
        if os.path.isdir(suite) and len(os.listdir(suite)) > TAR_SUITE_OVER:
            with tarfile.open(suite + '.tar.gz', 'w:gz') as t:
                t.add(suite, arcname='test-suite')
            shutil.rmtree(suite)


# ─── Run directory ───────────────────────────────────────────────────────────

def tool_versions(cfg):
    def first_line(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True).stdout.splitlines()[0]
        except (OSError, IndexError):
            return None
    git = lambda *a: subprocess.run(['git', '-C', REPO, *a], capture_output=True, text=True).stdout.strip()
    try:
        from importlib.metadata import version
        libclang = version('libclang')
    except Exception:
        libclang = None
    sik_version = os.path.join(cfg.sikraken_dir, 'bin', 'version.txt')
    return {
        'c2obra_commit': git('rev-parse', 'HEAD'),
        'c2obra_dirty': bool(git('status', '--porcelain', '--untracked-files=no')),
        'sikraken_version': open(sik_version).read().strip() if os.path.exists(sik_version) else None,
        'gcc': first_line(['gcc', '--version']),
        'clang': first_line([os.environ.get('C2OBRA_CLANG', 'clang'), '--version']),
        'libclang': libclang,
        'python': sys.version.split()[0],
    }


def load_sample(path):
    with open(path, newline='') as f:
        return S.assign_ids(list(csv.DictReader(f)))


def pilot_props(cfg):
    def props(r):
        p = os.path.join(cfg.sv_root, r['input_file'])
        tags = set()
        with open(p, 'rb') as f:
            head = f.read(64).decode('utf-8', errors='replace')
        if r['extension'] == '.i' and S.starts_with_line_marker(head):
            tags.add('cleaned')
        if not S.uses_nondet(read_text(p)):
            tags.add('no_nondet')
        return tags
    return props


def rebuild_outputs(cfg, planned_ids, wall):
    results = [r for r in (S.load_result(os.path.join(cfg.tasks_dir, i)) for i in planned_ids) if r]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=S.FIELDS, lineterminator='\n')
    w.writeheader()
    for r in results:
        w.writerow(S.csv_row(r))
    S.atomic_write(os.path.join(cfg.run_dir, 'results.csv'), buf.getvalue())
    text = S.summary(results, len(planned_ids), wall)
    S.atomic_write(os.path.join(cfg.run_dir, 'summary.txt'), text)
    return text


def retire(cfg, task_dir):
    """Move an interrupted (or to-be-retried) task dir aside; never delete it."""
    dest = os.path.join(cfg.run_dir, '_incomplete',
                        f"{os.path.basename(task_dir)}.{datetime.datetime.now():%Y%m%d-%H%M%S-%f}")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.move(task_dir, dest)
    shutil.rmtree(os.path.join(cfg.sikraken_dir, 'sikraken_output', SIK_PREFIX + os.path.basename(task_dir)),
                  ignore_errors=True)


def parse_args(argv):
    home = os.path.expanduser('~')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--sample', default=os.path.join(home, 'benchmarks', 'sample.csv'))
    ap.add_argument('--sv-root', help='sv-benchmarks checkout (default: <sample dir>/sv-benchmarks)')
    ap.add_argument('--runs-dir', help='parent of run directories (default: <sample dir>/runs)')
    ap.add_argument('--sikraken-dir', default=os.path.join(os.path.dirname(REPO), 'sikraken'))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--name', help='start a new run in <runs-dir>/<YYYY-MM-DD>_<name>')
    g.add_argument('--run-dir', help='resume this run directory')
    ap.add_argument('--pilot', type=int, metavar='N', help='new run: deterministic pilot of N tasks')
    ap.add_argument('--limit', type=int, metavar='N', help='only the first N tasks (sample order)')
    ap.add_argument('--only-list', metavar='FILE', help='only these task ids or yml paths, one per line')
    ap.add_argument('--retry-status', default='', help='comma-separated statuses to run again')
    ap.add_argument('--budget', type=int, default=10, help='Sikraken budget[N] in seconds (default 10)')
    ap.add_argument('--sikraken-timeout', type=float, default=180)
    ap.add_argument('--c2obra-timeout', type=float, default=600)
    ap.add_argument('--task-timeout', type=float, default=900)
    ap.add_argument('--dry-run', action='store_true', help='print the selected tasks and stop')
    return ap.parse_args(argv)


def main(argv=None):
    cfg = parse_args(argv)
    cfg.sample = os.path.abspath(cfg.sample)
    base = os.path.dirname(cfg.sample)
    cfg.sv_root = os.path.abspath(cfg.sv_root or os.path.join(base, 'sv-benchmarks'))
    cfg.sikraken_dir = os.path.abspath(cfg.sikraken_dir)
    rows = load_sample(cfg.sample)
    by_id = {r['id']: r for r in rows}

    if cfg.run_dir:
        cfg.run_dir = os.path.abspath(cfg.run_dir)
        if not os.path.isfile(os.path.join(cfg.run_dir, 'tasks.txt')):
            sys.exit(f"❌ {cfg.run_dir} is not a run directory (no tasks.txt)")
        if cfg.pilot:
            sys.exit('❌ --pilot only selects tasks for a new run; a resumed run keeps tasks.txt')
        with open(os.path.join(cfg.run_dir, 'tasks.txt')) as f:
            planned = [l.strip() for l in f if l.strip()]
        unknown = [i for i in planned if i not in by_id]
        if unknown:
            sys.exit(f"❌ {len(unknown)} task(s) of tasks.txt are not in {cfg.sample}, e.g. {unknown[0]}")
        selected = [by_id[i] for i in planned]
    else:
        runs = os.path.abspath(cfg.runs_dir or os.path.join(base, 'runs'))
        cfg.run_dir = os.path.join(runs, f"{datetime.date.today():%Y-%m-%d}_{cfg.name}")
        if os.path.exists(cfg.run_dir):
            sys.exit(f"❌ {cfg.run_dir} exists; resume it with --run-dir")
        selected = rows
        if cfg.pilot:
            on_disk = [r for r in rows if os.path.isfile(os.path.join(cfg.sv_root, r['input_file']))]
            selected = S.pick_pilot(on_disk, n=cfg.pilot, min_categories=min(10, cfg.pilot),
                                    props=pilot_props(cfg))
    cfg.tasks_dir = os.path.join(cfg.run_dir, 'tasks')
    if '.c' in cfg.run_dir:
        sys.exit(f"❌ run directory path contains '.c' ({cfg.run_dir}); instrument.py derives the "
                 f"branch-map name with str.replace('.c', ...), which would break")

    only = None
    if cfg.only_list:
        with open(cfg.only_list) as f:
            only = S.read_only_list(f.read())
    selected = S.filter_rows(selected, only=only, limit=cfg.limit)
    retry = {s for s in cfg.retry_status.split(',') if s}

    if cfg.dry_run:
        for r in selected:
            print(f"{r['id']},{r['category']},{r['extension']},{r['data_model']}")
        print(f"{len(selected)} tasks, {len({r['category'] for r in selected})} categories")
        return 0

    if not os.path.isfile(os.path.join(cfg.sikraken_dir, 'bin', 'sikraken.sh')):
        sys.exit(f"❌ no Sikraken at {cfg.sikraken_dir} (bin/sikraken.sh); use --sikraken-dir")
    new_run = not os.path.exists(cfg.run_dir)
    os.makedirs(cfg.tasks_dir, exist_ok=True)
    if new_run:
        S.atomic_write(os.path.join(cfg.run_dir, 'tasks.txt'), ''.join(r['id'] + '\n' for r in selected))
        planned = [r['id'] for r in selected]
    meta_path = os.path.join(cfg.run_dir, 'run.json')
    meta = {'invocations': []}
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
    with open(cfg.sample, 'rb') as f:
        sample_sha = hashlib.sha256(f.read()).hexdigest()
    meta['invocations'].append({
        'started': datetime.datetime.now().isoformat(timespec='seconds'), 'argv': sys.argv[1:] if argv is None else argv,
        'sample': cfg.sample, 'sample_sha256': sample_sha, 'sv_root': cfg.sv_root,
        'sikraken_dir': cfg.sikraken_dir, 'budget': cfg.budget,
        'timeouts': {'sikraken': cfg.sikraken_timeout, 'c2obra': cfg.c2obra_timeout, 'task': cfg.task_timeout},
        **tool_versions(cfg)})
    S.atomic_write(meta_path, json.dumps(meta, indent=1))

    to_run, to_retire = S.select_tasks(selected, cfg.tasks_dir, retry)
    for d in to_retire:
        retire(cfg, d)
    print(f"Run directory: {cfg.run_dir}")
    print(f"{len(planned)} planned, {len(selected)} selected now, {len(to_run)} to run "
          f"({len(to_retire)} moved to _incomplete/)", flush=True)

    def on_term(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, on_term)
    t0 = time.monotonic()
    code = 0
    try:
        for i, row in enumerate(to_run, 1):
            r = Task(cfg, row).run()
            print(f"[{i}/{len(to_run)}] {r['status']:18s} {r['seconds']:7.1f} s  {row['id']}", flush=True)
            rebuild_outputs(cfg, planned, time.monotonic() - t0)
    except KeyboardInterrupt:
        print('\nInterrupted: the current task has no result.json and will run again on resume.', flush=True)
        code = 130
    text = rebuild_outputs(cfg, planned, time.monotonic() - t0)
    print('\n' + text)
    print(f"results: {os.path.join(cfg.run_dir, 'results.csv')}")
    return code


if __name__ == '__main__':
    sys.exit(main())
