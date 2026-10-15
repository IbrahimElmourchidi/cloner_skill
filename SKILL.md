---
name: clone-site
description: >
  Turn any software repository into a step-by-step teaching site: one static HTML
  page per source file, in the order a developer actually works, each carrying the
  real file contents plus a plain assessment of whether its choices are good ones.
  Works for any
  programming language or ecosystem — Flutter, React, Django, Rust, Go, Rails, a
  CLI, a monorepo, anything. Use this whenever the user wants to explain a
  codebase, teach how it was built, produce a file-by-file walkthrough, write a
  "how we built this" or "rebuild this" guide, turn a repo into a tutorial, or set
  up the multi-page docs site that lives at docs/site — even if they never say
  "site", "skill", or "generator", and even if the project is not the one this
  skill was last used on.
version: 2.1.0
user-invocable: true
argument-hint: "[init|scan|plan|sync|build|render|appendix|check|split|renumber|next]"
license: MIT
---

# Clone a repository into a step-by-step site

A directory of plain HTML files that opens from `file://`, loads nothing over the
network, and needs no build tooling to view. One page per source file, in the
order a developer would build it — so the reader gets something that runs early,
and what is underneath it is stubbed until its turn comes.

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
Why first, then the code, then the assessment. A page that is only a file dump
teaches nothing. Each page carries: why the file exists, in plain English and
before any code; the file, whole; how it works; an honest verdict on whether
its choices are good (`Best practice` / `Debatable` / `Avoid`), what breaks if
you get it wrong, and what you would have done differently.
</code_first>

<whole_file>
A lesson's code block is the **complete file**, every line, in its own order. A
reader must be able to copy the block into a file and get exactly the file the
lesson claims to write. Never trim it, never replace part of it with a `// ...`
comment, and never show a path manifest where the code should be.

Marking the cut is not the fix. An unmarked fragment reads as a finished file;
a marked one still is not a file the reader can use, and on a `sealed` class the
missing subclasses are ones the rest of the project imports. If a file is too
large to show, **split the file**. The elision marker survives only inside
hand-written prose fragments, never in the block that carries a lesson's file.
</whole_file>

<why_first>
Every lesson that writes a file opens with why it exists — what problem it
solves, what breaks without it — in very simple English, before any code. Set
`why=` in pages.py; the builder emits the heading and the section.

It used to be optional, and optional meant absent: on a 511-lesson site every
entry carried a purpose statement and not one reached a page. A stored-but-
unrendered field is worse than an absent one, because it looks like the work was
done. Use `why=None` — and only that — for a step that writes no file.
</why_first>

<forward_reference>
No lesson may use a name that a later lesson defines — unless it declares that
name in `stubs=`. A reader follows the order and writes each file as they go, so
a step referencing a class introduced three steps later cannot be completed — the
code does not compile at the point they are told to write it. `check_site.py`
names both lessons when this happens.

The exception is deliberate and narrow. See the `stub` invariant below.
</forward_reference>

<stub>
`stubs=` on a lesson declares the placeholders the reader has to invent for that
step to compile: the file that does not exist yet, the type names it must define,
and where the real one lands.

```python
stubs=[dict(path='lib/catalog/domain/usecases.dart',
            names='CatalogUsecase, HomeFeedType',
            real='Phase 4 &middot; Catalog domain',
            note='Every method returns an empty list.')]
```

Two rules, and the validator holds both:

- **Declare it or do not do it.** An undeclared forward reference stays an error.
  A stub is the reader being told what to write; without it they meet a compile
  error and a name, and nothing else.
- **Every stub is retired.** A *later* lesson must carry that same `path=`. A
  placeholder nobody replaces is a placeholder taught as the answer. There is no
  `retired=` field to maintain: retirement is matched against later `path=`
  values, so a stub that is never paid off is reported rather than remembered.

A stub is metadata on the consuming lesson, never a lesson of its own. The same
path is therefore never taught twice, and `sync.py` stays unambiguous.
</stub>

<preview>
`preview=` is what the reader can now see that they could not before — one or two
plain sentences, present tense. On any step that makes the project *do*
something rather than merely compile, not optional.

Without it, a lesson that wires up a screen and a lesson that renames a helper
look identical from the outside, and a reader who followed the order cannot tell
that anything is working until the very end.

Set it where it changes, not where it is comfortable: "Run it. Home shows four
tabs, each with three grey cards" tells the reader more than any amount of prose
about why the grid exists.
</preview>

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
  inventory, and stop. Do not write `pages.py`.
