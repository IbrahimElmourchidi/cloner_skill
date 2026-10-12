---
name: clone-site
description: >
  Turn any software repository into a step-by-step teaching site: one static HTML
  page per source file, in dependency order, each carrying the real file contents
  plus a plain assessment of whether its choices are good ones. Works for any
  programming language or ecosystem — Flutter, React, Django, Rust, Go, Rails, a
  CLI, a monorepo, anything. Use this whenever the user wants to explain a
  codebase, teach how something was built, produce a file-by-file walkthrough,
  write a "how we built this" or "rebuild this" guide, turn a repo into a
  tutorial, or set up the multi-page docs site that lives at docs/site — even if
  they never say "site", "skill", or "generator", and even if the project is
  not the one this skill was last used on.
---

# Clone a repository into a step-by-step site

Produces a directory of plain HTML files that opens from `file://`, loads
nothing over the network, and needs no build tooling to view. One page per
source file, ordered so every file exists before the one that depends on it.

Language-agnostic by construction: the generator holds no project names, the
highlighter covers ~55 languages and degrades to plain text for the rest, and
the file-type tables are extension-driven.

## Quickstart

```bash
SKILL=<path to this skill>

# 1. scaffold a working site (builds + validates itself)
python3 $SKILL/scripts/bootstrap.py ~/code/my-project --name "My Project"

# 2. see what the project is made of, and draft a step order
python3 $SKILL/scripts/scan.py ~/code/my-project

# 3. fill in _build/pages.py, write _build/content/NN.html, rebuild
cd ~/code/my-project/docs/site/_build
python3 build.py && python3 index.py
python3 check_site.py     # must print BAD: none
```

`bootstrap.py` writes `docs/site/assets/`, `docs/site/_build/`, a filled-in
`config.py`, and one example lesson, then runs the build and both validators
before it exits. If it exits 0, the plumbing works and the remaining work is
purely writing.

## What you are actually producing

```
docs/site/
├── index.html              overview + full table of contents   (generated)
├── assets/style.css        the design system                   (copied)
├── assets/app.js           highlighting, read-tracking         (copied)
├── NNN-slug.html           one per lesson                      (generated)
└── _build/
    ├── build.py            renderer                            (copied)
    ├── index.py            generates index.html                (copied)
    ├── check_site.py       structural validator                (copied)
    ├── check_svg.py        SVG geometry linter                 (copied)
    ├── config.py           ← THE project-specific file
    ├── pages.py            ← the page list: what exists, in what order
    └── content/NN.html     ← one fragment per lesson
```

`config.py` and `pages.py` are yours to edit. Everything else is copied
verbatim and can be replaced with a newer copy later without touching your
content — that is why no project name appears anywhere in the generator.

## Workflow

### 1. Read the project before writing anything

`scan.py` inventories the repository: languages and line counts, manifests,
documentation, likely entry points, and which directories hold the bulk of it.
It also prints a draft step order.

```bash
python3 $SKILL/scripts/scan.py ~/code/my-project
python3 $SKILL/scripts/scan.py ~/code/my-project --json        # machine-readable
python3 $SKILL/scripts/scan.py ~/code/my-project --write       # pages.py draft
```

The draft order is sorted by directory, then by file size. That is a serviceable
default and a *poor* dependency order — it cannot see that one module imports
another. Treat it as a shape to argue with. Read the project properly and fix
the order before writing lessons; see `references/curriculum.md`.

Useful flags: `--skip DIR` replaces the built-in skip list,
`--include docs` re-enables a directory skipped by default (docs output is
skipped, so re-running scan on a project that already has a clone-site does not
find the clone-site).

### 2. Design the curriculum

One lesson = one file. That constraint is the spine of the site: it forces
each page to be self-contained and makes the order meaningful.

Read `references/curriculum.md` before the first `pages.py`. It covers how to
group files into phases, how to order within a phase, when a file is too big to
teach in one step, and what to do about generated files, lockfiles, and assets.

Then write `pages.py`. Each entry:

```python
dict(n=1, slug='01-pubspec', nav='the manifest',
     h1='What the project declares',
     lead='One or two sentences that make the reader want to keep going.',
     path='pubspec.yaml',
     cmd='$ flutter create .',
     phase='Phase 0 &middot; Toolchain',
     why='Why this file exists, in a sentence. Not "what it is" — the code '
          'already says that — but what constraint it removes.'),
```

