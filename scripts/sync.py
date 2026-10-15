#!/usr/bin/env python3
"""Brings a site back in line with a repository that has moved on.

    python3 _build/sync.py                  # report only; changes nothing
    python3 _build/sync.py --apply          # rewrite pages.py for the safe cases
    python3 _build/sync.py --apply --yes    # and do not stop to ask

A site is not a one-shot export. The repository keeps moving after the lessons
are written, and until this existed there was no way to find out which lessons
had fallen behind: nothing recorded what a lesson was built from, so "has this
file changed since I wrote the page?" was not merely unchecked, it was
unanswerable.

Five cases, because they need five different answers:

  ADDED      a source file with no lesson. Reported as a candidate. Never
             auto-authored: a lesson is written by reading the repository and
             deciding what a reader needs, and that is the part that carries
             the value. Guessing it here would produce the generated-lesson
             list the skill exists to avoid.

  MODIFIED   the file's contents changed since the last build. Reported with a
             diff, and the lesson is flagged stale. Not rewritten: the prose
             around the code is about that code, and regenerating the block
             without rethinking the page teaches something false.

  RENAMED    the path moved but the contents are byte-identical. Safe to fix
             automatically — `path=` is updated and the lesson is untouched,
             because the lesson is about the contents, not the filename.

  DELETED    the file is gone AND its hash appears nowhere in the repository.
             The lesson is removed from pages.py, its fragment and its
             generated HTML are deleted. Provable, so it is applied.

  ORPHANED   the file is gone, but its hash was never seen in the repository,
             so this scan cannot say whether it was deleted, moved outside the
             scan root, or hand-added without ever existing. Reported loudly
             and left alone. Auto-deleting on an inference is how a sweep turns
             a misconfigured root into a site with half its lessons.

Dry run is the default because the cheapest mistake here is deleting a lesson
somebody spent an hour on, and a dry run costs one command.
"""
import argparse
import difflib
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)
MANIFEST = os.path.join(HERE, 'manifest.json')
CONTENT = os.path.join(HERE, 'content')
PAGES_PY = os.path.join(HERE, 'pages.py')

SKIP_DIRS = {
    '.git', '.hg', '.svn', '.idea', '.vscode', '.vs', '.gradle', '.dart_tool',
    'node_modules', 'vendor', 'bower_components', 'venv', '.venv', 'env',
    '__pycache__', '.mypy_cache', '.pytest_cache', '.ruff_cache', 'dist',
    'build', 'target', 'out', 'obj', '.next', '.nuxt', '.svelte-kit',
    '.output', '.turbo', 'coverage', 'htmlcov', 'Pods', 'DerivedData',
    'third_party', 'external', '.bundle', 'deps', 'elm-stuff', '.serverless',
}

ADDED, MODIFIED, RENAMED, DELETED, ORPHANED, UNKNOWN = (
    'added', 'modified', 'renamed', 'deleted', 'orphaned', 'unknown')


