# cloner_skill

An AI skill that turns any software repository into a step-by-step teaching
site: one static HTML page per source file, in dependency order, each carrying
the real file contents and a plain assessment of whether its choices are good.

No framework, no build step to view it, no network. Open `index.html` from disk.

```bash
# scaffold a working site for any project
python3 scripts/bootstrap.py ~/code/my-project --name "My Project"

# see what the project is made of, and draft a step order
python3 scripts/scan.py ~/code/my-project
```

Language-agnostic: the highlighter covers ~55 languages, file-type detection is
extension-driven over ~90, and nothing in the generator contains a project name.

## Install

```bash
git clone https://github.com/IbrahimElmourchidi/cloner_skill.git \
    ~/.claude/skills/clone-site
```

Then ask for what you want in your own words — *"set up the step-by-step guide
site for this repo"*, *"turn this project into a file-by-file walkthrough"*.
The skill's description covers the phrasings; you do not have to name it.

To use it directly instead:

```bash
export SKILL=~/.claude/skills/clone-site
python3 $SKILL/scripts/bootstrap.py ~/code/my-project --name "My Project"
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

- `SKILL.md` — how to use the skill
- `references/authoring.md` — page format, block vocabulary, escaping
- `references/curriculum.md` — designing the step order, per ecosystem
- `references/pitfalls.md` — every bug that produced plausible wrong output

## What it does not do

It does not generate the lessons. `scan.py` gives you an inventory and a
starting order; deciding what the steps are means reading the repository, and
an unchecked generated lesson list is worse than none. That part is the value,
so it stays with you.

## Requirements

Python 3.8+, standard library only. Node is optional — it is used to sanity-check
`app.js` syntax if you edit the highlighter.

## License

MIT. See [LICENSE](LICENSE).