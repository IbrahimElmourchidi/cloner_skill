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
   `_build/content/<slug>.html` fails as one clear message instead of a
   same-shaped page plus a dozen lookalikes downstream.

Checks: tag balance, no heading directly inside a list, duplicate ids, link
targets, in-page anchors, prev/next agrees with the reading order, the sidebar's
numbers agree with the step order, data-lang is known, no emoji, every table row
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

# A list may only contain <li> (plus a couple of inert exceptions). A heading
# written straight into one is invalid HTML, and the sidebar used to do exactly
# that: it injected `<h4>` between `<li>` elements to label each phase. It looked
# right because the CSS set `list-style:none`, which hides the symptom — the
# bullets a strict parser objects to — while the fault is real. Assistive
# technology is handed a broken list. Groups now render as <details>, so a
# heading can only reappear here if someone hand-writes one into the markup.
HEADINGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
LIST_TAGS = {'ol', 'ul'}


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
        if tag in HEADINGS and self.stack and self.stack[-1][0] in LIST_TAGS:
            self._err('<%s> is a direct child of <%s>, which may only contain '
                      '<li> — put it in a <details><summary> or wrap it' % (
                          tag, self.stack[-1][0]))
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

    Also cross-references pages.py, so "pages.py declares a lesson but there
    is no fragment for that slug" is caught here with a filename, rather than
    by build.py aborting partway through a rebuild.
    """
    if not os.path.isdir(CONTENT):
        bad.append('no _build/content/ directory')
        return []
    on_disk = {f for f in os.listdir(CONTENT) if f.endswith('.html')}
    if not on_disk:
        bad.append('_build/content/ is empty')
        return []

    # The filename is derived from the slug, not from n. It used to be derived
    # from n, which made the fragment's name a function of its position: a
    # reorder would hand each lesson a different body without anything
    # complaining. See build.py.
    try:
        sys.path.insert(0, HERE)
        from pages import PAGES, APPENDIX
        expected = set()
        for p in PAGES:
            expected.add('%s.html' % p['slug'])
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


def menu_numbering():
    """The sidebar's number is derived from the item's index; prove it agrees.

    menu.py deliberately computes the displayed number instead of reading
    pages.py's `n`, so inserting a lesson cannot leave a row showing a stale
    number. That is only true while the two agree — if pages.py's `n` ever stops
    being 1..N in order, the sidebar would silently renumber the whole site
    around a different sequence than the step pills and the prev/next chain.

    `n` is now *derived* from list position by build.py rather than authored, so
    the remaining job here is to prove the two still agree, and that each row's
    read-tracking key matches the slug it links to. The key used to be
    `step-<n>`, which meant it tracked the number and a reorder invalidated
    every reader's saved progress — the exact thing it was documented as
    preventing.
    """
    sys.path.insert(0, HERE)
    try:
        from build import PAGES
        import menu
    except Exception as exc:
        print('check_site: cannot import menu/pages (%s)' % exc, file=sys.stderr)
        return []

    bad = []
    ordered = PAGES
    for i, p in enumerate(ordered):
        if p.get('n') != i + 1:
            bad.append('pages.py: %r is at position %d but reports n=%r — the '
                       'sidebar would number it %02d while the pill and the '
                       'prev/next chain use %r'
                       % (p['slug'], i + 1, p.get('n'), i + 1, p.get('n')))

    # And the rendered menu must carry the right number AND the right key.
    for g in menu.build_groups(PAGES, []):
        for item in g.items:
            at = int(item.number) - 1
            if 0 <= at < len(ordered):
                want = 'step-%s' % ordered[at]['slug']
                if item.page_id != want:
                    bad.append('menu: row %s links %s but its read-tracking key '
                               'is %s — should be %s' % (item.number, item.href,
                                                          item.page_id, want))
    return bad


def order():
    """Reading order: index.html, the numbered lessons, then the appendix.

    Lesson order comes from pages.py, in list order. It used to come from the
    numeric filename prefix, which only worked while slugs were required to
    start with the step number — a coupling that existed so that sorting
    filenames recovered the order. Slugs no longer carry a number prefix, so
    filename order and reading order are no longer the same thing, and taking
    order from the filenames would quietly reorder the site the moment one slug
    stopped looking like a number.

    Appendix order comes from the APPENDIX list in pages.py, NOT from sorting
    the filenames. Sorting looks equivalent and is not: the builder emits
    appendix pages in declaration order, so an appendix whose slugs are not
    alphabetically ordered builds one sequence and validates another, and the
    result is a wall of prev/next errors that look like a generator bug.
    """
    sys.path.insert(0, HERE)
    lessons = []
    try:
        from build import PAGES
        expected = ['%s.html' % p['slug'] for p in PAGES]
    except Exception as exc:                       # pages.py missing or broken
        print('check_site: cannot import pages.py (%s); falling back to '
              'directory order for the lessons' % exc, file=sys.stderr)
        expected = None

    on_disk = {f for f in os.listdir(SITE) if f.endswith('.html')}
    try:
        from pages import APPENDIX
        apx = [a['slug'] + '.html' for a in APPENDIX]
    except Exception as exc:
        print('check_site: cannot import APPENDIX (%s)' % exc, file=sys.stderr)
        apx = []

    if expected is not None:
        for f in expected:
            if f not in on_disk:
                bad_msg = 'lesson %s is declared in pages.py but not on disk' % f
                print('check_site: ' + bad_msg)
            else:
                lessons.append(f)
        stray = sorted(on_disk - set(expected) - set(apx) - {'index.html'})
        for f in stray:
            print('check_site: %s is on disk but not in pages.py — a stale '
                  'build artefact, or a lesson that was deleted' % f)
    else:
        # pages.py is unimportable, so fall back to whatever order the
        # filenames give. Only correct for number-prefixed slugs, which is the
        # pre-v2 convention; it is a degraded path for a broken build, not a
        # supported layout.
        lessons = [f for _, f in sorted(
            (int(re.match(r'^(\d+)-', f).group(1)), f) for f in on_disk
            if re.match(r'^\d+-.*\.html$', f))]

    apx_present = [f for f in apx if f in on_disk]
    return (['index.html'] + lessons, apx_present)


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


# ---------------------------------------------------------------------------
# Checks added in v2.0. They are real failures, but every existing site fails
# all three, so they report as WARN until a site opts in.
#
# The reason is that these three encode rules nobody was told: the ordering was
# never checked, fragments were allowed to be trimmed, and `why` was optional.
# Turning them on for an existing 500-lesson site would report thousands of
# problems at once, which is indistinguishable from a broken validator, and the
# reflex would be to delete the checks rather than fix the lessons. WARN keeps
# them visible without making that reflex available.
#
# CLONE_SITE_STRICT=1, or `check_site.py --strict`, promotes them to failures.
# ---------------------------------------------------------------------------
STRICT = os.environ.get('CLONE_SITE_STRICT') == '1' or '--strict' in sys.argv

CODE_CLASS = re.compile(
    r'^\s*(?:@[\w.]+\s*)*(?:public\s+|internal\s+|private\s+|abstract\s+|final\s+|'
    r'sealed\s+|open\s+|export\s+|pub\s+|async\s+)*'
    r'(class|interface|struct|enum|trait|impl|mixin|extension|typedef|type|record|'
    r'actor|object|module|namespace|protocol|def|fn|func|function|sub)\s+'
    r'([A-Za-z_][\w]*)', re.M)

IDENT = re.compile(r'\b([A-Z][A-Za-z0-9_]{2,})\b')


def declared_names(text):
    """Type and function names a code block appears to define."""
    return {m.group(2) for m in CODE_CLASS.finditer(text)}


def code_blocks(src):
    return re.findall(r'<pre class="code"[^>]*>(.*?)</pre>', src, re.S)


def unescape_code(block):
    block = re.sub(r'</?code[^>]*>', '', block)
    for a, b in (('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"'),
                 ('&#39;', "'"), ('&apos;', "'"), ('&amp;', '&')):
        block = block.replace(a, b)
    return block.replace('&nbsp;', ' ')


def dependency_order(bad, warn):
    """No lesson may use a name that a LATER lesson defines.

    The lesson order is the site's spine: a reader follows it and writes each
    file as they go. A step that references a class introduced three steps
    later is not a reading inconvenience, it is a step that cannot be
    completed — the code does not compile at the point the reader is told to
    write it.

    This is a heuristic and says so. It collects names each lesson's code block
    defines, then reports any name an earlier lesson *uses* that only a later
    one defines. It cannot see a name from outside the set taught here, and it
    will call an ordinary same-named local something it is not. Both errors
    point the reader at a real coincidence, which is the acceptable direction:
    a false positive costs one look, a false negative is a broken step.
    """
    try:
        sys.path.insert(0, HERE)
        from build import PAGES          # normalised: `n` is the list position
    except Exception as exc:
        bad.append('cannot import build/pages (%s) — dependency order skipped' % exc)
        return

    order, first_use = [], {}
    for p in PAGES:
        frag = os.path.join(CONTENT, '%s.html' % p['slug'])
        if not os.path.exists(frag):
            continue
        with open(frag, encoding='utf-8') as f:
            text = '\n'.join(unescape_code(b) for b in code_blocks(f.read()))
        defines = declared_names(text)
        uses = {i for i in IDENT.findall(text)} - defines
        for name in sorted(uses):
            if name not in first_use:
                first_use[name] = p['n']
        order.append((p['n'], p['slug'], defines))

    later = {}
    for n, slug, defines in order:
        for name in defines:
            later.setdefault(name, n)

    out = warn if not STRICT else bad
    for n, slug, defines in order:
        frag = os.path.join(CONTENT, '%s.html' % slug)
        if not os.path.exists(frag):
            continue
        with open(frag, encoding='utf-8') as f:
            text = '\n'.join(unescape_code(b) for b in code_blocks(f.read()))
        uses = {i for i in IDENT.findall(text)} - declared_names(text)
        for name in sorted(uses):
            born = later.get(name)
            if born is not None and born > n:
                out.append('content/%s.html: step %d uses %s, which is not '
                           'defined until step %d — move that lesson earlier '
                           'or teach %s before anything that needs it'
                           % (slug, n, name, born, name))


def file_block_is_whole(bad, warn):
    """The block that carries a file's path must be that whole file.

    A code block that stops early and says nothing reads as a finished file.
    The old guidance told authors to mark the cut, which they did — and a
    reader copying the block got a file that does not compile, because the
    class the file declares was `sealed` and its subclasses had been elided
    into a comment. So a cut inside the *file* block is now an error even
    though the same marker in a hand-written prose fragment is still fine.
    """
    try:
        sys.path.insert(0, HERE)
        from build import PAGES
    except Exception as exc:
        bad.append('cannot import build/pages (%s) — file block check skipped' % exc)
        return

    out = warn if not STRICT else bad
    for p in PAGES:
        if not p.get('path'):
            continue
        frag = os.path.join(CONTENT, '%s.html' % p['slug'])
        if not os.path.exists(frag):
            continue
        with open(frag, encoding='utf-8') as f:
            blocks = code_blocks(f.read())
        if not blocks:
            continue
        first = unescape_code(blocks[0])
        for marker in ('// ...', '// …', '# ...', '# …', '/* ...', '...  '):
            if marker in first:
                out.append('content/%s.html: the file block is cut short (%r). '
                           'A lesson shows its whole file — if the file is too '
                           'big to show, split the file and give each part its '
                           'own lesson.' % (p['slug'], marker.strip()))
                break


def why_is_present(bad, warn):
    """Every lesson states why its file exists, before the code.

    `why` exists in pages.py, is rendered by build.py, and was optional — so on
    a real 511-lesson site every entry carried a purpose statement and not one
    of them appeared, because nothing required it and nothing reported it
    missing. A stored-but-unrendered field is worse than an absent one: it
    looks like the work was done.

    `why=None` is the explicit opt-out and is respected here. It exists so that
    "not written yet" and "deliberately not applicable" stay distinguishable —
    a step that only runs a command has no file to justify.
    """
    try:
        sys.path.insert(0, HERE)
        from build import PAGES
    except Exception as exc:
        bad.append('cannot import build/pages (%s) — why check skipped' % exc)
        return

    out = warn if not STRICT else bad
    for p in PAGES:
        if p.get('why', '') is None:
            continue
        if not p.get('why'):
            out.append('pages.py: step %r (%s) has no `why` — every lesson '
                       'opens with why its file exists, in plain English, '
                       'before the code. Use why=None only if the step writes '
                       'no file.' % (p.get('slug'), p.get('n')))
            continue
        frag = os.path.join(CONTENT, '%s.html' % p['slug'])
        if not os.path.exists(frag):
            continue
        with open(frag, encoding='utf-8') as f:
            body = f.read()
        # build.py generates the section itself, so its presence is implied by
        # `why` being set. What is worth catching is the author having written
        # the section by hand as well — which renders the same prose twice.
        if 'Why this file exists' in body:
            out.append('content/%s.html: the fragment contains its own "Why '
                       'this file exists" section AND pages.py sets `why` — the '
                       'builder already emits one from `why`. Keep the text in '
                       'pages.py, or set why=None, not both.' % p['slug'])


def main():
    args = sys.argv[1:]
    frag_only = '--fragments' in args
    pages_only = '--pages' in args
    bad = []
    warn = []

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

    dependency_order(bad, warn)
    file_block_is_whole(bad, warn)
    why_is_present(bad, warn)

    report(bad, frags or [], pages, langs, warn)
    return 1 if bad else 0


def report(bad, frags, pages, langs=None, warn=None):
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
    if warn:
        print('WARN: %d (staged checks; run with --strict to make these fail)'
              % len(warn))
        for w in warn:
            print('  ' + w)
    if bad:
        print('BAD:')
        for b in bad:
            print('  ' + b)
        return
    print('BAD: none')


if __name__ == '__main__':
    sys.exit(main())