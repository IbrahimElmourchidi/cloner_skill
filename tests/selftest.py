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


def main():
    tmp = tempfile.mkdtemp(prefix='cloner-selftest-')
    try:
        project = os.path.join(tmp, 'proj')
        os.makedirs(os.path.join(project, 'src'))
        for f in ('main.py', 'util.py', 'store.py'):
            open(os.path.join(project, 'src', f), 'w').write('x = 1\n')
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
        for i, f in enumerate(('main', 'util', 'store'), 1):
            steps.append("    dict(n=%d, slug='%02d-%s', nav='%s',\n"
                         "         h1='The %s file', lead='Lead.',\n"
                         "         path='src/%s.py', phase='Phase 1 &middot; Core'),\n"
                         % (i, i, f, f, f, f))
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
        for i in (1, 2, 3):
            open(os.path.join(bdir, 'content', '%02d.html' % i), 'w').write(
                '<h2>Step %d</h2>\n<p>Body.</p>\n' % i)
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

        # ---- validator catches what it claims to ----
        frag = os.path.join(bdir, 'content', '02.html')
        good = '<h2>Step 2</h2>\n<p>Body.</p>\n'

        # (label, setup, teardown, pattern) — setup returns a teardown callable
        def put(body):
            open(frag, 'w', encoding='utf-8').write(body)

        def take():
            os.rename(frag, frag + '.bak')

            def back():
                os.rename(frag + '.bak', frag)
            return back

        def add_stray():
            stray = os.path.join(bdir, 'content', '77.html')
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

        # ---- escaping survives a round trip ----
        # The fragment is inserted verbatim, so `&lt;int&gt;` stays escaped in the
        # source. What matters is what the BROWSER sees: the text `list[int]`,
        # and no element named `int`. Asserting on the raw string is the
        # mistake this test originally made.
        put('<h2>x</h2>\n<pre class="code" data-lang="python">'
            '<code>def f(x: list[int]) -&gt; None: ...</code></pre>\n')
        rc, out = run(['python3', 'build.py'], bdir)
        page = open(os.path.join(site, '02-util.html'), encoding='utf-8').read()
        tags, text = parse_tags_and_text(page)
        check('escaped generics render as text, not markup',
              rc == 0 and 'int' not in tags and 'list[int]' in text,
              'tags included %r' % sorted(t for t in tags if t == 'int'))
        put(good)

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
        r = subprocess.run([os.path.join(canon, 'bin', 'clone-site'), 'init', target,
                            '--name', 'T', '--out', 'site'],
                           capture_output=True, text=True, env=env, cwd=tmp)
        check('installed copy scaffolds a site from an unrelated cwd',
              r.returncode == 0 and os.path.exists(
                  os.path.join(target, 'site', '_build', 'pages.py')),
              (r.stdout + r.stderr)[-300:])

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