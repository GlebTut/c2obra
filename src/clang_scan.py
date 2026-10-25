#!/usr/bin/env python3
"""
C²oBra - Clang decision scan (Phase 2, spec section 5.3: hybrid design)

Clang decides WHICH branch decisions exist in the program as compiled (it honours -D, -I,
#ifdef and macros). Tree-sitter is then only used to find the byte range to rewrite
(see pair_decisions() in instrument.py).

Uses the libclang Python bindings (pip: libclang==18.1.1). The pip wheel ships no Clang
builtin headers (stddef.h, stdarg.h ...), so the resource directory of an installed clang is
passed with -isystem; without it libclang silently returns a partial AST.
"""
import bisect, ctypes, functools, os, subprocess
from collections import Counter
import clang.cindex as ci

K = ci.CursorKind
KINDS = {K.IF_STMT: 'if', K.FOR_STMT: 'for', K.WHILE_STMT: 'while', K.DO_STMT: 'do',
         K.SWITCH_STMT: 'switch', K.CONDITIONAL_OPERATOR: '?:'}
KEYWORD = {'if': 'if', 'for': 'for', 'while': 'while', 'do': 'do', 'switch': 'switch'}

# Scan-only leniency flags. Clang >= 16 makes these hard errors in C99+, GCC 13 only warns,
# so without them the scan would stop on files that the pipeline's gcc compiles. Printed on
# every run; later flags win in Clang, so the user can override them (e.g. -Werror=implicit-int).
LENIENCY_FLAGS = ['-Wno-error=implicit-function-declaration',
                  '-Wno-error=implicit-int',
                  '-Wno-error=int-conversion',
                  '-Wno-error=incompatible-function-pointer-types']   # ntdrivers *_i_cil callbacks
# Clang's default bracket-nesting limit (256) is lower than GCC's; CIL-reduced SV-COMP files
# need more. Affects only whether Clang accepts the file, not its meaning.
CLANG_ONLY_FLAGS = ['-fbracket-depth=4096']


class ClangScanError(Exception):
    """The scan cannot be trusted: no resource dir, or the compiler reported an error."""


