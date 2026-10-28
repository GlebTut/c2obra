#!/usr/bin/env python3
"""Lua 5.4 end to end through C²oBra (docs/lua_case_study.md).

  venv/bin/python3 scripts/batch/lua_e2e.py --work ~/benchmarks/lua/e2e \\
      --lua-tar ~/benchmarks/lua/dl/lua-5.4.9.tar.gz --tests-tar ~/benchmarks/lua/dl/lua-5.4.9-tests.tar.gz

Steps (each one logged in <work>/e2e.log):
 1. check the tarballs' sha256 (values published on lua.org), extract them fresh into <work>;
 2. baseline: build Lua unchanged ('make linux') and run the test suite with it;
 3. instrument the sources of the 'lua' binary (CORE_O, LIB_O, LUA_O of src/Makefile) one by
    one with global cover() ids, with the flags of 'make linux'. A file that instrument.py
    stops on is compiled uninstrumented and listed;
 4. build 'lua' from the instrumented files + cov_runtime.c with the Makefile's flags;
 5. run the test suite with it: 'lua -e"_U=true" all.lua' in testes/ (the suite's basic mode).
    A wrapper named lua gives every lua process its own COVERAGE_OUTPUT;
 6. add up the counters of all processes, write <base>_coverage.json per file, and run
    report.py per file and merge_reports.py (unchanged) for the HTML reports;
 7. write <work>/summary.json: decisions, edges, covered, % (edges.edge_coverage()).
Coverage logic is not changed: instrument.py, cov_runtime.c, edges.py are used as they are.
"""
import argparse, contextlib, glob, hashlib, io, json, os, re, shutil, subprocess, sys, tarfile, time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, 'src')
sys.path.insert(0, SRC)
import instrument as I
import edges as E

SHA256 = {   # https://www.lua.org/ftp/ and https://www.lua.org/tests/, checked 2026-10-26
    'lua-5.4.9.tar.gz':       '2335b6c582a52654f94612bf10d2f4672805d05329aa6568b1d8cd9e5c6fb8e6',
    'lua-5.4.9-tests.tar.gz': '7d971845f545ffc09fbb3128a86b2c6524161c70d0fdf0154a16e8c00c343fca',
}
# 'make linux' = linux-noreadline: CC, CFLAGS, SYSCFLAGS, LIBS + SYSLIBS of src/Makefile
CC = ['gcc', '-std=gnu99']
CFLAGS = ['-O2', '-Wall', '-Wextra', '-DLUA_COMPAT_5_3', '-DLUA_USE_LINUX']
LIBS = ['-lm', '-Wl,-E', '-ldl']
SCAN_FLAGS = ['-std=gnu99', '-DLUA_COMPAT_5_3', '-DLUA_USE_LINUX']      # what changes the program text
SUITE_CMD = ['-e_U=true', 'all.lua']
SUITE_TIMEOUT = 1800


class Log:
    def __init__(self, path):
        self.f, self.t0 = open(path, 'w'), time.monotonic()

    def __call__(self, msg):
        line = f"[{time.monotonic() - self.t0:7.1f} s] {msg}"
        print(line, flush=True)
        self.f.write(line + '\n')
        self.f.flush()


