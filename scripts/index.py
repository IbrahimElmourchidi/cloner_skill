#!/usr/bin/env python3
"""Generates <site>/index.html — the overview and the table of contents.

    python3 _build/index.py

The sidebar is imported from build.py so it can never drift from the lesson
list. Everything else here is derived from pages.py except the prose in
config.py (intro, how-to-use, phase blurbs), which is where a project's own
framing belongs.

Ordering matters when you read the output: check_site.py asserts that this page
links to every generated page, so a lesson added to pages.py without appearing
here fails the validator rather than silently vanishing from the index.
"""
import os
import html
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from config import SITE as CFG                      # noqa: E402
from build import PAGES, TOTAL_STEPS, sidebar, phase_of, footer_html, APPENDIX_PHASE  # noqa: E402
from pages import APPENDIX                          # noqa: E402


def phases():
    """Group lessons by phase, preserving first-appearance order."""
    out = []
    for p in PAGES:
        ph = phase_of(p)
        if not out or out[-1][0] != ph:
            out.append((ph, []))
        out[-1][1].append(p)
    return out


def toc_table():
    rows = []
    for ph, items in phases():
        rows.append('      <tr class="ph"><td colspan="3">%s</td></tr>'
                    % html.unescape(ph))
        for p in items:
            path = html.escape(p['path']) if p.get('path') else '&mdash;'
            rows.append(
                '      <tr><td class="pnum">%d</td>'
                '<td><a href="%s.html">%s</a></td>'
                '<td><code>%s</code></td></tr>'
                % (p['n'], p['slug'], html.escape(p['nav']), path))
    return '\n'.join(rows)


def phase_cards():
    """One card per phase, linking to its first lesson."""
    out = []
    for ph, items in phases():
        blurb = CFG.get('phase_blurbs', {}).get(ph, '')
        paths = [i['path'] for i in items if i.get('path')]
        foot = ('%d steps' % len(items))
        if paths:
            foot += ' &middot; %s' % html.escape(paths[0])
        if len(paths) > 1:
            foot += ' +%d more' % (len(paths) - 1)
        out.append(
            '    <a class="card" href="%s.html"><span class="cn">%s</span>'
            '<h3>%s</h3><p>%s</p><span class="file">%s</span></a>'
            % (items[0]['slug'], '%d&ndash;%d' % (items[0]['n'], items[-1]['n']),
               html.escape(ph), blurb or '&nbsp;', foot))
    return '\n'.join(out)


def appendix_rows():
    out = []
    for i, a in enumerate(APPENDIX, 1):
        out.append('      <tr><td class="pnum">A%d</td>'
                   '<td><a href="%s.html">%s</a></td><td>reference</td></tr>'
                   % (i, a['slug'], html.escape(a['nav'])))
    return '\n'.join(out)


TEMPLATE = """<!doctype html>
<html lang="en" dir="ltr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{doctitle}</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body data-page="index"{readkey}>
<div class="shell">
{sidebar}
<main>
  <div class="eyebrow">
    <span class="ep">{eyebrow}</span>
    <span class="step-pill">{total} steps</span>
    <span>{subtitle}</span>
  </div>
  <h1>{title}</h1>
  <p class="lede">{intro}</p>

  <div class="bar" data-progress><i></i></div>
  <div class="pnum" data-progress-label>0 of {total} steps read (0%)</div>
  <p><button class="btn" data-mark data-on="0" type="button">Mark as read</button></p>

  <div class="cards">
{cards}
  </div>

  <h2>How to use this</h2>
{howto}

  <h2>Every step</h2>
  <div class="tbl">
    <table>
      <thead><tr><th>#</th><th>Step</th><th>Writes to</th></tr></thead>
      <tbody>
{toc}
      </tbody>
    </table>
  </div>
{appendix}

  <footer>
{footer}
  </footer>
</main>
</div>
<script src="assets/app.js"></script>
</body>
</html>
"""


def main():
    if APPENDIX:
        appendix = (
            '  <h2>%s</h2>\n'
            '  <p>%s</p>\n'
            '  <div class="tbl">\n    <table>\n'
            '      <thead><tr><th>#</th><th>Topic</th><th>Kind</th></tr></thead>\n'
            '      <tbody>\n%s\n      </tbody>\n    </table>\n  </div>'
            % (html.escape(APPENDIX_PHASE),
               html.escape(CFG.get('appendix_intro',
                                   'Reference material. Not part of the step order.')),
               appendix_rows()))
    else:
        appendix = ''

    howto = CFG.get('howto', [
        'Read it in order. Each step is one file, and the order is chosen so '
        'that every file exists before the one that depends on it.',
        'Your reading progress is stored in this browser only. Nothing is sent '
        'anywhere; the site is plain files you can open from disk.',
    ])
    howto_html = '\n'.join('  <li>%s</li>' % h for h in howto)

    readkey = (' data-read-key="%s"' % html.escape(CFG['read_key'], quote=True)
               if CFG.get('read_key') else '')

    page = TEMPLATE.format(
        doctitle=CFG['name'],
        eyebrow=html.escape(CFG.get('eyebrow', '')),
        subtitle=html.escape(CFG.get('subtitle', '')),
        title=html.escape(CFG.get('title', CFG['name'])),
        intro=CFG.get('intro', ''),
        total=TOTAL_STEPS, sidebar=sidebar(None), readkey=readkey,
        cards=phase_cards(), toc=toc_table(), howto=howto_html,
        appendix=appendix, footer=footer_html())

    with open(os.path.join(SITE, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(page)
    print('wrote index.html (%d steps + %d appendix)' % (TOTAL_STEPS, len(APPENDIX)))


if __name__ == '__main__':
    main()