- **`sync`** — run `sync.py` to compare the site against the repository, report
  what moved, and act only with `--apply`. See
  [Keeping the site honest](#keeping-the-site-honest).
- **`plan`** — read the project properly, design the phases, write `pages.py`,
  then **present the plan and stop.** See [Plan first, then batch](#plan-first-then-batch).
  With `--context "..."`, treat that text as a standing instruction for the whole
  build — audience, depth, what to skip, what to emphasise — and hold it for
  every later command too. It is not just for the plan; see
  [Passing context](#passing-context).
- **`build`** — take the batch size from the argument, or **10** if there is no
  number. Author that many lessons, write each to its slug-named fragment, render,
  validate, then **stop** and report. Ask whether to continue; never exceed the
  agreed batch without asking, because "keep going" is a new agreement rather
  than an extension of the last one. See [3. Author and build](#3-author-and-build).
- **`render`** — run the generator and both validators, changing nothing under
  `content/`. This is the idempotent half. Use it after a hand-edit, after
  `split` or `renumber`, or on a site someone else wrote.
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
- **`next`** — the same as `build` with the size from the last agreed batch, or
  10 if there was no last batch. "Keep going" from the user means this, and it is
  a new agreement rather than an extension of the old one.

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
   Write `pages.py`. If `--context` was given, read it first and hold it for
   every later command — see [Passing context](#passing-context).
2. **Present the plan and stop.** Phases, lesson count, ordering rationale, and
   anything you are unsure about — files that look generated, a module whose role
   you had to guess at. **Do not write a lesson until the plan is agreed.**
3. **Ask for a batch size**, and offer a default of 10. A good one is 8–15 for
   the first batch: enough to establish the rhythm and the page shape, few enough
   that a course correction is cheap. If the user has already said "keep going"
   without naming a size, take 10 and say so rather than asking again.
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

## Passing context

`plan` takes an optional `--context` flag whose text is a **standing
instruction for the whole build**, not a note about the plan:

```bash
/clone-site plan ~/code/my-project --context "for junior hires who know Flutter
but not Dart; skip generated files; spend more time on state management than
on routing"
```

What it is good for: the audience, the depth, what to skip, what to emphasise,
anything you would otherwise have to ask about at the first gate.

**Hold it for every later command.** A `--context` that only shapes `plan` is
wasted, because the batch loop is where it actually pays off — "skip generated
files" is a decision made while writing lesson 40, not while planning lesson 1.
Echo it back at the first gate so the user can see it was understood, and keep
it in force across `build`, `appendix`, `split` and `renumber`.

**When it conflicts with the project, the project wins.** If the user asks for a
site covering a subsystem that does not exist, say so at the gate rather than
inventing it. Context narrows scope; it does not author content.

Later corrections do not need the flag again. "Actually make these for a team
that already knows Flutter" is an instruction, not a mode — apply it and carry
it forward.

---

## Commands

Invoked as `/clone-site COMMAND`. Optional argument narrows the target.

| Command | Argument | Does | Go to |
|---|---|---|---|
| `init` | project path | Scaffold a site: copy the generator in, write the config, build, validate. | [below](#commands) |
| `scan` | project path, `--journey` | Inventory the repo and draft a step order. `--journey` starts at the entry points and prints the stub debt; the default sorts leaf-first. | [step 1](#1-inventory-the-project) |
| `plan` | project path, `--context "…"` | Read the project, design the phases, write `pages.py`, present the plan. | [step 2](#2-design-the-curriculum) |
| `sync` | site path | Compare the site against the repository; act on what moved. | [Keeping the site honest](#keeping-the-site-honest) |
| `appendix` | topic, or none | Propose the appendix topics, then write them. | `references/appendix.md` |
| `build` | batch size, default 10 | Author that many lessons, write them to disk, render, validate, then stop and ask. | [step 3](#3-author-and-build) |
| `render` | — | Render every page and validate, changing no content. | [step 4](#4-render-and-validate) |
| `check` | `fragments` \| `pages` | Validate without rebuilding. | [step 4](#4-render-and-validate) |
| `split` | step number | Break one oversized lesson into several. | `references/splitting.md` |
| `renumber` | — | Shift step numbers after an insert, delete, or split. | `references/renumbering.md` |
| `next` | — | Continue the current batch run. | [batch workflow](#plan-first-then-batch) |

`init` with no argument scaffolds in the current directory. It is the only
command that copies files into a project.

**These are modes of one workflow, not separate tools.** `plan` → `build N`
(repeat) → `appendix` → `render` is the arc; the others exist because those steps
get interrupted or need redoing.

**Three of them are gates, not work:** `plan`, `build`, and `appendix` stop and
ask rather than continuing on an assumption. `plan` stops because lesson order is
a judgement call the user owns. `build` stops at the batch boundary because
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
├── <slug>.html             one per lesson                      (generated)
└── _build/
    ├── build.py            renderer                            (copied)
    ├── index.py            generates index.html                (copied)
    ├── check_site.py       structural validator                (copied)
    ├── check_svg.py        SVG geometry linter                 (copied)
    ├── menu.py             the sidebar's shape                 (copied)
    ├── sync.py             compare site against repository     (copied)
    ├── config.py           ← site-specific prose
    ├── pages.py            ← what exists, in what order
    ├── manifest.json       ← what each lesson was built from   (generated)
    └── content/<slug>.html ← one fragment per lesson
```

`config.py` and `pages.py` are yours to edit. Everything else is copied verbatim
and can be replaced with a newer copy without touching your content — that is why
no project name appears anywhere in the generator.

---

## Workflow

### 1. Inventory the project

```bash
python3 $SKILL/scripts/scan.py ~/code/my-project
python3 $SKILL/scripts/scan.py ~/code/my-project --journey   # breadth-first from the entry point
python3 $SKILL/scripts/scan.py ~/code/my-project --json     # machine-readable
python3 $SKILL/scripts/scan.py ~/code/my-project --write    # pages.py draft
```

Two orders, and choosing between them is the first real decision in the build.

**`--journey` — breadth-first from the entry points.** This is the order a
developer works in: the thing that runs first, then what sits underneath it,
then what sits underneath that. The scan walks the import graph outward from
`main` and prints, for each step, how many files it reaches for that are taught
later — the **stub debt**, and the bill for this order. Almost every step has
some; that is what the order costs, and `stubs=` is how you pay it.

**Default — leaf-first by the import graph.** Where B imports A, A comes first.
Correct for a library. For an application it means teaching the bottom of the
stack for two hundred lessons and the reader seeing nothing run until the end.

Both break ties by directory, then size, so two scans of an unchanged repository
produce the same list. Pass `--no-deps` to see the raw directory order — useful
precisely because it is what you are arguing against.

Neither sort knows that a reader needs the domain before the wiring, or that a
file does not deserve a lesson at all. Read the result and argue with it. One
signal is worth reading carefully: a step in the journey draft with a dozen or
more placeholders is a dependency-wiring file — a DI module, a router, a
bootstrap — and the right answer is usually to leave the whole file stubbed
behind one placeholder and teach it near the end.

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
dict(slug='pubspec', nav='the manifest',
     h1='What the project declares',
     lead='One or two sentences that make the reader want to keep going.',
     path='pubspec.yaml',
     cmd='$ flutter create .',
     phase='Phase 0 &middot; Toolchain',
     why='Why this file exists, in plain English — the section that leads the '
         'page. Inserted raw, so it may hold a <figure class="diagram"> too.'),
```

`slug`, `nav`, `h1`, `lead` are required. **The order of the list is the reading
order** — there is no `n` field, because the step number is derived from the
position and an entry that still declares an `n` contradicting its position is
a hard error naming both. To insert, move or delete a lesson, move the entry.

**Above about forty lessons, do not write `pages.py` in one pass.** A few hundred
`dict(...)` entries is sixty kilobytes produced in a single edit, and the only
way to change lesson 40 afterwards is to read and rewrite the whole file — which
is how a curriculum gets re-emitted from a stale copy and loses an entry nobody
notices. Write the lessons as `_build/_parts/NN.py`, one dict per entry, and let
`join.py` concatenate them:

```bash
python3 $SKILL/scripts/join.py <site>/docs/site/_build --check --root <repo>
python3 $SKILL/scripts/join.py <site>/docs/site/_build --root <repo>
```

The list is still one list; nothing downstream can tell. `pages.py` becomes
**derived**: edit the parts, not the file. Everything outside the `PAGES = [...]`
span — the field docstring, and the `APPENDIX` below it — is preserved byte for
byte. `--check` validates without writing, and `--split N` goes the other
direction if you want to start over. Part filenames must be zero-padded
(`part02.py`, never `part2.py`), because filename order is reading order and
`part10` sorts before `part2`.

`slug` names three things at once: the content fragment, the page URL, and the
reader's saved-progress key. It must never start with the step number, and it
must never change for a lesson you only renumbered — that is what makes
reordering free.

`why` is **required** on any lesson that writes a file, and `why=None` is the
explicit opt-out for a step that writes none. "Not written yet" and "does not
apply" are different facts and the field keeps them apart.

`preview` and `stubs` carry a journey-ordered site. Set `preview` wherever a step
changes what the reader can see; set `stubs` wherever the step reaches for
something taught later — which, in a journey order, is most of them. Both are
invariants above.

### 3. Author and build

`/clone-site build 10` authors ten lessons, writes them to disk, renders, and
validates. One command because the two halves are not separable in practice: a
lesson that has been written but not rendered cannot be validated, and the
validator is what tells you the fragment is broken.

One fragment per lesson, named after its slug, inserted verbatim into the shell.

```bash
/clone-site build 10     # author 10, write, render, validate, then ask
/clone-site build 25     # a bigger batch once the page shape has settled
/clone-site build        # no number: 10, the default
/clone-site next         # same size as the last batch, or 10
```

**The default is 10 because a batch has to be big enough to establish the rhythm
and small enough that a course correction is still cheap.** Quality starts
decaying somewhere around lesson 30 of an uninterrupted run and nothing reports
it, so the batch is the only safeguard there is. Ten is roughly where a mistake
in the page shape is still visible across one batch rather than three.

To re-render without authoring anything, use `render` — see
[step 4](#4-render-and-validate). Never infer that from a bare `build`.

`check_site.py` validates `_build/content/*.html` *before* the built pages and
reports `file:line`. A fragment is inserted verbatim into the shell, so an
unbalanced fragment is guaranteed to cascade into the rendered page — checking it
first turns one clear message into a page you can fix, instead of a wall of
lookalikes downstream.

### 4. Render and validate

`/clone-site render`. No content changes. Safe on its own at any point, and the
right command after a hand-edit, after `split` or `renumber`, or on a site
someone else wrote.

```bash
python3 build.py && python3 index.py
python3 check_site.py && python3 check_svg.py
```

`build.py` prunes generated pages that `pages.py` no longer claims, so deleting a
lesson leaves no orphan HTML behind.

---

## Adding a lesson later

1. Append a `dict(...)` to `PAGES` in `pages.py`.
2. Create the content fragment named after that slug.
3. Build and validate.

Inserting in the *middle* is a **move within the list**. Nothing else changes —
not the step numbers, not the fragment names, not the URLs, and not any
reader's saved progress. That used to require renumbering every later `n` and
every cross-reference by hand; see `references/renumbering.md` for what that
used to cost.

Keep slugs stable. A slug is the fragment's filename, the page URL and the
progress key all at once, so renaming one to match a new step number undoes all
three at the same time.

---

## Keeping the site honest

A site is not a one-shot export. The repository keeps moving after the lessons
are written, and `sync` is how the two are brought back together:

```bash
clone-site sync                    # dry run; changes nothing
clone-site sync --apply            # act on the safe cases
clone-site sync --apply --yes      # and do not stop to ask
```

Each build writes `_build/manifest.json` recording, per lesson, the source path
it teaches and a hash of both the source file and the fragment. Without it there
is no way to know whether anything moved — staleness was not merely unchecked,
it was unanswerable.

`sync` reports five cases, and the difference between the last two is the whole
point:

| Case | What it means | What `--apply` does |
|---|---|---|
| `ADDED` | A source file with no lesson. | Nothing. Authoring a lesson means reading the repository and deciding what a reader needs — that is not a string operation. |
| `MODIFIED` | The file changed since the last build. | Nothing. The prose around the code is about that code. Re-author it. |
| `RENAMED` | The path moved, the contents are identical. | Updates `path=`. The lesson is about contents, not filenames. |
| `DELETED` | The file is gone **and** its contents appear nowhere in the repository. | Removes the entry, the fragment and the generated HTML. Provable, so it is applied. |
| `ORPHANED` | The file is gone but its contents were never seen in the repository. | **Nothing.** It may have moved outside the scan root, or been hand-added and never have existed. |

That last row is why the run is a dry run by default and asks before deleting.
Auto-removing a lesson on an inference is how one misconfigured `--root` takes
half a site with it, so the unprovable case is reported and left for a human.

After a `--apply`, re-run `render`.

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
carries the value, and it is the part you do. `sync.py` is the same principle in
the other direction: it reports that a file moved, and does not rewrite the page
about it.

It also does not invent content. Every claim on a page should be traceable to a
file in the repository. `config.py`'s `source_root` is asserted in the footer of
every page and is what `sync.py` compares against, so set it to the repository
the lessons were actually read from.

---

## When this skill changes

Skills are copied into each agent and nothing watches them for updates, so a
rule that changes needs to travel with the skill. The mechanism is a
self-deleting block at the top of this file:

```markdown
<post-update-cleanup>
BEFORE doing any work, run the migration below. Then delete this entire
section from THIS file so it does not run again until the next update.

    python3 ~/.agents/skills/clone-site/scripts/migrate.py docs/site --to v1.1-to-v2.0 --apply

It is a dry run without --apply. It renames fragments from their number to
their slug, drops the now-derived n= field, writes .bak beside anything it
rewrites, and reports anything it will not touch.
</post-update-cleanup>
```

The agent runs it once and removes the section, so the migration costs one
session rather than a version check on every session. **Only ship a block when
there is a real migration.** An always-present block that finds nothing to do is
noise that trains people to skip it.

The pending migration, when the Rust port lands, is `config.py` / `pages.py` →
`config.toml` / `pages.toml`. The `sync.py`, `migrate.py` and `menu.py` paths
added in v2.0 must exist there too, or `bootstrap.py` will scaffold a site whose
generator is missing half of itself — which is what happened with `menu.py` in
v1.1.