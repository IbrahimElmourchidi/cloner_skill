#!/usr/bin/env python3
"""The side menu: groups of collapsible items, one data structure, one renderer.

The menu used to be a `sidebar()` function that walked PAGES, injected an `<h4>`
group heading *between* `<li>` elements, and read each row's number out of
pages.py's own `n` field. For a site with any phases in it, that is a long list
with three defects that all came from the same root cause — the menu had no
shape of its own:

  1. **The number was stored, not derived.** It came from a field that existed
     for other reasons — it was the topological sort's output, and it was what
     the fragment filename was keyed by. So "what number does this row show"
     and "what number does the rest of the site call this lesson" were two
     independent facts that had to be kept in agreement by hand, in every row.
     That coupling has since been removed: the number is derived from position
     here and nowhere else, and the fragment is keyed by slug.

  2. **A group heading inside `<ol>` is invalid HTML.** The `<h4>` was a direct
     child of the list, so assistive technology and any strict parser saw a
     broken list. It worked by accident because the CSS hid the bullets.

  3. **Nothing could collapse.** A reader who opened lesson 001 had every row of
     navigation above the lesson, with no way to see one phase's worth of steps
     without scrolling past all the others.

The fix is to give the menu a shape. It is a list of groups; each group is a
list of items; each item is a link. Each group renders as a `<details>`, so the
collapse is native — no JavaScript, keyboard-reachable, and it reports its own
state to assistive technology. Nothing about a specific lesson is written into
the renderer: `render()` knows about groups and items, and has no idea what a
"cart" is.

    **The number is the index.** An item's number is its position in the
    flattened list, so inserting a lesson renumbers everything after it for
    free, and no row can disagree with its own file name. pages.py's `n` is
    still the authority for *ordering*, but it is no longer the authority for
    *display*; check_site.py's `menu_numbering()` fails the build if the two
    ever drift apart, which keeps the derivation honest rather than merely
    convenient.

The other half of the shape is `page_id` — the `data-page` attribute that
read-tracking keys on. It is keyed on the **slug**, not the displayed number, so
renumbering a site cannot invalidate a reader's saved progress. It used to be
`step-<n>`, which meant it was NOT independent of the number despite the
comment right above it saying it was: inserting one lesson near the front reset
every reader's progress markers from that point on. Keying on the slug makes the
comment true.

Appendix entries are keyed `appendix-<slug>` rather than a bare `appendix`, so
that two appendix pages are distinguishable — as one shared key they all matched
`holds()` at once, and every appendix row highlighted together.
"""
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import SITE as CFG           # noqa: E402

APPENDIX_PHASE = CFG.get('appendix_phase', 'Appendix')


def phase_of(p):
    """The group a page belongs to. A consequence of the list, not a second list."""
    return p.get('phase') or CFG.get('default_phase', 'Setup')


class MenuItem:
    """One row. A destination, a label, a read-tracking key, and a number.

    `page_id` is the read-tracking key (`data-page`): `step-<slug>` for a lesson,
    `appendix-<slug>` for an appendix entry. It is derived from the slug rather
    than the number, so renumbering cannot invalidate a reader's saved progress.
    """

    __slots__ = ('href', 'nav', 'page_id', 'number', 'kind')

    def __init__(self, href, nav, page_id, number, kind='lesson'):
        self.href = href
        self.nav = nav
        self.page_id = page_id
        self.number = number
        self.kind = kind

    @property
    def key(self):
        """Identity used to mark the current row, independent of its number."""
        return self.page_id


class MenuGroup:
    """A run of consecutive items that share a heading."""

    __slots__ = ('title', 'items', 'kind')

    def __init__(self, title, items, kind='lesson'):
        self.title = title
        self.items = items
        self.kind = kind

    @property
    def label(self):
        """The range this group covers, e.g. `21-52` or `A1-A9`.

        Derived from the items, so it is right for a group of any size and needs
        no bookkeeping when lessons are inserted.
        """
        if not self.items:
            return ''
        if len(self.items) == 1:
            return self.items[0].number
        return '%s&ndash;%s' % (self.items[0].number, self.items[-1].number)

    @property
    def count(self):
        return len(self.items)

    def holds(self, page_id):
        return any(i.page_id == page_id for i in self.items)


def _number_for(kind, position):
    """The displayed number for the item at `position` (0-based)."""
    return '%02d' % (position + 1) if kind == 'lesson' else 'A%d' % (position + 1)


