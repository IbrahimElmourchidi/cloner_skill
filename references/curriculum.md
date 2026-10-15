# Designing the curriculum

The generator takes any list of lessons you give it. Everything that makes the
site worth reading happens in this step, and none of it is automatable: you have
to read the repository and decide what a reader needs, in what order, and why.

- [The one rule](#the-one-rule)
- [Reordering is moving a line](#reordering-is-moving-a-line)
- [Phases](#phases)
- [Ordering within a phase](#ordering-within-a-phase)
- [Files that do not make good lessons](#files-that-do-not-make-good-lessons)
- [File sizes that do not make good lessons](#file-sizes-that-do-not-make-good-lessons)
- [Cross-references](#cross-references)
- [Ecosystem checklists](#ecosystem-checklists)
- [A worked example](#a-worked-example)

## The one rule

**One lesson = one file.**

Everything else follows from it. It forces each page to be self-contained,
which makes the prev/next chain meaningful and lets the reader stop at any
point and still have something coherent.

The cost is that a genuinely cross-cutting idea — an architectural rule, a
recurring pattern — does not belong to any one step. That is what the
[appendix](#the-appendix) is for. Put it there and cross-reference it.

## Reordering is moving a line

`PAGES` is an ordered list and the order *is* the reading order. The step number
is derived from the position, the content fragment is named after the slug, and
the reader's saved progress is keyed on the slug too — so inserting, moving or
deleting a lesson is a move within one list, and nothing else changes.

Three things used to fight that, and all three are gone:

- `n=` was stored per entry, so a move meant editing one field per entry and a
  stale value silently disagreed with the position. It is derived now, and an
  entry that still declares an `n` contradicting its position is a hard error
  naming both numbers.
- fragments were named `content/%02d.html` — after the *position* — so a
  reorder handed each lesson a different body. The site still built clean and
  still passed validation, with the wrong content on every page after the edit
  point.
- the read-tracking key was `step-<n>`, despite a comment directly above it
  saying it was independent of the number. Inserting one lesson near the front
  reset every reader's markers from there on.

The lesson is that a number used as a *display* value should not also be a
*storage key*. Once the two share a field, every future edit has to remember
that it is editing two things at once.

## Phases

A phase is a sidebar heading. It gives a long site structure, so a reader at
step 240 can tell roughly where they are.

Set `phase=` per entry. Use the project's *own* structure rather than a generic
one — the point is that this project's shape is what the reader is learning.
`scan.py`'s draft grouping by directory is a reasonable starting point for most
projects, because directories usually *are* how a project describes itself.

A workable default, for any project:

| Phase | Contents |
|---|---|
| Toolchain | Manifest, lockfile, linter/formatter config, CI, editor config, `.gitignore`, the entry point |
| Domain | The core types and business rules. The part with no dependencies. |
| Data | Persistence, schema, migrations, serialisation |
| Interfaces | Routes, controllers, handlers, public API |
| UI | Views, components, templates, styling |
| Operations | Deployment, environment, logging, monitoring |

Adjust it. A library has no UI phase. A monorepo might want one phase per
package. A script might be five lessons and need no phases at all.

## Ordering within a phase

**Sort by dependency, and the direction is always leaf first.** A file should
come after everything it depends on. `utils.ts` before `api.ts`, `schema`
before `repository`, `types` before anything that imports them.

`scan.py` does this for you: it reads the import lines, builds the graph over
the files it is teaching, and topologically sorts them, keeping the
directory/size order as the tie-break so two scans of an unchanged repository
produce the same list. Pass `--no-deps` to see the raw directory order instead —
useful precisely because it is what you are arguing against.

**The sort is necessary and not sufficient.** It knows that `b.py` imports
`a.py`. It does not know that a reader needs the domain before the wiring, or
that two files are more useful together, or that one of them deserves no lesson
at all. Read the result and argue with it.

How to establish the order when you want to go beyond the automatic sort:

1. **Find the entry point** and work backwards. `scan.py` flags likely ones by
   name (`main.py`, `index.ts`, `main.rs`, `wsgi.py`, `urls.py`…). The file that
   imports everything is usually last.
2. **Follow the imports** one level at a time. The script has already done the
   mechanical part; this is for the judgement calls — whether a directory is a
   phase boundary, whether an import is load-bearing or incidental.
3. **Break cycles by judgement.** Mutual imports exist and are legal in most of
   these languages, so the sort emits them in seed order rather than refusing.
   Put the lower-level file first and note the cycle on the later page — a
   reader who hits it deserves to know the author saw it too. `scan.py` lists
   the cycles it found.

Where a phase has no dependencies at all (a folder of independent components),
sort alphabetically so the order is predictable and reproducible.

### The rule this exists to prevent

**No lesson may use a name that a later lesson defines.** A reader follows the
order and writes each file as they go, so a step referencing a class introduced
three steps later is not an inconvenience — it is a step that cannot be
completed. The code does not compile at the point the reader is told to write
it, and the lesson never says where the missing piece came from.

`check_site.py` checks this and names both lessons, so it reads like a compile
error rather than something the reader has to diagnose:

```
content/025-result-contract.html: step 25 uses AppFailure, which is not
defined until step 26 — move that lesson earlier or teach AppFailure before
anything that needs it
```

The common instance of this is an error type defined one file away from the
`Result` wrapper that carries it: the wrapper is more interesting, so it gets
the lower number, and the two files are otherwise interchangeable in size.

## Files that do not make good lessons

Some files are not worth a page, and including them makes the site worse:

- **Lockfiles.** `package-lock.json` is 40,000 lines of resolved hashes. It
  belongs in the Toolchain phase as a *mention*, inside the manifest's page, not
  as its own step.
- **Generated code.** Protoc output, OpenAPI clients, ORM migrations, compiled
  assets, `*.g.dart` / `*.pb.go` / `*_pb2.py`. Explain the generator in a
  `div.note` on the file it produces, and teach the generator's *config* as its
  own step. Never transcribe the output.
- **Binary assets.** Fonts, images, icons. Cover them where they are configured.
- **Minified bundles.** Never.
- **Vendored dependencies.** Third-party code is not this project.

If the reader must know a file exists, say so on the page of the file that
uses it. That is more useful than a page that transcribes it.

## File sizes that do not make good lessons

Rough thresholds, to argue with rather than obey:

| Size | What to do |
|---|---|
| < 50 lines | Perfect as-is. |
| 50–200 lines | Usually one lesson. |
| 200–400 lines | One lesson, showing the whole file, if it has one idea. Otherwise split the file by idea and say so. |
| 400+ lines | Split the file by concept, not by line range. Each part is still "one file" in the sense that matters — one coherent thing — but it is its own file now, and each part is shown whole. |

The split that works is by *reason to exist*, not by line count. A 600-line file
with three distinct responsibilities is three files and three lessons. A 400-line
file that does one thing slowly is one lesson with a long code block.

**Splitting means splitting the file.** Showing part of a file you decided to
keep whole is not a split — it is an excerpt, and an excerpt is not something a
reader can build from. See [Whole files, not excerpts](authoring.md#whole-files-not-excerpts)
for why the elision marker is not an acceptable answer.

When you split, the verdict and risk blocks belong on the part they apply to. If
a judgement is about the file as a whole, it goes on the first part, with a
pointer. Stranded judgements are worse than a repeated one.

## Cross-references

**Refer to other lessons by what they do, never by number.**

> The dependency the config file's lesson declared is the one used here.

not

> As established in step 14, …

Numbers make the site fragile. Inserting a lesson renumbers everything after
it, and a stale reference points at the wrong page — silently, because the page
it names still exists and still looks plausible. If you must use a number, it is
`{n}` in a template you substitute after numbering is final, not a literal.

## The appendix

The appendix is for anything that should not sit in the lesson order.

- a deep dive on one mechanism
- an audit or scored review of the finished codebase
- a checklist, glossary, or debugging runbook
- background on a decision that spans many steps
- material that would break the "step N of M" narrative

It has no `n`, does not advance the counter, and never appears in a lesson's
prev/next chain. Readers reach it from the sidebar or the index. Slugs only need
to be unique; name them for the topic so more than one appendix can exist.

## Ecosystem checklists

What the Toolchain phase usually contains, by ecosystem. Use as a prompt, not
a form.

**Flutter / Dart** — `pubspec.yaml` (split: identity, dependencies, assets),
`.gitignore`, `analysis_options.yaml`, asset and font copying, launcher icons,
splash config, `lib/main.dart`, l10n setup, and a step for running the code
generators (Riverpod, `envied`, `build_runner`) as a command, not a file.

**Node / TypeScript** — `package.json` (split: scripts, deps, engines),
lockfile, `tsconfig.json`, bundler config, linter/formatter, `.env.example`,
`.gitignore`, entry point, type declarations, CI.

**Python** — `pyproject.toml` (split: build metadata, deps, tool config),
lockfile, `conftest.py`, linter config, `.env.example`, package layout, entry
point, `__init__.py` policy.

**Rust** — `Cargo.toml` (split: package, features, deps, profiles),
`Cargo.lock`, `rust-toolchain.toml`, `rustfmt.toml`/`clippy.toml`, `src/main.rs`
vs `src/lib.rs`, module layout, error-handling strategy as its own decision.

**Go** — `go.mod`, `go.sum`, `Makefile`, `cmd/` vs `internal/` layout, package
boundaries, the `internal` rule as a design point.

**Ruby / Rails** — `Gemfile` (split), `Gemfile.lock`, `Rakefile`,
`.rubocop.yml`, `config/application.rb`, environment files, initializers,
the `db/schema.rb` convention as a concept.

**Java / Kotlin** — `build.gradle[.kts]`, `settings.gradle`, wrapper,
`pom.xml`, package layout, module boundaries.

Anything else: `scan.py` will name the manifests it recognises, and you know
the ecosystem better than a table here does.

## A worked example

The ordering decision for a small Flask API, from directory listing to phases:

```
app/
  __init__.py     create_app() factory — everything imports this
  config.py       reads env, one class per environment
  models.py       SQLAlchemy models
  routes/
    __init__.py
    users.py      imports models
    orders.py     imports models
tests/
```

becomes

| # | phase | file |
|---|---|---|
| 1 | Toolchain | `pyproject.toml` |
| 2 | Toolchain | `.env.example` |
| 3 | Toolchain | `requirements.txt` |
| 4 | Domain | `app/__init__.py` — the factory |
| 5 | Config | `app/config.py` |
| 6 | Data | `app/models.py` |
| 7 | Interfaces | `app/routes/__init__.py` |
| 8 | Interfaces | `app/routes/users.py` |
| 9 | Interfaces | `app/routes/orders.py` |

Note what is *not* there: `requirements.lock`, `tests/`. The tests are worth a
mention on the pages of the code they exercise, not a lesson each — unless
testing is the point of the site, in which case they get their own phase and
this table is wrong.