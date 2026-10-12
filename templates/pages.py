"""The page list — data only.

This file is the single source of truth for what exists and in what order. The
builder reads it and never writes to it, so a bad entry fails loudly at build
time instead of corrupting generated HTML.

One lesson = one PAGES entry = one `_build/content/NN.html` fragment.

Fields (only n, slug, nav, h1 and lead are required):

    n      int    1-based, contiguous, no gaps. Drives every "Step N of M".
    slug   str    Unique. Must start with the zero-padded number, because the
                  generated filename is <slug>.html and the reading order is
                  recovered from the filename by the validator.
    nav    str    Sidebar label. Keep it under about four words or the sidebar
                  turns into a wall.
    h1     str    Page title.
    lead   str    The paragraph under the title. This is the hook — write it
                  last, once you know what the step actually turned out to be.
    path   str    The file or directory this step writes. Shows in the panel.
    cmd    str    Shell command to run. Prefix with `$ ` to get a prompt.
    phase  str    Sidebar section heading. Defaults to config default_phase.
    why    str    Why this file exists, in one or two sentences. Worth writing
                  for any configuration file, abstraction, or special-purpose
                  module — "what is this" is obvious from the code, "why is
                  this here" is not.

Numbers here are the only numbers that matter. If a lesson mentions another
lesson, refer to it by what it does ("the routing lesson"), not by number:
inserting a lesson then renumbers every reference by hand.
"""

PAGES = [
    dict(n=1, slug='01-first-file', nav='the first file',
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