@functools.lru_cache(maxsize=None)
def resource_dir(clang=None):
    """Clang resource directory (holds the builtin headers). Stops with a clear error if missing.
    The clang binary is `clang` unless the C2OBRA_CLANG environment variable names another one
    (CI sets clang-18 to match libclang 18). Cached: running clang costs ~11 ms."""
    clang = clang or os.environ.get('C2OBRA_CLANG', 'clang')
    try:
        out = subprocess.run([clang, '-print-resource-dir'], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        raise ClangScanError(
            f"cannot run '{clang} -print-resource-dir' ({e}). Install clang (same major version as "
            f"libclang, 18) so its builtin headers can be passed to the scan, or set C2OBRA_CLANG.")
    d = out.stdout.strip()
    if not os.path.isfile(os.path.join(d, 'include', 'stddef.h')):
        raise ClangScanError(f"Clang resource directory '{d}' has no include/stddef.h; "
                             f"the scan would silently see a partial AST.")
    return d


def scan_flags(user_flags, res_dir):
    """Full flag list given to libclang: scan-only leniency, then the user flags (shared with
    gcc; after the leniency flags so they can override them), then Clang-only flags."""
    return LENIENCY_FLAGS + list(user_flags) + CLANG_ONLY_FLAGS + ['-isystem', os.path.join(res_dir, 'include')]


# libclang's Python bindings do not wrap clang_getSpellingLocation; declare it here.
_spelling = ci.conf.lib.clang_getSpellingLocation
_spelling.argtypes = [ci.SourceLocation, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint),
                      ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
_spelling.restype = None


def _spelling_offset(loc):
    off = ctypes.c_uint()
    _spelling(loc, None, None, None, ctypes.byref(off))
    return off.value


def _depth0(tokens):
    """Yield (index, spelling) of tokens outside any (), [] or {}."""
    depth = 0
    for i, t in enumerate(tokens):
        if t in ('(', '[', '{'):
            depth += 1
        elif t in (')', ']', '}'):
            depth -= 1
        elif depth == 0:
            yield i, t


def _is_gnu_conditional(cursor):
    """GNU 'a ?: b' (BinaryConditionalOperator) has no cursor kind in libclang 18: it is an
    UNEXPOSED_EXPR with 4 children whose own tokens have '?' directly followed by ':'.
    The cheap checks come first: most UNEXPOSED_EXPRs are implicit casts with one child."""
    if cursor.kind != K.UNEXPOSED_EXPR or len(list(cursor.get_children())) != 4:
        return False
    top = [t for _, t in _depth0([t.spelling for t in cursor.get_tokens()])]
    return any(a == '?' and b == ':' for a, b in zip(top, top[1:]))


class _FileTokens:
    """The main file's tokens (comments dropped), lexed ONCE per translation unit.

    Why not cursor.get_tokens(): for a macro-produced statement it returns the tokens of the
    macro definition (e.g. 'if' for WHEN_POS(a)), not what is written in the file.
    Why not lex each decision's extent: a statement's extent includes its body, so nested
    decisions re-lex the same text again and again (4.4M tokens for 145 SV-COMP files)."""

    def __init__(self, tu, path):
        f = tu.get_file(path)
        size = os.path.getsize(path)
        r = ci.SourceRange.from_locations(ci.SourceLocation.from_offset(tu, f, 0),
                                          ci.SourceLocation.from_offset(tu, f, size))
        toks = [t for t in tu.get_tokens(extent=r) if t.kind != ci.TokenKind.COMMENT]
        self.offsets = [t.location.offset for t in toks]
        self.spellings = [t.spelling for t in toks]
        self.tu, self.file = tu, f

    def between(self, start, end, limit=None):
        """Spellings of tokens starting in [start, end); at most `limit` of them."""
        i = bisect.bisect_left(self.offsets, start)
        j = bisect.bisect_left(self.offsets, end)
        if limit is not None:
            j = min(j, i + limit)
        return self.spellings[i:j]

    def paren_group(self, start):
        """(offset, spelling) of the tokens from the first '(' at or after `start` to its
        matching ')', both included; [] if there is none. Reads only the header, not the body."""
        i = bisect.bisect_left(self.offsets, start)
        while i < len(self.spellings) and self.spellings[i] != '(':
            i += 1
        depth = 0
        for j in range(i, len(self.spellings)):
            t = self.spellings[j]
            if t in ('(', '[', '{'):
                depth += 1
            elif t in (')', ']', '}'):
                depth -= 1
                if depth == 0:
                    return list(zip(self.offsets[i:j + 1], self.spellings[i:j + 1]))
        return []

    def line_col(self, offset):
        loc = ci.SourceLocation.from_offset(self.tu, self.file, offset)
        return loc.line, loc.column


def _decision_tokens(ftoks, cursor, kind):
    """File tokens needed to classify a decision: the keyword for if/while/do/switch, the
    whole statement for 'for' (header scan stops at its ')'), the expression for '?:'."""
    e = cursor.extent
    return ftoks.between(e.start.offset, e.end.offset, limit=1 if kind in KEYWORD and kind != 'for' else None)


def _from_macro(cursor, kind, tokens):
    """True if the decision's keyword / '?' is not written in the file text at its location.
    `tokens` are the file tokens (_decision_tokens). Two checks, because libclang exposes no
    isMacroID():
      - spelling != expansion offset: the decision sits in a macro argument;
      - the file tokens do not start with the keyword (or have no top-level '?'): the
        decision comes from a macro body, e.g. WHEN_POS(a) -> if ((a) > 0)."""
    if _spelling_offset(cursor.location) != cursor.location.offset:
        return True
    if kind == '?:':
        return not any(t == '?' for _, t in _depth0(tokens))
    return not tokens or tokens[0] != KEYWORD[kind]


def _for_has_condition(tokens):
    """for(init; cond; inc): True if there are tokens between the two ';' inside the parens."""
    if len(tokens) < 2 or tokens[0] != 'for' or tokens[1] != '(':
        return None
    depth, semis = 0, []
    for i, t in enumerate(tokens[1:], 1):
        if t in ('(', '[', '{'):
            depth += 1
        elif t in (')', ']', '}'):
            depth -= 1
            if depth == 0:
                break
        elif t == ';' and depth == 1:
            semis.append(i)
    if len(semis) != 2:
        return None
    return semis[1] > semis[0] + 1


def _header_stmt_expr(group):
    """True if a header's tokens (a paren_group) contain a GNU statement expression '({',
    written in the file text. Tree-sitter has no rule for it and loses the header's structure;
    one that comes from a macro is a plain macro call to Tree-sitter and needs nothing."""
    return any(a == '(' and b == '{' for (_, a), (_, b) in zip(group, group[1:]))


def _depth1_semicolons(group):
    """Offsets of the ';' directly inside a for header's parens (a paren_group), or None
    unless there are exactly two."""
    depth, semis = 0, []
    for off, t in group:
        if t in ('(', '[', '{'):
            depth += 1
        elif t in (')', ']', '}'):
            depth -= 1
        elif t == ';' and depth == 1:
            semis.append(off)
    return tuple(semis) if len(semis) == 2 else None


def _header_info(cursor, kind, ftoks, in_main):
    """Clang's view of an if/while/do/for header, for headers that contain a statement
    expression (instrument.py then wraps Clang's condition span instead of Tree-sitter's).

    Returns a dict:
      header_stmt_expr - the header text contains '({'
      cond_span        - (start, end) byte offsets of the condition (end exclusive), or None
                         (for without condition, or a span that is not plain file text inside
                         the header, e.g. a macro whose expansion holds the ')' or a ';')
      cond_lc          - ((line, col), (line, col)) of cond_span, for messages and the map
      for_semis        - for: offsets of the two ';' of the header, or None
      else_info        - if: (has_else, else_line, is_else_if), as instrument.get_else_info()
    Only header_stmt_expr is computed for headers without a statement expression."""
    children = list(cursor.get_children())
    # The header starts at the keyword, except for do: its 'while (' follows the body
    start = children[0].extent.end.offset if kind == 'do' else cursor.extent.start.offset
    group = ftoks.paren_group(start)
    info = {'header_stmt_expr': _header_stmt_expr(group), 'cond_span': None, 'cond_lc': None,
            'for_semis': None, 'else_info': None}
    if not info['header_stmt_expr']:
        return info
    lo, hi = group[0][0], group[-1][0]            # offsets of the header's '(' and ')'
    if kind in ('if', 'while'):
        cond = children[0]
    elif kind == 'do':
        cond = children[-1]
    else:
        # libclang leaves out a missing init/cond/inc, so for(;c;i++) has children
        # [cond, inc, body]: the condition is the child that starts between the two ';'
        info['for_semis'] = semis = _depth1_semicolons(group)
        cond = None
        if semis:
            lo, hi = semis
            cond = next((c for c in children[:-1] if lo < c.extent.start.offset < hi), None)
    if cond is not None:
        e = cond.extent
        if (in_main(e.start) and in_main(e.end) and lo < e.start.offset < e.end.offset <= hi
                and _spelling_offset(e.start) == e.start.offset):
            info['cond_span'] = (e.start.offset, e.end.offset)
            info['cond_lc'] = ((e.start.line, e.start.column), (e.end.line, e.end.column))
    if kind == 'if':
        if len(children) == 3:
            # the 'else' keyword: the last 'else' token between the then-branch and the else-branch
            then_end, else_start = children[1].extent.end.offset, children[2].extent.start.offset
            i = bisect.bisect_left(ftoks.offsets, then_end)
            j = bisect.bisect_left(ftoks.offsets, else_start)
            elses = [k for k in range(i, j) if ftoks.spellings[k] == 'else']
            else_line = ftoks.line_col(ftoks.offsets[elses[-1]])[0] if elses else children[2].extent.start.line
            info['else_info'] = (True, else_line, children[2].kind == K.IF_STMT)
        else:
            info['else_info'] = (False, None, False)
    return info


def _count_cases(switch_cursor):
    """case/default labels belonging to this switch (not to a nested one)."""
    n, stack = 0, list(switch_cursor.get_children())
    while stack:
        c = stack.pop()
        if c.kind == K.SWITCH_STMT:
            continue
        if c.kind in (K.CASE_STMT, K.DEFAULT_STMT):
            n += 1
        stack.extend(c.get_children())
    return n


def _format_diag(d):
    loc = d.location
    where = f"{loc.file.name}:{loc.line}:{loc.column}" if loc.file else "<no location>"
    sev = {ci.Diagnostic.Error: 'error', ci.Diagnostic.Fatal: 'fatal error'}.get(d.severity, 'note')
    return f"{where}: {sev}: {d.spelling}"


def scan(path, user_flags=(), res_dir=None):
    """Every decision Clang sees whose expansion location is in `path`, in source order.

    Each entry: kind, line, col (1-based expansion location; col counts bytes),
    from_macro, has_condition (for loops; None otherwise or unknown), n_cases (switch),
    in_function (inside the body of a function definition), header_stmt_expr (if/while/do/for
    header written with a GNU statement expression; then also cond_span, cond_lc, for_semis,
    else_info, see _header_info()).
    Raises ClangScanError if Clang reports any error-level diagnostic: a fatal error still
    yields a partial AST, so a scan with errors is never used.
    """
    res_dir = res_dir or resource_dir()
    flags = scan_flags(user_flags, res_dir)
    tu = ci.Index.create().parse(path, args=flags)
    errors = [d for d in tu.diagnostics if d.severity >= ci.Diagnostic.Error]
    if errors:
        raise ClangScanError(
            f"Clang reported {len(errors)} error(s) in {path}; the scan would be incomplete.\n"
            + '\n'.join('  ' + _format_diag(d) for d in errors[:10])
            + f"\n  flags used: {' '.join(flags)}"
            + "\n  A missing -D or -I in CFLAGS is the usual cause.")

    main = os.path.realpath(path)
    is_main = {}                                          # file name -> bool (realpath is slow)

    def in_main(loc):
        if loc.file is None:
            return False
        name = loc.file.name
        if name not in is_main:
            is_main[name] = os.path.realpath(name) == main
        return is_main[name]

    ftoks = _FileTokens(tu, path)
    out = []
    # Top-level declarations from headers (most of the cursors when stdio.h etc. are included)
    # are skipped as whole subtrees; inside a main-file declaration every cursor is checked.
    for top in tu.cursor.get_children():
        if not in_main(top.location):
            continue
        stack = [(top, False)]    # (cursor, inside a function body)
        while stack:              # explicit stack: Cursor.walk_preorder() is a recursive generator,
            c, in_body = stack.pop()   # O(cursors x depth), slow on deeply nested CIL-reduced files
            # The body of a function definition is its COMPOUND_STMT child (not its parameters:
            # a ?: in a parameter's array size is outside the body).
            fdef = c.kind == K.FUNCTION_DECL and c.is_definition()
            stack.extend(reversed([(ch, in_body or (fdef and ch.kind == K.COMPOUND_STMT))
                                   for ch in c.get_children()]))   # reversed: pop in preorder
            loc = c.location                              # expansion location
            if not in_main(loc):
                continue
            kind = KINDS.get(c.kind)
            if kind is None:
                if not _is_gnu_conditional(c):
                    continue
                kind = '?:'
            tokens = _decision_tokens(ftoks, c, kind)
            d = {
                'kind':          kind,
                'line':          loc.line,
                'col':           loc.column,
                'offset':        loc.offset,
                'from_macro':    _from_macro(c, kind, tokens),
                'has_condition': _for_has_condition(tokens) if kind == 'for' else None,
                'n_cases':       _count_cases(c) if kind == 'switch' else None,
                'in_function':   in_body,
                'header_stmt_expr': False,
            }
            if kind in ('if', 'while', 'do', 'for') and not d['from_macro']:
                d.update(_header_info(c, kind, ftoks, in_main))
            out.append(d)
    out.sort(key=lambda d: d['offset'])
    return out


def counts_as_decision(d):
    """THE rule for which Clang decisions C²oBra instruments. Returns (bool, reason).

    Kept in one place because the definition of a branch is still open (supervisor questions:
    macros, constant conditions, how switch is counted). Reasons for skipping:
      outside_function - not inside a function body (enum value, global initialiser, array
                         size at file scope): never executed at run time, and a constant
                         expression there cannot contain the cover() call (busybox _ISupper)
      macro          - produced by a macro expansion: no text in the file to wrap (Phase 5)
      switch_no_case - switch without case/default labels has nothing to count
    A for without a condition (for(;;)) IS counted, like while(1) (tests/definition/d07,
    confirmed 2026-10-16); instrument.py inserts cover((1), id) in its empty slot.
    """
    if not d['in_function']:
        return False, 'outside_function'
    if d['from_macro']:
        return False, 'macro'
    if d['kind'] == 'switch' and d['n_cases'] == 0:
        return False, 'switch_no_case'
    return True, 'counted'


def decisions(path, user_flags=(), res_dir=None):
    """(counted decisions, Counter of skip reasons)."""
    kept, skipped = [], Counter()
    for d in scan(path, user_flags, res_dir):
        ok, reason = counts_as_decision(d)
        if ok:
            kept.append(d)
        else:
            skipped[reason] += 1
    return kept, skipped
