"""Pure helpers for the batch driver (batch/mass_test.py); no processes are started here.

  task_id()              stable, unique, file-name-safe id from a Test-Comp .yml path
  strip_line_markers()   blank out gcc line markers ('# 12 "f.c" 2'), keeping line numbers
  classify_sikraken()    status of the Sikraken stage from exit code, timeout and log
  classify_c2obra()      status and stage of c2obra.sh (instrument/compile/run/report)
  classify_run()         ok / partial / run_crash from the coverage JSON written by run_tests.py
  pick_pilot()           deterministic pilot sample
  select_tasks()         resume: which tasks still need running
  csv_row(), summary()   results.csv and summary.txt

Coverage numbers are never computed here: the driver gets them from
merge_reports.compute_stats(), i.e. edges.edge_coverage().
"""
import hashlib
import json
import os
import re
import statistics
from collections import Counter, defaultdict

# ─── Task ids ────────────────────────────────────────────────────────────────

def task_id(yml_path):
    """'c/array-cav19/foo.bar.yml' -> 'array-cav19__foo_bar'.

    Only [A-Za-z0-9_-]: the id becomes a file name that Sikraken quotes as a Prolog atom
    (sikraken.sh), and dots would also confuse '${file%.*}'."""
    p = yml_path
    if p.startswith('c/'):
        p = p[2:]
    if p.endswith('.yml'):
        p = p[:-4]
    return re.sub(r'[^A-Za-z0-9_-]', '_', p.replace('/', '__'))


def assign_ids(rows):
    """Add row['id'] to every row; ValueError if two rows get the same id."""
    seen = {}
    for r in rows:
        tid = task_id(r['yml_path'])
        if tid in seen and seen[tid] != r['yml_path']:
            raise ValueError(f"task id collision: {seen[tid]} and {r['yml_path']} -> {tid}")
        if tid in seen:
            raise ValueError(f"duplicate task in sample: {r['yml_path']}")
        seen[tid] = r['yml_path']
        r['id'] = tid
    return rows


# ─── Prepare ─────────────────────────────────────────────────────────────────

# gcc line marker: '# <line> "<file>" <flags>' (flags 1-4), e.g. '# 0 "<built-in>"', '# 12 "x.c" 2 3 4'
LINE_MARKER = re.compile(r'^# [0-9]+(?: "(?:[^"\\]|\\.)*")?(?: [1-4])*[ \t]*\r?$')


def starts_with_line_marker(text):
    return bool(re.match(r'# [0-9]', text))


def strip_line_markers(text):
    """(new text, number of lines blanked).

    Only if the first line is a gcc line marker: every marker line becomes an empty line,
    so all other lines keep their line numbers. Line endings are kept. '#pragma', '#include',
    '# define' and '#line' directives are not markers and are left alone."""
    if not starts_with_line_marker(text):
        return text, 0
    out, n = [], 0
    for line in text.splitlines(keepends=True):
        body = line.rstrip('\r\n')
        if LINE_MARKER.match(body):
            out.append(line[len(body):])     # keep only the line ending
            n += 1
        else:
            out.append(line)
    return ''.join(out), n


def uses_nondet(text):
    return '__VERIFIER_nondet' in text


def notes_for(row):
    """Known defects that make a task's numbers unreliable, recorded with its result.
    None at present ('floats_stub_unfixed' ended when the float/double stubs started
    reading their input)."""
    return []


# ─── Classification ──────────────────────────────────────────────────────────

SIK_PARSER_FAIL = re.compile(r'Sikraken ERROR from \S*call_parser\.sh.*')
UNDEFINED_REF = re.compile(r"undefined reference to [`'‘]([^'`’]+)['’]")
STAGE_MARKERS = [
    ('=== Step 1: Instrument ===', 'instrument'),
    ('=== Step 2: Compile ===', 'compile'),
    ('=== Step 3: Run Tests ===', 'run'),
    ('=== Step 4: Report ===', 'report'),
    ('✅ Done', 'done'),
]


def parser_error_line(log):
    """The parser's own error line: the last non-empty line before Sikraken's
    'ERROR from .../call_parser.sh' line that is not Sikraken's own framing; else that line."""
    lines = log.splitlines()
    for i, line in enumerate(lines):
        if SIK_PARSER_FAIL.search(line):
            for prev in reversed(lines[:i]):
                p = prev.strip()
                if p and not p.startswith('Sikraken'):
                    return p
            return line.strip()
    return None


