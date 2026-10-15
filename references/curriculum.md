# Designing the curriculum

The generator takes any list of lessons you give it. Everything that makes the
site worth reading happens in this step, and none of it is automatable: you have
to read the repository and decide what a reader needs, in what order, and why.

- [The one rule](#the-one-rule)
- [Reordering is moving a line](#reordering-is-moving-a-line)
- [Writing it in parts](#writing-it-in-parts)
- [Phases](#phases)
- [Order the spine by journey, not by the import graph](#order-the-spine-by-journey-not-by-the-import-graph)
- [Pay for it with stubs](#pay-for-it-with-stubs)
- [Ordering within a slice](#ordering-within-a-slice)
- [Finding the journey](#finding-the-journey)
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

## Writing it in parts

A curriculum is one list of `dict(...)` entries, and it is the only artefact in
`_build/` that cannot be written incrementally. Everything else here is small: a
fragment, a config, a script. A 300-step `pages.py` is about sixty kilobytes,
produced in a single pass, before any lesson exists, by the step whose whole job
is to hold the shape of the site in mind at once.

That works up to a point and then quietly stops. The failure is not a crash. It
is that changing lesson 40 means reading and rewriting the entire file — which is
how a curriculum gets re-emitted from a slightly stale copy, and how one entry
goes missing with nothing reporting it, because the build is green and the
validator is green and the site is one lesson short of what it was.

**Above about forty lessons, write the lessons as parts.**

```bash
$SKILL/scripts/join.py ~/code/proj/docs/site/_build --check --root ~/code/proj
$SKILL/scripts/join.py ~/code/proj/docs/site/_build --root ~/code/proj
```

`_build/_parts/01.py`, `02.py`, `03.py`… each a run of `dict(...)` entries and
nothing else. `join.py` concatenates them in filename order and writes
`pages.py`. The result is still one list; nothing downstream — `build.py`,
`check_site.py`, `sync.py`, `index.py`, `menu.py` — can tell that it was
assembled. No downstream script changed.

What `join.py` preserves, and this is the part that matters:

- **Everything outside `PAGES = [...]`**, byte for byte. The docstring documenting
  every field, and the `APPENDIX` below the list. `APPENDIX` is hand-edited
  occasionally by somebody with no reason to know a parts directory exists, and
  joining a curriculum must never disturb it.
- **Your formatting.** Parts are copied verbatim, comments and all. Reformatting
  would be a kindness with a large bill: every rebuild would fight you over
  whitespace, and your comments marking a decision would be thrown away.
- **Nothing else.** A file not called `NN.py`, or starting with `_`, is skipped.

What it refuses, because each of these is silent otherwise:

| Refused | Why |
|---|---|
| a part filename that is not zero-padded | `part10.py` sorts before `part2.py`, which moves ninety lessons with no other symptom |
| two entries with one `slug` | the second page overwrites the first's progress marker |
| two entries with one `path` | one lesson is one file; the reader writes it twice |
| a stored `n=` | derived from position; one that disagrees stops the build |
| a missing `why` | found at step 40 of a batch costs a whole batch |
| a `path` that is not in the repository (`--root`) | a typo here is invisible until someone tries to follow the site |
| a value that is not a literal | `pages.py` is read by name, so a computed value is one nobody can see |

### `pages.py` becomes derived

That is the whole trade. Once the parts exist, `pages.py` is an **output** — edit
the parts, not the file. It is the only rule this adds, and it is worth stating
plainly because it is the one that catches people out: someone reads `pages.py`,
sees the change they want to make, makes it, and the next `join.py` silently
takes it back.

`--split N` goes the other direction — it explodes `pages.py` into parts of `N`
entries and leaves `pages.py` alone, so adopting or abandoning the split is
reversible. It is a structural change, not a reformat: comments *between* entries
are dropped, because they belong to a file that no longer exists.

### How big is too big

Not a lesson count, a **file size**. Roughly 40 entries in one `pages.py` is
about eight kilobytes, which is comfortable to read and rewrite in one go. Past
that, every edit is a whole-file rewrite, and a whole-file rewrite of a
hand-curated list is how lessons go missing.

Split at a phase boundary where you can, so each part is a coherent run and the
filename still means something. Beyond that, `join.py` does not care how you
cut it — but you will.

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

## Order the spine by journey, not by the import graph

**Sort by what the developer does, not by what imports what.**

A developer opening an application does something a topological sort cannot
predict: they get something on screen first. `main.dart` before the router
before the data layer, with the catalogue stubbed to return nothing, so the home
page renders grey cards on step four. Then they come back and grow the catalogue
while watching the screen fill in.

Leaf-first ordering gives them the opposite, and it is a bad experience. In most
applications the file that runs imports everything, so a topological sort puts it
last — which means lesson one is a leaf with no idea what it is for, and the
reader sees nothing work for two hundred lessons. Every step compiles. Nothing
happens.

The sort is not wrong, it is answering the wrong question. "What has to exist
first" is the right question for a library. For an application the right question
is "what can I see first", and those two orders have almost nothing in common.

**This is the load-bearing decision in the whole curriculum.** Everything else —
phases, slugs, page shape — is a consequence of it. Get the spine right and the
rest is bookkeeping; get it wrong and no amount of good prose makes lesson one
worth reading.

### The price, stated up front

Journey order means the reader compiles a file that imports something they do not
have yet. That is not a bug you can design away; it is the order working as
intended. What you can do is make the gap **explicit**, which is what
[stubs](#pay-for-it-with-stubs) are for.

The measure of a good journey order is not that it compiles — it is that the
reader sees the program do something early, and never meets a gap they were not
told about.

### When leaf-first is still right

Not every project is an application.

- **A library.** Its entry point *is* a leaf. Order by dependency and nothing is
  compromised.
- **A CLI with a real pipeline.** `parse → transform → emit` is a dependency
  chain a reader would follow anyway.
- **Generated code.** Protoc output has a genuine topological order and no
  meaningful "what the reader sees".

The test is whether there is a thing on screen — or in stdout — that changes
when a file changes. If yes, journey order. If the program's output is a pure
function of its inputs with no intermediate observable state, dependency order
and the stub machinery is dead weight.

## Pay for it with stubs

A stub is the reader's placeholder. It is declared on the lesson that needs it,
not taught as a lesson of its own:

```python
dict(slug='home-product-grid', nav='the product grid',
     path='lib/features/home/widgets/product_grid.dart',
     preview='Run it. Home shows four tabs, each with three grey cards.',
     stubs=[dict(path='lib/features/catalog/domain/usecases/catalog_usecases.dart',
                 names='CatalogProductsUsecase, HomeFeedType',
                 real='Phase 4 &middot; Catalog domain',
                 note='Three methods, every one returns an empty list.')]),
```

Four fields. `path` is required — it is the file the reader has to invent, and it
is matched against later lessons to decide whether the stub was ever retired.
`names` are the types the placeholder must define, and they are exempt from the
forward-reference check, which is the entire point of the mechanism. `real` says
where the real file lands, so the reader knows this is temporary. `note` says
what the placeholder does meanwhile, which is usually the only interesting thing
about it: "returns an empty list" is a design decision, and saying so turns a
placeholder into a lesson.

Three rules, and `check_site.py` holds all of them:

- **Declare it or don't do it.** An undeclared forward reference is still an
  error. A stub is the author telling the reader what to write; without it they
  meet a compile error and a type name and nothing else.
- **Every stub is retired.** A later lesson must carry that same `path=`. There
  is no `retired=` field: retirement is matched against later `path=` values, so
  a stub nobody pays off is *reported*, not remembered.
- **A stub comes before the real file, never after.** Pointing the reader at a
  placeholder they have already built is a contradiction, and the validator
  names it.

And set `preview` on every step that changes what the reader can see. It is the
one line that makes a journey order legible: without it, a lesson that wires up a
screen and a lesson that renames a helper look identical from the outside, and a
reader who followed the order has no way to tell that anything is working.

### When a stub is the wrong answer

Most stubs are small and honest. Some are not, and `--journey`'s debt table is
how you spot them: a step needing a dozen or more placeholders is a
dependency-wiring file — a DI module, a router, a bootstrap — and asking a reader
to invent fourteen files is not a lesson, it is a puzzle.

For those, stub **the whole file** behind one placeholder and teach it near the
end, when the things it wires already exist:

> `stubs=[dict(path='lib/core/di/app_di.dart', note='One empty module. Everything else in this phase imports it; it imports nothing back yet.')]`

One gap, clearly labelled, replaced by a real lesson once there is something real
to wire. That is a better reader experience than fourteen small lies.

## Ordering within a slice

The dependency sort has not been demoted, it has been given its actual job. It is
the right axis *inside* a slice — the handful of files that implement one idea
and genuinely need each other in a fixed sequence.

`utils.ts` before `api.ts`, `schema` before `repository`, `types` before anything
that imports them. `scan.py` does this mechanically, keeping directory/size order
as the tie-break so two scans of an unchanged repository produce the same list.
Pass `--no-deps` to see the raw directory order instead — useful precisely
because it is what you are arguing against.

So: journey order for the spine, dependency order within each slice, and stubs
for every place the spine runs ahead of the graph.

### The rule this exists to prevent

**No lesson may use a name that a later lesson defines — unless it declares that
name in `stubs=`.** A reader follows the order and writes each file as they go,
so an undeclared forward reference is not an inconvenience, it is a step that
cannot be completed: the code does not compile at the point the reader is told to
write it, and the lesson never says where the missing piece came from.

`check_site.py` checks this and names both lessons, so it reads like a compile
error rather than something the reader has to diagnose:

```
content/025-result-contract.html: step 25 uses AppFailure, which is not
defined until step 26 — move that lesson earlier, list AppFailure in this
lesson's stubs=, or teach it before anything that needs it
```

Under leaf-first ordering the common instance is an error type defined one file
away from the `Result` wrapper that carries it: the wrapper is more interesting,
so it gets the lower number, and the two files are otherwise interchangeable in
size. Under journey order it is every step, which is why `stubs=` exists.

Break cycles by judgement. Mutual imports exist and are legal in most of these
languages, so the sort emits them in seed order rather than refusing. Put the
lower-level file first and note the cycle on the later page — a reader who hits it
deserves to know the author saw it too. `scan.py` lists the cycles it found.

Where a slice has no dependencies at all (a folder of independent components),
sort alphabetically so the order is predictable and reproducible.

## Finding the journey

The journey is not in the import graph, so it has to be read out of the
repository. Four passes, in order.

1. **Find the entry point and read it.** Not what it imports — what it *does*.
   `main.dart` that builds a `MaterialApp` and hands off to a router tells you
   the first three lessons: manifest, app widget, entry point. That is a working
   app, and it is lesson three.
2. **Find the first thing a user can see.** Follow from the entry point to the
   first screen, ignoring everything below it. That file, plus the stub list it
   needs, is your second or third lesson. This is the step that justifies the
   whole order, so give it a real `preview=` — "run it, four tabs, three grey
   cards each" is worth more than any amount of prose about why grids exist.
3. **Work outward from what they can see, one layer at a time.** Each layer is
   what the previous layer reaches for. `scan.py --journey` does this
   mechanically and prints the debt for each step; your job is to decide which of
   those layers become lessons now and which stay stubbed until later.
4. **Decide where the wiring goes.** Dependency injection, routers, bootstraps
   and registries import the whole application and are taught by nobody early.
   Find them, and put them near the end. This is the one place leaf-first is
   simply correct, and the journey draft's very high placeholder counts for those
   files are the signal.

The last pass is the one that matters and the one most often skipped. A journey
order without a deliberate ending — where the wiring finally lands and every
stub is paid off — is just the first half of the curriculum.

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

The ordering decision for a small Flask API, from directory listing to lessons:

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

A dependency sort puts `models.py` third and `__init__.py` last, which is
correct and useless: the reader builds an ORM for twenty minutes before anything
responds to a request.

A journey order puts the thing that responds first:

| # | phase | file | |
|---|---|---|---|
| 1 | Toolchain | `pyproject.toml` | |
| 2 | Toolchain | `.env.example` | |
| 3 | Domain | `app/models.py` | slice: `models.py` is the one file with no dependencies |
| 4 | Interfaces | `app/__init__.py` — the factory | **stubs** `config` |
| 5 | Interfaces | `app/routes/__init__.py` | **stubs** `users`, `orders` |
| 6 | Interfaces | `app/routes/users.py` | first request answered — `preview=` |
| 7 | Interfaces | `app/routes/orders.py` | |
| 8 | Config | `app/config.py` | every stub above is retired here |

Two things to notice.

Lesson 4 stubs `config` — the factory reads it immediately, so the reader
invents a class with the right attributes and no behaviour. Lesson 8 pays that
off. Same for `users` and `orders` at lesson 5. Every stub on this list is
retired, which is what `stubs_are_retired` checks and what stops the placeholder
from becoming the lesson.

And lesson 8 is last. Config is a leaf, so the dependency sort would have put it
first; the journey order puts it last because nothing about the app is visible
without it, and because by lesson 8 the reader has seen three different things
reach for it and can be told what it is *for*. That is the trade in one row:
leaf-first is cheaper to compile, journey-first is worth more to read.

Note what is *not* there: `requirements.lock`, `tests/`. The tests are worth a
mention on the pages of the code they exercise, not a lesson each — unless
testing is the point of the site, in which case they get their own phase and
this table is wrong.