def sha256_file(path):
    try:
        with open(path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def repo_hashes(root):
    """Every readable source file's hash, keyed by repo-relative path.

    Built so DELETED can be distinguished from ORPHANED: a file is only
    definitely gone if its contents are absent from the whole repository. If
    the same bytes are still there under another name, the file was renamed,
    and that is a different — and recoverable — event.
    """
    by_hash, by_path = {}, {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS
                             and not (d.startswith('.') and d != '.github'))
        for fn in sorted(filenames):
            ap = os.path.join(dirpath, fn)
            if os.path.getsize(ap) > 1_000_000:
                continue
            h = sha256_file(ap)
            if h is None:
                continue
            rel = os.path.relpath(ap, root)
            by_hash.setdefault(h, []).append(rel)
            by_path[rel] = h
    return by_path, by_hash


def source_paths(p):
    return [s.strip() for s in (p.get('path') or '').split(',') if s.strip()]


def load_pages():
    """PAGES straight out of pages.py, without importing build.py.

    build.py exits on a bad `n`, and a sync is exactly when a bad `n` is
    likeliest — someone has been hand-editing the list. Importing it would turn
    a reportable condition into a stack trace.
    """
    ns = {}
    with open(PAGES_PY, encoding='utf-8') as f:
        exec(compile(f.read(), PAGES_PY, 'exec'), ns)
    return ns.get('PAGES', [])


def diff_for(root, rel, old_sha):
    """A short unified diff of what changed, or None when it cannot be made."""
    new_path = os.path.join(root, rel)
    if not os.path.exists(new_path) or not old_sha:
        return None
    try:
        old = old_text_from_manifest(rel, old_sha)
        with open(new_path, encoding='utf-8', errors='replace') as f:
            new = f.read()
    except OSError:
        return None
    if old is None:
        return None
    return '\n'.join(list(difflib.unified_diff(
        old.splitlines(), new.splitlines(), 'before', rel, lineterm='',
        n=1))[:40])


_OLD_TEXT = {}


def old_text_from_manifest(rel, sha):
    """Text as it was at build time, when the build kept a copy.

    Only available if snapshot/ exists. Otherwise the diff is skipped and the
    lesson is still reported as modified — knowing *that* it changed is the
    part that matters; the diff is a convenience.
    """
    if not sha:
        return None
    snap = os.path.join(SITE, '_build', 'snapshot', rel)
    if os.path.exists(snap):
        with open(snap, encoding='utf-8', errors='replace') as f:
            return f.read()
    return _OLD_TEXT.get(sha)


def classify(pages, root, repo_by_hash, repo_by_path, prev):
    """Sort every lesson into one of the five cases."""
    rows = []
    claimed = set()
    for i, p in enumerate(pages, 1):
        slug = p.get('slug') or 'step-%d' % i
        rec = prev.get(slug, {})
        paths = source_paths(p)
        paths = [q for q in paths if '*' not in q]
        if not paths:
            rows.append((UNKNOWN, slug, paths, p, rec,
                         'writes no file, or a glob — nothing to compare'))
            continue
        for rel in paths:
            claimed.add(rel)
            now = sha256_file(os.path.join(root, rel))
            was = rec.get('src_sha') if isinstance(rec.get('paths'), list) and rel in rec.get('paths', []) else None
            if was is None:
                was = (rec or {}).get('src_sha')
            if now is not None and was is None:
                rows.append((ADDED, slug, [rel], p, rec,
                             'no manifest entry for this path'))
            elif now is not None and now == was:
                continue
            elif now is not None:
                rows.append((MODIFIED, slug, [rel], p, rec,
                             diff_for(root, rel, was) or 'contents changed'))
            else:
                moved = repo_by_hash.get(was) if was else None
                if moved:
                    rows.append((RENAMED, slug, [rel], p, rec,
                                 'contents now at %s' % moved[0]))
                elif was is None:
                    rows.append((ORPHANED, slug, [rel], p, rec,
                                 'no manifest hash and no such file'))
                else:
                    rows.append((DELETED, slug, [rel], p, rec,
                                 'file gone, contents absent from the repo'))
    for rel in sorted(set(repo_by_path) - claimed):
        rows.append((ADDED, '', [rel], None, None, 'source file with no lesson'))
    return rows


def entry_spans(src):
    """Line ranges of each dict(...) inside PAGES, keyed by slug.

    Uses ast rather than a regex because a page entry can wrap across many
    lines and contain commas, brackets and quotes inside its strings. A regex
    that tried to find `dict(slug='x' ... )` would stop at the first `)` inside
    a lead sentence and leave half an entry behind — which is a syntax error in
    a file the generator is about to import.
    """
    import ast
    tree = ast.parse(src)
    spans = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.List):
            for el in node.value.elts:
                if not isinstance(el, ast.Call):
                    continue
                slug = None
                for kw in el.keywords:
                    if kw.arg == 'slug' and isinstance(kw.value, ast.Constant):
                        slug = kw.value.value
                if slug is None:
                    continue
                # ast gives 1-based inclusive line numbers for the call itself,
                # which already covers every argument of dict(...).
                spans[slug] = (el.lineno - 1, el.end_lineno)
    return spans


