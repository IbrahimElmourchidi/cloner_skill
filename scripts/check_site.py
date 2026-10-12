#!/usr/bin/env python3
"""Structure validator. Prints `BAD: none` when everything passes.

    python3 _build/check_site.py              # content fragments, then built pages
    python3 _build/check_site.py --fragments  # authoring check, no build needed
    python3 _build/check_site.py --pages      # only the rendered output

Two things here exist because of how this validator used to behave:

1. Every error carries a file and a line. Tag-balance errors used to be
   reported with no page name, so one stray `</div>` produced a wall of
   indistinguishable failures and you had to guess where it started. The
   parser records getpos() at the point of failure, so the first error in a
   file is now the one you act on.

2. Content fragments are validated BEFORE the built pages. A fragment is
   inserted verbatim into the shell, so an unbalanced fragment is guaranteed
   to cascade into the rendered page. Checking it first means a typo in
   `_build/content/17.html` fails as one clear message instead of a
   same-shaped page plus a dozen lookalikes downstream.

Checks: tag balance, duplicate ids, link targets, in-page anchors, prev/next
agrees with the reading order, data-lang is known, no emoji, every table row
has the cell count its header declares, a code block is not truncated without
saying so, a code block is not an empty container holding only its own path
header, and no fragment is empty at all.

The last three share one property: each is a page that looks built and validates
clean. An empty fragment renders a sidebar, a heading and no body. A code block
cut mid-class reads as the whole file. A block whose body was never filled shows
an empty box where the lesson promised the file. None of them is a malformed
tag, which is why tag balance found none of them.

That last check exists because tag balance cannot see the fault. A row written
as `<tr><td><td>x</td></td><td>y</td></tr>` is perfectly balanced — two opens,
two closes — so a stack-based checker has nothing to report. A browser disagrees:
it closes the first cell where it meets the second, the row renders one column
wider than the header, and every cell to the right of the fault shifts along with
it. The page reads as a styling bug and the markup reads as correct. Counting
cells per row against the header is the only thing that catches it.
"""
import os
import re
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)
CONTENT = os.path.join(HERE, 'content')

VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta',
        'param', 'source', 'track', 'wbr'}

# Languages a <pre class="code" data-lang="…"> may declare. Anything outside
# this set is almost always a typo — `data-lang="dartt"` renders as unhighlighted
# plain text with no other symptom, so it is worth catching mechanically.
# To add one: append the name here AND add a RULES entry in assets/app.js.
# A name listed here but absent from app.js is fine: it renders as plain text.
KNOWN_LANG = {
    # C-like
    'c', 'cpp', 'csharp', 'cs', 'java', 'javascript', 'js', 'typescript', 'ts',
    'tsx', 'jsx', 'react', 'mts', 'go', 'rust', 'rs', 'kotlin', 'kt', 'swift', 'php',
    'scala', 'dart', 'lua', 'zig', 'solidity', 'groovy', 'clojure', 'elixir',
    'erlang', 'haskell', 'ocaml', 'fsharp', 'vb', 'objc', 'd', 'nim', 'crystal',
    'cc', 'hpp', 'hxx', 'cts',
    # hash-comment
    'python', 'py', 'ruby', 'rb', 'bash', 'sh', 'shell', 'zsh', 'fish', 'r',
    'perl', 'pl', 'makefile', 'make', 'cmake', 'dockerfile', 'docker',
    'powershell', 'ps1', 'awk', 'julia', 'jl', 'tcl', 'vbnet',
    # markup, data, config
    'html', 'xml', 'svg', 'vue', 'svelte', 'astro', 'css', 'scss', 'sass',
    'less', 'json', 'json5', 'jsonc', 'yaml', 'yml', 'toml', 'ini', 'cfg',
    'conf', 'properties', 'env', 'dotenv', 'graphql', 'gql', 'proto', 'sql',
    'plsql', 'sqlite', 'markdown', 'md', 'rst', 'tex', 'latex', 'diff', 'patch',
    'text', 'txt', 'plain', 'log', 'csv', 'tsv', 'http', 'reg', 'regex', 'grep',
}

EMOJI = re.compile('[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F02F]')


def _span(attrs):
    """Column span of a cell. Absent or unparseable means one, as in a browser."""
    v = attrs.get('colspan')
    if v is None:
        return 1
    try:
        n = int(str(v).strip())
    except ValueError:
        return 1
    return n if n > 0 else 1


def _rowspan(attrs):
    """Row span of a cell. Absent or unparseable means one, as in a browser."""
    v = attrs.get('rowspan')
    if v is None:
        return 1
    try:
        n = int(str(v).strip())
    except ValueError:
        return 1
    return n if n > 0 else 1


