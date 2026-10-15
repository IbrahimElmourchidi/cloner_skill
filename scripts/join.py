#!/usr/bin/env python3
"""Assemble a large curriculum from `_parts/*.py` into `pages.py`.

    python3 join.py                    # write pages.py from the parts
    python3 join.py --check            # validate, change nothing
    python3 join.py --root ~/code/p    # also check every path= exists
    python3 join.py --split 40         # the other direction: pages.py -> parts

**Why this exists.** A curriculum for a large project is a list of a few hundred
`dict(...)` entries, and that is the one artefact in `_build/` that cannot be
written incrementally. Every other file here is small: a fragment, a config, a
script. `pages.py` at 300 steps is around sixty kilobytes, and it is produced in
a single pass, before any lesson exists, by the step whose whole job is to hold
the entire shape of the site in mind at once. Emitting it that way works until
the list stops fitting in one edit, and then the only way to change lesson 40 is
to read and rewrite the whole file — which is how a curriculum gets re-emitted
from a stale copy and loses an entry nobody notices.

Splitting it into ordered parts makes it appendable. Lesson 40 lives in
`part02.py`, alongside its neighbours, and adding lesson 241 means writing one
more part file. The list is still one list: `join.py` concatenates the parts and
writes `pages.py` whole, so nothing downstream can tell.

**pages.py becomes derived.** That is the trade, and it is the whole trade: once
the parts exist, `pages.py` is an output. Edit the parts. `--split` goes the
other way if you change your mind, and it leaves `pages.py` alone.

Everything outside the `PAGES = [...]` span is preserved byte for byte — the
module docstring that documents the fields, and the `APPENDIX = [...]` after it.
Only the list body is regenerated.

This does not import `build.py`. `build.py` imports `pages` at module scope to
get `PAGES`, which is precisely the file this script produces, so importing it
here would be circular. That means the field rules below are a second copy of
what `build.py` and `check_site.py` enforce — so this script checks only what
is cheap and certain at plan time, and leaves the rest to the real validators.
The overlap that matters (`n=` being derived, `why` being present) is checked
here because a curriculum is assembled long before anything renders, and finding
a typo at step 40 of a batch costs a whole batch. Everything else waits.
"""
import argparse
import ast
import os
import re
import sys

# `PAGES = [` and the `]` that closes it, each at the start of a line. Both
# anchors are the generated file's own convention, so matching them is stable —
# but a page entry can contain a `]` inside a string, which is why the closing
# bracket has to be at column zero rather than merely the next `]`.
OPEN_PAGES = re.compile(r'^PAGES\s*=\s*\[', re.M)
CLOSE_PAGES = re.compile(r'^\]', re.M)

# A slug names a filename, a URL and a saved-progress key: lowercase letters,
# digits and dashes, nothing that could escape the directory. Matches the rule
# in SKILL.md's `slug` invariant.
SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$')

# A slug that opens with a number and a separator is a slug that encodes a step
# number. The number is derived from position now, so the slug stops matching
# its step the moment a lesson is inserted — and nothing reports it, because
# the filename, the URL and the progress key are all still perfectly valid.
# Separately checked from the charset because the two fixes are different: one
# is a typo, the other is a decision that used to be encouraged.
NUMBER_PREFIX_RE = re.compile(r'^\d+[-_]')

REQUIRED = ('slug', 'nav', 'h1', 'lead', 'why')


class Problems:
    """Collects everything wrong, so one run reports all of it.

    A validator that stops at the first error is a validator that gets run
    again. Every one of these is independent of every other, so there is no
    reason to make the author discover them one rebuild at a time.
    """

    def __init__(self):
        self.errors = []
        self.notes = []

    def error(self, msg):
        self.errors.append(msg)

    def note(self, msg):
        self.notes.append(msg)

    def __bool__(self):
        return bool(self.errors)


def fail(problems, out=sys.stderr):
    """Print what is wrong and say what to do about it, once."""
    for m in problems.errors:
        print('  %s' % m, file=out)
    print('\n%d problem%s. pages.py not written.'
          % (len(problems.errors), '' if len(problems.errors) == 1 else 's'),
          file=out)


