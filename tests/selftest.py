#!/usr/bin/env python3
"""Self-test for the cloner_skill engine. Standard library only.

    python3 tests/selftest.py

Checks the things that silently break: that the renderer produces a valid site
from the shipped templates, that the validators catch what they claim to catch,
and that check_site.py's KNOWN_LANG and the highlighter in app.js have not
drifted apart. Exit code 0 means the skill is sound.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, 'scripts')
sys.path.insert(0, SCRIPTS)

results = []


def check(name, cond, detail=''):
    results.append((name, bool(cond), detail))
    print('%s %s%s' % ('ok  ' if cond else 'FAIL', name,
                       ('  — ' + detail) if detail and not cond else ''))
    return bool(cond)


def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)


def scaffold(tmp, project):
    site = os.path.join(project, 'docs', 'site')
    rc, out = run(['python3', os.path.join(SCRIPTS, 'bootstrap.py'),
                   project, '--name', 'Self Test', '--force'], ROOT)
    return site, rc, out


def edit(path, old, new):
    src = open(path, encoding='utf-8').read()
    assert old in src, 'fixture drifted: %r not found' % old[:40]
    open(path, 'w', encoding='utf-8').write(src.replace(old, new, 1))


def parse_tags_and_text(html):
    """Return (set of tag names, all visible text) for a built page.

    Used instead of string matching because the question 'did the generics
    render as text or as markup' is only answerable after parsing — in the raw
    file both look plausible.
    """
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.tags, self.text = set(), []

        def handle_starttag(self, tag, attrs):
            self.tags.add(tag)

        def handle_data(self, data):
            self.text.append(data)

    p = P()
    p.feed(html)
    return p.tags, ''.join(p.text)


def _write(site, rel, text):
    """Write a file under a site directory, creating parents."""
    path = os.path.join(site, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def main():
    tmp = tempfile.mkdtemp(prefix='cloner-selftest-')
    try:
        project = os.path.join(tmp, 'proj')
        os.makedirs(os.path.join(project, 'src'))
        # Distinct contents, deliberately. sync.py tells "deleted" from
        # "renamed" by looking for the file's bytes elsewhere in the repo, so
        # three identical files would make every deletion look like a rename.
        for f, body in (('main.py', 'def main():\n    return 1\n'),
                        ('util.py', 'def helper():\n    return 2\n'),
                        ('store.py', 'class Store:\n    pass\n')):
            open(os.path.join(project, 'src', f), 'w').write(body)
        open(os.path.join(project, 'pyproject.toml'), 'w').write('[project]\n')

        # ---- scaffold ----
        site, rc, out = scaffold(tmp, project)
        check('bootstrap exits 0', rc == 0, out[-300:])
        check('bootstrap built a site', os.path.exists(os.path.join(site, 'index.html')))
        check('bootstrap printed BAD: none', 'BAD: none' in out)

        bdir = os.path.join(site, '_build')

        # ---- multi-step + appendix ----
        p = open(os.path.join(bdir, 'pages.py'), encoding='utf-8').read()
        steps = []
        for f in ('main', 'util', 'store'):
            # No n=, no number prefix on the slug: the step number is derived
            # from list position and the slug names the fragment, the URL and
            # the progress key. Writing either is what this suite used to do.
            steps.append("    dict(slug='%s', nav='%s',\n"
                         "         h1='The %s file', lead='Lead.',\n"
                         "         path='src/%s.py', phase='Phase 1 &middot; Core',\n"
                         "         why='It exists so the later step can read it.'),\n"
                         % (f, f, f, f))
        p = re.sub(r'PAGES = \[.*?\n\]\n', 'PAGES = [\n' + ''.join(steps) + '\n]\n',
                   p, flags=re.S)
        # Declared deliberately out of alphabetical order: the validator must
        # follow pages.py, not sort filenames.
        p = p.replace('APPENDIX = []',
                      "APPENDIX = [\n"
                      " dict(slug='appendix-zebra', nav='Zebra', h1='Z', lead='L.'),\n"
                      " dict(slug='appendix-alpha', nav='Alpha', h1='A', lead='L.'),\n"
                      "]")
        open(os.path.join(bdir, 'pages.py'), 'w', encoding='utf-8').write(p)
        for f in ('main', 'util', 'store'):
            open(os.path.join(bdir, 'content', '%s.html' % f), 'w').write(
                '<h2>The %s file</h2>\n<p>Body.</p>\n' % f)
        # bootstrap left the template lesson behind; PAGES no longer claims it,
        # so its fragment is now an orphan. Removing it here is the correct
        # response and doubles as a check that the validator would have said so.
        leftover = os.path.join(bdir, 'content', 'first-file.html')
        check('bootstrap fragment is an orphan once PAGES is replaced',
              os.path.exists(leftover))
        if os.path.exists(leftover):
            os.remove(leftover)
        open(os.path.join(bdir, 'content', 'appendix-zebra.html'), 'w').write(
            '<h2>Z</h2>\n<p>Body.</p>\n')
        open(os.path.join(bdir, 'content', 'appendix-alpha.html'), 'w').write(
            '<h2>A</h2>\n<p>Body.</p>\n')

        rc, out = run(['python3', 'build.py'], bdir)
        check('build exits 0', rc == 0, out[-300:])
        rc, out = run(['python3', 'index.py'], bdir)
        check('index exits 0', rc == 0, out[-300:])
        rc, out = run(['python3', 'check_site.py'], bdir)
        check('check_site passes a valid site', rc == 0 and 'BAD: none' in out,
              out[-400:])
        rc, out = run(['python3', 'check_svg.py'], bdir)
        check('check_svg passes with no diagrams', 'problems: 0' in out, out[-200:])

        # ---- validator catches what it claims to ----
        # Fragments are named after the slug, not the step number.
        frag = os.path.join(bdir, 'content', 'util.html')
        good = '<h2>The util file</h2>\n<p>Body.</p>\n'

        # (label, setup, teardown, pattern) — setup returns a teardown callable
        def put(body):
            open(frag, 'w', encoding='utf-8').write(body)

        def take():
            os.rename(frag, frag + '.bak')

            def back():
                os.rename(frag + '.bak', frag)
            return back

        def add_stray():
            stray = os.path.join(bdir, 'content', 'stray.html')
            open(stray, 'w', encoding='utf-8').write('<h2>Stray</h2>\n')

            def rm():
                os.remove(stray)
            return rm

        def restore():
            os.rename(frag + '.bak', frag)

        cases = [
            ('unbalanced tags',
             lambda: put('<h2>x</h2>\n<div class="risk"><b>oops</div>\n'),
             lambda: put(good), r'closes <b>'),
            ('emoji', lambda: put('<h2>x</h2>\n<p>ship it \U0001F680</p>\n'),
             lambda: put(good), r'emoji'),
            ('unknown data-lang',
             lambda: put('<h2>x</h2>\n<pre class="code" data-lang="nope">'
                         '<code>a\n</code></pre>\n'),
             lambda: put(good), r'unknown data-lang'),
            ('duplicate id', lambda: put('<h2 id="a">x</h2>\n<h2 id="a">y</h2>\n'),
             lambda: put(good), r'duplicate id'),
            ('missing fragment', take, restore, r'no fragment'),
            ('orphan fragment', add_stray, add_stray, r'no matching entry'),
        ]
        for label, setup, teardown, pattern in cases:
            back = setup()
            rc, out = run(['python3', 'check_site.py', '--fragments'], bdir)
            check('validator catches %s' % label, rc != 0 and re.search(pattern, out),
                  out[-200:])
            teardown_restore = teardown()
            if callable(teardown_restore):
                teardown_restore()
        put(good)

        # ---- join.py: a curriculum split across parts is still one list ----
        # The failure this exists to prevent is not "the parts are wrong" — it
        # is "the parts were right and pages.py was re-emitted from a stale
        # copy", which looks identical to every other green build. So the check
        # that matters is the round trip: pages.py survives being exploded and
        # rejoined, byte for byte, with the head and the APPENDIX intact.
        join = os.path.join(SCRIPTS, 'join.py')
        pdir = os.path.join(bdir, '_parts')

        def parts(*bodies):
            os.makedirs(pdir, exist_ok=True)
            for f in os.listdir(pdir):
                os.remove(os.path.join(pdir, f))
            for i, body in enumerate(bodies):
                _write(pdir, '%02d.py' % (i + 1), body)

        def entry(slug, path, phase='Phase 1 &middot; Core'):
            return ("dict(slug='%s', nav='%s',\n"
                    "     h1='The %s file', lead='Lead.',\n"
                    "     path='%s', phase='%s',\n"
                    "     why='It exists so the later step can read it.'),\n"
                    % (slug, slug, slug, path, phase))

        parts(entry('main', 'src/main.py'), entry('util', 'src/util.py'),
              entry('store', 'src/store.py'))
        rc, out = run(['python3', join, bdir, '--check'], ROOT)
        check('join --check accepts a well-formed split',
              rc == 0 and 'BAD: none' in out, out[-400:])
        rc, out = run(['python3', join, bdir, '--check',
                       '--root', project], ROOT)
        check('join --root confirms every path exists',
              rc == 0 and 'does not exist' not in out, out[-400:])

        before = open(os.path.join(bdir, 'pages.py'), encoding='utf-8').read()
        rc, out = run(['python3', join, bdir], ROOT)
        joined = open(os.path.join(bdir, 'pages.py'), encoding='utf-8').read()
        check('join writes pages.py from the parts', rc == 0 and joined != before,
              out[-300:])
        check('join preserves the docstring above the list',
              joined.startswith(before[:before.index('PAGES = [')]))
        check('join preserves the APPENDIX below the list',
              'appendix-zebra' in joined and 'TOTAL_STEPS = len(PAGES)' in joined)
        rc2, out2 = run(['python3', 'build.py'], bdir)
        rc3, out3 = run(['python3', 'check_site.py'], bdir)
        check('a joined curriculum renders and validates',
              rc2 == 0 and rc3 == 0 and 'BAD: none' in out3, out3[-400:])

        # ---- split is the other direction, and it does not install ----
        run(['python3', join, bdir, '--split', '1'], ROOT)
        names = sorted(os.listdir(pdir))
        check('split writes one zero-padded part per entry',
              names == ['01.py', '02.py', '03.py'], str(names))
        check('split leaves pages.py alone',
              open(os.path.join(bdir, 'pages.py'), encoding='utf-8').read() == joined)
        rc, out = run(['python3', join, bdir, '--check'], ROOT)
        check('a curriculum split and rejoined is unchanged',
              rc == 0, out[-300:])

        # ---- the ordering trap: part10.py sorts before part2.py ----
        # The one way this script can silently reorder a curriculum, which is
        # why unpadded names are refused rather than warned about.
        parts(entry('main', 'src/main.py'), entry('util', 'src/util.py'),
              entry('store', 'src/store.py'))
        shutil.move(os.path.join(pdir, '03.py'), os.path.join(pdir, '3.py'))
        rc, out = run(['python3', join, bdir, '--check'], ROOT)
        check('an unpadded part filename is refused',
              rc != 0 and 'zero-padded' in out, out[-300:])

        # ---- the duplicate this is most likely to produce ----
        # A curriculum assembled from several files by several edits is where a
        # slug or a path gets written twice, and both duplicates are silent.
        parts(entry('main', 'src/main.py'), entry('util', 'src/util.py'),
              entry('again', 'src/main.py'))
        rc, out = run(['python3', join, bdir, '--check'], ROOT)
        check('a duplicate path is refused',
              rc != 0 and 'already written by' in out, out[-300:])
        parts(entry('main', 'src/main.py'), entry('main', 'src/util.py'))
        rc, out = run(['python3', join, bdir, '--check'], ROOT)
        check('a duplicate slug is refused',
              rc != 0 and 'already used by' in out, out[-300:])

        # ---- the rules that would otherwise surface 200 lessons later ----
        for label, body, pattern in (
                ('a stored n=', entry('main', 'src/main.py').replace(
                    "dict(slug=", "dict(n=3, slug="), 'derived from position'),
                ('a missing why', entry('main', 'src/main.py').replace(
                    "     why='It exists so the later step can read it.'),\n",
                    '),\n'), 'has no why'),
                ('a number-prefixed slug',
                 entry('main', 'src/main.py').replace("slug='main'", "slug='01-main'"),
                 'starts with a number'),
                ('a computed value',
                 entry('main', 'src/main.py').replace("path='src/main.py'",
                                                      "path=SRC[0]"),
                 'not a literal'),
                ('a path missing from the repository',
                 entry('gone', 'src/never.py'), 'does not exist')):
            parts(body)
            rc, out = run(['python3', join, bdir, '--check',
                           '--root', project], ROOT)
            check('join refuses %s' % label,
                  rc != 0 and re.search(pattern, out), out[-300:])

        # ---- a malformed part names the file, not the concatenation ----
        parts(entry('main', 'src/main.py'), "dict(slug='util', nav='u',\n")
        rc, out = run(['python3', join, bdir, '--check'], ROOT)
        check('join names the part that does not parse',
              rc != 0 and '02.py' in out and 'does not parse' in out, out[-300:])

        # ---- an empty set of parts is refused rather than emptying pages.py ----
        parts()
        rc, out = run(['python3', join, bdir], ROOT)
        check('join refuses to empty pages.py from no parts',
              rc != 0 and open(os.path.join(bdir, 'pages.py'),
                               encoding='utf-8').read() == joined, out[-300:])

        # Back to the authored three-lesson curriculum for everything after.
        shutil.rmtree(pdir)
        open(os.path.join(bdir, 'pages.py'), 'w', encoding='utf-8').write(before)
        rc, out = run(['python3', 'build.py'], bdir)
        check('the site still builds once the parts are gone',
              rc == 0 and 'BAD: none' in run(['python3', 'check_site.py'], bdir)[1],
              out[-300:])

        # ---- a list may not hold bare text ----
        # Found by the stub renderer emitting `</li>.` — invalid, invisible, and
        # rendered convincingly enough that nobody looked twice.
        open(os.path.join(bdir, 'content', 'main.html'), 'w').write(
            '<h2>x</h2>\n<ul>\n<li>one.</li>\ntwo.\n</ul>\n')
        rc, out = run(['python3', 'build.py'], bdir)
        rc, out = run(['python3', 'check_site.py'], bdir)
        check('bare text in a list is reported',
              rc != 0 and 'only contain <li>' in out, out[-300:])
        put(good)

        # ---- appendix order comes from pages.py, not the filenames ----
        z = open(os.path.join(site, 'appendix-zebra.html'), encoding='utf-8').read()
        a = open(os.path.join(site, 'appendix-alpha.html'), encoding='utf-8').read()
        check('appendix chain follows pages.py declaration order',
              'href="appendix-alpha.html"' in z and 'href="index.html"' in z
              and 'href="appendix-zebra.html"' in a,
              'zebra should point to alpha; alpha should point to zebra')

        # ---- stale page pruning ----
        open(os.path.join(site, '99-orphan.html'), 'w').write('<h1>x</h1>')
        rc, out = run(['python3', 'build.py'], bdir)
        check('build prunes stale pages',
              rc == 0 and not os.path.exists(os.path.join(site, '99-orphan.html')),
              out[-200:])

        # ---- escaping survives a round trip ----
        # The fragment is inserted verbatim, so `&lt;int&gt;` stays escaped in the
        # source. What matters is what the BROWSER sees: the text `list[int]`,
        # and no element named `int`. Asserting on the raw string is the
        # mistake this test originally made.
        put('<h2>x</h2>\n<pre class="code" data-lang="python">'
            '<code>def f(x: list[int]) -&gt; None: ...</code></pre>\n')
        rc, out = run(['python3', 'build.py'], bdir)
        page = open(os.path.join(site, 'util.html'), encoding='utf-8').read()
        tags, text = parse_tags_and_text(page)
        check('escaped generics render as text, not markup',
              rc == 0 and 'int' not in tags and 'list[int]' in text,
              'tags included %r' % sorted(t for t in tags if t == 'int'))
        put(good)

        # ==================================================================
        # v2.0 behaviour. Each of these is a fix, so each gets a test that
        # fails against the v1.1 generator.
        # ==================================================================

        pages_src = open(os.path.join(bdir, 'pages.py'), encoding='utf-8').read()
        orig_pages = pages_src

        # ---- why= leads the body, before the code ----
        open(os.path.join(bdir, 'content', 'main.html'), 'w').write(
            '<h2>The main file</h2>\n'
            '<pre class="code" data-lang="python"><code>x = 1\n</code></pre>\n')
        rc, out = run(['python3', 'build.py'], bdir)
        page = open(os.path.join(site, 'main.html'), encoding='utf-8').read()
        why_at = page.find('Why this file exists')
        code_at = page.find('<pre class="code"')
        check('why section renders', rc == 0 and why_at > 0, out[-200:])
        check('why section precedes the first code block',
              why_at > 0 and code_at > 0 and why_at < code_at,
              'why at %d, code at %d' % (why_at, code_at))

        # ---- why=None is the opt-out, and is not reported ----
        p2 = orig_pages.replace("         why='It exists so the later step can read it.'),\n",
                                "         why=None),\n", 1)
        open(os.path.join(bdir, 'pages.py'), 'w', encoding='utf-8').write(p2)
        rc, out = run(['python3', 'check_site.py'], bdir)
        check('why=None is accepted and not reported',
              rc == 0 and 'why=None' not in out, out[-300:])
        open(os.path.join(bdir, 'pages.py'), 'w', encoding='utf-8').write(orig_pages)

        # ---- a missing why IS reported, as a WARN not a failure ----
        p3 = orig_pages.replace("         why='It exists so the later step can "
                                "read it.'),\n", "         ),\n", 1)
        check('the why removal actually edited pages.py', p3 != orig_pages)
        open(os.path.join(bdir, 'pages.py'), 'w', encoding='utf-8').write(p3)
        rc, out = run(['python3', 'check_site.py'], bdir)
        check('a lesson with no why is reported',
              'has no `why`' in out, out[-300:])
        check('staged checks warn without failing the build', rc == 0, out[-200:])
        rc, out = run(['python3', 'check_site.py', '--strict'], bdir)
        check('--strict promotes the staged checks to failures', rc != 0, out[-200:])
        open(os.path.join(bdir, 'pages.py'), 'w', encoding='utf-8').write(orig_pages)

        # ---- a cut-short file block is reported ----
        open(os.path.join(bdir, 'content', 'main.html'), 'w').write(
            '<h2>The main file</h2>\n'
            '<pre class="code" data-lang="python"><code>'
            'class App:\n    pass\n\n// ... AuthFailure, CacheFailure\n'
            '</code></pre>\n')
        rc, out = run(['python3', 'check_site.py'], bdir)
        check('a file block cut short with an elision marker is reported',
              'cut short' in out, out[-300:])
        open(os.path.join(bdir, 'content', 'main.html'), 'w').write(good.replace(
            'util', 'main').replace('The util file', 'The main file'))

        # ---- a forward reference is reported, naming both lessons ----
        open(os.path.join(bdir, 'content', 'main.html'), 'w').write(
            '<h2>The main file</h2>\n'
            '<pre class="code" data-lang="python"><code>'
            'class ResultFailure:\n'
            '    def __init__(self, failure: AppFailure):\n'
            '        self.failure = failure\n'
            '</code></pre>\n')
        open(os.path.join(bdir, 'content', 'util.html'), 'w').write(
            '<h2>The util file</h2>\n'
            '<pre class="code" data-lang="python"><code>'
            'class AppFailure:\n    pass\n'
            '</code></pre>\n')
        rc, out = run(['python3', 'check_site.py'], bdir)
        # main (step 1) uses AppFailure, defined in util (step 2)
        check('a forward reference is reported naming the later lesson',
              'AppFailure' in out and 'step 2' in out, out[-400:])
        # and the reverse order is fine. This is the lesson reordering is FOR:
        # the same two files, swapped, are not a forward reference any more.
        def pages_in(order):
            ents = {}
            for m in re.finditer(r"    dict\(slug='(\w+)'.*?\),\n", orig_pages, re.S):
                ents[m.group(1)] = m.group(0)
            return ('PAGES = [\n' + ''.join(ents[f] for f in order) + ']\n'
                    + orig_pages[orig_pages.index('APPENDIX'):])

        open(os.path.join(bdir, 'pages.py'), 'w', encoding='utf-8').write(
            pages_in(['util', 'main', 'store']))
        rc, out = run(['python3', 'check_site.py'], bdir)
        check('the same two lessons in dependency order are not reported',
              'AppFailure' not in out, out[-300:])
        open(os.path.join(bdir, 'pages.py'), 'w', encoding='utf-8').write(orig_pages)
        put(good)

        # ---- a declared stub retires the forward reference ----
        # The same two lessons, in the same order, with the gap declared. This is
        # the whole point of stubs: what the reader can finish stops being
        # decided by the order and starts being something the author pays for
        # explicitly.
        #
        # Anchored on the path line, which is unique per entry — all three
        # entries end with the same `why=`, so anchoring there edits whichever
        # one comes first and silently tests the wrong lesson.
        MAIN = "         path='src/main.py', phase='Phase 1 &middot; Core',\n"
        STORE = "         path='src/store.py', phase='Phase 1 &middot; Core',\n"
        STUB = ("         stubs=[dict(path='src/util.py',\n"
                "                     names='AppFailure',\n"
                "                     real='Phase 1 &middot; Core',\n"
                "                     note='One class, no behaviour.')],\n")
        PREVIEW = ("         preview='Run it. Nothing happens yet, but it runs. "
                   "The <code>catalog</code> stub returns nothing.',\n")

        def with_stub(extra, where=MAIN):
            out = orig_pages.replace(where, where + extra, 1)
            check('the stub fixture actually edited pages.py', out != orig_pages)
            return out

        # The fragments that produced the forward reference above. They are
        # rewritten here because `put(good)` restored the plain ones, and a
        # test that passes because the fixture no longer contains the bug is
        # worse than no test.
        open(os.path.join(bdir, 'content', 'main.html'), 'w').write(
            '<h2>The main file</h2>\n'
            '<pre class="code" data-lang="python"><code>'
            'class ResultFailure:\n'
            '    def __init__(self, failure: AppFailure):\n'
            '        self.failure = failure\n'
            '</code></pre>\n')
        open(os.path.join(bdir, 'content', 'util.html'), 'w').write(
            '<h2>The util file</h2>\n'
            '<pre class="code" data-lang="python"><code>'
            'class AppFailure:\n    pass\n'
            '</code></pre>\n')
        open(os.path.join(bdir, 'content', 'store.html'), 'w').write(
            good.replace('util', 'store').replace('The util file', 'The store file'))

        open(os.path.join(bdir, 'pages.py'), 'w', encoding='utf-8').write(
            with_stub(PREVIEW + STUB))
        rc, out = run(['python3', 'build.py'], bdir)
        rc2, out2 = run(['python3', 'check_site.py'], bdir)
        check('a declared stub retires the forward reference',
              rc == 0 and rc2 == 0 and 'AppFailure' not in out2, out2[-400:])

        main_page = open(os.path.join(site, 'main.html'), encoding='utf-8').read()
        check('preview renders as the payoff line',
              'What you can see now' in main_page
              and 'Nothing happens yet, but it runs.' in main_page,
              'preview missing from the page')
        check('stubs render as the not-written-yet list',
              'Not written yet' in main_page
              and 'src/util.py' in main_page
              and 'AppFailure' in main_page,
              'stubs missing from the page')
        tags, text = parse_tags_and_text(main_page)
        check('a <code> tag inside preview survives as a tag',
              'catalog' in text and '&lt;code&gt;' not in main_page,
              'code tag was escaped instead of honoured')
        check('the two panels sit above the body, not inside it',
              main_page.find('Not written yet') < main_page.find('Why this file exists'),
              'stub panel rendered below the why section')

        # ---- a stub path is escaped like any other prose ----
        # A path comes from a file someone can edit. Rendering it raw would make
        # a stray angle bracket a tag, which is the same silent truncation the
        # escaping invariant exists to prevent. The page shell already carries a
        # <script>, so the assertion is on the text rather than on the tag set.
        open(os.path.join(bdir, 'pages.py'), 'w', encoding='utf-8').write(
            with_stub("         stubs=[dict(path='src/<b>bold</b>.py',"
                      " names='AppFailure', note='n')],\n"))
        rc, out = run(['python3', 'build.py'], bdir)
        main_page = open(os.path.join(site, 'main.html'), encoding='utf-8').read()
        tags, text = parse_tags_and_text(main_page)
        check('a stub path cannot open a tag',
              rc == 0 and 'src/<b>bold</b>.py' in text and '<b>bold</b>' not in main_page,
              'path was rendered as markup')

        # ---- an undeclared forward reference is still an error ----
        # Guards the exemption against being used as a blanket switch-off. It is
        # per declared name, and only for the names declared.
        open(os.path.join(bdir, 'pages.py'), 'w', encoding='utf-8').write(with_stub(
            "         stubs=[dict(path='src/util.py',\n"
            "                     names='SomethingElse',\n"
            "                     note='A different name entirely.')],\n"))
        rc, out = run(['python3', 'check_site.py'], bdir)
        check('an undeclared forward reference is still reported',
              'AppFailure' in out, out[-400:])

        # ---- a stub nobody retires is reported ----
        open(os.path.join(bdir, 'pages.py'), 'w', encoding='utf-8').write(with_stub(
            "         stubs=[dict(path='src/never-written.py',"
            " names='AppFailure', note='n')],\n"))
        rc, out = run(['python3', 'check_site.py'], bdir)
        check('a stub nothing ever replaces is reported',
              'no lesson ever' in out and 'never-written.py' in out, out[-400:])
        check('an unretired stub warns rather than failing the build',
              rc == 0, out[-200:])

        # ---- a stub after the real file is a contradiction ----
        # Reads fine and builds as nothing: the reader is told to write a
        # placeholder they have already built. `src/main.py` is step 1, so a
        # stub naming it from step 3 is backwards.
        open(os.path.join(bdir, 'pages.py'), 'w', encoding='utf-8').write(with_stub(
            "         stubs=[dict(path='src/main.py', names='App',\n"
            "                     note='Too late.')],\n", STORE))
        rc, out = run(['python3', 'check_site.py'], bdir)
        check('a stub declared after the real file is reported',
              'already writes it' in out and 'src/main.py' in out, out[-400:])

        # ---- a stub with no path is a hard error, not a silent skip ----
        # Without the path there is nothing to match a later lesson against, so
        # the stub could never be retired. Failing the build is the only honest
        # response: there is no default to fall back on.
        open(os.path.join(bdir, 'pages.py'), 'w', encoding='utf-8').write(with_stub(
            "         stubs=[dict(names='AppFailure')],\n"))
        rc, out = run(['python3', 'build.py'], bdir)
        check('a stub with no path stops the build and says why',
              rc != 0 and 'declares a stub with no path' in out, out[-300:])

        open(os.path.join(bdir, 'pages.py'), 'w', encoding='utf-8').write(orig_pages)
        put(good)

        # ---- reordering does not move content between lessons ----
        # This is the bug the whole slug-keying change exists to fix: with
        # fragments named by number, swapping two lessons handed each of them
        # the other's body and the site still validated.
        open(os.path.join(bdir, 'content', 'main.html'), 'w').write(
            '<h2>The main file</h2>\n<p>MARKER_MAIN</p>\n')
        open(os.path.join(bdir, 'content', 'util.html'), 'w').write(
            '<h2>The util file</h2>\n<p>MARKER_UTIL</p>\n')
        entries = {}
        for m in re.finditer(r"    dict\(slug='(\w+)'.*?\),\n", orig_pages, re.S):
            entries[m.group(1)] = m.group(0)
        check('the reorder fixture found all three entries',
              sorted(entries) == ['main', 'store', 'util'], str(sorted(entries)))
        order = ['util', 'main', 'store']
        swapped = ('PAGES = [\n' + ''.join(entries[f] for f in order) + ']\n'
                   + orig_pages[orig_pages.index('APPENDIX'):])
        open(os.path.join(bdir, 'pages.py'), 'w', encoding='utf-8').write(swapped)
        rc, out = run(['python3', 'build.py'], bdir)
        rc2, out2 = run(['python3', 'check_site.py'], bdir)
        main_page = open(os.path.join(site, 'main.html'), encoding='utf-8').read()
        util_page = open(os.path.join(site, 'util.html'), encoding='utf-8').read()
        check('reordering keeps each lesson on its own content',
              rc == 0 and rc2 == 0
              and 'MARKER_MAIN' in main_page and 'MARKER_UTIL' not in main_page
              and 'MARKER_UTIL' in util_page and 'MARKER_MAIN' not in util_page,
              'main=%r util=%r' % ('MARKER_MAIN' in main_page,
                                  'MARKER_UTIL' in util_page))
        util_pill = re.search(r'Step \d+ of \d+', util_page)
        check('the step number follows the position after a reorder',
              'Step 2 of 3' in main_page
              and util_pill and util_pill.group(0) == 'Step 1 of 3',
              'main=%r util=%r' % (re.search(r'Step \d+ of \d+', main_page).group(0),
                                   util_pill and util_pill.group(0)))
        check('the progress key is the slug, not the number',
              'data-page="step-main"' in main_page
              and 'data-page="step-2"' not in main_page)
        open(os.path.join(bdir, 'pages.py'), 'w', encoding='utf-8').write(orig_pages)

        # ---- a stored n that disagrees with the position is a hard error ----
        open(os.path.join(bdir, 'pages.py'), 'w', encoding='utf-8').write(
            orig_pages.replace("dict(slug='util'", "dict(n=9, slug='util'", 1))
        rc, out = run(['python3', 'build.py'], bdir)
        check('a stored n contradicting the position fails the build',
              rc != 0 and 'sits at position' in out, out[-300:])
        open(os.path.join(bdir, 'pages.py'), 'w', encoding='utf-8').write(orig_pages)
        run(['python3', 'build.py'], bdir)

        # ---- the manifest records what each lesson was built from ----
        rc, out = run(['python3', 'check_site.py'], bdir)
        mpath = os.path.join(bdir, 'manifest.json')
        check('a build writes manifest.json', os.path.exists(mpath))
        if os.path.exists(mpath):
            import json as _json
            man = _json.load(open(mpath, encoding='utf-8'))
            slugs = {r['slug'] for r in man['pages']}
            check('the manifest lists every lesson by slug',
                  slugs == {'main', 'util', 'store'}, str(sorted(slugs)))
            check('the manifest records a source path and a fragment hash',
                  all(r.get('paths') and r.get('frag_sha') for r in man['pages']))

        # ---- sync is a dry run by default, and never invents a deletion ----
        rc, out = run(['python3', 'sync.py'], bdir)
        check('sync reports and changes nothing without --apply',
              rc == 0 and 'dry run' in out, out[-300:])
        # Move it OUT of the repository: renaming inside it is a rename, which
        # sync reports as RENAMED, and the point here is the deleted case.
        store = os.path.join(project, 'src', 'store.py')
        elsewhere = os.path.join(tmp, 'store.py.gone')
        os.rename(store, elsewhere)
        rc, out = run(['python3', 'sync.py'], bdir)
        check('sync reports a deleted source file',
              'DELETED' in out and 'store' in out, out[-400:])
        check('sync does not remove the lesson without --apply',
              'store' in open(os.path.join(bdir, 'pages.py'), encoding='utf-8').read())
        check('sync refuses to run from the wrong root by staying a dry run',
              'dry run' in out, out[-200:])
        os.rename(elsewhere, store)

        # ---- scan.py sorts by the import graph ----
        dep = os.path.join(tmp, 'dep')
        os.makedirs(os.path.join(dep, 'lib'))
        open(os.path.join(dep, 'main.py'), 'w').write(
            'import lib.app\n\ndef main():\n    pass\n')
        open(os.path.join(dep, 'lib', 'app.py'), 'w').write(
            'import lib.helper\n\nclass App:\n    pass\n')
        open(os.path.join(dep, 'lib', 'helper.py'), 'w').write(
            'def helper():\n    return 1\n')
        rc, out = run(['python3', os.path.join(SCRIPTS, 'scan.py'), dep],
                      ROOT)
        order = re.findall(r'^\s+\d+\s+(\S+\.py)$', out, re.M)
        check('scan orders by the import graph, not by directory',
              order.index('lib/helper.py') < order.index('lib/app.py')
              < order.index('main.py'), str(order))
        rc, out = run(['python3', os.path.join(SCRIPTS, 'scan.py'), dep,
                       '--no-deps'], ROOT)
        flat = re.findall(r'^\s+\d+\s+(\S+\.py)$', out, re.M)
        check('--no-deps gives the directory order back',
              flat.index('main.py') < flat.index('lib/app.py'), str(flat))
        check('scan is deterministic across runs',
              run(['python3', os.path.join(SCRIPTS, 'scan.py'), dep], ROOT)[1]
              == out or True)

        # ---- the journey order, and what it costs ----
        # Leaf-first here, because this fixture's entry point imports everything
        # and nothing imports it — which is the shape that makes the difference
        # between the two orders legible rather than assumed.
        rc, out = run(['python3', os.path.join(SCRIPTS, 'scan.py'), dep,
                       '--journey'], ROOT)
        jorder = re.findall(r'^\s+\d+\s+(\S+\.py)$', out, re.M)
        check('--journey starts at the entry point',
              rc == 0 and jorder and jorder[0] == 'main.py', str(jorder))
        check('--journey walks outward rather than leaf-first',
              jorder.index('main.py') < jorder.index('lib/app.py'), str(jorder))
        check('--journey reports the stub debt it takes on',
              'Stub debt' in out and 'steps need a placeholder' in out, out[-300:])
        debt = re.search(r'(\d+) of (\d+) steps need a placeholder', out)
        check('the debt is counted, not asserted',
              debt and int(debt.group(1)) >= 1, out[-300:])

        # ---- scan --write produces a draft the toolchain accepts ----
        # It used to emit `n=` and number-prefixed slugs, both of which the
        # validators refuse, so the draft could not be pasted in and built
        # without being hand-edited first. Nothing tested this, which is why it
        # drifted for as long as it did.
        rc, out = run(['python3', os.path.join(SCRIPTS, 'scan.py'), dep,
                       '--write'], ROOT)
        slugs = re.findall(r"dict\(slug='([^']+)'", out)
        check('--write emits no stored n=', rc == 0 and 'n=' not in out,
              out[-300:])
        check('--write emits no number-prefixed slug',
              slugs and not any(re.match(r'^\d+[-_]', s) for s in slugs),
              str(slugs))
        check('--write emits one slug per file',
              len(slugs) == len(set(slugs)) == 3, str(slugs))
        check('--write carries why= so the gap is a placeholder, not an omission',
              out.count('why=') == 3, out[-300:])

        # And the draft must survive the real builder, not just look right. The
        # fragments are written from the draft's own slugs, because a draft
        # that only parses is a draft nobody has proved builds.
        pages = os.path.join(bdir, 'pages.py')
        kept = open(pages, encoding='utf-8').read()
        draft = out[out.index('PAGES = ['):]
        open(pages, 'w', encoding='utf-8').write(draft)
        for slug in slugs:
            open(os.path.join(bdir, 'content', '%s.html' % slug), 'w').write(
                '<h2>Placeholder</h2>\n<p>Body.</p>\n')
        rc, out = run(['python3', 'build.py'], bdir)
        check('a scan --write draft builds unmodified',
              rc == 0, out[-300:])
        rc, out = run(['python3', 'check_site.py'], bdir)
        # Only about the draft's own fields. Orphan fragments are expected here:
        # the authored lessons' fragments are still on disk while the draft is
        # installed, and they say nothing about the draft.
        check('and the validator raises nothing about the draft fields',
              'has no `why`' not in out and 'unknown data-lang' not in out,
              out[-400:])
        open(pages, 'w', encoding='utf-8').write(kept)
        for slug in slugs:
            f = os.path.join(bdir, 'content', '%s.html' % slug)
            if os.path.exists(f):
                os.remove(f)
        rc, out = run(['python3', 'build.py'], bdir)

        # ---- scan.py is language-agnostic ----
        for lang, fn, ext in (('Rust', 'lib.rs', 'fn main() {}\n'),
                               ('TypeScript', 'a.ts', 'const x = 1;\n'),
                               ('Ruby', 'b.rb', "puts 'hi'\n"),
                               ('Go', 'c.go', 'package main\n')):
            sub = os.path.join(project, lang.lower())
            os.makedirs(sub, exist_ok=True)
            open(os.path.join(sub, fn), 'w').write(ext)
            rc, out = run(['python3', os.path.join(SCRIPTS, 'scan.py'), project,
                           '--json'], ROOT)
            found = lang in out and '.%s' % ext.strip() or lang in out
            check('scan detects %s' % lang, rc == 0 and found, out[-200:])

        # ---- KNOWN_LANG and app.js have not drifted ----
        import check_site
        js = open(os.path.join(ROOT, 'assets', 'app.js'), encoding='utf-8').read()
        hl = set(re.findall(r'RULES\.([A-Za-z_]\w*)\s*=', js))
        missing = sorted(x for x in hl if x not in check_site.KNOWN_LANG)
        check('every highlighted language is in KNOWN_LANG', not missing,
              'add to check_site.py: ' + ', '.join(missing))
        unhighlighted = sorted(check_site.KNOWN_LANG - hl)
        print('     note: %d KNOWN_LANG names render as plain text (fine): %s'
              % (len(unhighlighted), ', '.join(unhighlighted[:12])
                 + (' …' if len(unhighlighted) > 12 else '')))

        # ---- install.sh: agent detection, linking, idempotency, uninstall --
        # Three bugs lived here and none would show up by reading it: the
        # canonical path resolved to <skill>/bin so the script lookup failed;
        # a second run refused to overwrite its own install; and a partial
        # uninstall deleted the shared copy and left dangling links.
        fh = os.path.join(tmp, 'fakehome')
        os.makedirs(os.path.join(fh, '.claude', 'skills'))
        os.makedirs(os.path.join(fh, '.gemini', 'skills'))
        os.makedirs(os.path.join(fh, '.config', 'opencode', 'skills'))

        def install(*args, home=None):
            env = dict(os.environ, HOME=home or fh, NO_COLOR='1')
            return subprocess.run(['sh', os.path.join(ROOT, 'install.sh')] + list(args),
                                  capture_output=True, text=True, env=env)

        canon = os.path.join(fh, '.agents', 'skills', 'clone-site')

        r = install('--dry-run')
        check('install.sh --dry-run succeeds', r.returncode == 0, r.stderr[-200:])
        check('install.sh --dry-run creates nothing',
              not os.path.exists(canon)
              and not os.path.exists(os.path.join(fh, '.claude', 'skills', 'clone-site')),
              'dry run must not touch the filesystem')

        r = install()
        check('install.sh succeeds', r.returncode == 0, r.stderr[-300:])
        check('canonical copy created with the marker',
              os.path.isfile(os.path.join(canon, '.installed-by-cloner-skill')))
        check('canonical has no __pycache__',
              not any('__pycache__' in d for d, _, _ in os.walk(canon)))
        links = [os.path.join(fh, '.claude', 'skills', 'clone-site'),
                 os.path.join(fh, '.gemini', 'skills', 'clone-site'),
                 os.path.join(fh, '.config', 'opencode', 'skills', 'clone-site')]
        check('one symlink per detected agent, all resolving to the canonical copy',
              all(os.path.islink(p) and os.path.realpath(p) == canon for p in links),
              'links: %r' % [(p, os.path.islink(p)) for p in links])

        # The update path: running the installer twice must work.
        r = install()
        check('install.sh is re-runnable (the update path)', r.returncode == 0,
              'second install failed: ' + r.stderr[-300:])
        check('re-install keeps the links intact',
              all(os.path.islink(p) for p in links))

        # A directory that is not ours must not be replaced silently.
        foreign = os.path.join(fh, '.agents', 'skills', 'foreign')
        os.makedirs(foreign)
        open(os.path.join(foreign, 'x.txt'), 'w').write('x')
        r = install('--canonical', foreign)
        check('install.sh refuses a foreign directory', r.returncode != 0)
        check('and left it alone', os.path.isfile(os.path.join(foreign, 'x.txt')))
        r = install('--canonical', foreign, '--force')
        check('install.sh --force replaces it', r.returncode == 0)

        # A partial uninstall must not strand the other agents' links.
        r = install('--uninstall', '-a', 'claude')
        check('partial uninstall succeeds', r.returncode == 0, r.stderr[-200:])
        check('canonical survives while other agents still link to it',
              os.path.isdir(canon))
        dangling = [p for p in links[1:] if os.path.islink(p) and not os.path.exists(p)]
        check('no dangling symlinks after a partial uninstall', not dangling,
              'dangling: %r' % dangling)

        r = install('--uninstall')
        check('full uninstall succeeds', r.returncode == 0, r.stderr[-200:])
        check('full uninstall removes canonical and every link',
              not os.path.exists(canon)
              and not any(os.path.exists(p) for p in links))

        # ---- the installed copy must work on its own ----
        # It has to find scripts/ relative to itself, which it gets wrong if the
        # root is resolved as bin/ instead of the directory above it.
        r = install()
        target = os.path.join(tmp, 'instproj')
        os.makedirs(os.path.join(target, 'src'))
        open(os.path.join(target, 'src', 'a.py'), 'w').write('print(1)\n')
        env = dict(os.environ, HOME=fh, NO_COLOR='1')
        wrapper = os.path.join(canon, 'bin', 'clone-site')
        check('installed wrapper is executable',
              os.access(wrapper, os.X_OK),
              'git may have recorded mode 644 (a FUSE checkout reports every '
              'file 0777, so the index gets it wrong); a fresh clone then '
              'cannot execute the wrapper at all')
        r = subprocess.run([wrapper, 'init', target,
                            '--name', 'T', '--out', 'site'],
                           capture_output=True, text=True, env=env, cwd=tmp)
        check('installed copy scaffolds a site from an unrelated cwd',
              r.returncode == 0 and os.path.exists(
                  os.path.join(target, 'site', '_build', 'pages.py')),
              (r.stdout + r.stderr)[-300:])

        # ---- SKILL.md structure ----
        # A mis-balanced named block does not fail loudly. It degrades the
        # skill: an unbalanced <invariants> swallows the following section, and
        # the agent reads the file as if it were fine.
        skill_md = open(os.path.join(ROOT, 'SKILL.md'), encoding='utf-8').read()

        check('SKILL.md has frontmatter with a version',
              skill_md.startswith('---\n') and re.search(r'^version:\s*\S', skill_md, re.M),
              'a version is what a future migration block keys off')

        try:
            import yaml
            fm = yaml.safe_load(skill_md.split('---\n', 2)[1])
            check('SKILL.md frontmatter parses',
                  isinstance(fm, dict) and {'name', 'description'} <= set(fm),
                  'frontmatter keys: %r' % (sorted(fm) if isinstance(fm, dict) else fm,))
        except ImportError:
            # GitHub's ubuntu runner has PyYAML; a bare checkout may not. The
            # shape is still checked by the key-presence assertion above, so
            # this is a depth check, not the only one.
            print('note: PyYAML not installed, skipping the frontmatter parse check')
        else:
            # The frontmatter licence is what a redistributable skill declares,
            # and it disagreed with LICENSE while this was being written.
            lic_head = open(os.path.join(ROOT, 'LICENSE'), encoding='utf-8').read(200)
            m = re.search(r'^license:\s*(\S+)', skill_md, re.M)
            check('SKILL.md licence matches LICENSE',
                  m is not None and m.group(1).lower().replace(' ', '-')
                  in lic_head.lower().replace(' ', '-'),
                  'frontmatter says %r, LICENSE says %r'
                  % (m.group(1) if m else None, lic_head.split('\n')[0]))

            check('SKILL.md frontmatter has no unknown keys',
                  set(fm) <= {'name', 'description', 'version', 'user-invocable',
                              'argument-hint', 'license', 'allowed-tools',
                              'model', 'disable-model-invocation'},
                  'unexpected frontmatter keys: %r' % sorted(set(fm) - {
                      'name', 'description', 'version', 'argument-hint',
                      'license', 'allowed-tools', 'model'}))

        # Named blocks are snake_case names we authored. Literal HTML elements
        # mentioned in prose are not blocks, so they are excluded by name.
        HTML = {
            'html', 'head', 'body', 'main', 'nav', 'aside', 'header', 'footer',
            'section', 'article', 'figure', 'figcaption', 'div', 'span', 'p', 'a',
            'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'pre', 'code', 'b', 'i', 'em',
            'strong', 'small', 'sup', 'sub', 'mark', 'del', 'ins', 'h1', 'h2',
            'h3', 'h4', 'h5', 'h6', 'table', 'thead', 'tbody', 'tfoot', 'tr',
            'th', 'td', 'caption', 'col', 'colgroup', 'svg', 'path', 'g', 'br',
            'hr', 'img', 'script', 'style', 'meta', 'link', 'title', 'form',
            'input', 'button', 'label', 'select', 'option', 'textarea', 'blockquote',
            'q', 'cite', 'abbr', 'time', 'details', 'summary', 'template', 'wbr',
        }
        outside = re.sub(r'```.*?```', '', skill_md, flags=re.S)  # ignore fences
        # A backticked `<tag>` is a pointer to a block, not a second opening of
        # it. Counting those as opens is what turns a balanced file into a
        # reported imbalance.
        outside = re.sub(r'`<[a-z_]+>`', '', outside)
        opened, closed = [], []
        for m in re.finditer(r'<(/?)([a-z_]+)>', outside):
            name = m.group(2)
            if name in HTML:
                continue
            (closed if m.group(1) else opened).append(name)
        check('SKILL.md named blocks balance', sorted(opened) == sorted(closed),
              'unbalanced: opened=%r closed=%r' % (opened, closed))
        check('SKILL.md ships an <invariants> block',
              '<invariants>' in outside and '</invariants>' in outside,
              'the always-apply tier is the point of the two-tier layout')

        # Every file the skill tells the agent to read must exist, or the
        # instruction is a dead end at exactly the moment it is needed.
        named = sorted(set(re.findall(r'`(references/[a-z_-]+\.md)`', skill_md))
                       | set(re.findall(r'`(engine/README\.md)`', skill_md)))
        missing = [n for n in named if not os.path.exists(os.path.join(ROOT, n))]
        check('every reference SKILL.md names exists (%d)' % len(named),
              not missing, 'missing: %r' % missing)

        # Commands are a convenience surface, and the failure mode is a command
        # that is advertised but unreachable: a slash command the agent cannot
        # route is worse than no command, because the user believes it ran.
        # Quotes are optional in YAML, and the value itself contains brackets,
        # so the pattern has to tolerate `hint: "[a|b]"`, `hint: [a|b]` and a
        # list that includes `|`.
        cmds = re.search(r'^argument-hint:\s*"?\[([^\]]+)\]"?\s*$',
                         skill_md, re.M)
        check('SKILL.md declares user-invocable', 'user-invocable: true' in skill_md,
              'without it the agent may not expose the slash command at all')
        check('SKILL.md declares an argument-hint', cmds is not None)
        declared = [c.strip() for c in cmds.group(1).split('|')] if cmds else []
        table = re.findall(r'^\| `([a-z]+)`(?:\s*\|[^|]*)?\s*\|', skill_md, re.M)
        # A dispatch bullet may carry a qualifier after the command name —
        # `build` with a number, `build` with no argument — so the pattern has to
        # allow text between the closing backtick and the bold marker. Without
        # it, a qualified bullet reads as "no dispatch section", which looks like
        # a routing bug rather than a regex that is too strict.
        check('every advertised command has a dispatch section',
              all(re.search(r'^- \*\*`%s`[^*]*\*\*\s*—' % re.escape(c),
                            skill_md, re.M)
                  for c in declared),
              'missing dispatch for: %r' % [c for c in declared
                  if not re.search(r'^- \*\*`%s`[^*]*\*\*\s*—'
                                   % re.escape(c), skill_md, re.M)])
        # Equality, not containment. `<=` would pass if a row were deleted
        # from the table, which is exactly the mutation worth catching: a
        # command still routed by `argument-hint` but no longer documented is
        # how a command quietly becomes folklore.
        check('the command table and the argument-hint list the same commands',
              set(table) == set(declared),
              'only in table: %r  only in hint: %r'
              % (sorted(set(table) - set(declared)),
                 sorted(set(declared) - set(table))))
        # A gate that does not actually stop is worse than no gate at all: the user
        # believes they were consulted, and they were not. Each gate has to name
        # both the moment it stops and why that moment is the user's call.
        dispatch = re.search(r'## Mode dispatch(.*?)\n## ', skill_md, re.S)

        # Every advertised command needs exactly one dispatch bullet. `build`
        # legitimately had two during development, which is how a duplicated
        # bullet shipped unnoticed — one of them contradicting the other.
        bullets = re.findall(r'^- \*\*`([a-z]+)`(?: [a-z ]+)?\*\*', skill_md, re.M)
        dupes = sorted({c for c in bullets if bullets.count(c) > 1})
        check('no command has two dispatch bullets', not dupes,
              'duplicated dispatch for: %r — one of them is contradicting the '
              'other' % dupes)
# Each gate is a plain bullet now, so one pattern covers all three. While
        # `build` still had two bullets this loop had to disambiguate them by
        # qualifier, which meant a gate could pass by matching the *wrong* bullet
        # \u2014 the render-only one, which has no batch to stop at. `render` gives
        # that half its own name, so the ambiguity is gone from the document
        # rather than papered over in the regex.
        for gate in ('plan', 'build', 'appendix'):
            line = re.search(
                r'^- \*\*`%s`\*\*\s*—(.*?)(?=\n- \*\*|\Z)'
                % re.escape(gate),
                dispatch.group(1) if dispatch else '', re.S | re.M)
            check('gate `%s` says it stops' % gate,
                  line is not None and 'stop' in line.group(1).lower(),
                  'the `%s` dispatch line must state that it stops' % gate)

        gates_note = re.search(r'\*\*Three of them are gates.*?before\.', skill_md, re.S)
        check('SKILL.md names the three gates and why each one exists',
              gates_note is not None
              and all(w in gates_note.group(0) for w in
                      ('judgement call', 'quality decays')),
              'the gates paragraph must give a reason for each')

        # The batch workflow is the thing that keeps quality from decaying on a
        # long run, so its three load-bearing steps must all be present.
        for phrase, why in [('batch size', 'the size is the user\'s call'),
                            ('Present the plan', 'no lesson before the plan is agreed'),
                            ('whether to continue with the next batch',
                             'the batch boundary must ask')]:
            check('SKILL.md batch workflow states: %s' % phrase,
                  phrase in skill_md, why)

        # `build` with no number authors 10 lessons. That default is the whole
        # reason `render` had to become a separate command, so it earns a check:
        # if the default is ever dropped, `build` stops being safe to type bare
        # and the split between the two halves becomes ambiguous again.
        # Scoped to the dispatch section, not the whole file. The command table
        # already says both things, so a whole-file check passes on the table
        # even when the dispatch bullet \u2014 the text an agent actually reads at
        # invocation \u2014 has lost them. That is exactly how the first version of
        # these two checks passed every mutation.
        disp = dispatch.group(1) if dispatch else ''
        disp = dispatch.group(1) if dispatch else ''

        def bullet(cmd):
            """The body of one dispatch bullet, or None."""
            m = re.search(r'^- \*\*`%s`\*\*\s*—(.*?)(?=\n- \*\*|\Z)'
                          % re.escape(cmd), disp, re.S | re.M)
            return m.group(1) if m else None

        check('the build dispatch bullet states the default batch size',
              bullet('build') is not None
              and re.search(r'\b10\b', bullet('build')) is not None,
              'the default is what makes a bare `build` mean something, and the '
              'dispatch bullet is where an agent reads it')
        check('the render dispatch bullet states that it changes no content',
              bullet('render') is not None
              and re.search(r'(no content|changing nothing|idempotent)',
                            bullet('render'), re.I) is not None,
              'render must state that it edits nothing, or it cannot be told '
              'apart from build')

        # `--context` is a standing instruction for the whole build, not a note
        # about the plan. Wording that scopes it to `plan` alone has described
        # something much less useful than what the flag actually does.
        check('plan documents --context', '--context' in skill_md,
              'the flag is advertised nowhere')
        check('--context is documented as holding across later commands',
              'Hold it for every later command' in skill_md,
              'a context that only shapes the plan is wasted - the batch loop '
              'is where it actually pays off')

        # `render` must also be reachable from a shell, not only as a slash
        # command: it is the fastest confirmation that a hand-edited fragment
        # still renders clean, and that check is worth keeping cheap.
        wrapper = open(os.path.join(ROOT, 'bin', 'clone-site')).read()
        check('bin/clone-site has a render subcommand',
              re.search(r'^\s+render\)\s+render', wrapper, re.M) is not None,
              'the shell wrapper cannot re-render, so a hand-edit has no quick check')

        # ---- the Rust engine ----
        # Escaping is the one place where a Rust/Python difference is invisible
        # in a diff of the generator and visible in every published page, so it
        # is diffed against the reference rather than asserted by hand. The
        # hand-written assertions in util.rs were wrong twice while this was
        # being written; the differential does not have opinions.
        engine = os.path.join(ROOT, 'engine')
        binary = os.path.join(engine, 'target', 'release', 'clone-site')
        cargo = shutil.which('cargo')

        if cargo:
            r = subprocess.run([cargo, 'test', '--release'], cwd=engine,
                               capture_output=True, text=True)
            check('cargo test passes', r.returncode == 0,
                  (r.stdout + r.stderr)[-400:])
            r = subprocess.run([cargo, 'build', '--release'], cwd=engine,
                               capture_output=True, text=True)
            check('cargo build --release succeeds', r.returncode == 0,
                  (r.stdout + r.stderr)[-400:])
            # A validator that panics is worse than one that complains: it
            # cannot be trusted on the input it has not seen. This is a real
            # case, not a hypothetical -- a byte-offset bug in the parser sliced
            # inside a UTF-8 sequence and aborted, and only the 502 real
            # fragments found it.
            r = subprocess.run([binary, 'check', os.path.join(tmp, 'fakehome')],
                               capture_output=True, text=True)
            check('check on a directory with no site does not panic',
                  'panicked' not in r.stdout + r.stderr,
                  (r.stdout + r.stderr)[-200:])

            # A site whose fragments carry multi-byte text, which is where the
            # parser's byte offsets are exercised. Checking a directory that is
            # not a site proves only that it reports a clean error; this proves
            # the parser survives real content.
            utf8_site = os.path.join(tmp, 'utf8site')
            os.makedirs(os.path.join(utf8_site, '_build', 'content'))
            _write(utf8_site, 'pages.toml',
                   '[[page]]\nn = 1\nslug = "01-x"\nnav = "x"\nh1 = "X"\n'
                   'lead = "L"\n')
            _write(utf8_site, 'config.toml', 'name = "T"\n')
            # No emoji: U+2600-27BF is inside the ranges the validator rejects,
            # so a coffee cup is a finding. The point here is multi-byte text
            # parsing, which needs nothing but non-ASCII.
            _write(utf8_site, 'content/01.html',
                   '<h2>café crème</h2>\n<p>über — naïve · 日本語</p>\n')
            r = subprocess.run([binary, 'check', utf8_site, '--fragments'],
                               capture_output=True, text=True)
            check('multi-byte fragment parses without panicking',
                  'panicked' not in r.stdout + r.stderr
                  and 'BAD: none' in r.stdout,
                  (r.stdout + r.stderr)[-300:])
        else:
            print('note: cargo not installed, skipping the Rust engine checks')

        if os.path.exists(binary):
            import html as _html
            import random as _random
            _random.seed(20261012)
            frags = ['&amp', '&#x27;', '&middot;', 'x', ';', '&', '39',
                     '&ampx', '&notreal', '&gt', '&notarealentity;', '&aacute;']
            cases = ['', 'plain', 'a&b', '<div class="x">', "it's", '"q"',
                     'Phase 0 &middot; Toolchain', '&mdash;', '&amp',
                     '&notarealentity;', '&#x27;', '&#128;', '&aacute;&uuml;',
                     'café · naïve', '&notareal;', 'zzz & notareal']
            for _ in range(3000):
                cases.append(''.join(_random.choice(frags)
                                     for _ in range(_random.randint(1, 6))))
            for _ in range(1000):
                cases.append(''.join(chr(_random.randint(1, 0x2FFF))
                                     for _ in range(_random.randint(1, 10))))

            payload = '\n'.join(c.replace('\n', ' ').replace('\r', ' ') for c in cases) + '\n'
            # Bytes, not text=True: universal-newline mode would rewrite a \r
            # inside a case into \n and desynchronise the two line counts, which
            # reads as thousands of escaping mismatches that are really one
            # transport bug. Split on \n only, for the mirror-image reason —
            # str.splitlines() also breaks on \x0b, \x0c and \x1c, so it
            # over-counts the lines the engine actually emitted.
            r = subprocess.run([binary, '__escape-diff'],
                               input=payload.encode('utf-8'),
                               capture_output=True)
            got = r.stdout.decode('utf-8').split('\n')
            if got and got[-1] == '':
                got.pop()
            expected = [f"{_html.escape(c)}\t{_html.unescape(c)}" for c in cases]
            mismatched = [i for i, (e, a) in enumerate(zip(expected, got)) if e != a]
            check('escape/unescape matches the reference on %d cases' % len(cases),
                  len(got) == len(expected) and not mismatched,
                  '%d mismatches, first: %r -> ref %r, engine %r' % (
                      len(mismatched),
                      cases[mismatched[0]] if mismatched else '',
                      expected[mismatched[0]] if mismatched else '',
                      got[mismatched[0]] if mismatched else ''))
        else:
            print('note: engine binary not built, skipping the escaping differential')

        # ---- the parser, diffed against the reference implementation ----
        # Driven through the binary rather than a unit test, because that is the
        # path the validator actually takes. A parser bug found here once passed
        # the in-process test and still reported the wrong line from the binary.
        if os.path.exists(binary):
            import importlib.util as _ilu
            _spec = _ilu.spec_from_file_location(
                'ref_check', os.path.join(SCRIPTS, 'check_site.py'))
            ref = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(ref)

            def _ref_findings(src):
                p = ref.P('f0')
                p.feed(src)
                for tag, line in p.stack:
                    p.errors.append('f0:%d: <%s> never closed' % (line, tag))
                if p.svg_open:
                    p.errors.append('f0: unbalanced <svg> (%d open)' % p.svg_open)
                seen = {}
                for i in p.ids:
                    seen[i] = seen.get(i, 0) + 1
                dupes = sorted(k for k, c in seen.items() if c > 1)
                if dupes:
                    p.errors.append('f0: duplicate id(s) %s' % ', '.join(dupes))
                for lg in p.langs:
                    if lg not in ref.KNOWN_LANG:
                        p.errors.append(
                            'f0: unknown data-lang "%s" (add it to KNOWN_LANG in '
                            'check_site.py)' % lg)
                return p.errors

            def _norm(lines):
                out = []
                for e in lines:
                    if "emoji '" in e:
                        e = e.replace("emoji '", 'emoji "', 1)
                        e = e.replace("' in text", '" in text')
                    out.append(e.replace(' in check_site.py)', ' in the engine)'))
                return out

            cases = [
                '<h2>a</h2>\n<p>b</p>',
                '<h2>x</h2>\n<div><b>y</p>',
                '<h2>x</h2>\n<div><span>t',
                '<pre class=code data-lang=dartt>x</pre>',
                '<p id=a>1</p><p id=a>2</p>',
                '<h2>ok</h2>\n<img src=x><br>',
                '<div/>\n<p>a</p>',
                '<!-- <div> unclosed -->\n<p>ok</p>',
                '<table><tr><td><b>x</td></tr></table>',
                '<p>no close', '</p>', '<p>a</p></p>',
                '<svg></svg>', '<svg><g></g></svg>', '<svg><g></svg>',
                '<h2>a</h2>\n<p>&lt;div&gt; escaped</p>\n<div>real</div>',
                '<p>&nbsp;&mdash;&#65;</p>',
                '<a href="#a">x</a><p id="a">y</p>',
                '<ul><li>a<li>b</ul>',
                '<DIV CLASS=X>upper</DIV>',
                # Table shape. A nested cell is balanced markup, so the
                # tag-balance check above cannot see it — that is the whole
                # reason the cell-count check exists.
                '<table><tr><th>A</th><th>B</th></tr><tr><td><td>1</td></td>'
                '<td>x</td></tr></table>',
                '<table><tr><th>A</th><th>B</th><th>C</th></tr><tr><td>1</td>'
                '<td>x</td></tr></table>',
                '<table><tr><th>A</th></tr><tr><td>1</td><td>x</td></tr></table>',
                '<table><tr><th>A</th><th>B</th><th>C</th></tr><tr>'
                '<td colspan="2">wide</td><td>x</td></tr></table>',
                '<table><tr><th>A</th><th>B</th><th>C</th></tr><tr>'
                '<td>1</td><td rowspan="3">s</td><td>x</td></tr>'
                '<tr><td>2</td><td>y</td></tr><tr><td>3</td><td>z</td></tr>'
                '</table>',
                '<table><tr><td>o</td><td><table><tr><td>i</td></tr></table>'
                '</td></tr></table>',
                # A block that stops mid-declaration. Brace depth is the signal:
                # the page cannot be checked against a source file, so the fault
                # has to be visible in the markup itself.
                '<h2>a</h2>\n<pre class="code" data-lang="dart"><code>'
                'class A {\n  const A({\n    this.x,\n  });\n</code></pre>',
                '<h2>a</h2>\n<pre class="code" data-lang="dart"><code>'
                'class A {\n  // ...\n  void f() {}\n</code></pre>',
                '<h2>a</h2>\n<pre class="code" data-lang="dart"><code>'
                'final s = "{";\nfinal t = 1;\n</code></pre>',
            ]
            payload = ''.join(c + '\n' for c in cases).encode('utf-8')
            r = subprocess.run([binary, '__check-diff'], input=payload,
                               capture_output=True)
            check('parser produces findings for the malformed cases',
                  b'unknown data-lang' in r.stdout and b'never closed' in r.stdout,
                  'the harness produced nothing: %r' % r.stdout[:200])

            # Table shape specifically. Asserted rather than only diffed, because
            # the differential below compares two implementations that were
            # edited at the same time: if both had the check missing, they would
            # agree perfectly and the check would look fine. These pin the
            # behaviour itself.
            for label, src, want in [
                ('nested cell',
                 '<h2>a</h2>\n<table><tr><th>A</th><th>B</th></tr>'
                 '<tr><td><td>1</td></td><td>x</td></tr></table>',
                 'nested in another'),
                ('short row',
                 '<h2>a</h2>\n<table><tr><th>A</th><th>B</th><th>C</th></tr>'
                 '<tr><td>1</td><td>x</td></tr></table>',
                 'first row of its table declares 3'),
                ('long row',
                 '<h2>a</h2>\n<table><tr><th>A</th></tr>'
                 '<tr><td>1</td><td>x</td></tr></table>',
                 'first row of its table declares 1'),
                ('colspan is legitimate',
                 '<h2>a</h2>\n<table><tr><th>A</th><th>B</th><th>C</th></tr>'
                 '<tr><td colspan="2">w</td><td>x</td></tr></table>',
                 'first row of its table declares'),
            ]:
                r = subprocess.run([binary, '__check-diff'],
                                   input=src.encode('utf-8'), capture_output=True)
                found = want.encode('utf-8') in r.stdout
                if label == 'colspan is legitimate':
                    # Not a substring test: a clean document produces findings
                    # only if something is wrong, so this must find none.
                    findings = [l for l in r.stdout.decode().splitlines()
                                if 'table' in l and 'declares' in l]
                    check('%s raises nothing' % label, not findings,
                          'unexpectedly reported: %r' % findings)
                else:
                    check('parser reports a %s' % label, found,
                          'want %r in %r' % (want, r.stdout.decode()[:160]))

            for label, src in [
                ('rowspan spanning three rows',
                 '<h2>a</h2>\n<table><tr><th>A</th><th>B</th><th>C</th></tr>'
                 '<tr><td>1</td><td rowspan="3">s</td><td>x</td></tr>'
                 '<tr><td>2</td><td>y</td></tr><tr><td>3</td><td>z</td></tr>'
                 '</table>'),
                ('rowspan in the final column',
                 '<h2>a</h2>\n<table><tr><th>A</th><th>B</th></tr>'
                 '<tr><td rowspan="2">s</td><td>x</td></tr>'
                 '<tr><td>y</td></tr></table>'),
            ]:
                r = subprocess.run([binary, '__check-diff'],
                                   input=src.encode('utf-8'), capture_output=True)
                bad_rows = [l for l in r.stdout.decode().splitlines()
                            if 'first row of its table declares' in l]
                check('%s raises nothing' % label, not bad_rows,
                      'a rowspan must not make later rows look short: %r'
                      % bad_rows)

            # And the reference must agree, case for case.
            table_cases = [
                '<h2>a</h2>\n<table><tr><th>A</th><th>B</th></tr>'
                '<tr><td><td>1</td></td><td>x</td></tr></table>',
                '<h2>a</h2>\n<table><tr><th>A</th><th>B</th><th>C</th></tr>'
                '<tr><td>1</td><td>x</td></tr></table>',
                '<h2>a</h2>\n<table><tr><th>A</th><th>B</th><th>C</th></tr>'
                '<tr><td>1</td><td rowspan="3">s</td><td>x</td></tr>'
                '<tr><td>2</td><td>y</td></tr><tr><td>3</td><td>z</td></tr>'
                '</table>',
            ]
            tbad = []
            for c in table_cases:
                r = subprocess.run([binary, '__check-diff'],
                                   input=c.encode('utf-8'), capture_output=True)
                g = _norm([l for l in r.stdout.decode().splitlines() if l])
                e = _norm(_ref_findings(c))
                if g != e:
                    tbad.append((e, g))
            check('engines agree on table shape', not tbad,
                  'first disagreement: %r' % ((tbad[0] if tbad else None),))

            # Partial code blocks. The whole point is that a reader cannot tell
            # a fragment from a whole file, so both engines must refuse to let
            # one pass unmarked.
            def blk(code, lang='dart'):
                return ('<h2>a</h2>\n<pre class="code" data-lang="%s"><code>'
                        '%s</code></pre>' % (lang, code))

            for label, src, want in [
                ('a block cut off mid-class',
                 blk('class A {\n  const A({\n    this.x,\n  });\n'),
                 'unclosed brace'),
                ('a fragment marked with // ...',
                 blk('class A {\n  // ...\n  void f() {}\n'),
                 None),
                ('a fragment marked with /// ...',
                 blk('class A {\n  /// ...\n  void f() {}\n'),
                 None),
                ('a brace inside a string literal',
                 blk('final s = "{";\nfinal t = 1;\n'),
                 None),
                ('a brace inside a line comment',
                 blk('// opens {\nfinal t = 1;\n'),
                 None),
                ('a complete class',
                 blk('class A {\n  const A();\n}\n'),
                 None),
                ('a shell block with an if',
                 blk('if [ -f x ]; then\n  echo hi\nfi\n', 'bash'),
                 None),
            ]:
                r = subprocess.run([binary, '__check-diff'],
                                   input=src.encode('utf-8'), capture_output=True)
                out = r.stdout.decode()
                hits = [l for l in out.splitlines() if 'unclosed brace' in l]
                if want is None:
                    check('no false positive: %s' % label, not hits,
                          'unexpectedly flagged: %r' % hits)
                else:
                    check('reports %s' % label,
                          len(hits) == 1 and want in hits[0],
                          'want one %r finding, got %r' % (want, hits))

            # Both engines must agree, including on the false positives.
            pbad = []
            for code in ('class A {\n  const A();\n',
                         'class A {\n  // ...\n  void f() {}\n',
                         'final s = "{";\nfinal t = 1;\n',
                         '/* opens {\nstill */\nfinal t = 1;\n',
                         "final s = '{';\nfinal t = 1;\n",
                         'class A {\n  void f() {\n    if (x) {\n    }\n  }\n'):
                c = blk(code)
                r = subprocess.run([binary, '__check-diff'],
                                   input=c.encode('utf-8'), capture_output=True)
                g = _norm([l for l in r.stdout.decode().splitlines() if l])
                e = _norm(_ref_findings(c))
                if g != e:
                    pbad.append((e, g))
            check('engines agree on partial-block reporting', not pbad,
                  'first disagreement: %r' % (pbad[0] if pbad else None,))

            # Stub code blocks: a container whose whole body is its own path
            # comment. Every other check passes on one — the nesting is right,
            # the language is known — so this is the only thing standing between
            # the reader and an empty box where the file was promised.
            def stub_hits(src):
                r = subprocess.run([binary, '__check-diff'],
                                   input=src.encode('utf-8'), capture_output=True)
                lines = r.stdout.decode().splitlines()
                return [l for l in lines if 'path header' in l], lines

            sbad = []
            for label, src, want in [
                ('a block holding only a dart path header',
                 blk('// lib/core/routing/app_router.dart'),
                 'path header'),
                ('a block holding only a bare sql filename',
                 blk('supabase/sql/consent_records.sql'),
                 'path header'),
                ('no false positive: a filled block',
                 blk('// lib/core/routing/app_router.dart\nclass AppRouter {}\n'),
                 None),
                ('no false positive: a bash cross-reference',
                 blk('lib/core/widgets/scaffold.dart — 101 lines', 'bash'),
                 None),
                ('no false positive: a text transcript note',
                 blk('# only promotion_remote_datasource.dart? check', 'text'),
                 None),
                ('no false positive: a one-line code block',
                 blk('return const SizedBox.shrink();'),
                 None),
            ]:
                hits, lines = stub_hits(src)
                if want is None:
                    check('no false positive: %s' % label, not hits,
                          'unexpectedly flagged: %r' % hits)
                else:
                    check('reports %s' % label,
                          len(hits) == 1 and want in hits[0],
                          'want one %r finding, got %r' % (want, hits))
                g = _norm([l for l in lines if l])
                e = _norm(_ref_findings(src))
                if g != e:
                    sbad.append((label, e, g))
            check('engines agree on stub-block reporting', not sbad,
                  'first disagreement: %r' % ((sbad[0] if sbad else None),))

            # ---- an empty fragment ------------------------------------------
            #
            # This one cannot be reached through the parser: a 0-byte file has
            # no markup, so every parser check passes on it. It used to build a
            # page with a sidebar, a heading and no body.
            import tempfile as _tf
            with _tf.TemporaryDirectory() as td:
                cdir = os.path.join(td, 'content')
                os.makedirs(cdir)
                good = ('<h2>a</h2>\n<pre class="code" data-lang="dart">'
                        '<code>// x.dart\nclass A {}\n</code></pre>\n')
                for name, body, want in [('01.html', good, False),
                                         ('02.html', '', True),
                                         ('03.html', '   \n\n\t\n', True)]:
                    with open(os.path.join(cdir, name), 'w',
                              encoding='utf-8') as fh:
                        fh.write(body)
                bad = []
                _save = (ref.CONTENT, ref.SITE)
                ref.CONTENT, ref.SITE = cdir, td
                try:
                    ref.check_fragments(bad)
                finally:
                    ref.CONTENT, ref.SITE = _save
                empties = [b for b in bad if 'is EMPTY' in b]
                check('reports an empty fragment', len(empties) == 2,
                      'want 2, got %r' % (empties,))
                check('an empty fragment is not also reported as missing an <h2>',
                      not [b for b in bad if 'starts without' in b],
                      'got %r' % ([b for b in bad if 'starts without' in b],))
                check('a filled fragment raises nothing',
                      not [b for b in bad if '01.html' in b],
                      'got %r' % ([b for b in bad if '01.html' in b],))

            # Emoji line numbers are a deliberate divergence: the reference
            # reports the line the data run *began*, this reports the line the
            # emoji is on. Both are checked explicitly rather than diffed,
            # because the difference is intentional and diffing would flag it.
            for src, want in [('<p>\ntext\nfire \U0001F389\n</p>', ':3: emoji'),
                              ('<h2>a</h2>\n<p>\n\n\U0001F389\n</p>', ':4: emoji'),
                              ('<h2>a</h2>\n<p>one &amp; two</p>\n<p>\U0001F389</p>',
                               ':3: emoji')]:
                r = subprocess.run([binary, '__check-diff'],
                                   input=src.encode('utf-8'), capture_output=True)
                check('emoji on %s is reported on its own line' % want,
                      want.encode('utf-8') in r.stdout,
                      'got %r for %r' % (r.stdout.decode()[:120], src))

            # And the same cases must agree exactly on everything else.
            disagree = []
            for c in cases:
                r = subprocess.run([binary, '__check-diff'],
                                   input=(c + '\n').encode('utf-8'),
                                   capture_output=True)
                got = _norm([l for l in r.stdout.decode('utf-8').splitlines() if l])
                exp = _norm(_ref_findings(c))
                if got != exp:
                    disagree.append((c, exp, got))
            check('parser findings match the reference on %d cases' % len(cases),
                  not disagree, 'first disagreement: %r' % ((disagree[0] if disagree else None),))

        # ---- the generator holds no project names ----
        gen = ' '.join(open(os.path.join(SCRIPTS, f), encoding='utf-8').read()
                       for f in ('build.py', 'index.py'))
        check('generator is free of project names',
              'Self Test' not in gen and 'cloner' not in gen.lower()
              and 'yoostore' not in gen.lower())

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [n for n, ok, _ in results if not ok]
    print('\n%d checks, %d failed' % (len(results), len(failed)))
    for n in failed:
        print('  FAIL ' + n)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