def apply_rows(rows, assume_yes):
    """Carry out the two provable cases. Returns True if anything changed.

    DELETED and RENAMED only. ADDED, MODIFIED and ORPHANED are reported and
    left alone on purpose: the first needs a lesson written, the second needs
    the page rethought, and the third cannot be told apart from a lesson whose
    file simply lives outside the scan root.
    """
    removals, renames = [], []
    for kind, slug, paths, p, _rec, detail in rows:
        if kind == DELETED and slug:
            removals.append((slug, paths, detail))
        elif kind == RENAMED and slug and p is not None:
            renames.append((slug, paths[0], str(detail).replace('contents now at ', '')))

    if not removals and not renames:
        print('sync: nothing to apply — the other categories need a human.')
        return False

    if not assume_yes:
        print('')
        for slug, paths, _d in removals:
            print('  will DELETE lesson %r (file %s)' % (slug, ', '.join(paths)))
        for slug, old, new in renames:
            print('  will RENAME %s -> %s for lesson %r' % (old, new, slug))
        answer = input('  proceed? [y/N] ').strip().lower()
        if answer not in ('y', 'yes'):
            print('sync: cancelled, nothing changed.')
            return False

    src = open(PAGES_PY, encoding='utf-8').read()
    spans = entry_spans(src)
    lines = src.splitlines(keepends=True)
    drop = set()
    for slug, _p, _d in removals:
        if slug in spans:
            lo, hi = spans[slug]
            drop.update(range(lo, hi))
    if drop:
        lines = [l for i, l in enumerate(lines) if i not in drop]

    for slug, old, new in renames:
        text = ''.join(lines)
        lo, hi = entry_spans(text).get(slug, (None, None))
        if lo is None:
            continue
        chunk = ''.join(lines[lo:hi])
        if old in chunk:
            lines[lo:hi] = [chunk.replace("'%s'" % old, "'%s'" % new)]

    with open(PAGES_PY, 'w', encoding='utf-8') as f:
        f.write(''.join(lines))

    for slug, _p, _d in removals:
        for path in (os.path.join(CONTENT, '%s.html' % slug),
                     os.path.join(SITE, '%s.html' % slug)):
            if os.path.exists(path):
                os.remove(path)
                print('sync: removed %s' % path)

    print('sync: applied %d deletion(s), %d rename(s). re-run build.py.'
          % (len(removals), len(renames)))
    return True


def render(rows, apply_, assume_yes=False):
    counts = {}
    for kind, _, _, _, _, _ in rows:
        counts[kind] = counts.get(kind, 0) + 1
    print('sync: %s' % ', '.join('%d %s' % (counts[k], k)
                                 for k in (ADDED, MODIFIED, RENAMED, DELETED,
                                           ORPHANED, UNKNOWN) if counts.get(k)))
    print('')
    for kind, slug, paths, _p, _rec, detail in rows:
        print('%s  %s  %s' % (kind.upper().ljust(9),
                              slug or '(no lesson)'.ljust(28),
                              ', '.join(paths)))
        for line in str(detail).splitlines():
            print('          %s' % line)
    print('')
    hard = sum(counts.get(k, 0) for k in (DELETED, ORPHANED))
    if not apply_:
        print('dry run. nothing was changed. re-run with --apply to act.')
        if hard:
            print('%d lesson(s) would be REMOVED. check those paths before '
                  'agreeing.' % hard)
        return 0
    if hard:
        print('%d lesson(s) are DELETED and will be removed; %d ORPHANED and '
              'will NOT be touched — their file is gone but its contents were '
              'never seen in the repository, so this run cannot prove a '
              'deletion. Decide those by hand.'
              % (counts.get(DELETED, 0), counts.get(ORPHANED, 0)))
    apply_rows(rows, assume_yes)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', default=None,
                    help='repository root. Default: config.py source_root.')
    ap.add_argument('--apply', action='store_true', help='act, not just report')
    ap.add_argument('--yes', action='store_true', help='do not stop to ask')
    args = ap.parse_args()

    root = args.root
    if not root:
        cfg = {}
        with open(os.path.join(HERE, 'config.py'), encoding='utf-8') as f:
            exec(compile(f.read(), 'config.py', 'exec'), cfg)
        root = cfg.get('SITE', {}).get('source_root', '')
    if not root or not os.path.isdir(root):
        print('sync: no repository to compare against. pass --root, or set '
              'source_root in _build/config.py', file=sys.stderr)
        return 2

    prev = {}
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding='utf-8') as f:
            data = json.load(f)
        prev = {r['slug']: r for r in data.get('pages', []) if isinstance(r, dict)}

    pages = load_pages()
    repo_by_path, repo_by_hash = repo_hashes(root)
    rows = classify(pages, root, repo_by_hash, repo_by_path, prev)
    return render(rows, args.apply, args.yes)


if __name__ == '__main__':
    sys.exit(main())