def _brace_delta(text):
    """Net `{` minus `}` in a run of source, ignoring strings and comments.

    Deliberately crude. Dart's string interpolation (`` '${a}' ``) puts braces
    back in after the string is stripped, which can make a balanced block look
    unbalanced — so the strings are stripped first and interpolation braces are
    accepted as lost. That errs towards reporting a block that is fine, which
    costs an author one `// ...` line, rather than missing a block that stops
    mid-class, which costs a reader a wrong conclusion.
    """
    t = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    t = re.sub(r'//[^\n]*', '', t)
    t = re.sub(r"'(?:\\.|[^'\\\n])*'", "''", t)
    t = re.sub(r'"(?:\\.|[^"\\\n])*"', '""', t)
    return t.count('{') - t.count('}')


ELISION = re.compile(r'(?m)^\s*(///|//|\*|/\*)?\s*(\.\.\.|…|omitted|rest of|'
                     r'and more)\s*(\*/)?\s*$')

# A first line that names a source file: "// lib/x.dart", "# x.sql", "x.arb".
PATH_HEADER = re.compile(
    r'^\s*(?://|#)?\s*([\w./-]+\.(?:dart|arb|ya?ml|sql|json|md))\b')


def _has_elision(text):
    """True when the block marks its own gap.

    A line that is nothing but an ellipsis, in any of the comment spellings an
    author reaches for. This is what makes a fragment honest, so it is the one
    thing the check is willing to accept.
    """
    return bool(ELISION.search(text))


