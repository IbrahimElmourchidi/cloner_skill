# cloner_skill

An AI skill that turns any software repository into a step-by-step teaching
site: one static HTML page per source file, in dependency order, each carrying
the real file contents and a plain assessment of whether its choices are good.

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
├── NNN-slug.html           one page per lesson
└── _build/
    ├── config.py           ← the only project-specific file
    ├── pages.py            ← what exists, in what order
    └── content/NN.html     ← one fragment per lesson
```

`config.py` and `pages.py` are yours. Everything else is copied verbatim and can
be updated later without touching your content.

## The commands

| Command | Does |
|---|---|
| `bootstrap.py PROJECT --name NAME` | Copies the generator in, writes a config, builds, and validates. Exits non-zero if the result is not valid. |
| `scan.py PROJECT` | Inventories the repo: languages, line counts, manifests, entry points, and a draft step order. `--json`, `--write`, `--skip DIR`, `--include DIR` |
| `build.py` | Renders `pages.py` + `content/` into pages. Prunes stale ones. |
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
| `plan` | project path, `--context "…"` | Read the project, design phases, write `pages.toml`, present the plan |
| `appendix` | topic, or none | Propose the appendix topics, then write them |
| `build` | batch size, default 10 | Author that many lessons, write them to disk, render, validate, then stop and ask |
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

Reads the project properly, designs the phases, writes `pages.toml`, then
**presents the plan and stops.** You approve or correct the order before a single
lesson exists.

The draft order `scan` produces is sorted by directory and then file size, which
is a poor dependency order — it cannot see that one module imports another — so
this step is an argument with a draft, not a rubber stamp. Ask for just the
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