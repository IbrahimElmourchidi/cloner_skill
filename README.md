# cloner_skill

An AI skill that turns any software repository into a step-by-step teaching
site: one static HTML page per source file, in the order a developer actually
works, each carrying the real file contents and a plain assessment of whether
its choices are good.

No framework, no build step to view it, no network. Open `index.html` from disk.

```bash
./install.sh                                            # install for every agent found
./bin/clone-site init ~/code/my-project --name "My Project"
./bin/clone-site scan ~/code/my-project
```

Language-agnostic: the highlighter covers ~71 languages, file-type detection is
extension-driven over ~90, and nothing in the generator contains a project name.
Python 3 (standard library only) is the one runtime requirement today — a Rust
engine is being ported to remove even that. `build` and `check` are ported and
verified; the rest is not. See [`engine/README.md`](engine/README.md).

## Install

```bash
git clone https://github.com/IbrahimElmourchidi/cloner_skill.git
cd cloner_skill
./install.sh
```

`install.sh` detects every AI agent on the machine and installs for all of them.
It is safe to re-run — that is the update path.

| Flag | |
|---|---|
| `--dry-run` | print the plan, change nothing |
| `--list` | report what was detected, install nothing |
| `--uninstall` | remove every link and the canonical copy |
| `-a, --agents a,b` | restrict to specific agents |
| `--link ID=PATH` | add an agent that is not in the table |
| `-f, --force` | replace files that are in the way |

**Restart your agents afterwards.** Skills are discovered at startup, not
watched for changes — an installed skill is invisible until the agent restarts.

### How it installs

One real copy, then symlinks:

```
~/.agents/skills/clone-site/          ← the only copy on disk
~/.claude/skills/clone-site           → ~/.agents/skills/clone-site
~/.gemini/skills/clone-site           → ~/.agents/skills/clone-site
~/.gemini/antigravity-cli/skills/…    → ~/.agents/skills/clone-site
~/.config/opencode/skills/clone-site  → ~/.agents/skills/clone-site
```