def read_parts(parts_dir, problems):
    """`_parts/*.py` in filename order, with the ordering made explicit.

    Filename order is the reading order, so the names have to sort the way the
    curriculum runs. `part10.py` sorts before `part2.py`, which would silently
    move ninety lessons. An unpadded name is therefore a hard error rather than
    a warning: it is not wrong yet, but it is one lesson away from being wrong,
    and nothing else in the toolchain would catch it.
    """
    if not os.path.isdir(parts_dir):
        problems.error(
            'no %s directory. Write the lessons as %s/NN.py, one dict per entry,\n'
            '  or run --split to explode an existing pages.py into parts.'
            % (parts_dir, os.path.basename(os.path.dirname(parts_dir) or '_build')))
        return []

    files = sorted(f for f in os.listdir(parts_dir)
                   if f.endswith('.py') and not f.startswith('_'))
    if not files:
        problems.error('%s holds no .py files. Part files are named NN.py.'
                       % parts_dir)
        return []

    seen = {}
    for f in files:
        stem = f[:-3]
        if not re.match(r'^\d\d+$', stem):
            problems.error(
                '%s is not zero-padded. Part files are ordered by filename, so\n'
                '  part10 would sort before part2 and move ninety lessons. Rename\n'
                '  it part%02d.py.' % (f, len(files)))
            continue
        if stem in seen:
            problems.error('%s and %s share the number %s.'
                           % (seen[stem], f, stem))
            continue
        seen[stem] = f
    return [os.path.join(parts_dir, seen[s]) for s in sorted(seen)]


def parse_parts(paths, problems):
    """Each part's text, plus the entries it holds.

    A part is a fragment — a run of `dict(...)` entries, not a module — so it is
    parsed by wrapping it in the list it is about to become. That way a part
    with a missing bracket, a stray top-level statement or a trailing comma
    problem fails here, with the filename, rather than in `pages.py` later with
    a line number pointing at a concatenation of four other files.
    """
    out = []
    for path in paths:
        name = os.path.basename(path)
        text = open(path, encoding='utf-8').read()
        if not text.strip():
            problems.error('%s is empty. Remove it, or give it lessons.' % name)
            out.append((name, text, []))
            continue
        try:
            tree = ast.parse('LIST = [\n' + text + '\n]')
        except SyntaxError as exc:
            problems.error('%s does not parse as a list of entries: %s (line %s)'
                           % (name, exc.msg, exc.lineno))
            out.append((name, text, []))
            continue
        value = tree.body[0].value
        if not isinstance(value, ast.List):
            problems.error('%s did not produce a list.' % name)
            out.append((name, text, []))
            continue
        entries = []
        for node in value.elts:
            if not _is_dict_call(node):
                problems.error('%s holds something that is not a dict(...) entry.'
                               % name)
                continue
            entries.append(_literal(node, problems, name))
        out.append((name, text, entries))
    return out


def _is_dict_call(node):
    """`dict(slug=…)` is a Call, not a Dict — the only shape an entry may take.

    A bare `{…}` literal parses as a Dict and would be accepted by a looser
    check, then reach build.py, which does `dict(p)` on each entry and would
    work anyway. So this is about refusing to support two spellings: the
    template shows one, and one spelling is one fewer thing to get wrong across
    a few hundred entries.
    """
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == 'dict'
            and not node.args)


def _literal(node, problems, name):
    """Read an entry's keywords as plain Python values.

    `stubs=[dict(…)]` is a list of calls, which `ast.literal_eval` refuses, so
    the walk is done by hand and allows exactly what a curriculum entry needs: a
    constant, a list or tuple of them, and nested `dict(…)`. Anything else —
    a name, a call, a comprehension — raises, because a computed value in
    `pages.py` means the lesson list depends on something no reader of pages.py
    can see, and the validators read it by name.
    """
    out = {}
    for kw in node.keywords:
        if kw.arg is None:                  # **something
            problems.error('%s: an entry uses ** unpacking. Every key in pages.py\n'
                           '  has to be readable by name — join, build and the\n'
                           '  validator all read them that way.' % name)
            continue
        try:
            out[kw.arg] = _value(kw.value)
        except ValueError:
            problems.error('%s: the value of %s= is not a literal.\n'
                           '  pages.py is read by name, so every value has to be\n'
                           '  written out rather than computed.' % (name, kw.arg))
    return out


