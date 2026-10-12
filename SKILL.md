---
name: clone-site
description: >
  Turn any software repository into a step-by-step teaching site: one static HTML
  page per source file, in dependency order, each carrying the real file contents
  plus a plain assessment of whether its choices are good ones. Works for any
  programming language or ecosystem — Flutter, React, Django, Rust, Go, Rails, a
  CLI, a monorepo, anything. Use this whenever the user wants to explain a
  codebase, teach how it was built, produce a file-by-file walkthrough, write a
  "how we built this" or "rebuild this" guide, turn a repo into a tutorial, or set
  up the multi-page docs site that lives at docs/site — even if they never say
  "site", "skill", or "generator", and even if the project is not the one this
  skill was last used on.
version: 1.1.0
user-invocable: true
argument-hint: "[init|scan|plan|build|appendix|check|split|renumber|next]"
license: MIT
---

# Clone a repository into a step-by-step site

A directory of plain HTML files that opens from `file://`, loads nothing over the
network, and needs no build tooling to view. One page per source file, ordered so
every file exists before the one that depends on it.

Language-agnostic by construction: the generator holds no project names, the
highlighter covers ~71 languages and degrades to plain text for the rest, and
file-type detection is extension-driven.

---

## Invariants

**Always apply these — do not consult a reference, just do them.** Each one is
here because breaking it produces output that looks correct and is not. The
symptom each one produced is in `references/pitfalls.md`.

<invariants>
<fragments>
A fragment is a body slice, not a document. Start with `<h2>`. No `<html>`, no
`<head>`, no `<main>`, no `<body>`. Everything around it already exists.
</fragments>

<tag_balance>
Tags must balance *within* the fragment. The most common authoring error, and
the most expensive, because HTML parsers do not complain — they cascade. One
stray close produces a page with mismatched nesting and every validator
downstream reports something else. `check_site.py` records the opening line for
each mismatch, so the error names where to start: **fix the first error in a
file, and the rest are usually consequences of it.**
</tag_balance>

<escape_generics>
A bare `<` or `>` inside a code block is not text, it is a tag. `<List<File>>`
parses as a `<List<File>` start tag and the code silently stops rendering — no
error anywhere. Write `&lt;List&lt;File&gt;&gt;`.

The same applies to a code block containing `</code>`, which closes the block
early, and to any `&` that was meant literally.
</escape_generics>

<path_header>
Every code block's first line names its path, and says whether the file is
generated. A reader must be able to tell which files they are allowed to edit
without asking. Something like `// lib/core/config/env.dart — hand written`.
</path_header>

<code_first>
Code first, then the assessment. A page that is only a file dump teaches
nothing. Each page carries: the file, how it works, an honest verdict on whether
its choices are good (`Best practice` / `Debatable` / `Avoid`), what breaks if
you get it wrong, and what you would have done differently.
</code_first>

<refer_by_role>
Refer to another lesson by what it does — "the routing lesson", "the config
file's lesson" — never by number. Inserting a lesson renumbers everything after
it, so a numeric reference silently becomes a lie. The step count is in the
page header anyway.
</refer_by_role>

<no_generated_edits>
Never hand-edit `docs/site/*.html` or `index.html`. They are generated and
edits vanish on the next build. Keep authored sources in `_build/content/`,
which nothing overwrites.
</no_generated_edits>

<derive_totals>
Derive totals, never write them: `total_steps = len(pages)`. A saved literal
outlives the rename that made it wrong and puts a plausible wrong number in
every page header, which is how 739 survived long enough to be noticed.
</derive_totals>

<no_emoji>
No emoji, and no screenshots unless the user asks. The validator rejects emoji;
it cannot reject a screenshot you were not asked for, which is why that one is
yours to hold.
</no_emoji>
</invariants>

## Mode dispatch

When invoked with a COMMAND argument, follow that command's section and skip
the rest. The sections are written to be self-contained about *what to do next*; the
invariants above apply to all of them.