`n`, `slug`, `nav`, `h1`, `lead` are required. The filename is `<slug>.html`
and the reading order is recovered from the numeric prefix, so **the slug must
start with the zero-padded number**.

### 3. Author each page

One fragment per lesson, `content/07.html`, inserted verbatim into the shell.
No `<html>`, no `<head>`, no `<main>` — start with an `<h2>`.

**Code first, then the assessment.** A page that is only a file dump teaches
nothing. Each page carries: the file, how it works, an honest verdict on whether
its choices are good (`Best practice` / `Debatable` / `Avoid`), what breaks if
you get it wrong, and what you would have done differently.

Read `references/authoring.md` before writing the first one. It has the full
block vocabulary, the escaping rules that bite, and the page shape.

### 4. Rebuild and validate

```bash
cd ~/code/my-project/docs/site/_build
python3 build.py && python3 index.py
python3 check_site.py       # structure — must print BAD: none
python3 check_svg.py        # diagram geometry — must print problems: 0
```

**Always build before validating.** The validators read the generated pages, so
running them after an edit but before a build tells you about the previous
build and nothing about your change.

`check_site.py` validates `_build/content/*.html` *before* the built pages,
and reports `file:line`. An unbalanced fragment is inserted verbatim into the
shell, so checking it there turns one clear message into a page you can fix,
instead of a wall of lookalike errors downstream.

`build.py` prunes generated pages that pages.py no longer claims, so deleting a
lesson leaves no orphan HTML behind.

## Adding a lesson later

1. Append a `dict(...)` to `PAGES` in `pages.py`.
2. Create `content/NN.html` (zero-padded to two digits).
3. Build and validate.

Inserting a lesson in the *middle* means renumbering every later `n` and every
cross-reference by hand. Avoid it: **refer to other lessons by what they do**
("the routing lesson", "the config file's lesson"), never by number. The step
count is in the page header anyway.

## Extending

**A new language.** Add the name to `KNOWN_LANG` in `check_site.py` so the
validator accepts `data-lang="..."`, then add a `RULES` entry in `assets/app.js`
for highlighting. An accepted-but-unhighlighted language renders as plain text,
so the two are separable — but a language with neither is almost always a typo.

Most languages need only a keyword list: `cLike()` and `hashLike()` in `app.js`
build the whole rule set from one line. See the existing definitions for
`RULES.python` and `RULES.rust`.

**The appendix.** Material that should not sit in the lesson order — deep
dives, audits, checklists, background on a cross-cutting decision — goes in
`APPENDIX` in `pages.py` and gets a fragment named after its slug. It has no
`n`, does not advance the counter, and never appears in a lesson's prev/next
chain. Any topic; the pattern is not tied to whatever the first project used it
for.

**Phases.** `phase=` on any entry groups it under that sidebar heading. Phases
are set by whoever authored the project — use them to reflect the project's own
structure rather than imposing a generic one.

## Rules worth knowing

These are not style preferences; each one exists because ignoring it produces
output that looks fine and is wrong. `references/pitfalls.md` has the full list
with the symptom each one produced.

- **Never hand-edit anything in `docs/site/*.html` or `index.html`.** They are
  generated. Edits vanish on the next build.
- **Never put a project name in `build.py` or `index.py`.** That is what makes
  the generator reusable. It goes in `config.py`.
- **Derive totals, never write them.** `TOTAL_STEPS = len(PAGES)`. A stale
  literal puts a wrong number in every page header.
- **Escape generics inside code blocks.** `<String>` becomes `&lt;String&gt;`.
- **Every code block's first line names its path and whether it is generated.**
  A reader must be able to tell which files they are allowed to edit.
- **No screenshots** unless the user asks for them.
- **No emoji.** The validator rejects the page.

## What this deliberately does not do

It does not generate lessons. `scan.py` gives you an inventory and a starting
order; deciding what the steps *are* means reading the repository, and a
generated lesson list nobody checked is worse than none. That work — reading
the project, arguing about the order, writing the assessment — is the part
that carries the value, and it is the part you do.

It also does not invent content. Every claim on a page should be traceable to a
file in the repository. `config.py`'s `source_root` is asserted in the footer of
every page, so set it to the repository the lessons were actually read from.