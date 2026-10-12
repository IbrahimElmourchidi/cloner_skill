"""Site configuration — the ONLY project-specific file in the generator.

Everything in here is text that changes between projects. build.py and index.py
read it and hold no project names of their own, which is what lets you update
the generator by copying a new version over an old one without touching your
site.

HTML entities are allowed in the prose fields (they are inserted raw, not
escaped) — use &rsquo; for a typographic apostrophe and &middot; for a middot,
so the strings stay inside single-quoted Python literals.
"""

SITE = {
    # ---- identity ----------------------------------------------------------
    'name': 'My Project',
    'eyebrow': 'MYPROJECT',              # small caps tag beside the step pill
    'tagline': 'Rebuilding it, one file at a time',
    'title': 'My Project, from nothing',
    'subtitle': 'Overview',
    'read_key': 'clonedocs.read.v1',      # localStorage namespace for read-tracking

    # ---- provenance --------------------------------------------------------
    # Put the absolute path of the repository the lessons were read from. The
    # footer claims every path on every page came from it, so it must be true.
    'source_root': '/absolute/path/to/the/repo',

    'footer_notes': [
        'Code excerpts are the project&rsquo;s real file contents, reformatted '
        'for the page.',
        'This site is plain files &mdash; open <code>index.html</code> from disk. '
        'Nothing is fetched over the network.',
    ],

    # ---- sidebar -----------------------------------------------------------
    'default_phase': 'Phase 0 &middot; Setup',
    'sidebar_note': None,   # short paragraph at the foot of the sidebar, or None

    # ---- index page --------------------------------------------------------
    'intro': (
        'One file per step, in an order where every file exists before the one '
        'that depends on it. Each step carries the real file contents, a plain '
        'assessment of whether the choices are good ones, and what breaks if '
        'you get them wrong.'
    ),

    'howto': [
        'Read in order. Each step is one file, and the order is a dependency '
        'order, so nothing on a page refers to something you have not met yet.',
        'Progress is kept in this browser only. Nothing is sent anywhere, and '
        'the site works with JavaScript disabled &mdash; you lose highlighting '
        'and the read-tracking, nothing else.',
    ],

    # Optional: one line per phase, shown on the index card for that phase.
    # Keyed by the phase string exactly as it appears in pages.py.
    'phase_blurbs': {},

    # ---- appendix (optional) ----------------------------------------------
    'appendix_phase': 'Appendix',
    'appendix_eyebrow': 'Appendix &middot; reference',
    'appendix_intro': (
        'Reference material that deliberately sits outside the step order: '
        'deep dives, audits, and background on decisions that span many steps.'
    ),
}