def classify_sikraken(exit_code, timed_out, log, n_tests):
    """(status or None if fine, detail). n_tests: test_input-*.xml count, None if no test-suite/.

    sikraken.sh turns exit 137 (SIGKILL) into 0, so exit 0 alone does not mean success."""
    if timed_out:
        return 'sikraken_timeout', {}
    if exit_code != 0:
        if SIK_PARSER_FAIL.search(log) or 'parser failed' in log:
            return 'sikraken_parse', {'parser_error': parser_error_line(log),
                                      'sikraken_error': (SIK_PARSER_FAIL.search(log) or [None])[0]}
        err = [l.strip() for l in log.splitlines() if 'Sikraken ERROR' in l]
        return 'sikraken_error', {'sikraken_error': err[-1] if err else f'exit {exit_code}'}
    if n_tests is None:
        return 'sikraken_error', {'sikraken_error': 'exit 0 but no test-suite/ directory'}
    return None, {}


def c2obra_stage(log):
    """Last stage c2obra.sh announced ('instrument' if it stopped before Step 1)."""
    stage, pos = 'instrument', -1
    for marker, name in STAGE_MARKERS:
        i = log.rfind(marker)
        if i > pos:
            stage, pos = name, i
    return stage


def missing_symbols(log, limit=5):
    """First `limit` distinct names from gcc's 'undefined reference to `x'' lines."""
    out = []
    for m in UNDEFINED_REF.finditer(log):
        if m.group(1) not in out:
            out.append(m.group(1))
        if len(out) == limit:
            break
    return out


RUN_SIGNAL = re.compile(r'\[([^\]]+)\] ended by (SIG\w+|signal \d+) \(exit code (-?\d+)\)')
RUN_TIMEOUT = re.compile(r'\[([^\]]+)\] TIMED OUT after')


def run_signals(log):
    """From run_tests.py's log lines: ({test name: signal name}, [timed-out test names])."""
    return ({m.group(1): m.group(2) for m in RUN_SIGNAL.finditer(log)},
            [m.group(1) for m in RUN_TIMEOUT.finditer(log)])


def step_seconds(marks, end):
    """marks: [(stage, monotonic time)] in log order; end: time the process ended.
    {stage: seconds} from one marker to the next (or to end)."""
    out = {}
    for (name, t), nxt in zip(marks, marks[1:] + [(None, end)]):
        out[name] = round(out.get(name, 0) + nxt[1] - t, 3)
    return out


def _error_excerpt(log, n=4):
    lines = log.splitlines()
    for i, line in enumerate(lines):
        if line.startswith('❌'):
            return '\n'.join(l.rstrip() for l in lines[i:i + n])
    return None


def classify_c2obra(exit_code, timed_out, log):
    """(status or None, stage, detail) for one c2obra.sh run."""
    stage = c2obra_stage(log)
    if timed_out:
        return ('run_timeout' if stage == 'run' else 'tool_timeout'), stage, {}
    if exit_code == 0:
        return None, stage, {}
    if stage == 'instrument':
        if 'could not be paired' in log:
            status = 'pairing_error'
        elif 'Clang reported' in log or 'print-resource-dir' in log or 'Clang resource directory' in log:
            status = 'clang_error'
        else:
            status = 'instrument_error'
        return status, stage, {'error': _error_excerpt(log)}
    if stage == 'compile':
        first = next((l.strip() for l in log.splitlines() if 'error:' in l), None)
        return 'compile_error', stage, {'missing_symbols': missing_symbols(log), 'first_error': first}
    if stage == 'run':
        return 'run_crash', stage, {'error': _error_excerpt(log) or f'exit {exit_code}'}
    if stage == 'report':
        return 'report_error', stage, {'error': f'exit {exit_code}'}
    # 'done' with a non-zero exit should not happen
    return 'driver_error', stage, {'error': f'c2obra.sh exit {exit_code} after Done'}


def classify_run(cov_json, nondet, sikraken_tests):
    """(status, detail) once c2obra.sh finished. cov_json: run_tests.py's JSON, or None.

    no_tests: a nondet file for which Sikraken wrote no test (run once with no inputs);
    partial:  some test runs ended on a signal or timed out (run_tests.py 'partial'/'crash'/
              'timeout'), with at least one Sikraken test."""
    if not cov_json or ('branches' not in cov_json and 'summary' not in cov_json):
        return 'run_crash', {'error': 'no coverage JSON'}
    runs = cov_json.get('summary', {}).get('test_run_statuses', {})
    bad = {k: v for k, v in runs.items() if k != 'pass' and v}
    if runs and not runs.get('pass') and not runs.get('partial'):
        status = 'run_timeout' if runs.get('timeout') and not runs.get('crash') else 'run_crash'
        return status, {'test_run_statuses': runs}
    if nondet and not sikraken_tests:
        return 'no_tests', {'reason': 'nondet file, Sikraken wrote no test', 'test_run_statuses': runs}
    if bad:
        return 'partial', {'reason': 'some test runs did not pass', 'test_run_statuses': runs}
    return 'ok', {'test_run_statuses': runs}


