#!/usr/bin/env python3
"""Renders the whole site from _build/pages.py + _build/content/*.html.

    python3 _build/build.py

Everything shared — <head>, sidebar, prev/next, footer — is generated here, so
adding lesson 51 means adding one PAGES entry and one content fragment, never
hand-editing a shell. Lesson pages and appendix pages share one template on
purpose: a fix to the shell then reaches both.

Project-specific text (site name, tagline, where the source lives) lives in
config.py, not here. This file stays byte-identical across every site the
skill produces, so it can be updated by copying a new version over an old one.
"""
import os
import html
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)
CONTENT = os.path.join(HERE, 'content')

sys.path.insert(0, HERE)

from config import SITE as CFG           # noqa: E402
from pages import PAGES as _RAW, APPENDIX as _APPENDIX   # noqa: E402

PAGES = sorted(_RAW, key=lambda d: d['n'])
TOTAL_STEPS = len(PAGES)
APPENDIX_PHASE = CFG.get('appendix_phase', 'Appendix')


def phase_of(p):
    return p.get('phase') or CFG.get('default_phase', 'Setup')


def sidebar(active_n=None, active_slug=None):
    out, phase = [], None
    for p in PAGES:
        ph = phase_of(p)
        if ph != phase:
            phase = ph
            out.append('  <h4>%s</h4>' % html.unescape(ph))
        cur = ' aria-current="page"' if p['n'] == active_n else ''
        out.append(
            '    <li><a href="{slug}.html" data-page="step-{n}"{cur}>'
            '<span class="n">{n:02d}</span><span>{nav}</span>'
            '<span class="tick" hidden>read</span></a></li>'.format(cur=cur, **p))
    if _APPENDIX:
        out.append('  <h4>%s</h4>' % html.unescape(APPENDIX_PHASE))
        for i, a in enumerate(_APPENDIX, 1):
            cur = ' aria-current="page"' if a['slug'] == active_slug else ''
            out.append(
                '    <li><a href="{slug}.html" data-page="appendix{cur}">'
                '<span class="n">A{i}</span><span>{nav}</span>'
                '<span class="tick" hidden>read</span></a></li>'.format(
                    cur=cur, i=i, nav=html.escape(a['nav']), slug=a['slug']))
    note = CFG.get('sidebar_note')
    if note:
        out.append('  <div class="note-box"><p>%s</p></div>' % note)
    return '\n'.join(out)


def steptop(p):
    """The panel above the lesson body: what this step is and why it exists."""
    body = ''
    cmd = p.get('cmd')
    if cmd:
        esc = html.escape(cmd)
        if esc.startswith('$'):
            body += '<pre class="cmd"><code><span class="c-prompt">$</span> ' \
                    + esc[1:].strip() + '</code></pre>'
        else:
            body += '<pre class="cmd"><code>' + esc + '</code></pre>'
    if p.get('path'):
        body += '<div class="srcpath">writes to <b>%s</b></div>' % html.escape(p['path'])
    elif not body:
        body += '<div class="srcpath">This lesson writes <b>no file</b>.</div>'
    why = p.get('why')
    if why:
        body += '<div class="why"><b>Why it exists.</b> %s</div>' % why
    return body


def navbottom_appendix(idx):
    """Appendix pages chain among themselves and link back to the index."""
    parts = []
    if idx > 0:
        q = _APPENDIX[idx - 1]
        parts.append('    <a class="pv" href="%s.html"><span class="lbl">Previous</span>'
                     'A%s &middot; %s</a>'
                     % (q['slug'], idx, html.escape(q['nav'])))
    else:
        parts.append('    <a class="pv" href="index.html">'
                     '<span class="lbl">Back</span>Overview</a>')
    if idx < len(_APPENDIX) - 1:
        q = _APPENDIX[idx + 1]
        parts.append('    <a class="nx" href="%s.html"><span class="lbl">Next</span>'
                     'A%s &middot; %s</a>'
                     % (q['slug'], idx + 2, html.escape(q['nav'])))
    return '\n'.join(parts)


def navbottom(p, idx):
    parts = []
    if idx > 0:
        q = PAGES[idx - 1]
        parts.append('    <a class="pv" href="{slug}.html"><span class="lbl">Previous</span>'
                     'Step {n} &middot; {nav}</a>'.format(**q))
    else:
        parts.append('    <a class="pv" href="index.html">'
                     '<span class="lbl">Back</span>Overview</a>')
    if idx < len(PAGES) - 1:
        q = PAGES[idx + 1]
        parts.append('    <a class="nx" href="{slug}.html"><span class="lbl">Next</span>'
                     'Step {n} &middot; {nav}</a>'.format(**q))
    return '\n'.join(parts)


SHELL = """<!doctype html>
<html lang="en" dir="ltr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{doctitle}</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body data-page="step-{n}"{readkey}>
<div class="shell">
<nav class="side" aria-label="Steps">
  <a class="brand" href="index.html">{brand}<small>{tagline}</small></a>
  <ol>
{sidebar}
  </ol>
</nav>
<main>
  <div class="eyebrow">
    <span class="ep">{eyebrow}</span>
    {pill}
    <span>{phase}</span>
  </div>
  <h1>{h1}</h1>
  <p class="lede">{lead}</p>

  <div class="steptop">
    <div class="what">{what_label}</div>
{steptop}
  </div>

{content}

  <div class="nav-bottom">
{navbottom}
  </div>

  <footer>
{footer}
  </footer>
</main>
</div>
<script src="assets/app.js"></script>
</body>
</html>
"""


