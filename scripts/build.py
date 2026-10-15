#!/usr/bin/env python3
"""Renders the whole site from _build/pages.py + _build/content/*.html.

    python3 _build/build.py
    python3 _build/build.py --incremental   # only pages whose fragment changed

Everything shared — <head>, sidebar, prev/next, footer — is generated here, so
adding lesson 51 means adding one PAGES entry and one content fragment, never
hand-editing a shell. Lesson pages and appendix pages share one template on
purpose: a fix to the shell then reaches both.

The sidebar itself lives in menu.py, which owns the *shape* of the navigation —
groups, collapsible, numbers derived from position — so build.py and index.py
cannot disagree about it and neither has to know what a phase is.

Project-specific text (site name, tagline, where the source lives) lives in
config.py, not here. This file stays byte-identical across every site the
skill produces, so it can be updated by copying a new version over an old one.

**Fragments are keyed by slug, not by lesson number.** Keying them by number
(`content/%02d.html`) made the fragment a *position*, so reordering lessons
silently handed lesson N the body that belonged to a different lesson — and the
site still built clean and still passed validation, with the wrong content on
every page after the edit point. Slugs are stable under renumbering, so an
insert or a reorder is a move within one list and nothing else.

**`n` is derived, not stored.** The position in PAGES *is* the step number.
Storing it made reordering mean editing one field per moved entry, and the
stored value could disagree with the position — a silent failure the validator
can only catch after the damage. Authoring order by moving lines is the whole
mechanism now; see references/curriculum.md.
"""
import os
import html
import json
import re
import sys
import hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)
CONTENT = os.path.join(HERE, 'content')
MANIFEST = os.path.join(HERE, 'manifest.json')

sys.path.insert(0, HERE)

from config import SITE as CFG           # noqa: E402
from pages import PAGES as _RAW, APPENDIX as _APPENDIX   # noqa: E402
import menu                             # noqa: E402
from menu import phase_of, APPENDIX_PHASE  # noqa: E402,F401  (re-exported: index.py imports them here)

# Bumped when the fragment-naming or the manifest shape changes, so migrate.py
# knows what a given manifest was written by.
MANIFEST_VERSION = 2


def normalise(pages):
    """Give each lesson its step number from its position in the list.

    `n` is accepted but not trusted. A stored `n` that disagrees with the
    position is a hard error rather than a silent correction: someone hand-set a
    number, and quietly overwriting it would hide the fact that two things
    disagree about the order. The message names both numbers.
    """
    out = []
    for i, d in enumerate(pages, 1):
        p = dict(d)
        want = p.get('n')
        if want is not None and want != i:
            sys.exit(
                'pages.py: %r declares n=%r but sits at position %d.\n'
                '  `n` is derived from list order now, so it does not need to be\n'
                '  written. Delete the n= from this entry, or move the entry to\n'
                '  position %s. The two must not disagree.'
                % (p.get('slug'), want, i, want))
        p['n'] = i
        out.append(p)
    return out


PAGES = normalise(_RAW)
TOTAL_STEPS = len(PAGES)


def sha256_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def sha256_file(path):
    """Hash a source file, or None when there is nothing there to hash.

    A lesson whose file has been deleted is a fact sync.py has to be able to
    report, so this returns None instead of raising: "no hash" and "the hash of
    nothing" must stay distinguishable.
    """
    try:
        with open(path, encoding='utf-8') as f:
            return sha256_text(f.read())
    except OSError:
        return None


def sidebar(active_n=None, active_slug=None):
    """The complete `<nav class="side">` element, groups and all.

    Kept as a one-line wrapper so the two callers below keep a trivial call site
    and there is exactly one implementation of the menu.
    """
    return menu.sidebar(PAGES, _APPENDIX, active_n=active_n,
                        active_slug=active_slug)