# ─── Task selection ──────────────────────────────────────────────────────────

def _h(row, salt):
    return hashlib.sha256(f"{salt}:{row['yml_path']}".encode()).hexdigest()


def pick_pilot(rows, n=20, min_categories=10, props=None):
    """Deterministic pilot: the result depends only on the rows given, not on their order.

    Cells: extension x data_model. Inside a cell rows are taken in sha256('pilot:'+yml_path)
    order, preferring a category not picked yet. Phase 1: round-robin over the cells, at most
    n // cells each. Phase 2: if a cell ran short, the others fill up to n, again round-robin.
    props(row) -> set of tags ({'cleaned', 'no_nondet'}): if a tag exists in rows but not in
    the pick, the last pick of the fullest cell that has no tag is swapped for the first row
    (hash order) that has it. ValueError if fewer than min_categories categories result while
    the input has at least that many."""
    cells = defaultdict(list)
    for r in rows:
        cells[(r['extension'], r['data_model'])].append(r)
    keys = sorted(cells)
    for k in keys:
        cells[k].sort(key=lambda r: _h(r, 'pilot'))
    target = min(n, len(rows))
    per_cell = max(1, n // max(1, len(keys)))
    picked, cats, taken = [], set(), Counter()

    def take(k):
        left = [r for r in cells[k] if r not in picked]
        if not left:
            return False
        r = next((r for r in left if r['category'] not in cats), left[0])
        picked.append(r)
        cats.add(r['category'])
        taken[k] += 1
        return True

    for capped in (True, False):
        progress = True
        while len(picked) < target and progress:
            progress = False
            for k in keys:
                if len(picked) >= target:
                    break
                if capped and taken[k] >= per_cell:
                    continue
                progress |= take(k)

    if props:
        tags = {id(r): props(r) for r in rows}
        for tag in ('cleaned', 'no_nondet'):
            if any(tag in tags[id(r)] for r in picked):
                continue
            cand = sorted((r for r in rows if r not in picked and tag in tags[id(r)]),
                          key=lambda r: _h(r, 'pilot'))
            if not cand:
                continue
            for k in sorted(keys, key=lambda k: (-taken[k], k)):
                victim = next((r for r in reversed(picked)
                               if (r['extension'], r['data_model']) == k and not tags[id(r)]), None)
                if victim:
                    picked[picked.index(victim)] = cand[0]
                    break

    want = min(min_categories, len({r['category'] for r in rows}))
    got = len({r['category'] for r in picked})
    if got < want:
        raise ValueError(f"pilot has {got} categories, need {want}")
    return sorted(picked, key=lambda r: r['yml_path'])


def read_only_list(text):
    """Task ids or yml paths, one per line; '#' comments and blank lines ignored."""
    return {l.split('#', 1)[0].strip() for l in text.splitlines()} - {''}


def filter_rows(rows, only=None, limit=None):
    if only is not None:
        rows = [r for r in rows if r['id'] in only or r['yml_path'] in only]
    if limit is not None:
        rows = rows[:limit]
    return rows


def task_state(task_dir):
    """'new' (no dir), 'done' (result.json parses) or 'incomplete' (dir without a valid result)."""
    if not os.path.isdir(task_dir):
        return 'new'
    try:
        with open(os.path.join(task_dir, 'result.json')) as f:
            json.load(f)
        return 'done'
    except (OSError, ValueError):
        return 'incomplete'


def load_result(task_dir):
    try:
        with open(os.path.join(task_dir, 'result.json')) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def select_tasks(rows, tasks_dir, retry_statuses=()):
    """(to_run, to_retire): rows that need running, and existing task dirs that must be moved
    aside first (interrupted attempts, and finished tasks whose status is in retry_statuses)."""
    to_run, to_retire = [], []
    for r in rows:
        d = os.path.join(tasks_dir, r['id'])
        state = task_state(d)
        if state == 'new':
            to_run.append(r)
        elif state == 'incomplete':
            to_retire.append(d)
            to_run.append(r)
        elif (load_result(d) or {}).get('status') in retry_statuses:
            to_retire.append(d)
            to_run.append(r)
    return to_run, to_retire


# ─── Results ─────────────────────────────────────────────────────────────────

FIELDS = ['id', 'category', 'yml_path', 'input_file', 'extension', 'data_model', 'cleaned_markers',
          'status', 'stage', 'sikraken_tests', 'decisions', 'skipped_macro', 'skipped_outside_function',
          'edges_covered', 'edges_total', 'pct', 'seconds', 'log', 'detail', 'sikraken_exit', 'c2obra_exit',
          'seconds_sikraken', 'seconds_c2obra', 'nondet']


def csv_row(result):
    """One results.csv row from a result.json dict; 'detail' becomes compact JSON."""
    row = {k: result.get(k, '') for k in FIELDS}
    for k, v in row.items():
        if v is None:
            row[k] = ''
    row['detail'] = json.dumps(result.get('detail', {}), sort_keys=True, separators=(',', ':'))
    return row


def atomic_write(path, text):
    """Write text to path via a temp file + fsync + rename: readers see old or new, never half."""
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, 'w', newline='') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def counts_for_coverage(r):
    """ok/partial, and the inputs came from Sikraken (>= 1 test) or there are none (no nondet)."""
    if r['status'] not in ('ok', 'partial') or r.get('edges_total') in (None, ''):
        return False
    nondet = r.get('nondet')
    if nondet is None:                       # results written before the nondet column
        nondet = r.get('sikraken_tests') is not None
    return not nondet or bool(r.get('sikraken_tests'))