def footer_html():
    """The provenance block. Every claim here should be true of the project."""
    root = CFG.get('source_root')
    lines = []
    if root:
        lines.append('    <p><b>Sources.</b> Every path on this page was read from the '
                     'repository at <code>%s</code>.</p>' % html.escape(root))
    for line in CFG.get('footer_notes', []):
        lines.append('    <p>%s</p>' % line)
    return '\n'.join(lines)


def prune(written):
    """Delete generated pages that are no longer in pages.py.

    Without this, renaming a lesson or dropping one leaves its old HTML in the
    output. The site still opens, and the validator then fails with a page
    whose prev/next chains no longer exist — an error that looks like a builder
    bug and is not. Deleting the orphan here turns a confusing failure into a
    silent, correct rebuild.

    Only files matching the two generated name patterns are touched, so a
    hand-written page sitting in the same directory survives.
    """
    keep = set(written) | {'index.html'}
    removed = []
    for fn in os.listdir(SITE):
        if fn in keep or not fn.endswith('.html'):
            continue
        if re.match(r'^\d+-.*\.html$', fn) or fn.startswith('appendix-'):
            os.remove(os.path.join(SITE, fn))
            removed.append(fn)
    if removed:
        print('pruned %d stale page(s): %s' % (len(removed), ', '.join(sorted(removed))))


def read_fragment(src):
    """Read a content fragment, refusing to build an empty one.

    A 0-byte fragment used to render a page with the sidebar, the heading and
    no body at all: `os.path.exists` was the only test, so a file truncated by
    an interrupted write or a failed edit passed straight through and the site
    looked built. Nothing downstream reported it. Failing the build here is the
    only point where the mistake is still cheap to fix.
    """
    body = open(src, encoding='utf-8').read()
    if not body.strip():
        sys.exit('empty content fragment: %s\n'
                 '  The file exists but holds nothing, so the page would build '
                 'with no body.\n'
                 '  Re-author it from the source file this lesson writes.' % src)
    return body


def build():
    brand = html.escape(CFG['name'])
    readkey = ''
    if CFG.get('read_key'):
        readkey = ' data-read-key="%s"' % html.escape(CFG['read_key'], quote=True)
    written = set()

    for idx, p in enumerate(PAGES):
        src = os.path.join(CONTENT, '%02d.html' % p['n'])
        if not os.path.exists(src):
            sys.exit('missing content fragment: ' + src)
        read_fragment(src)
        page = SHELL.format(
            doctitle='%s \u00b7 Step %d \u00b7 %s' % (brand, p['n'], p['nav']),
            pill='<span class="step-pill">Step %d of %d</span>' % (p['n'], TOTAL_STEPS),
            n=p['n'], nav=html.escape(p['nav']), h1=html.escape(p['h1']),
            lead=html.escape(p['lead']), phase=html.unescape(phase_of(p)),
            sidebar=sidebar(active_n=p['n']), readkey=readkey,
            brand=brand, tagline=html.escape(CFG.get('tagline', '')),
            eyebrow=html.escape(CFG.get('eyebrow', '')),
            what_label=html.escape(CFG.get('what_label', 'The step')),
            steptop=steptop(p), content=open(src, encoding='utf-8').read(),
            navbottom=navbottom(p, idx), footer=footer_html())
        with open(os.path.join(SITE, '%s.html' % p['slug']), 'w', encoding='utf-8') as f:
            f.write(page)
        written.add('%s.html' % p['slug'])

    for i, a in enumerate(_APPENDIX):
        src = os.path.join(CONTENT, '%s.html' % a['slug'])
        if not os.path.exists(src):
            sys.exit('missing appendix fragment: ' + src)
        read_fragment(src)
        page = SHELL.format(
            doctitle='%s \u00b7 Appendix \u00b7 %s' % (brand, a['nav']),
            pill='<span class="step-pill">Appendix \u00b7 not in the lesson order</span>',
            n=i + 1, nav=html.escape(a['nav']), h1=html.escape(a['h1']),
            lead=html.escape(a['lead']),
            phase=html.unescape(CFG.get('appendix_eyebrow', 'Appendix \u00b7 reference')),
            sidebar=sidebar(active_slug=a['slug']), readkey=readkey,
            brand=brand, tagline=html.escape(CFG.get('tagline', '')),
            eyebrow=html.escape(CFG.get('eyebrow', '')),
            what_label=html.escape(CFG.get('what_label', 'The step')),
            steptop='', content=read_fragment(src),
            navbottom=navbottom_appendix(i), footer=footer_html())
        with open(os.path.join(SITE, '%s.html' % a['slug']), 'w', encoding='utf-8') as f:
            f.write(page)
        written.add('%s.html' % a['slug'])

    prune(written)
    print('built %d pages + %d appendix' % (len(PAGES), len(_APPENDIX)))


if __name__ == '__main__':
    build()