def esc_prose(text):
    """Escape for prose, but leave `<code>&hellip;</code>` intact.

    `nav`, `h1` and `lead` are escaped flat, which is right for a hook. A
    preview is prose that routinely names a file or a type, so `<code>` is the
    one tag worth keeping. Everything else is still escaped, so a stray `<` in
    a sentence cannot open a tag — the same trade `why` makes, in the other
    direction.
    """
    out = html.escape(text, quote=False)
    return out.replace('&lt;code&gt;', '<code>').replace('&lt;/code&gt;', '</code>')


def stubs_of(p):
    """`stubs=` as a list of dicts, whatever shape it was written in.

    A single dict is accepted so the common case — one placeholder — reads as
    one dict rather than a list of one. A missing key is an empty list, which
    is the overwhelmingly common case and must stay free of ceremony.

    `path` is required and is the whole point: it is the file the reader has to
    invent in order to compile this step, and it is matched against later
    lessons' own `path=` to decide whether the stub was ever retired.
    """
    raw = p.get('stubs') or []
    if isinstance(raw, dict):
        raw = [raw]
    out = []
    for s in raw:
        if isinstance(s, str):                      # path= only, nothing else
            s = {'path': s}
        s = dict(s)
        if not s.get('path'):
            raise SystemExit(
                'pages.py: %r declares a stub with no path.\n'
                '  A stub exists to name a file the reader has to invent in order\n'
                '  to compile this step. Without the path there is nothing to match\n'
                '  against a later lesson, so nothing could ever retire it.'
                % p.get('slug'))
        out.append(s)
    return out


def preview_block(p):
    """What the reader can now see that they could not before.

    This is the payoff line, and it is the reason a journey order is worth
    having at all: without it, a step that wires up a screen and a step that
    rewrites a helper look identical from the outside.
    """
    text = p.get('preview')
    if not text:
        return ''
    return ('<div class="preview"><b>What you can see now.</b> %s</div>'
            % esc_prose(text))


def stubs_block(p):
    """The placeholders this step needs in order to compile.

    Rendered next to the file path because that is where the reader looks when
    the compiler says a name is undefined. Naming the missing file, the names it
    has to provide, and where the real one lands turns a compile error into a
    to-do the author already wrote down.
    """
    stubs = stubs_of(p)
    if not stubs:
        return ''
    items = []
    for s in stubs:
        bits = ['<code>%s</code>' % html.escape(s['path'])]
        if s.get('names'):
            bits.append('must provide <code>%s</code>'
                        % html.escape(s['names']))
        if s.get('real'):
            bits.append('replaced in %s' % html.unescape(s['real']))
        if s.get('note'):
            bits.append(esc_prose(s['note']))
        items.append('<li>%s.</li>' % '; '.join(bits))
    return ('<div class="stubs"><b>Not written yet.</b> Write a placeholder '
            'for each of these, or this step will not compile. They are '
            'replaced by real lessons later, in the order they are read.'
            '<ul>%s</ul></div>' % ''.join(items))


def steptop(p):
    """The panel above the lesson body: what this step does.

    Deliberately does NOT carry `why`. That used to render here, inside the step
    panel, where it was a single sentence wedged between the command and the
    file path. A purpose statement is not metadata about the step — it is the
    thing the reader needs before the code — so it now leads the body as its own
    section (see `why_section`).

    `preview` and `stubs` DO live here, and for the same reason in the opposite
    direction: both are statements about this step in particular rather than
    about the file, and both are consulted at the moment the reader tries the
    step — run it, then compile it. Putting them in the body buries them under
    the code they describe.
    """
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
    body += preview_block(p)
    body += stubs_block(p)
    return body


