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
| `plan` | project path | Read the project, design phases, write `pages.toml`, present the plan |
| `write` | batch size | Author that many lessons, then stop and report |
| `build` | — | Render every page and validate |
| `check` | `fragments` \| `pages` | Validate without rebuilding |
| `split` | step number | Break one oversized lesson into several |
| `renumber` | — | Shift step numbers after an insert, delete, or split |
| `next` | — | Continue the current batch run |

They are modes of one workflow, not separate tools: `plan` → `write` → `build`
is the loop, and the rest exist because those steps get interrupted or redone.
Invoking `build` on its own is fine — it is idempotent.

`split` and `renumber` are almost always used together, since splitting shifts
every later number. Both carry their own reference file.

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