- **`init`** — run the scaffolder, then report the site path and what was
  written. Do not begin planning lessons; that is `plan`.
- **`scan`** — run `scan.py` on the argument (or the current project), report the
  inventory, and stop. Do not write `pages.toml`.
- **`plan`** — read the project properly, design the phases, write `pages.toml`,
  then **present the plan and stop.** See [Plan first, then batch](#plan-first-then-batch).
- **`build` with a number** — take the batch size from the argument. Author that
  many lessons, write each to `content/NN.html`, render, validate, then **stop**
  and report. Ask whether to continue; never exceed the agreed batch without
  asking, because "keep going" is a new agreement rather than an extension of the
  last one. See [3. Author and build](#3-author-and-build).
- **`appendix`** — read `references/appendix.md` and follow it. With no
  argument, propose the topics and stop for approval before writing. With a topic,
  write that one.
- **`check`** — run the validator only, never rebuilding first. `fragments`
  validates authored content without needing a build; `pages` validates rendered
  output; no argument does both, fragments first.
- **`split`** — read `references/splitting.md` and follow it. Stop and show the
  proposed split before editing anything.
- **`renumber`** — read `references/renumbering.md` and follow it. Never rewrite
  numbers without classifying each occurrence first.
- **`next`** — the same as `build` with the size from the last agreed batch.
  "Keep going" from the user means this, and it is a new agreement rather than an
  extension of the old one.

Invoked with **no argument**, or with free text, do the obvious thing: if the
user describes what they want in their own words, follow the workflow below from
the appropriate step. Do not ask which command they meant when the request is
clear — asking them to name a mode is a worse experience than reading the
request.

---

## Plan first, then batch

Writing hundreds of lessons in one pass fails in a specific, predictable way:
quality decays from around lesson 30, and nothing reports it. There is no
validator for "this page is less careful than the previous one." So the work is
batched, and the batch size is the user's call.

1. **Read the project.** Run `scan`, read the actual code, design the phases.
   Write `pages.toml`.
2. **Present the plan and stop.** Phases, lesson count, ordering rationale, and
   anything you are unsure about — files that look generated, a module whose role
   you had to guess at. **Do not write a lesson until the plan is agreed.**
3. **Ask for a batch size**, and offer a default. A good one is 8–15 for the
   first batch: enough to establish the rhythm and the page shape, few enough
   that a course correction is cheap.
4. **Build that many lessons.** `/clone-site build N` writes each fragment,
   renders, and validates. Stop at the batch boundary even if you have momentum —
   the point of a batch is the stopping point.
5. **At the end of every batch, report and ask:**
   - what was written, by phase
   - what `check_site.py` and `check_svg.py` said
   - anything you noticed that the plan got wrong
   - **whether to continue with the next batch**

Never exceed the agreed batch without asking. "Keep going" is a new agreement,
not a continuation of the last one.

---

## Commands

Invoked as `/clone-site COMMAND`. Optional argument narrows the target.

| Command | Argument | Does | Go to |
|---|---|---|---|
| `init` | project path | Scaffold a site: copy the generator in, write the config, build, validate. | [below](#commands) |
| `scan` | project path | Inventory the repo and draft a step order. | [step 1](#1-inventory-the-project) |
| `plan` | project path | Read the project, design the phases, write `pages.toml`, present the plan. | [step 2](#2-design-the-curriculum) |
| `appendix` | topic, or none | Propose the appendix topics, then write them. | `references/appendix.md` |
| `build` | batch size | Author that many lessons, write them to disk, render, validate, then stop and ask. **No argument renders only.** | [step 3](#3-author-and-build) |
| `check` | `fragments` \| `pages` | Validate without rebuilding. | [step 4](#4-build-and-validate) |
| `split` | step number | Break one oversized lesson into several. | `references/splitting.md` |
| `renumber` | — | Shift step numbers after an insert, delete, or split. | `references/renumbering.md` |
| `next` | — | Continue the current batch run. | [batch workflow](#plan-first-then-batch) |

`init` with no argument scaffolds in the current directory. It is the only
command that copies files into a project.

**These are modes of one workflow, not separate tools.** `plan` → `build N`
(repeat) → `appendix` → `build` is the arc; the others exist because those steps
get interrupted or need redoing.

**Three of them are gates, not work:** `plan`, `build N`, and `appendix` stop and
ask rather than continuing on an assumption. `plan` stops because lesson order is
a judgement call the user owns. `build N` stops at the batch boundary because
quality decays on a long run and nothing detects it. `appendix` stops because its
scope is a judgement call, and it reads better after the lessons than before.

**`split` and `renumber` are almost always used together.** Splitting shifts
every later number, so run `split` then `renumber` unless the split is at the end
of the site. Both carry their own reference file, because both are the kind of
bulk edit that silently corrupts a large site: on the 492-lesson reference site,
one blind numeric remap broke ~150 pages and every validator still passed.

---

## Reading a reference

Only when you reach the step below. Each is short and specific; there is no need
to load one before you know you need it.

| When you are about to | Read |
|---|---|
| design the lesson order, or split a big file | `references/curriculum.md` |
| write the first fragment | `references/authoring.md` |
| plan or write the appendix | `references/appendix.md` |
| split one lesson into several | `references/splitting.md` |
| shift step numbers after any insert, delete, or split | `references/renumbering.md` |
| do a bulk edit: renumber, retarget, restructure | `references/pitfalls.md` |

---

## Commands

The Python engine is the shipped path and needs only Python 3 (standard
library).

```bash
SKILL=~/.agents/skills/clone-site       # where install.sh puts the copy
python3 $SKILL/scripts/scan.py ~/code/my-project
python3 $SKILL/scripts/bootstrap.py ~/code/my-project --name "My Project"
```

Or, once installed, in the project:

```bash
cd ~/code/my-project/docs/site/_build
python3 build.py && python3 index.py
python3 check_site.py       # must print BAD: none
python3 check_svg.py        # must print problems: 0
```

> A Rust engine is being ported as a drop-in replacement, so that installing the
> skill needs no interpreter. `build` and `check` are done and verified; `index`,
> `check-svg`, `scan` and `init` are not. Until they all exist, the commands
> above are the ones to use — `bin/clone-site` still dispatches to Python. See
> `engine/README.md`.

**Always build before validating.** The validators read the generated pages, so
running them after an edit but before a build tells you about the *previous*
build — which reads as "my change passed validation" when it was never checked.

---

## What you are producing

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
    ├── config.py           ← site-specific prose
    ├── pages.py            ← what exists, in what order
    └── content/NN.html     ← one fragment per lesson
```

`config.py` and `pages.py` are yours to edit. Everything else is copied verbatim
and can be replaced with a newer copy without touching your content — that is why
no project name appears anywhere in the generator.

---

## Workflow

### 1. Inventory the project

```bash
python3 $SKILL/scripts/scan.py ~/code/my-project
python3 $SKILL/scripts/scan.py ~/code/my-project --json     # machine-readable
python3 $SKILL/scripts/scan.py ~/code/my-project --write    # pages.py draft
```

The draft order is sorted by directory, then by file size. That is a serviceable
default and a *poor* dependency order — it cannot see that one module imports
another. Treat it as a shape to argue with.

Useful flags: `--skip DIR` replaces the built-in skip list, `--include docs`
re-enables a directory skipped by default (docs output is skipped by default, so
re-running scan on a project that already has a site does not find that site).

### 2. Design the curriculum

One lesson = one file. That constraint is the spine of the site: it forces each
page to be self-contained and makes the order meaningful.

Read `references/curriculum.md` before the first `pages.py`. It covers grouping
into phases, ordering within a phase, when a file is too big to teach in one
step, and what to do about generated files, lockfiles and assets.

Each entry:

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

`n`, `slug`, `nav`, `h1`, `lead` are required. The filename is the slug plus `.html`, and
reading order is recovered from the numeric prefix, so **the slug must start with
the zero-padded number**. `why` is worth writing for any configuration file,
abstraction, or special-purpose module: "what is this" is obvious from the code,
"why is this here" is not.

### 3. Author and build

`/clone-site build 10` authors ten lessons, writes them to disk, renders, and
validates. One command because the two halves are not separable in practice: a
lesson that has been written but not rendered cannot be validated, and the
validator is what tells you the fragment is broken.

One fragment per lesson, `content/07.html`, inserted verbatim into the shell.

```bash
/clone-site build 10     # author 10, write, render, validate, then ask
/clone-site build 25     # a bigger batch once the page shape has settled
/clone-site next         # same size as the last batch
```

**No argument means render only** — see [step 4](#4-build-and-validate). That is
the idempotent half, and it is why `build` alone is still safe to run after a
`split` or a `renumber`.

`check_site.py` validates `_build/content/*.html` *before* the built pages and
reports `file:line`. A fragment is inserted verbatim into the shell, so an
unbalanced fragment is guaranteed to cascade into the rendered page — checking it
first turns one clear message into a page you can fix, instead of a wall of
lookalikes downstream.

### 4. Render and validate

No content changes. Safe on its own at any point.

```bash
python3 build.py && python3 index.py
python3 check_site.py && python3 check_svg.py
```

`build.py` prunes generated pages that `pages.py` no longer claims, so deleting a
lesson leaves no orphan HTML behind.

---

## Adding a lesson later

1. Append a `dict(...)` to `PAGES` in `pages.py`.
2. Create `content/NN.html` (zero-padded to two digits).
3. Build and validate.

Inserting in the *middle* means renumbering every later `n` and every
cross-reference by hand. Avoid it — see the `<refer_by_role>` invariant above.

---

## Extending

**A new language.** Add the name to `KNOWN_LANG` in `check_site.py`, then add a
`RULES` entry in `assets/app.js`. An accepted-but-unhighlighted language renders
as plain text, so the two are separable — but a language with neither is almost
always a typo.

Most languages need only a keyword list: `cLike()` and `hashLike()` in `app.js`
build the whole rule set from one line. See `RULES.python` and `RULES.rust`.

**The appendix.** Material that should not sit in the lesson order — deep dives,
audits, checklists, background on a cross-cutting decision — goes in `APPENDIX`
in `pages.py` and gets a fragment named after its slug. It has no `n`, does not
advance the counter, and never appears in a lesson's prev/next chain.

**Phases.** `phase=` on any entry groups it under that sidebar heading. Phases
are set by whoever authored the project — use them to reflect the project's own
structure rather than imposing a generic one.

---

## What this deliberately does not do

It does not generate lessons. `scan.py` gives you an inventory and a starting
order; deciding what the steps *are* means reading the repository, and a
generated lesson list nobody checked is worse than none. Reading the project,
arguing about the order, and writing the assessment — that is the part that
carries the value, and it is the part you do.

It also does not invent content. Every claim on a page should be traceable to a
file in the repository. `config.py`'s `source_root` is asserted in the footer of
every page, so set it to the repository the lessons were actually read from.

---

## When this skill changes

Skills are copied into each agent and nothing watches them for updates, so a
rule that changes needs to travel with the skill. The mechanism is a
self-deleting block at the top of this file:

```markdown
<post-update-cleanup>
BEFORE doing any work, run the migration below. Then delete this entire
section from THIS file so it does not run again until the next update.

    python3 .agents/skills/clone-site/scripts/migrate.py v1.0-to-v1.1
</post-update-cleanup>
```

The agent runs it once and removes the section, so the migration costs one
session rather than a version check on every session. **Only ship a block when
there is a real migration.** An always-present block that finds nothing to do is
noise that trains people to skip it.

The pending migration, when the Rust port lands, is `config.py` / `pages.py` →
`config.toml` / `pages.toml`.