#!/usr/bin/env python3
"""Compare the instrumented output of the OLD src (Tree-sitter) with the NEW src (Clang only).

Usage:  python3 compare_old_new.py OLD_SRC NEW_SRC FILE_LIST [-- compiler flags]
  OLD_SRC / NEW_SRC : the src/ folders of the two versions
  FILE_LIST         : text file, one .c/.i path per line (or a folder: all .c/.i files in it)
Prints one line per file that differs or stops, then a summary. Whitespace-only differences
are counted separately. Each version runs in its own process so the two instrument.py do not mix.
"""
import sys, os, re, subprocess, tempfile, glob, json

def files(arg):
    if os.path.isdir(arg):
        return sorted(glob.glob(arg + '/**/*.c', recursive=True) + glob.glob(arg + '/**/*.i', recursive=True))
    return [l.strip() for l in open(arg) if l.strip()]

def run(src, f, out, flags):
    r = subprocess.run([sys.executable, os.path.join(src, 'instrument.py'), f, out, '--'] + flags,
                       capture_output=True, text=True)
    return r.returncode == 0 and os.path.exists(out), (r.stdout + r.stderr)

def main():
    args = sys.argv[1:]
    flags = []
    if '--' in args:
        i = args.index('--'); args, flags = args[:i], args[i + 1:]
    old, new, lst = args
    norm = lambda t: re.sub(r'\s+', '', t)
    n = same = ws = diff = stop_both = fixed = broke = 0
    with tempfile.TemporaryDirectory() as d:
        for f in files(lst):
            n += 1
            o, nw = os.path.join(d, 'o.c'), os.path.join(d, 'n.c')
            for p in (o, nw, o.replace('.c', '_branch_map.json'), nw.replace('.c', '_branch_map.json')):
                if os.path.exists(p): os.remove(p)
            ok_o, log_o = run(old, f, o, flags)
            ok_n, log_n = run(new, f, nw, flags)
            if not ok_o and not ok_n:
                stop_both += 1
                rest = log_n.split('❌', 1)[1].strip().splitlines() if '❌' in log_n else log_n.strip().splitlines()
                print('BOTH STOP:', f, '|', ' / '.join(l.strip() for l in rest[:3])[:260]); continue
            if ok_o and not ok_n: broke += 1; print('BROKE (old ok, new stops):', f, log_n.strip().splitlines()[-1][:150]); continue
            if ok_n and not ok_o: fixed += 1; print('NOW WORKS (old stopped):', f); continue
            a, b = open(o).read(), open(nw).read()
            NEW_KEYS = ('switch_id', 'falls_through', 'breaks')   # facts added in iteration 2 for --mode testcov
            def load_map(path):
                m = json.load(open(path))
                for e in m.get('branches', []):
                    for k in NEW_KEYS: e.pop(k, None)
                return json.dumps(m, sort_keys=True)
            ma = load_map(o.replace('.c', '_branch_map.json'))
            mb = load_map(nw.replace('.c', '_branch_map.json'))
            ma, mb = (re.sub(r'"source_file": "[^"]*",?', '', m) for m in (ma, mb))
            if a == b and ma == mb: same += 1
            elif norm(a) == norm(b) and ma == mb: ws += 1
            else: diff += 1; print('DIFFERENT:', f, 'code' if norm(a) != norm(b) else '', 'map' if ma != mb else '')
    print(f"\nfiles {n}: identical {same}, whitespace-only {ws}, different {diff}, "
          f"new works / old stopped {fixed}, old ok / new stops {broke}, both stop {stop_both}")

main()
