# Writing the appendix

The appendix is for material that should not sit in the lesson order.

- a deep dive on one mechanism
- an audit or scored review of the finished codebase
- a checklist, glossary, or debugging runbook
- background on a decision that spans many steps
- anything that would break the "step N of M" narrative

It has no `n`, does not advance the step counter, and never appears in a
lesson's prev/next chain. Readers reach it from the sidebar or the index. Slugs
only need to be unique; name them for the topic so more than one can exist.

## Do it after the lessons

An appendix is usually the *result* of having understood the lessons. Written
first, it is background nobody had earned yet — a reader on step 1 cannot follow
it, and a reader on step 200 has already inferred it.

The one exception: background the reader genuinely cannot proceed without. If
step 3 depends on a concept step 40 introduces, that concept is a lesson, not an
appendix page.

## Choosing topics

Propose the list and stop. Do not write pages on the strength of having a list.

The signal is a question a reader finishes the site still asking. Good sources
for one:

- **A concept used repeatedly without being explained.** It was load-bearing and
  quietly assumed — that is the most valuable kind of appendix page.
- **A decision with real trade-offs.** Why this approach over the obvious
  alternative, and what it costs. Especially where the code shows the *what* and
  not the *why*.
- **Something you checked and found worth reporting.** A performance
  characteristic, an inconsistency, a place where the project is weaker than it
  looks. An audit that finds nothing is still worth publishing as a page.
- **A runbook.** How to do the thing this project exists to do.

Not appendix material: a lesson that happens to be long (`split` it instead), a
glossary that could be a table on one page, or anything that is only interesting
to the author.

Propose each as a one-line topic with a sentence on why it earns a page. Let the
user cut. Nine good pages beat twenty-one nobody wanted.

## Then write

Each appendix entry in `pages.py`:

```python
APPENDIX = [
    dict(slug='appendix-how-codegen-works',
         nav='How codegen works',
         h1='Where the generated files come from',
         lead='The pipeline from a source of truth to a file on disk, and why '
              'it is worth understanding before you touch anything.'),
]
```

Only four fields, and deliberately fewer than a lesson: no `n`, no `phase`, no
`path`, no `cmd`. An appendix page describes something, it does not write a file.

One fragment per entry, named after the slug — `content/appendix-how-codegen-works.html` —
which is the one place a fragment name is not a number.

## What an appendix page owes the reader

The lessons assume a reader is building along. An appendix page is where they
stop building and start understanding, so:

- **No assumed position.** Someone may arrive from the sidebar having read step
  1. Do not open "As we saw in step 240".
- **Standalone.** This page is the only place some idea is written down.
- **Cross-reference by role, never number.** `<refer_by_role>` applies with extra
  force here: appendix pages are written last, when step numbers are moving.
- **Say what it costs.** A page explaining a clever mechanism that does not
  mention its downside is marketing, not teaching.

## Diagrams

Diagrams are the reason `check_svg.py` exists, so they are worth reaching for
here. The rules the validator enforces:

- Text must not overlap other text.
- Text must not cross a box it does not belong to.
- Nothing may fall outside the `viewBox`.

Text inside an `<svg>` cannot be selected, searched, or read by a screen reader.
For a diagram that conveys one idea, put the idea in prose next to it and let the
diagram carry the shape. See `references/authoring.md` for the block vocabulary.

## Verify

```bash
python3 build.py && python3 index.py
python3 check_site.py && python3 check_svg.py
```

`build` prunes appendix pages no longer declared, so deleting one leaves no
orphan behind.