def build_groups(pages, appendix):
    """The whole menu as data: groups in reading order, numbers by index.

    Two rules, and everything else falls out of them:

      * A new group starts wherever the phase changes — so grouping is a
        consequence of the list, not a second list to maintain.
      * The number is a running counter across *all* groups, not per group, so
        "lesson 105" means the same thing in the sidebar, in the filename and
        in the page's own pill.
    """
    groups, current, position = [], None, 0
    for p in sorted(pages, key=lambda d: d['n']):
        phase = phase_of(p)
        if current is None or current.title != phase:
            current = MenuGroup(phase, [])
            groups.append(current)
        current.items.append(MenuItem(
            href='%s.html' % p['slug'],
            nav=p['nav'],
            page_id='step-%s' % p['slug'],
            number=_number_for('lesson', position),
        ))
        position += 1

    # The appendix is reference material, not part of the order, so it gets its
    # own group and its own A-numbering rather than continuing the lesson count.
    apx = MenuGroup(APPENDIX_PHASE, [
        MenuItem(href='%s.html' % a['slug'], nav=a['nav'],
                 page_id='appendix-%s' % a['slug'],
                 number=_number_for('appendix', i),
                 kind='appendix')
        for i, a in enumerate(appendix)
    ], kind='appendix')
    if apx.items:
        groups.append(apx)
    return groups


def _row(item, active):
    # `cur` is a sibling attribute, never part of the data-page value. Putting
    # it inside the quotes produces data-page="appendix aria-current="page"",
    # which the browser parses as one attribute whose value is
    # `appendix aria-current=` — so the current-page highlight never applies
    # and read-tracking keys on the mangled string.
    cur = ' aria-current="page"' if item.key == active else ''
    return ('      <li><a href="{href}" data-page="{pid}"{cur}>'
            '<span class="n">{n}</span><span class="t">{nav}</span>'
            '<span class="tick" hidden>read</span></a></li>').format(
        href=item.href, pid=item.page_id, cur=cur,
        n=item.number, nav=html.escape(item.nav))


def _group(g, active, force_open=False):
    """One collapsible group. Open if it holds the current page."""
    is_active = g.holds(active)
    opened = ' open' if (is_active or force_open) else ''
    # `<ol start>` is how the number stays semantic rather than decorative: the
    # list itself knows it begins at the group's first lesson, so the rendered
    # row and the `<ol>` cannot disagree about what "lesson 21" means.
    start = (' start="%d"' % int(g.items[0].number)) if (g.kind == 'lesson' and g.items) else ''
    return (
        '    <details class="grp" data-kind="{kind}"{opened}>\n'
        '      <summary><span class="gt">{title}</span>'
        '<span class="gr">{label}</span></summary>\n'
        '      <ol{start}>\n{rows}\n      </ol>\n'
        '    </details>').format(
        kind=g.kind, opened=opened,
        title=html.unescape(g.title).replace('·', '&middot;'),
        label=g.label, start=start,
        rows='\n'.join(_row(i, active) for i in g.items))


def render(groups=None, active=None):
    """Groups in, `<nav>` contents out. Knows nothing about any feature.

    On the overview nothing is `active`, so no group would be open and the menu
    would read as a wall of collapsed headings. The first group is forced open
    instead: enough to show the component works, and the reader has one-click
    routes to the rest.
    """
    groups = build_groups() if groups is None else groups
    return '\n'.join(
        _group(g, active, force_open=(active is None and i == 0))
        for i, g in enumerate(groups))


def wrap(body, brand, tagline='', note=''):
    """The complete `<nav>` element, so build.py and index.py emit the same one."""
    note_html = ('\n  <div class="note-box">\n    <p>%s</p>\n  </div>' % note) if note else ''
    return (
        '<nav class="side" aria-label="Steps">\n'
        '  <a class="brand" href="index.html">{brand}<small>{tagline}</small></a>\n'
        '  <div class="menu" data-menu>\n{body}\n  </div>{note}\n'
        '</nav>').format(brand=brand, tagline=tagline, body=body, note=note_html)


def sidebar(pages, appendix, active_n=None, active_slug=None):
    """The one call the two callers make: the whole `<nav>`, ready to format in.

    `active_n` and `active_slug` are the two ways a page says which row it is:
    a lesson knows its own slug, an appendix page knows its own slug. Both key
    on the slug, so moving a lesson does not move its highlight.
    """
    active = None
    if active_n is not None:
        active = 'step-%s' % active_n
    elif active_slug is not None:
        active = ('appendix-%s' % active_slug if active_slug in
                  {a['slug'] for a in appendix} else 'step-%s' % active_slug)
    return wrap(render(build_groups(pages, appendix), active=active),
                brand=html.escape(CFG['name']),
                tagline=html.escape(CFG.get('tagline', '')),
                note=CFG.get('sidebar_note') or '')