def why_section(p):
    """The opening "Why this file exists" section, or '' when there is none.

    Inserted raw, not escaped, so it may contain markup: prose is the normal
    case, and a `<figure class="diagram">` is how a type hierarchy or a data
    flow is made concrete. A plain string still works and is still a section —
    the heading is generated here so the page shape cannot vary.

    `why=None` is the explicit opt-out, and it is distinguishable from a missing
    key on purpose: "this step has no purpose statement yet" and "this step
    genuinely needs none" are different facts, and check_site reports the first
    while staying silent about the second. A step that only runs a command, such
    as a code generator, is the normal case for opting out.
    """
    why = p.get('why')
    if not why:
        return ''
    return ('<h2 id="why-it-exists">Why this file exists</h2>\n'
            '<div class="why">%s</div>\n' % why)


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
<body data-page="{page_id}"{readkey}>
<div class="shell">
{sidebar}
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


def prune(written, previously_written=()):
    """Delete generated pages that are no longer in pages.py.

    Without this, renaming a lesson or dropping one leaves its old HTML in the
    output. The site still opens, and the validator then fails with a page whose
    prev/next chains no longer exist — an error that looks like a builder bug
    and is not. Deleting the orphan here turns a confusing failure into a
    silent, correct rebuild.

    What counts as "generated" comes from the manifest, not from a filename
    pattern. The pattern used to be `^\\d+-.*\\.html$`, which relied on slugs
    starting with the step number — a coupling this version removes, so the
    pattern now matches almost nothing and every orphan survives. The manifest
    records exactly what this builder emitted, which is both correct and the
    safer question: a hand-written page sitting in the site directory was never
    generated, so it is never a candidate.

    A site with no manifest yet has no record of what it generated, so nothing
    is pruned and nothing is deleted by accident. `migrate.py` is what brings an
    older site forward.
    """
    keep = set(written) | {'index.html'}
    removed = []
    # The manifest is authoritative. The filename patterns are kept as a
    # fallback for a site that has no manifest yet, which is every site built
    # before this version: it costs nothing, and dropping them would silently
    # stop pruning on exactly the sites that have the most orphans.
    candidates = set(previously_written)
    for fn in os.listdir(SITE):
        if fn.endswith('.html') and (
                fn.startswith('appendix-') or re.match(r'^[0-9]{2,4}-.*\.html$', fn)):
            candidates.add(fn)
    for fn in sorted(candidates):
        if fn in keep or not fn.endswith('.html'):
            continue
        target = os.path.join(SITE, fn)
        if os.path.exists(target):
            os.remove(target)
            removed.append(fn)
    if removed:
        print('pruned %d stale page(s): %s' % (len(removed), ', '.join(removed)))


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


