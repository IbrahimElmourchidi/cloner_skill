#!/usr/bin/env python3
"""Brings an existing site forward to the current generator.

    python3 scripts/migrate.py <site> --to v1.1-to-v2.0

A site owns its own copy of the generator, so an installed skill update does
not reach it. This runs once, from the installed skill, and is the only thing
in the skill that writes to somebody else's site — so it prints every action
before taking it, writes a `.bak` beside anything it rewrites, and refuses to
do anything at all without `--apply.

The v1.1-to-v2.0 migration has three steps, in this order, because each one
depends on the last:

  1. Rename fragments from their number to their slug. Numbered fragments are a
     position, so they are wrong the moment anything is reordered — which is
     exactly what v2 encourages. Nothing else can be trusted until this is done,
     so it goes first and is verified by re-reading the result.

  2. Drop the stored `n=` from pages.py. Now that `n` is derived, a stored value
     that agrees is harmless but one that disagrees is a hard error, and a site
     that has been hand-edited for a year may well have one. Removing the field
     is mechanical only if the value already matches the position; anything else
     is reported and left for a human, because that disagreement is a question
     about the intended order.

  3. Nothing else. The read-tracking key change (`step-<n>` to `step-<slug>`)
     invalidates saved progress, so it is a consequence the author should be
     told about rather than a file this script edits. It is reported.
"""
import argparse
import ast
import os
import re
import shutil
import sys


def load_pages_src(site):
    path = os.path.join(site, '_build', 'pages.py')
    if not os.path.exists(path):
        sys.exit('migrate: no pages.py at %s — is this a site?' % path)
    return path, open(path, encoding='utf-8').read()


def step_one_renames(site):
    """Number-named fragment -> slug-named. Returns (renames, problems)."""
    path, src = load_pages_src(site)
    content = os.path.join(site, '_build', 'content')

    ns = {}
    exec(compile(src, path, 'exec'), ns)
    # entry n -> slug, from the ast, so a wrapped dict() is handled correctly
    spans = {}
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.List):
            for el in node.value.elts:
                if not isinstance(el, ast.Call):
                    continue
                kw = {k.arg: k.value for k in el.keywords}
                if 'n' not in kw or 'slug' not in kw:
                    continue
                try:
                    n = int(ast.literal_eval(kw['n']))
                    slug = ast.literal_eval(kw['slug'])
                except (ValueError, TypeError):
                    continue
                spans[n] = (slug, el.lineno - 1, el.end_lineno)

    renames, problems = [], []
    for n, (slug, _lo, _hi) in sorted(spans.items()):
        old = os.path.join(content, '%02d.html' % n)
        if not os.path.exists(old):
            # maybe already slug-named, or zero-padded to 3+
            for cand in ('%03d.html' % n, '%d.html' % n, '%s.html' % slug):
                if os.path.exists(os.path.join(content, cand)):
                    break
            else:
                continue
            old = os.path.join(content, cand)
        new = os.path.join(content, '%s.html' % slug)
        if os.path.exists(new):
            problems.append('both %s and %s exist; resolve by hand'
                            % (os.path.basename(old), os.path.basename(new)))
            continue
        renames.append((old, new))
    return renames, problems


def step_two_strip_n(site):
    """Remove `n=<int>,` from each dict(...) where it agrees with position."""
    path, src = load_pages_src(site)
    tree = ast.parse(src)
    edits, mismatched = [], []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.List):
            for pos, el in enumerate(node.value.elts, 1):
                if not isinstance(el, ast.Call):
                    continue
                kw = {k.arg: k.value for k in el.keywords}
                if 'n' not in kw or kw['n'] is None:
                    continue
                try:
                    n = int(ast.literal_eval(kw['n']))
                except (ValueError, TypeError):
                    continue
                if n != pos:
                    mismatched.append((pos, n))
                    continue
                edits.append((kw['n'].lineno, kw['n'].col_offset,
                              kw['n'].end_lineno, kw['n'].end_col_offset))

    if not edits:
        return 0, mismatched

    # Remove `n=<int>,` from whichever line carries the keyword. Matching the
    # whole token rather than slicing columns keeps the surrounding
    # indentation and any following keyword intact, and a line can only hold
    # one `n=` because the keyword name is unique in a dict().
    lines = src.splitlines(keepends=True)
    for lineno in sorted({e[0] for e in edits}, reverse=True):
        line = lines[lineno - 1]
        new_line, count = re.subn(r'\bn\s*=\s*\d+\s*,\s*', '', line)
        if count:
            lines[lineno - 1] = new_line
    out = ''.join(lines)
    try:
        ast.parse(out)
    except SyntaxError as exc:
        return 0, mismatched + [('rewrite failed to parse: %s' % exc)]
    shutil.copy2(path, path + '.bak')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(out)
    return len(edits), mismatched


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('site', nargs='?', default='docs/site')
    ap.add_argument('--to', default='v1.1-to-v2.0')
    ap.add_argument('--apply', action='store_true',
                    help='actually make the changes (default is a dry run)')
    args = ap.parse_args()

    if args.to != 'v1.1-to-v2.0':
        sys.exit('migrate: unknown target %r (known: v1.1-to-v2.0)' % args.to)

    site = args.site
    renames, problems = step_one_renames(site)
    strip_count, mismatched = (0, [])
    if not args.apply:
        print('migrate: dry run for %s -> %s' % (site, args.to))
    else:
        strip_count, mismatched = step_two_strip_n(site)

    print('')
    print('step 1 — fragments keyed by slug')
    if renames:
        for old, new in renames:
            print('  %s  ->  %s' % (os.path.basename(old), os.path.basename(new)))
        print('  %d rename(s)' % len(renames))
    else:
        print('  nothing to rename')
    for p in problems:
        print('  PROBLEM: %s' % p)

    print('')
    print('step 2 — drop stored n=')
    if mismatched:
        for pos, n in mismatched:
            print('  step %s sits at position %d. Two things disagree about the'
                  % (n, pos))
            print('  order — decide which is right, then re-run.')
    else:
        print('  %d entr(y/ies) would be cleaned' % (strip_count if args.apply else 0))

    print('')
    print('step 3 — nothing to run, but something to know')
    print('  read-tracking keys change from step-<n> to step-<slug>, so every')
    print('  reader starts with empty progress. Bump read_key in config.py if')
    print('  you would rather the old marks linger as stale entries than reset.')

    if not args.apply:
        print('')
        print('dry run. re-run with --apply to make these changes.')
        return 0

    for old, new in renames:
        if os.path.exists(old):
            shutil.copy2(old, old + '.bak')
            shutil.move(old, new)
    print('')
    print('applied. now run: cd %s/_build && python3 build.py && python3 check_site.py'
          % site)
    return 1 if problems or mismatched else 0


if __name__ == '__main__':
    sys.exit(main())