def _value(node):
    """One literal, extended to cover the nested dicts a stub is made of."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_value(e) for e in node.elts]
    if _is_dict_call(node):
        out = {}
        for kw in node.keywords:
            if kw.arg is None:
                raise ValueError('** unpacking')
            out[kw.arg] = _value(kw.value)
        return out
    raise ValueError('not a literal')


def check_entries(parts, problems, root=None):
    """The rules that are cheap and certain at plan time.

    Duplicates are the ones that matter. A curriculum assembled from five files
    by five different edits is exactly where a slug or a path gets written
    twice, and both duplicates are silent: the build renders, the validator
    passes, and the reader finds two lessons claiming to write one file, or two
    pages fighting over one progress marker.
    """
    slugs, paths = {}, {}
    total = 0
    for name, _text, entries in parts:
        for entry in entries:
            total += 1
            where = '%s: %s' % (name, entry.get('slug', '<no slug>'))
            for key in REQUIRED:
                if key not in entry:
                    problems.error('%s has no %s.' % (where, key))
            if 'n' in entry:
                problems.error(
                    '%s declares n=%r. The step number is derived from position,\n'
                    '  so writing it is not allowed — and one that disagrees with\n'
                    '  the position stops the build.'
                    % (where, entry['n']))

            slug = entry.get('slug')
            if not isinstance(slug, str) or not slug:
                problems.error('%s has no usable slug.' % where)
            elif not SLUG_RE.match(slug):
                problems.error(
                    '%s: %r is not a usable slug. Lowercase letters, digits and\n'
                    '  dashes only, starting and ending with one of those.'
                    % (where, slug))
            elif NUMBER_PREFIX_RE.match(slug):
                problems.error(
                    '%s: slug %r starts with a number.\n'
                    '  The step number is derived from position, so a slug that\n'
                    '  encodes one stops matching its step the moment a lesson is\n'
                    '  inserted — and nothing reports it, because the filename,\n'
                    '  the URL and the progress key all stay valid. Name it for\n'
                    '  what it is: %r.'
                    % (where, slug, slug.split('-', 1)[-1] or 'the-file'))
            elif slug in slugs:
                problems.error('%s: slug %r is already used by %s.'
                               % (where, slug, slugs[slug]))
            else:
                slugs[slug] = where

            path = entry.get('path')
            if path is None:
                continue                        # a command-only step is allowed
            if not isinstance(path, str):
                problems.error('%s: path is not a string.' % where)
            elif path in paths:
                problems.error(
                    '%s: path %r is already written by %s.\n'
                    '  One lesson is one file. Two lessons claiming one path means\n'
                    '  one of them overwrites the other as the reader follows the\n'
                    '  order.' % (where, path, paths[path]))
            else:
                paths[path] = where

    if root:
        root = os.path.abspath(os.path.expanduser(root))
        missing = []
        for entry_path in sorted(paths):
            if not os.path.exists(os.path.join(root, entry_path)):
                missing.append((entry_path, paths[entry_path]))
        for entry_path, where in missing[:25]:
            problems.error('%s: %s does not exist under --root %s.'
                           % (where, entry_path, root))
        if len(missing) > 25:
            problems.error('... and %d more paths that do not exist.'
                           % (len(missing) - 25))
    return total


def render(parts):
    """The list body, exactly as the parts wrote it.

    Reformatting would be a small kindness with a large bill: it means every
    rebuild fights the author over whitespace, and it would throw away the
    comments they wrote inside a part to mark a decision. Parts are copied
    verbatim and separated by one blank line, so the boundary is still visible
    in `pages.py`.
    """
    chunks = []
    for _name, text, entries in parts:
        if not entries:
            continue
        chunks.append(text.strip('\n'))
    return '\n\n'.join(chunks)


def splice(existing, body):
    """Put `body` inside `pages.py`'s `PAGES = [...]`, keeping the rest.

    The head carries the docstring that documents every field, and the tail
    carries `APPENDIX` — which is hand-edited, occasionally, by a person who has
    no reason to know that a parts directory exists. Both are preserved byte for
    byte, so joining a curriculum never disturbs anything outside the list.
    """
    m = OPEN_PAGES.search(existing)
    if not m:
        return None, 'pages.py has no `PAGES = [` line.'
    cm = CLOSE_PAGES.search(existing, m.end())
    if not cm:
        return None, ('pages.py has `PAGES = [` but no closing `]` at the start of '
                      'a line. Refusing to guess where the list ends.')
    return existing[:m.end()] + '\n' + body + '\n' + existing[cm.start():], None


def split(existing, per_part, out_dir):
    """The other direction: `pages.py` -> parts, for when you want to start over.

    The source text of each entry is lifted out of the AST, so comments between
    entries are dropped — a split is a structural change, not a reformat, and
    the parts it writes are clean rather than faithful. `pages.py` is left
    exactly as it was: this produces parts, it does not install them.
    """
    m = OPEN_PAGES.search(existing)
    if not m:
        print('pages.py has no `PAGES = [` line.', file=sys.stderr)
        return 1
    cm = CLOSE_PAGES.search(existing, m.end())
    if not cm:
        print('pages.py has no closing `]` at the start of a line.', file=sys.stderr)
        return 1
    # The AST records positions in the string that was parsed, not in pages.py,
    # so the wrapped copy is kept and read back from. Reading segments from
    # `existing` instead silently returns the wrong text at every offset.
    wrapped = 'LIST = [\n' + existing[m.end():cm.start()] + '\n]'
    try:
        value = ast.parse(wrapped).body[0].value
    except SyntaxError as exc:
        print('pages.py does not parse: %s (line %s)' % (exc.msg, exc.lineno),
              file=sys.stderr)
        return 1

    os.makedirs(out_dir, exist_ok=True)
    items = list(value.elts)
    written = 0
    for i in range(0, len(items), per_part):
        chunk = items[i:i + per_part]
        name = '%02d.py' % (i // per_part + 1)
        path = os.path.join(out_dir, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write('# Lessons %d-%d. Concatenated in filename order by\n'
                    '# scripts/join.py — edit here, not in pages.py.\n\n'
                    % (i + 1, i + len(chunk)))
            for node in chunk:
                f.write(ast.get_source_segment(wrapped, node).rstrip() + ',\n')
        written += 1
    print('wrote %d part%s to %s, covering %d lesson%s'
          % (written, '' if written == 1 else 's', out_dir, len(items),
             '' if len(items) == 1 else 's'))
    print('pages.py is unchanged. Re-run join.py to adopt the parts.')
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('build_dir', nargs='?', default=None,
                    help='the site\'s _build directory '
                         '(default: docs/site/_build under the current directory)')
    ap.add_argument('--check', action='store_true',
                    help='report problems and exit non-zero without writing')
    ap.add_argument('--root', metavar='DIR', default=None,
                    help='repository root; every path= must exist under it')
    ap.add_argument('--parts', metavar='DIR', default=None,
                    help='where the parts live (default: <build_dir>/_parts)')
    ap.add_argument('--split', metavar='N', type=int, default=None,
                    help='explode pages.py into parts of N entries instead, and '
                         'leave pages.py alone')
    args = ap.parse_args()

    here = os.getcwd()
    build_dir = args.build_dir or os.path.join(here, 'docs', 'site', '_build')
    pages_path = os.path.join(build_dir, 'pages.py')
    parts_dir = args.parts or os.path.join(build_dir, '_parts')

    if not os.path.exists(pages_path):
        print('join: no pages.py at %s\n'
              '  Run init first — it writes the template this script edits.'
              % pages_path, file=sys.stderr)
        return 1
    existing = open(pages_path, encoding='utf-8').read()

    if args.split:
        return split(existing, max(1, args.split), parts_dir)

    problems = Problems()
    paths = read_parts(parts_dir, problems)
    parts = parse_parts(paths, problems) if paths else []
    total = check_entries(parts, problems, args.root)

    first = next((e['slug'] for _n, _t, es in parts for e in es
                  if isinstance(e.get('slug'), str)), None)
    last = None
    for _n, _t, es in parts:
        for e in es:
            if isinstance(e.get('slug'), str):
                last = e['slug']

    print('%d part%s, %d lesson%s'
          % (len(parts), '' if len(parts) == 1 else 's', total,
             '' if total == 1 else 's'))
    if first:
        print('  first  %s' % first)
        print('  last   %s' % last)
    for m in problems.notes:
        print('note: %s' % m)
    if problems:
        fail(problems)
        return 1
    print('BAD: none')

    if args.check:
        print('check only — pages.py not written.')
        return 0

    body = render(parts)
    if not body:
        print('join: the parts hold no entries, so there is nothing to write.\n'
              '  Refusing to empty pages.py.', file=sys.stderr)
        return 1
    merged, err = splice(existing, body)
    if err:
        print('join: %s' % err, file=sys.stderr)
        return 1
    if merged == existing:
        print('pages.py is already up to date.')
        return 0
    with open(pages_path, 'w', encoding='utf-8') as f:
        f.write(merged)
    print('wrote %s — %d lessons from %d part%s'
          % (pages_path, total, len(parts), '' if len(parts) == 1 else 's'))
    print('Edit the parts, not pages.py. `--split` goes back.')
    return 0


if __name__ == '__main__':
    sys.exit(main())