def load_manifest():
    """The previous build's record, or {} when there is not one yet."""
    try:
        with open(MANIFEST, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def source_paths(p):
    """The repository paths a lesson claims, as a list.

    `path` is ONE path for one lesson — that is the rule. It is split on commas
    so that a lesson naming several paths is still fully accounted for by
    sync.py and the file checks instead of only its first path being seen. Such
    a lesson is still wrong and the co-lesson check says so; this just means it
    is handled rather than half-ignored.
    """
    return [s.strip() for s in (p.get('path') or '').split(',') if s.strip()]


def write_manifest(records):
    """Record what each lesson was built from, so `sync` can tell what moved.

    Without this there is no way to know whether a source file changed since the
    last build: nothing recorded what a lesson was built from, or what the file
    looked like at the time. Staleness was not merely unchecked, it was
    unanswerable.

    It also records every generated filename, because that list is how `prune`
    knows what it may delete. Filenames alone cannot answer it: the old test was
    a leading-number pattern, and slugs no longer begin with the step number, so
    the pattern matched nothing and no orphan was ever removed.
    """
    payload = {'version': MANIFEST_VERSION,
               'source_root': CFG.get('source_root', ''),
               'pages': records,
               'generated': sorted(r['slug'] + '.html' for r in records) +
                            sorted(a['slug'] + '.html' for a in _APPENDIX)}
    with open(MANIFEST, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=1, sort_keys=True)
        f.write('\n')


def build(incremental=False):
    brand = html.escape(CFG['name'])
    readkey = ''
    if CFG.get('read_key'):
        readkey = ' data-read-key="%s"' % html.escape(CFG['read_key'], quote=True)
    written = set()
    records = []
    previous = load_manifest()
    prev_by_slug = {r['slug']: r for r in previous.get('pages', [])
                     if isinstance(r, dict) and 'slug' in r}
    root = (CFG.get('source_root') or '').rstrip('/')
    rebuilt = skipped = 0

    for idx, p in enumerate(PAGES):
        src = os.path.join(CONTENT, '%s.html' % p['slug'])
        if not os.path.exists(src):
            sys.exit('missing content fragment: %s\n'
                     '  Fragments are named after the slug, so this lesson needs\n'
                     '  %s.html. See scripts/migrate.py for a site authored before\n'
                     '  fragments were keyed by slug.' % (src, p['slug']))
        body = read_fragment(src)
        frag_sha = sha256_text(body)
        paths = source_paths(p)
        src_sha = sha256_file(os.path.join(root, paths[0])) if (root and len(paths) == 1) else None
        records.append({'n': p['n'], 'slug': p['slug'], 'paths': paths,
                        'src_sha': src_sha, 'frag_sha': frag_sha})

        out = os.path.join(SITE, '%s.html' % p['slug'])
        prior = prev_by_slug.get(p['slug'])
        if incremental and prior and prior.get('frag_sha') == frag_sha and os.path.exists(out):
            skipped += 1
            written.add('%s.html' % p['slug'])
            continue

        why = why_section(p)
        page = SHELL.format(
            doctitle='%s \u00b7 Step %d \u00b7 %s' % (brand, p['n'], p['nav']),
            pill='<span class="step-pill">Step %d of %d</span>' % (p['n'], TOTAL_STEPS),
            n=p['n'], nav=html.escape(p['nav']), h1=html.escape(p['h1']),
            lead=html.escape(p['lead']), phase=html.unescape(phase_of(p)),
            sidebar=sidebar(active_slug=p['slug']), readkey=readkey,
            eyebrow=html.escape(CFG.get('eyebrow', '')),
            what_label=html.escape(CFG.get('what_label', 'The step')),
            steptop=steptop(p), content=(why + '\n' + body) if why else body,
            page_id='step-%s' % p['slug'],
            navbottom=navbottom(p, idx), footer=footer_html())
        with open(out, 'w', encoding='utf-8') as f:
            f.write(page)
        written.add('%s.html' % p['slug'])
        rebuilt += 1

    for i, a in enumerate(_APPENDIX):
        src = os.path.join(CONTENT, '%s.html' % a['slug'])
        if not os.path.exists(src):
            sys.exit('missing appendix fragment: ' + src)
        body = read_fragment(src)
        page = SHELL.format(
            doctitle='%s \u00b7 Appendix \u00b7 %s' % (brand, a['nav']),
            pill='<span class="step-pill">Appendix \u00b7 not in the lesson order</span>',
            n=i + 1, nav=html.escape(a['nav']), h1=html.escape(a['h1']),
            lead=html.escape(a['lead']),
            phase=html.unescape(CFG.get('appendix_eyebrow', 'Appendix \u00b7 reference')),
            sidebar=sidebar(active_slug=a['slug']), readkey=readkey,
            eyebrow=html.escape(CFG.get('eyebrow', '')),
            what_label=html.escape(CFG.get('what_label', 'The step')),
            steptop='', content=body,
            page_id='appendix-%s' % a['slug'],
            navbottom=navbottom_appendix(i), footer=footer_html())
        with open(os.path.join(SITE, '%s.html' % a['slug']), 'w', encoding='utf-8') as f:
            f.write(page)
        written.add('%s.html' % a['slug'])

    prune(written, previous.get('generated', []))
    write_manifest(records)
    tail = (' (%d written, %d unchanged)' % (rebuilt, skipped)) if incremental else ''
    print('built %d pages + %d appendix%s' % (len(PAGES), len(_APPENDIX), tail))


if __name__ == '__main__':
    build(incremental='--incremental' in sys.argv[1:])