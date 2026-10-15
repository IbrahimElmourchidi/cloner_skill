"""The page list — data only.

This file is the single source of truth for what exists and in what order. The
builder reads it and never writes to it, so a bad entry fails loudly at build
time instead of corrupting generated HTML.

**Order is the order of this list.** To reorder or insert a lesson, move the
entry. Nothing else changes: the step number is derived from the position, the
fragment is keyed by the slug, and the read-tracking key is the slug too. An
`n=` left in an entry that disagrees with its position is a hard error rather
than a silent correction, because two things disagreeing about the order is the
bug this design exists to remove.

One lesson = one PAGES entry = one `_build/content/<slug>.html` fragment.

Fields (only slug, nav, h1 and lead are required):

    slug   str    Unique, and stable: it names the fragment file, the page URL
                  and the reader's saved-progress key, so it survives
                  reordering. Never prefix it with the step number.
    nav    str    Sidebar label. Keep it under about four words or the sidebar
                  turns into a wall.
    h1     str    Page title.
    lead   str    The paragraph under the title. This is the hook — write it
                  last, once you know what the step actually turned out to be.
    path   str    The file or directory this step writes. Shows in the panel.
                  One path: a lesson is one file. More than one is an error the
                  validator names, not a shorthand.
    cmd    str    Shell command to run. Prefix with `$ ` to get a prompt.
    phase  str    Sidebar section heading. Defaults to config default_phase.
    why    str    Why this file exists, in plain English — the section that
                  leads the page, before the code. Inserted raw, so it may
                  contain markup such as a <figure class="diagram">.
                  REQUIRED on every lesson that writes a file. Set `why=None`
                  explicitly for a step that writes none, such as a step that
                  only runs a command; the distinction matters, because a
                  missing key means "not written yet" and `None` means
                  "deliberately not applicable".

Never refer to another lesson by its number. Inserting a lesson renumbers
everything after it, so a numeric reference becomes a lie. Refer by what it
does — "the routing lesson".
"""

PAGES = [
    dict(slug='first-file', nav='the first file',
         h1='Where it starts',
         lead='One file. It does almost nothing yet, which is the point — it '
              'fixes the shape everything else has to fit into.',
         path='src/main.py',
         cmd='$ mkdir -p src && touch src/main.py',
         phase='Phase 0 &middot; Toolchain',
         why='Everything else imports this, so it exists before the rest of the '
             'project does. An empty module that only establishes the import '
             'shape is cheaper to delete than a working one.'),
]

# Reference material kept out of the lesson order: it has no `n`, does not
# advance the step counter, and never appears in a lesson's prev/next chain.
# Each needs its own `_build/content/<slug>.html` fragment.
APPENDIX = []

TOTAL_STEPS = len(PAGES)