class P(HTMLParser):

    def __init__(self, where):
        super().__init__(convert_charrefs=True)
        self.where = where
        self.stack = []
        self.ids, self.links, self.anchors, self.langs = [], [], [], []
        self.svg_open = 0
        self.errors = []
        # Table shape, tracked from the events rather than by re-parsing the
        # source. A nested cell has to be detected here: by the time the markup
        # is a string again the two <td> are indistinguishable from a row that
        # genuinely has one cell whose content starts with a cell.
        self.tables = []      # one entry per open <table>
        self.row = None       # cells seen in the row currently being read
        # Open `<pre class="code">` blocks, as (start line, is_pre/code).
        # Tracked so brace depth can be judged per block rather than per file.
        self.pre_depth = 0
        self.pre_line = 0
        self.pre_tag = None
        self.pre_text = ''      # the block's own source, for marker detection
        self.pre_lang = None    # its data-lang, so `text`/`bash` blocks can opt out
        # Rows still occupied by a rowspan from above, as a per-column countdown.
        # Without this every row a rowspan spans looks one cell short.
        self.pending = []

    def _err(self, msg):
        self.errors.append('%s:%d: %s' % (self.where, self.getpos()[0], msg))

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if 'id' in d:
            self.ids.append(d['id'])
        if tag == 'a' and 'href' in d:
            (self.anchors if d['href'].startswith('#') else self.links).append(d['href'])
        if tag == 'pre' and 'data-lang' in d:
            self.langs.append(d['data-lang'])
        if tag == 'svg':
            self.svg_open += 1
        if tag in ('pre', 'code'):
            # A <pre> without <code> holds source too, but the shell always
            # writes the pair; tracking either keeps a bare <pre> from silently
            # escaping the brace check.
            if self.pre_tag is None:
                self.pre_tag = tag
                self.pre_line = self.getpos()[0]
                self.pre_depth = 0
                self.pre_lang = d.get('data-lang') if tag == 'pre' else None
        self._table_shape(tag, d)
        if tag not in VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag == 'svg':
            self.svg_open -= 1
        self._end_table_shape(tag)
        if tag in VOID:
            return
        if self.pre_tag == tag and tag in ('pre', 'code'):
            self._close_pre(text=self.pre_text)
        if not self.stack:
            self._err('stray </%s>' % tag)
        elif self.stack[-1][0] != tag:
            self._err('</%s> closes <%s> opened on line %d'
                      % (tag, self.stack[-1][0], self.stack[-1][1]))
            self.stack.pop()
        else:
            self.stack.pop()

    def handle_data(self, data):
        if self.pre_tag == 'pre':
            # Only the text between <pre> and <code> is markup-free source.
            self.pre_depth += _brace_delta(data)
            self.pre_text += data
        m = EMOJI.search(data)
        if m:
            self._err('emoji %r in text' % m.group(0))

    # ---- partial code blocks ----------------------------------------------
    #
    # A block that leaves a brace open has either been cut off or is a
    # deliberate fragment, and the reader cannot tell which — so the block has
    # to say. One `// ...` line is the whole cost of that, and it is the only
    # thing standing between "this is the class" and "here is part of it".
    #
    # This is reported rather than fixed. Where an excerpt should end is an
    # authoring judgement: sometimes the honest fix is the elision marker,
    # sometimes it is the rest of the class, and only the author knows which.

    # ---- stub code blocks --------------------------------------------------
    #
    # A block whose entire body is its own path comment. Authoring a "The
    # file" section is two steps — emit the path comment, then fill the body
    # with the code — and the second is easy to miss. When it is, every other
    # check still passes: the nesting is correct, the language is known, and
    # the page shows an empty container where it promised the file. Fifty-five
    # of these shipped together in one site, which is what made it a pattern
    # rather than a one-off slip.
    def _check_stub(self, text):
        if self.pre_lang in ('text', 'bash'):
            # Commentary inside a terminal transcript, or a cross-reference
            # caption naming another file. Neither is a file listing.
            return
        lines = [l for l in text.split('\n') if l.strip()]
        if len(lines) != 1:
            return
        head = lines[0].strip()
        if not PATH_HEADER.match(head):
            return
        self.errors.append(
            '%s:%d: <pre class="code"> holds only its path header (%s) — fill it '
            'with the file, or delete the block'
            % (self.where, self.pre_line, head))

    # ---- partial code blocks ----------------------------------------------
    #
    # A block that leaves a brace open has either been cut off or is a
    # deliberate fragment, and the reader cannot tell which — so the block has
    # to say. One `// ...` line is the whole cost of that, and it is the only
    # thing standing between "this is the class" and "here is part of it".
    def _close_pre(self, text=''):
        if self.pre_depth > 0 and not _has_elision(text):
            self.errors.append(
                '%s:%d: <pre class="code"> ends with %d unclosed brace%s and no '
                'elision marker — a reader cannot tell a fragment from the whole '
                'file. Add a `// ...` line, or show the rest of the declaration.'
                % (self.where, self.pre_line, self.pre_depth,
                   '' if self.pre_depth == 1 else 's'))
        self._check_stub(text)
        self.pre_tag = None
        self.pre_depth = 0
        self.pre_lang = None
        self.pre_text = ''

    # ---- table shape -------------------------------------------------------
    #
    # Two independent faults produce the same symptom, and they need different
    # fixes, so they are reported separately rather than as one "bad row" count:
    #
    #   nested  <tr><td><td>x</td></tr>  — a cell inside a cell. Delete the
    #          inner <td>. The outer one was never meant to be there.
    #   arity   <tr><td>x</td></tr>       — a genuine cell count mismatch. The
    #          author has to decide what belongs in the missing cell, so this
    #          one is never auto-fixable and never should be.

    def _table_shape(self, tag, d):
        if tag == 'table':
            self.tables.append({'cols': None, 'row': None,
                                'line': self.getpos()[0], 'pending': []})
            return
        if not self.tables:
            return
        t = self.tables[-1]
        if tag == 'tr':
            # A row belongs to the innermost table, which is what `tables[-1]`
            # already is — that is why the nested-table case needs no special
            # handling here.
            #
            # `pending` is what earlier rows claimed, so it belongs to this
            # row's width. It is reset at the end of each row, which is where
            # this row's own rowspans are carried forward to the next one.
            t['row'] = []
        elif tag in ('td', 'th'):
            if t['row'] is None:          # a cell with no row: malformed anyway
                t['row'] = []
            # A cell inside a cell is the fault this whole check exists for.
            # self.stack is appended *after* this runs, so the top of the stack
            # is the enclosing tag.
            if self.stack and self.stack[-1][0] in ('td', 'th'):
                self._err('<%s> inside <%s> on line %d — one cell is nested in '
                          'another; delete the inner tag'
                          % (tag, self.stack[-1][0], self.stack[-1][1]))
            t['row'].append(d)

    def _end_table_shape(self, tag):
        if not self.tables:
            return
        t = self.tables[-1]
        if tag == 'tr' and t['row'] is not None:
            # Columns already claimed by a rowspan from an earlier row still
            # count towards this row's width — they are simply not written twice.
            # One `rowspan="3"` cell claims ONE column for two further rows, so
            # `pending` holds how many more rows each claimed column survives.
            span = sum(_span(c) for c in t['row']) + len(t['pending'])
            # The first row of a table defines its arity; only later rows are
            # compared against it. Using `<th>` to find the header instead would
            # miss a table that has no thead, which is legal and common.
            if t['cols'] is None:
                t['cols'] = span
            elif span != t['cols']:
                self._err('<tr> has %d cell%s but the first row of its table '
                          'declares %d (table opened line %d)'
                          % (span, '' if span == 1 else 's', t['cols'],
                             t['line']))
            # Age the claims already in flight, and add this row's own. The new
            # ones start at rowspan-1 because the row that declares them has
            # already been counted.
            aged = [p - 1 for p in t['pending'] if p > 1]
            fresh = [_rowspan(c) - 1 for c in t['row'] if _rowspan(c) > 1]
            t['pending'] = fresh + aged
            t['row'] = None
        elif tag == 'table':
            self.tables.pop()