def summary(results, planned, wall_seconds):
    """summary.txt text. results: result dicts of finished tasks; planned: number of tasks."""
    out = []
    w = out.append
    w(f"Tasks: {len(results)} finished of {planned} planned ({planned - len(results)} not done)")
    w(f"Wall time of this invocation: {wall_seconds / 3600:.2f} h")
    secs = [r['seconds'] for r in results if isinstance(r.get('seconds'), (int, float))]
    if secs:
        w(f"Task time: total {sum(secs) / 3600:.2f} h, median {statistics.median(secs):.1f} s")
    w('')
    st = Counter(r['status'] for r in results)
    w('Status counts:')
    for s, n in st.most_common():
        w(f"  {s:20s} {n:5d}")
    w('')
    cats = sorted({r['category'] for r in results})
    statuses = [s for s, _ in st.most_common()]
    if cats:
        cw = max(len(c) for c in cats)
        w('Per category:')
        w(f"  {'category':{cw}s} " + ' '.join(f"{s[:14]:>14s}" for s in statuses))
        by = Counter((r['category'], r['status']) for r in results)
        for c in cats:
            w(f"  {c:{cw}s} " + ' '.join(f"{by[(c, s)] or '':>14}" for s in statuses))
        w('')
    cov = [r for r in results if counts_for_coverage(r)]
    if cov:
        c = sum(r['edges_covered'] for r in cov)
        t = sum(r['edges_total'] for r in cov)
        w(f"Edges over {len(cov)} ok+partial tasks with >= 1 Sikraken test or no nondet "
          f"(sum of per-task edges.edge_coverage()): {c}/{t}" + (f" = {c / t * 100:.1f}%" if t else ''))
        w('')
    sigs = Counter(v for r in results for v in r.get('detail', {}).get('run_signals', {}).values())
    if sigs:
        tasks = Counter(v for r in results for v in set(r.get('detail', {}).get('run_signals', {}).values()))
        w('Test runs ended by a signal (runs / tasks):')
        for s_, n in sigs.most_common():
            w(f"  {s_:10s} {n:6d} / {tasks[s_]}")
        w('')
    w(f"Inputs with gcc line markers cleaned: {sum(1 for r in results if r.get('cleaned_markers'))}")
    notes = Counter(n for r in results for n in r.get('detail', {}).get('notes', []))
    for n, k in notes.items():
        w(f"Tasks with note {n}: {k}")
    w('')
    syms = Counter(s for r in results for s in r.get('detail', {}).get('missing_symbols', []))
    if syms:
        w('Missing symbols (undefined reference; first 5 distinct per task), tasks per symbol:')
        for s, n in syms.most_common():
            w(f"  {n:5d}  {s}")
        w('')
    slow = sorted((r for r in results if isinstance(r.get('seconds'), (int, float))),
                  key=lambda r: -r['seconds'])[:10]
    if slow:
        w('10 slowest tasks:')
        for r in slow:
            w(f"  {r['seconds']:8.1f} s  {r['status']:18s} {r.get('stage', ''):10s} {r['id']}")
    return '\n'.join(out) + '\n'
