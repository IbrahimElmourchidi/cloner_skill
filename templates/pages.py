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

**Order by journey, not by the import graph.** The order a developer works in
is the order a reader wants: something that runs, then the piece underneath it,
then the next piece. The import graph disagrees, because in most codebases the
thing that runs is the thing that imports everything. Rather than follow the
graph and end up teaching the entry point last, put the file where a developer
would put it and declare what the reader has to invent to make it compile —
`stubs=` below, `preview=` for what they get to see. The dependency sort is
still right *within* a slice; it is only the wrong axis for the spine.

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
    preview str   What the reader can see after this step that they could not
                  see before. One or two sentences, plain, present tense — the
                  payoff line. Strongly wanted on any step that makes the
                  project *do* something rather than merely compile: it is the
                  only thing on the page that distinguishes "wires up a screen"
                  from "renames a helper". `<code>` is honoured; everything
                  else is escaped.
    stubs  list   Placeholders the reader has to invent for this step to
                  compile, each a dict:
                      path  str   the file that does not exist yet. Required —
                               it is matched against later lessons' own `path=`
                               to decide whether the stub was ever retired.
                      names str   the type names that placeholder must define,
                               comma separated. These are exempt from the
                               forward-reference check, which is the whole
                               point: it is how an outcome-first order is
                               possible at all.
                      real  str   where the real file lands, e.g. a phase name.
                      note  str   what the placeholder does for now.
                  A bare string is accepted as `{path: ...}`. A stub is
                  metadata, not a lesson, so the same path is never taught
                  twice and sync.py stays unambiguous. Every stub must be
                  replaced by a *later* lesson carrying that path, or the
                  validator reports it: a placeholder nobody replaces is a
                  placeholder taught as the answer.
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