def parse_file(path, where, bad):
    p = P(where)
    with open(path, encoding='utf-8') as f:
        p.feed(f.read())
    for tag, line in p.stack:
        p.errors.append('%s:%d: <%s> never closed' % (where, line, tag))
    if p.svg_open != 0:
        p.errors.append('%s: unbalanced <svg> (%d open)' % (where, p.svg_open))
    dupes = sorted({i for i in p.ids if p.ids.count(i) > 1})
    if dupes:
        p.errors.append('%s: duplicate id(s) %s' % (where, ', '.join(dupes)))
    for lg in p.langs:
        if lg not in KNOWN_LANG:
            p.errors.append('%s: unknown data-lang "%s" (add it to KNOWN_LANG in '
                            'check_site.py)' % (where, lg))
    bad.extend(p.errors)
    return p


def check_fragments(bad):
    """A fragment is a body slice, not a document: no <html>, no <head>.

    Also cross-references pages.py, so "pages.py declares step 7 but there is
    no content/07.html" is caught here with a filename, rather than by build.py
    aborting partway through a rebuild.
    """
    if not os.path.isdir(CONTENT):
        bad.append('no _build/content/ directory')
        return []
    on_disk = {f for f in os.listdir(CONTENT) if f.endswith('.html')}
    if not on_disk:
        bad.append('_build/content/ is empty')
        return []

    # The filename is derived from n, not from slug: two lessons numbered 7 and
    # 8 both zero-pad fine, but a lesson numbered 1000 would not, so allow both
    # spellings when matching.
    try:
        sys.path.insert(0, HERE)
        from pages import PAGES, APPENDIX
        expected = set()
        for p in PAGES:
            expected.add('%02d.html' % p['n'])
        for a in APPENDIX:
            expected.add('%s.html' % a['slug'])
        for want in sorted(expected):
            if want not in on_disk:
                bad.append('pages.py declares a page with no fragment: '
                           'content/%s' % want)
        for extra in sorted(on_disk - expected):
            bad.append('content/%s has no matching entry in pages.py '
                       '(renamed slug? leftover fragment?)' % extra)
    except Exception as exc:
        bad.append('cannot import pages.py (%s) — cross-check skipped' % exc)

    for f in sorted(on_disk):
        src = open(os.path.join(CONTENT, f), encoding='utf-8').read()
        # An empty fragment is the common case behind the <h2> check below, and
        # the only one where the filename gives no clue what went wrong, so it
        # gets its own message. A file truncated by an interrupted write used to
        # sail through every other check and render a page with a sidebar, a
        # heading and no body at all.
        if not src.strip():
            bad.append('content/%s: is EMPTY (0 bytes or whitespace) — the page '
                       'would build with no body; re-author it' % f)
            continue
        p = parse_file(os.path.join(CONTENT, f), 'content/' + f, bad)
        if not re.search(r'<h2', src):
            bad.append('content/%s: starts without an <h2>' % f)
    return sorted(on_disk)


def order():
    """Reading order: index.html, the numbered lessons, then the appendix.

    Lesson order comes from the numeric filename prefix, which build.py derives
    from pages.py's `n`.

    Appendix order comes from the APPENDIX list in pages.py, NOT from sorting
    the filenames. Sorting looks equivalent and is not: the builder emits
    appendix pages in declaration order, so an appendix whose slugs are not
    alphabetically ordered builds one sequence and validates another, and the
    result is a wall of prev/next errors that look like a generator bug.
    """
    sys.path.insert(0, HERE)
    try:
        from pages import APPENDIX
        expected = [a['slug'] + '.html' for a in APPENDIX]
    except Exception as exc:                       # pages.py missing or broken
        print('check_site: cannot import pages.py (%s); falling back to '
              'filename order for the appendix' % exc, file=sys.stderr)
        expected = None

    nums, on_disk = [], []
    for f in os.listdir(SITE):
        m = re.match(r'^(\d+)-.*\.html$', f)
        if m:
            nums.append((int(m.group(1)), f))
        elif f.startswith('appendix-'):
            on_disk.append(f)

    apx = [f for f in (expected or []) if f in on_disk]
    # anything on disk that pages.py no longer claims is a stale build artefact;
    # build.py prunes these, so reaching here means the build was not re-run.
    for f in sorted(set(on_disk) - set(apx)):
        print('check_site: %s is on disk but not in APPENDIX — re-run build.py '
              '(it prunes stale pages)' % f)
    return (['index.html'] + [f for _, f in sorted(nums)], apx)