def sha256(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def extract(tar, dest):
    with tarfile.open(tar) as t:
        t.extractall(dest, filter='data')
    (top,) = {m.split('/')[0] for m in os.listdir(dest)}
    return os.path.join(dest, top)


def makefile_objects(makefile):
    """The .o names of CORE_O, LIB_O and LUA_O (the 'lua' binary) in src/Makefile."""
    text = open(makefile).read()
    objs = []
    for var in ('CORE_O', 'LIB_O', 'LUA_O'):
        m = re.search(rf'^{var}=\s*(.*)$', text, re.M)
        objs += m.group(1).split()
    return [o[:-2] + '.c' for o in objs if o.endswith('.o')]


def run(cmd, log, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        log(f"  exit {r.returncode}: {' '.join(cmd)}\n{r.stdout[-2000:]}{r.stderr[-2000:]}")
    return r


def run_suite(lua, testes, out_log, env=None):
    t = time.monotonic()
    with open(out_log, 'w') as f:
        r = subprocess.run([lua, *SUITE_CMD], cwd=testes, stdout=f, stderr=subprocess.STDOUT,
                           env=env, timeout=SUITE_TIMEOUT)
    text = open(out_log, errors='replace').read()
    return {'exit': r.returncode, 'final_ok': 'final OK !!!' in text, 'seconds': round(time.monotonic() - t, 2),
            'files': re.findall(r"\*\*\*\*\* FILE '([^']+)'", text)}


def merge_counters(paths):
    merged = {}
    for p in paths:
        with open(p) as f:
            for b in json.load(f)['branches']:
                m = merged.setdefault(b['id'], {'id': b['id'], 'true': 0, 'false': 0})
                m['true'] += b['true']
                m['false'] += b['false']
    return merged


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--work', required=True)
    ap.add_argument('--lua-tar', required=True)
    ap.add_argument('--tests-tar', required=True)
    a = ap.parse_args()
    work = os.path.abspath(a.work)
    if '.c' in work:
        sys.exit(f"❌ work dir contains '.c' ({work}): instrument.py derives map names with replace('.c', ...)")
    if os.path.exists(work):
        sys.exit(f"❌ {work} exists; give a new --work directory")
    os.makedirs(work)
    log = Log(os.path.join(work, 'e2e.log'))
    summary = {'lua_tar': a.lua_tar, 'tests_tar': a.tests_tar, 'flags': SCAN_FLAGS,
               'cflags': CC + CFLAGS, 'libs': LIBS, 'suite_cmd': ['lua', *SUITE_CMD]}

    # 1. tarballs
    for tar in (a.lua_tar, a.tests_tar):
        got, want = sha256(tar), SHA256.get(os.path.basename(tar))
        log(f"sha256 {os.path.basename(tar)} {got} {'OK' if got == want else 'MISMATCH, expected ' + str(want)}")
        if got != want:
            sys.exit(1)
    base = extract(a.lua_tar, os.path.join(work, 'base'))
    testes = extract(a.tests_tar, os.path.join(work, 'tests'))
    lua_src = os.path.join(base, 'src')

    # 2. baseline build + suite
    r = run(['make', '-C', base, 'linux'], log)
    log(f"baseline build: exit {r.returncode}")
    run(['make', '-C', os.path.join(testes, 'libs'), f'LUA_DIR={lua_src}'], log)
    summary['baseline'] = run_suite(os.path.join(lua_src, 'lua'), testes, os.path.join(work, 'suite_baseline.log'))
    log(f"baseline suite: {summary['baseline']}")

    # 3. instrument, file by file, global ids
    files = makefile_objects(os.path.join(lua_src, 'Makefile'))
    pristine = os.path.join(work, 'src')                     # unbuilt copy: the scan sees no .o files
    shutil.copytree(lua_src, pristine, ignore=shutil.ignore_patterns('*.o', '*.a', 'lua', 'luac'))
    inst_dir = os.path.join(work, 'inst')
    os.makedirs(inst_dir)
    next_id, per_file, failed = 1, [], {}
    os.chdir(work)                                           # branch maps record paths relative to here
    for c in files:
        src = os.path.relpath(os.path.join(pristine, c), work)
        out = os.path.join(inst_dir, c[:-2] + '_inst.c')
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                nid, n_edges = I.instrument_file(src, out, start_id=next_id, flags=SCAN_FLAGS)
        except SystemExit:
            err = [l for l in buf.getvalue().splitlines() if l.startswith(('❌', '  '))]
            failed[c] = err
            log(f"instrument {c}: STOPPED, compiled uninstrumented: {' | '.join(err)[:300]}")
            for p in glob.glob(out[:-2] + '*'):
                os.remove(p)
            continue
        text = buf.getvalue()
        dec = int(re.search(r'Done! Instrumented (\d+) decisions', text).group(1))
        macro = re.search(r'Skipped (\d+) Clang decision\(s\): macro', text)
        per_file.append({'file': c, 'ids': nid - next_id, 'decisions': dec, 'edges': n_edges,
                         'skipped_macro': int(macro.group(1)) if macro else 0,
                         'syntax_warning': 'syntax errors' in text})
        next_id = nid
    total_ids = next_id - 1
    summary['uninstrumented'] = failed
    log(f"instrumented {len(per_file)} of {len(files)} files, {total_ids} cover() ids; "
        f"uninstrumented: {sorted(failed) or 'none'}")

    # 4. build lua from the instrumented sources
    build = os.path.join(work, 'build')
    os.makedirs(build)
    objs, t = [], time.monotonic()
    units = [os.path.join(inst_dir, c[:-2] + '_inst.c') if c not in failed else os.path.join(pristine, c)
             for c in files] + [os.path.join(SRC, 'cov_runtime.c')]
    for u in units:
        o = os.path.join(build, os.path.basename(u)[:-2] + '.o')
        r = run(CC + CFLAGS + ['-w', f'-DMAX_BRANCHES={max(2, total_ids * 2)}', '-I', lua_src, '-I', SRC,
                               '-c', u, '-o', o], log)
        if r.returncode:
            summary['build'] = {'failed': u}
            json.dump(summary, open(os.path.join(work, 'summary.json'), 'w'), indent=1)
            sys.exit(f"❌ compile failed: {u}")
        objs.append(o)
    real = os.path.join(build, 'lua.real')
    r = run(CC + ['-o', real] + objs + LIBS, log)
    summary['build'] = {'exit': r.returncode, 'seconds': round(time.monotonic() - t, 2),
                        'max_branches': max(2, total_ids * 2)}
    log(f"instrumented build: {summary['build']}")
    if r.returncode:
        sys.exit("❌ link failed")

    # 5. suite with the instrumented lua; one coverage file per lua process
    covdir = os.path.join(work, 'cov')
    os.makedirs(covdir)
    wrapper = os.path.join(build, 'lua')
    with open(wrapper, 'w') as f:
        f.write('#!/bin/bash\n# one coverage file per lua process (pid); argv[0] stays this wrapper\n'
                f'export COVERAGE_OUTPUT="{covdir}/cov.$$.json"\nexec -a "$0" "{real}" "$@"\n')
    os.chmod(wrapper, 0o755)
    summary['instrumented_suite'] = run_suite(wrapper, testes, os.path.join(work, 'suite_instrumented.log'))
    cov_files = sorted(glob.glob(os.path.join(covdir, 'cov.*.json')))
    summary['instrumented_suite']['coverage_files'] = len(cov_files)
    s0, s1 = summary['baseline'], summary['instrumented_suite']
    summary['same_result_as_baseline'] = (s0['exit'], s0['final_ok'], s0['files']) == (s1['exit'], s1['final_ok'], s1['files'])
    log(f"instrumented suite: { {k: v for k, v in s1.items() if k != 'files'} }; "
        f"same exit / final OK / files as baseline: {summary['same_result_as_baseline']}")

    # 6. merge counters, per-file coverage JSON + reports
    merged = merge_counters(cov_files)
    report_dir = os.path.join(work, 'report')
    os.makedirs(report_dir)
    tot = {'decisions': 0, 'edges': 0, 'covered': 0}
    for pf in per_file:
        b = pf['file'][:-2] + '_inst'
        shutil.copy(os.path.join(inst_dir, b + '_branch_map.json'), report_dir)
        bmap = json.load(open(os.path.join(report_dir, b + '_branch_map.json')))
        ids = {int(x['id']) for x in bmap['branches']}
        cov = {'branches': [merged[i] for i in sorted(ids) if i in merged]}
        json.dump(cov, open(os.path.join(report_dir, b + '_coverage.json'), 'w'), indent=1)
        pf['covered'], pf['edges_check'] = E.edge_coverage(bmap, {e['id']: e for e in cov['branches']})
        for k, v in (('decisions', pf['decisions']), ('edges', pf['edges_check']), ('covered', pf['covered'])):
            tot[k] += v
        run([sys.executable, os.path.join(SRC, 'report.py'), os.path.join(report_dir, b + '_branch_map.json'),
             os.path.join(report_dir, b + '_coverage.json'), '--output', os.path.join(report_dir, b + '_report.html'),
             '--csv', os.path.join(report_dir, b + '_report.csv'), '--test-inputs', os.devnull], log)
    run([sys.executable, os.path.join(SRC, 'merge_reports.py'), report_dir], log)
    tot['pct'] = round(tot['covered'] / tot['edges'] * 100, 2) if tot['edges'] else 0.0
    tot['skipped_macro'] = sum(pf['skipped_macro'] for pf in per_file)
    tot['ids'] = total_ids
    summary['totals'], summary['per_file'] = tot, per_file
    json.dump(summary, open(os.path.join(work, 'summary.json'), 'w'), indent=1)
    log(f"totals: {tot}")
    log(f"summary: {os.path.join(work, 'summary.json')}; report: {report_dir}")


if __name__ == '__main__':
    main()