`~/.agents/skills/` is the cross-client location the [Agent Skills
specification](https://agentskills.io) documents for interoperability, so
clients that read it — Codex, Cursor, and others — pick the skill up with no
link at all. The symlinks exist for the clients that read only their own
directory.

Because there is exactly one copy, updating means re-running `./install.sh`;
nothing drifts between agents.

### Agent coverage is deliberately short

The table in `install.sh` lists only agents whose directory layout is verified
— checked against this machine, or documented by the client's own docs. A wrong
path would create a directory nothing ever reads while you believed the skill
was installed, which is worse than an agent being absent.

An agent not listed is one flag:

```bash
./install.sh --link myagent=~/.config/myagent/skills
```

Currently covered: Claude Code, Gemini CLI, Gemini Antigravity, OpenCode (all
linked), plus Codex and Cursor (covered by `~/.agents/skills/`).

### To run without installing

The scripts are plain Python 3, stdlib only. Nothing else is required:

```bash
python3 scripts/bootstrap.py ~/code/my-project --name "My Project"
python3 scripts/scan.py ~/code/my-project
```

Or use the wrapper, which resolves its own location:

```bash
./bin/clone-site init ~/code/my-project --name "My Project"
./bin/clone-site scan ~/code/my-project
```

## What gets generated

```
docs/site/
├── index.html              overview + full table of contents
├── assets/                 design system, syntax highlighting
├── <slug>.html             one page per lesson
└── _build/
    ├── config.py           ← the only project-specific file
    ├── pages.py            ← what exists, in what order
    ├── manifest.json       ← what each lesson was built from  (generated)
    └── content/<slug>.html ← one fragment per lesson
```

`config.py` and `pages.py` are yours. Everything else is copied verbatim and can
be updated later without touching your content.

Fragments are named after the **slug**, not the step number, and the step
number is derived from each entry's position in `pages.py`. Reordering is
therefore a move within one list — no renumbering, no renaming, and no reader's
saved progress invalidated.

## Journey order, and what it costs

The order of `pages.py` is the order a developer works in, which for an
application is *not* the order the import graph is readable in. The file that
runs imports everything, so a leaf-first sort teaches the bottom of the stack
first and the reader sees nothing work for two hundred lessons.

So the reader gets the entry point first, and what sits underneath it is
stubbed until its turn comes. Two fields carry that:

```python
dict(slug='home-grid', nav='the product grid',
     path='lib/features/home/widgets/product_grid.dart',
     preview='Run it. Home shows four tabs, each with three grey cards.',
     stubs=[dict(path='lib/catalog/domain/usecases.dart',
                 names='CatalogUsecase, HomeFeedType',
                 real='Phase 4 &middot; Catalog domain',
                 note='Every method returns an empty list.')]),
```

`preview` is the payoff line — what the reader can see now that they could not
see before. `stubs` declares the placeholders the reader has to invent, and the
names in it are exempt from the forward-reference check.

Two things are enforced, and both are mechanical:

- **Declare it or do not do it.** An undeclared forward reference is still
  reported, naming both lessons. A stub is the reader being told what to write;
  without it they meet a compile error and a type name.
- **Every stub is retired.** A *later* lesson must carry that same `path=`.
  There is no `retired=` field — retirement is matched against later `path=`
  values, so a placeholder nobody pays off is reported rather than remembered.

`scan.py --journey` produces the draft order and prints the debt per step, so
the price is visible before it is paid. A step needing a dozen or more
placeholders is a DI module or a router in disguise; the answer there is to stub
the whole file behind one placeholder and teach it near the end.

## A curriculum too big to hold in one edit

Past about forty lessons, `pages.py` stops being a file you can work on: a few
hundred `dict(...)` entries is sixty kilobytes, and the only way to change lesson
40 is to read and rewrite all of it. That is how a curriculum gets re-emitted
from a stale copy and loses a lesson, with the build green and the validator
green throughout.

So write it in parts and let `join.py` assemble it:

```bash
scripts/join.py ~/code/my-project/docs/site/_build --check --root ~/code/my-project
scripts/join.py ~/code/my-project/docs/site/_build --root ~/code/my-project
```

```
_build/_parts/01.py     dict(slug='manifest', …),
                       dict(slug='entry-point', …),
_build/_parts/02.py     dict(slug='the-router', …),
```

The result is still one list, and no downstream script can tell. `pages.py`
becomes **derived** — edit the parts, not the file — while everything outside
`PAGES = [...]` is preserved byte for byte, including the hand-edited
`APPENDIX`. `join.py --split N` goes the other direction if you want to back
out.

It refuses the things that are silent otherwise: an unpadded part filename
(`part10.py` sorts before `part2.py`, moving ninety lessons), a duplicate slug,
a duplicate `path`, a stored `n=`, a missing `why`, and — with `--root` — a
`path` that is not in the repository.

## The commands

| Command | Does |
|---|---|
| `bootstrap.py PROJECT --name NAME` | Copies the generator in, writes a config, builds, and validates. Exits non-zero if the result is not valid. |
| `scan.py PROJECT` | Inventories the repo: languages, line counts, manifests, entry points, and a draft step order. `--journey` orders breadth-first from the entry points and prints the stub debt each step takes on; the default sorts leaf-first by the import graph. `--json`, `--write`, `--no-deps`, `--skip DIR`, `--include DIR` |
| `join.py BUILD_DIR` | Assembles a large curriculum from `_build/_parts/NN.py` into `pages.py`, which becomes derived. `--check` validates without writing, `--root DIR` confirms every `path=` exists, `--split N` goes the other direction. |
| `build.py` | Renders `pages.py` + `content/` into pages. Prunes stale ones. `--incremental` rewrites only the pages whose fragment changed. |
| `sync.py` | Compares the site against the repository: what was added, modified, renamed, deleted. Dry run by default. `--apply`, `--root DIR`, `--yes` |
| `index.py` | Regenerates `index.html`. |
| `check_site.py` | Tag balance, duplicate ids, links, anchors, prev/next chains, `data-lang`, emoji. Prints `BAD: none`. Validates content fragments first, with `file:line`. |
| `check_svg.py` | Diagram geometry: overlapping text, text crossing a box it does not belong to, anything outside the `viewBox`. Prints `problems: 0`. |

## The rebuild loop

```bash
cd ~/code/my-project/docs/site/_build
python3 build.py && python3 index.py
python3 check_site.py
```

Always build before validating — the validators read the generated pages, so
they report on the previous build otherwise.

## Extending

**A new language.** Add it to `KNOWN_LANG` in `check_site.py`, then add a
`RULES` entry in `assets/app.js`. Most languages are one line: `cLike()` and
`hashLike()` build the whole rule set from a keyword list.

**The appendix.** Deep dives, audits, checklists, or anything else that should
sit outside the lesson order. No step number, its own chain, any topic.

**Phases.** `phase=` on a page entry sets its sidebar heading. Use the
project's own structure rather than a generic one.

## Documentation

- `SKILL.md` — the skill itself: invariants, batch workflow, commands
- `references/authoring.md` — page format, block vocabulary, escaping
- `references/curriculum.md` — designing the step order, per ecosystem
- `references/pitfalls.md` — every bug that produced plausible wrong output,
  as a match-and-refuse list
- `engine/README.md` — the Rust engine: status, what is verified, how

## Commands

Invoked as `/clone-site COMMAND` once the agent has restarted.

| Command | Argument | Does |
|---|---|---|
| `init` | project path | Scaffold a site: copy the generator in, write the config, build, validate |
| `scan` | project path | Inventory the repo and draft a step order |
| `plan` | project path, `--context "…"` | Read the project, design phases, write `pages.py`, present the plan |
| `appendix` | topic, or none | Propose the appendix topics, then write them |
| `build` | batch size, default 10 | Author that many lessons, write them to disk, render, validate, then stop and ask |
| `sync` | site path | Compare the site against the repository; act on what moved |
| `render` | — | Re-render every page and validate, changing no content |
| `check` | `fragments` \| `pages` | Validate without rebuilding |
| `split` | step number | Break one oversized lesson into several |
| `renumber` | — | Shift step numbers after an insert, delete, or split |
| `next` | — | Continue the current batch run |

They are modes of one workflow, not separate tools: `plan` → `build N` (repeat)
→ `appendix` → `render` is the arc, and the rest exist because those steps get
interrupted or redone.

`build` takes a batch size and **defaults to 10** — big enough to establish the
rhythm, small enough that a course correction is still cheap. `render` is the
idempotent half: it re-renders and validates and changes nothing under
`content/`, so it is what you want after a hand-edit, a `split`, a `renumber`,
or on a site someone else wrote.

`split` and `renumber` are almost always used together, since splitting shifts
every later number. Both carry their own reference file.

## Scenarios

What to run, given what happened to the repository. A site is not a one-shot
export — the code keeps moving after the lessons are written, and this is how
the two get back together.

| What happened | Run | What it does |
|---|---|---|
| **Starting new** | `init` → `plan` → `build N` → `render` | The full arc. `init` scaffolds and self-validates, `plan` stops for your approval, `build` writes lessons in batches. |
| **You edited a file** | `sync`, then re-author, then `render` | Reports `MODIFIED`. It does **not** rewrite the page — the prose around the code is about that code, so a changed value needs a changed explanation. |
| **You added a file** | `sync` → author a lesson | Reports `ADDED` as a candidate. It never invents a lesson: deciding what a reader needs means reading the file. |
| **You deleted a file** | `sync --apply` → `render` | Reports `DELETED` and removes the entry, the fragment and the generated HTML. The lesson disappears from the list entirely. |
| **You renamed a file** | `sync --apply` | Reports `RENAMED` and updates `path=`. The contents are identical, so the lesson is untouched. |
| **A file is gone and `sync` can't prove why** | `sync` | Reports `ORPHANED` and **changes nothing**. Its bytes were never seen in the repository, so this may be a deletion, or a file that moved outside the scan root, or a lesson that was hand-added and never existed. Yours to decide. |
| **You inserted or reordered a lesson** | move the entry in `pages.py`, then `render` | Nothing else changes: the number is derived, the fragment and URL follow the slug. |
| **Only prose changed** | `render` | No `sync` needed — `sync` is about the repository, not about you. |
| **You split a big file** | `split` → `renumber` → `render` | Split the *source file*, then each part is its own whole lesson. |

```bash
clone-site sync                # dry run; changes nothing
clone-site sync --apply        # act on the two provable cases
clone-site sync --apply --yes  # and do not stop to ask
```

`--apply` only touches `RENAMED` and `DELETED`, because those are the two it can
*prove*: a file is definitely gone only if its contents appear nowhere in the
repository. `ADDED`, `MODIFIED` and `ORPHANED` are reported and left alone.

Everything depends on `_build/manifest.json`, which each build writes and which
records the path a lesson teaches plus a hash of both the source file and the
fragment. Without it "has this changed since I wrote the page?" is not merely
unchecked — it is unanswerable, which is why `sync` could not exist before v2.

If your site predates v2, migrate it first — it renames the fragments and drops
the now-derived `n=`:

```bash
python3 ~/.agents/skills/clone-site/scripts/migrate.py docs/site --to v1.1-to-v2.0 --apply
```

It is a dry run without `--apply`, writes `.bak` beside anything it rewrites, and
reports anything it will not guess at.

## Building a full site

The order matters, and three of these steps are gates rather than work.

```bash
/clone-site init ~/code/my-project --name "My Project"   # 1
/clone-site plan ~/code/my-project                      # 2  ← stops and asks
/clone-site build 10                                    # 3  ← repeat until done
/clone-site appendix                                    # 4  ← stops and asks
/clone-site render                                     # 5
```

### 1. `init`

Scaffolds `docs/site/` in the project: copies the generator in, writes the
config, builds, and validates. Exits non-zero if the result is not valid, so a
green `init` means the plumbing works and everything after it is prose.

### 2. `plan` — gate

Reads the project properly, designs the phases, writes `pages.py`, then
**presents the plan and stops.** You approve or correct the order before a single
lesson exists.

The draft order `scan` produces is a **topological sort of the real import
graph** — it reads the import lines, resolves them to files, and puts each
module after everything it depends on, using directory order only as the
tie-break so two scans of an unchanged repo agree. Pass `--no-deps` to see the
raw directory order instead, which is what you are arguing against.

The sort knows that `b.py` imports `a.py`. It does not know that a reader needs
the domain before the wiring, or that a file does not deserve a lesson at all,
so this step is an argument with a draft, not a rubber stamp. Ask for just the
inventory with `/clone-site scan ~/code/my-project`.

### 3. `build 10` — the loop

Authors 10 lessons, writes them to disk, renders, validates, then reports and
asks whether to continue.

```bash
/clone-site build 10
/clone-site build 25        # a bigger batch once the page shape has settled
/clone-site build           # no number: 10
/clone-site next            # same size as the last batch, or 10
```

Writing and building are one command because the halves are not separable in
practice: a lesson written but not rendered cannot be validated, and the validator
is what tells you the fragment is broken.

The batch size is yours to set. Batching exists because quality decays on a long
run and nothing detects it — there is no validator for "this page is less careful
than the previous one" — so the stopping point has to be a decision rather than
an accident.

### 4. `appendix` — gate

Writes the appendix: deep dives, audits, checklists, background on a decision
that spans many steps. **Stops and lists the topics before writing any**, for the
same reason `plan` does — appendix scope is a judgement call, and nine good pages
beat twenty-one nobody wanted.

Pass a topic to skip the proposal: `/clone-site appendix "how the riverpod
codegen works"`.

Worth doing *after* the lessons rather than before. An appendix is usually the
result of having understood the lessons, and writing one first produces
background nobody had earned yet.

### 5. `render`

Renders every page and validates, changing no content. Idempotent, and safe on
its own at any point — including after `split` or `renumber`. Also available as
`clone-site render` from a shell, which is the fastest way to confirm a
hand-edited fragment still renders clean.

```bash
/clone-site render
/clone-site check fragments   # validate authored content, no build needed
```

### Editing afterwards

Adding one lesson:

```bash
/clone-site build 1
```

Then `render` to confirm it.

Changing the shape of the site — splitting a big file, inserting a step:

```bash
/clone-site split 87         # then, almost always:
/clone-site renumber
/clone-site render
```

Splitting shifts every later step number, so `renumber` follows it unless the
split is at the end. Both earn their own commands because they are the edits that
silently corrupt a large site: on a 492-lesson reference, one blind numeric
remap turned a pixel width and an item count into step numbers and broke ~150
pages with every validator still passing.

### What each command refuses to do

The gates are the point, not friction:

| Command | Stops because |
|---|---|
| `plan` | Lesson order is a judgement call you own |
| `build` | Quality decays on a long run; the batch boundary is the safeguard |
| `appendix` | Scope is a judgement call, and it reads better after the lessons |

None of them proceed on an assumption about what you wanted. If an assumption is
wrong, say so and the command will change course rather than continue.

## How it works

The skill is two tiers. The rules you must always follow are inlined in
`SKILL.md` inside named blocks, because an agent that has to go looking for them
will skip the lookup. The long form of each — the symptom it produced, the
pattern to match, what to do instead — is in `references/`, reached only when
you reach the step that needs it.

Lessons are written in **batches**. The skill plans first, asks for a batch
size, and reports at the end of every batch. Quality decays on a long run and
nothing detects it, so the stopping point is a decision rather than an accident.

## What it does not do

It does not generate the lessons. `scan.py` gives you an inventory and a
starting order; deciding what the steps are means reading the repository, and
an unchecked generated lesson list is worse than none. That part is the value,
so it stays with you.

## Requirements

Python 3.8+, standard library only, to build a site. Rust, only if you are
working on the engine. Node is optional — used to sanity-check `app.js` syntax
if you edit the highlighter.

## License

MIT. See [LICENSE](LICENSE).