def check_pages(bad):
    lessons, appendix = order()
    pages = lessons + appendix
    n_lessons = len(lessons)

    for page in pages:
        path = os.path.join(SITE, page)
        if not os.path.exists(path):
            bad.append('%s: missing' % page)
            continue
        p = parse_file(path, page, bad)
        src = open(path, encoding='utf-8').read()
        if '<h1>' not in src:
            bad.append('%s: no <h1>' % page)
        for a in p.anchors:
            if a[1:] not in p.ids:
                bad.append('%s: anchor %s does not resolve' % (page, a))
        for l in p.links:
            if l.startswith(('http', 'mailto')):
                continue
            target = l.split('#')[0]
            if target and not os.path.exists(os.path.join(SITE, target)):
                bad.append('%s: link target missing -> %s' % (page, l))

    # prev/next must agree with the reading order
    chains = [(i, pg) for i, pg in enumerate(pages) if pg in lessons]
    chains += [(i, pg) for i, pg in enumerate(pages) if pg in appendix]
    for i, page in chains:
        if page == 'index.html':
            continue
        in_appendix = page in appendix
        base = i - (n_lessons if in_appendix else 0)
        src = open(os.path.join(SITE, page), encoding='utf-8').read()
        if in_appendix:
            want_prev = pages[n_lessons + base - 1] if base > 0 else 'index.html'
            want_next = pages[n_lessons + base + 1] if base + 1 < len(appendix) else None
        else:
            want_prev = pages[i - 1]
            want_next = pages[i + 1] if i + 1 < n_lessons else None
        got_prev = re.search(r'<a class="pv" href="([^"]+)"', src)
        got_next = re.search(r'<a class="nx" href="([^"]+)"', src)
        if not got_prev or got_prev.group(1) != want_prev:
            bad.append('%s: prev is %s, expected %s'
                       % (page, got_prev.group(1) if got_prev else None, want_prev))
        if want_next is None:
            if got_next:
                bad.append('%s: is last but has a next link' % page)
        elif not got_next or got_next.group(1) != want_next:
            bad.append('%s: next is %s, expected %s'
                       % (page, got_next.group(1) if got_next else None, want_next))

    # every page must be reachable from the index
    idx_path = os.path.join(SITE, 'index.html')
    if not os.path.exists(idx_path):
        bad.append('index.html: missing — run build.py then index.py')
        return pages
    idx = open(idx_path, encoding='utf-8').read()
    for page in pages:
        if page != 'index.html' and 'href="%s"' % page not in idx:
            bad.append('index: does not link to %s' % page)
    return pages


def main():
    args = sys.argv[1:]
    frag_only = '--fragments' in args
    pages_only = '--pages' in args
    bad = []

    frags = None
    if not pages_only:
        frags = check_fragments(bad)
        # Fragments feed the pages verbatim, so a broken fragment guarantees a
        # broken page. Stop here rather than printing the same failure twice.
        if bad:
            report(bad, frags or [], 0)
            return 1

    pages = [] if frag_only else check_pages(bad)
    langs = set()
    if not frag_only:
        for page in pages:
            fp = os.path.join(SITE, page)
            if os.path.exists(fp):
                p = P(page)
                with open(fp, encoding='utf-8') as f:
                    p.feed(f.read())
                langs |= set(p.langs)

    report(bad, frags or [], pages, langs)
    return 1 if bad else 0


def report(bad, frags, pages, langs=None):
    """Stats first, verdict last — `BAD: none` is the line to grep for."""
    stats = []
    if frags:
        stats.append('fragments: %d' % len(frags))
    if pages:
        stats.append('pages: %d' % len(pages))
    if langs is not None:
        stats.append('langs: %d' % len(langs))
    if stats:
        print('   '.join(stats))
    if bad:
        print('BAD:')
        for b in bad:
            print('  ' + b)
        return
    print('BAD: none')


if __name__ == '__main__':
    sys.exit(main())