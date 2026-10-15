#!/usr/bin/env python3
"""Creates a working clone-site for any project, in one command.

    python3 scripts/bootstrap.py ~/code/some-project --name "Some Project"
    python3 scripts/bootstrap.py ~/code/some-project --name X --out docs/guide
    python3 scripts/bootstrap.py ~/code/some-project --name X --force

What it does: copies the generator into <out>/_build, copies the design system
into <out>/assets, writes a config.py filled in from the template, drops in one
example lesson, then runs the build and both validators to prove the result is
valid before you have written anything.

It deliberately does NOT try to write the lessons. Deciding what the steps are
means reading the target repository, and a generated lesson list that nobody
checked is worse than no lesson list. What it gives you instead is a site that
builds, a validator that catches authoring mistakes as you make them, and
templates showing the shape of a page. Run scan.py next for a draft ordering.

Exit code 0 means the scaffold built and validated. Anything else means read
the output — bootstrap aborts rather than leaving a half-written tree.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Copied into the generated site. build.py holds no project names of its own,
# so these files stay byte-identical between projects and can be updated later
# by copying over the top.
#
# `menu.py` is here because build.py and index.py both import it, and it is
# absent from this list in v1.1 — which meant every freshly scaffolded site
# failed its own smoke test with `ModuleNotFoundError: No module named 'menu'`.
# The scaffold has always run build.py immediately after copying, so this was
# caught by the scaffold itself rather than in the wild, which is why it
# survived: nobody had a site that had not been scaffolded by this script.
#
# `sync.py` is copied so the site can be brought back in line with a repository
# that has moved on. `migrate.py` is NOT copied — it runs once, from the
# installed skill, to bring an existing site forward to the current version.
GENERATOR = ['build.py', 'index.py', 'check_site.py', 'check_svg.py', 'menu.py',
             'sync.py']
STYLES = ['style.css', 'app.js']


def die(msg, code=1):
    print('bootstrap: ' + msg, file=sys.stderr)
    sys.exit(code)


def titlecase(s):
    """'my cool lib' -> 'My Cool Lib'. Deliberately dull: the user edits this."""
    return ' '.join(w[:1].upper() + w[1:] for w in s.split())


def write_config(dest, name, source_root):
    src = open(os.path.join(ROOT, 'templates', 'config.py'), encoding='utf-8').read()
    subs = [
        ("'name': 'My Project',", "'name': %r," % name),
        ("'eyebrow': 'MYPROJECT',", "'eyebrow': %r," % name.upper()[:12]),
        ("'title': 'My Project, from nothing',", "'title': %r," % name),
        ("'source_root': '/absolute/path/to/the/repo',",
         "'source_root': %r," % source_root),
    ]
    for old, new in subs:
        if old not in src:
            die('config template is missing the line %r — the template and this '
                'script have drifted apart' % old)
        src = src.replace(old, new, 1)
    with open(dest, 'w', encoding='utf-8') as f:
        f.write(src)


def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('project', help='path to the repository being documented')
    ap.add_argument('--name', help='display name of the project (default: the '
                                   'directory name)')
    ap.add_argument('--out', default='docs/site',
                    help='where to write the site, relative to the project '
                         '(default: docs/site)')
    ap.add_argument('--force', action='store_true',
                    help='overwrite an existing scaffold')
    args = ap.parse_args()

    project = os.path.abspath(os.path.expanduser(args.project))
    if not os.path.isdir(project):
        die('no such directory: ' + project)

    name = args.name or titlecase(os.path.basename(project))
    out = args.out if os.path.isabs(args.out) else os.path.join(project, args.out)
    build_dir = os.path.join(out, '_build')

    if os.path.exists(out):
        htmls = [f for f in os.listdir(out) if f.endswith('.html')]
        if htmls and not args.force:
            die('%s already holds %d built pages. Refusing to overwrite. Re-run '
                'with --force to replace assets/ and the generator — your own '
                '_build/content/ fragments are left alone.'
                % (out, len(htmls)))

    os.makedirs(os.path.join(build_dir, 'content'), exist_ok=True)
    os.makedirs(os.path.join(out, 'assets'), exist_ok=True)

    for f in GENERATOR:
        shutil.copy2(os.path.join(HERE, f), os.path.join(build_dir, f))
    for f in STYLES:
        shutil.copy2(os.path.join(ROOT, 'assets', f), os.path.join(out, 'assets', f))

    write_config(os.path.join(build_dir, 'config.py'), name, project)

    # The example fragment is named after the first lesson's slug, because
    # fragments are keyed by slug. Copying it to a fixed `01.html` produced a
    # scaffold that could not build itself — the builder looks for
    # `content/<slug>.html` and found nothing. The name is read from the
    # template's own pages.py rather than hardcoded, so the two cannot drift.
    example_slug = None
    ns = {}
    with open(os.path.join(ROOT, 'templates', 'pages.py'), encoding='utf-8') as f:
        exec(compile(f.read(), 'pages.py', 'exec'), ns)
    if ns.get('PAGES'):
        example_slug = ns['PAGES'][0].get('slug')

    if example_slug:
        example = os.path.join(build_dir, 'content', '%s.html' % example_slug)
        if args.force or not os.path.exists(example):
            shutil.copy2(os.path.join(ROOT, 'templates', 'content', '01.html'), example)
    if args.force or not os.path.exists(os.path.join(build_dir, 'pages.py')):
        shutil.copy2(os.path.join(ROOT, 'templates', 'pages.py'),
                     os.path.join(build_dir, 'pages.py'))

    print('scaffolded %s' % out)
    print('  %s' % os.path.join(out, 'assets', 'style.css'))
    print('  %s' % os.path.join(build_dir, 'pages.py'))

    for cmd in (['python3', 'build.py'], ['python3', 'index.py'],
                ['python3', 'check_site.py'], ['python3', 'check_svg.py']):
        code, out_txt = run(cmd, build_dir)
        tag = 'ok  ' if code == 0 else 'FAIL'
        print('  %s %-18s %s' % (tag, ' '.join(cmd[1:]),
                                  out_txt.splitlines()[-1] if out_txt else ''))
        if code != 0:
            print('\n--- %s ---\n%s' % (' '.join(cmd), out_txt))
            die('the scaffold did not validate. Nothing else was touched.')

    print('\nSite is live: file://%s/index.html' % out)
    print('\nNext:')
    print('  python3 %s scan.py %s        # draft the step order'
          % (os.path.join(ROOT, 'scripts'), project))
    print('  open %s and edit pages.py' % os.path.join(build_dir, 'pages.py'))
    print('\nRebuild loop (always build before validating — the validators read'
          ' the generated pages):')
    print('  cd %s && python3 build.py && python3 index.py && python3 check_site.py'
          % build_dir)


if __name__ == '__main__':
    main()