# The Rust engine

A single self-contained binary that does the work `scripts/*.py` used to do, so
installing the skill does not require an interpreter.

**Status: partially ported. `build` is done and verified; the other five
subcommands are not written yet. The Python engine remains the shipped path.**
See "Where this stands" below for what that means in practice.

## Why a binary rather than "no runtime"

The original framing was that this skill should need no runtime at all, the way
the reference skill does. That turned out to be a misread of the reference: its
*skill* is pure prose, but the repository around it trades a scripting runtime
for a compiled one — roughly 8.9 MB of Rust to avoid needing Node. Its skill
portion is 11 files and 1,366 lines.

So "no runtime" was never the win. What a binary actually buys is **a
distribution that cannot be forked.** That is the problem worth solving here,
and it is a real one rather than a hypothetical.

The generator used to live *inside each project*, at `_build/build.py`, where
it was editable. On the 492-lesson reference site it was forked: the site name
ended up hardcoded into a string literal and `config.py` — the indirection
built specifically to prevent that — was never read at all. The file being
editable is what allowed it.

A binary cannot be edited in place, and this layout removes the reason to try:

```
skill (one copy, read-only)      your project (data and content only)
  engine/  ──────────────▶        docs/site/
    clone-site                       _build/config.toml   ← site prose
    clone-site build  ──────▶        _build/pages.toml    ← what exists, in order
                                     _build/content/NN.html ← one fragment per lesson
```

Nothing in the project is code, so there is nothing there to fork.

## Where this stands

| Subcommand | Ported | Notes |
|---|---|---|
| `build` | **yes** | verified end to end; see below |
| `check` | **yes** | agrees with the reference on 474 real fragments |
| `index` | no | |
| `check-svg` | no | |
| `scan` | no | |
| `init` | no | |

`bin/clone-site` still dispatches to the Python engine. It has deliberately not
been pointed at this binary, because the binary cannot yet build a whole site.

## What has been verified, and how

Escaping is the one place where a difference between the two implementations is
invisible in a diff of the generator and visible on every published page. It is
therefore diffed against the reference rather than asserted by hand:

```bash
cargo test --release        # unit tests
python3 -B tests/selftest.py   # also runs a 4,016-case differential
```

The differential compares `escape`/`unescape` output line for line against
Python's `html.escape`/`html.unescape`, including randomly assembled entity
fragments and random Unicode. Three bugs were found this way that reading the
code did not:

- A hand-picked table of ~100 entity names resolved `&not` and not `&aacute;`,
  so accented prose rendered as literal source text. `src/entities.rs` is now
  generated in full from the reference table — 2,231 entities, plus the numeric
  edge-case tables.
- The longest-prefix match advanced past the text it did not consume, so
  `&ampx` rendered as `&` instead of `&x`.
- Numeric references were missing the Windows-1252 mapping, so `&#128;` would
  not have produced `€`.

Two of the hand-written assertions added alongside it were *also* wrong while
being written — one claimed `&notareal;` is unresolvable, when `not` makes it
resolve to `¬areal;`. That is the argument for the differential: assertions
written from the same understanding as the code cannot catch the
misunderstanding.

### The ported `check`

The structural validator, verified two ways.

**Against the reference, on the whole real corpus.** All 474 non-empty content
fragments from the 502-lesson reference site, byte-exact, one document per
comparison: 474 agree, 0 differ. Not a hand-picked sample — every fragment that
site actually contains.

The 27 fragments it *excludes* are zero-byte files on disk. Both validators
report them, so they are checked separately: the engine says "starts without an
`<h2>`", which is right. (The site-local fork of the validator does not carry
that check at all, which is why its run is green. The engine is the stricter of
the two, deliberately — it carries the skill's checks, not that site's subset.)

**Differentially, in `tests/selftest.py`.** The same parser, driven through the
real binary over generated inputs. Driving the binary rather than calling into
the library is the point: an earlier version of this parser passed its own unit
tests while the binary reported the wrong line, because the two paths were not
tokenizing the same string.

#### One deliberate divergence

The reference reports an emoji at the line where the text run *began*. The engine
reports the line the emoji is actually on. For a finding inside a paragraph that
spans five lines, the reference names row 1 and the emoji is on row 4. The engine
is the more useful answer, and it is asserted explicitly rather than diffed,
because diffing would flag it as a regression.

The other 20 differential cases are compared exactly.

#### Finding byte offsets without byte offsets

html5ever reports a *line* per token, not a byte offset. To put an emoji on the
right row the parser has to know where the text run came from, so it walks the
original source, skipping tags and matching the source spelling of character
references (`&amp;`) rather than the resolved text (`&`). Three bugs lived here,
all of which produced a plausible wrong line rather than a crash:

- Accumulating token lengths drifted, because a tag token's length is not its
  serialised length. Every line number crept upward.
- Counting `text` as bytes desynchronised the two counters on any non-ASCII
  character, which then sliced inside a UTF-8 sequence and **panicked**. Found by
  running the 502 real fragments, not by any test.
- Returning where the walk ended rather than where it began put every finding
  one line too low.

A panic here matters more than it looks: it is a validator, so the one input it
must never mishandle is the one that makes it stop.

### The ported `build`

- `src/model.rs` — `config.toml` / `pages.toml`, and the guards. Duplicate `n`
  is rejected because two lessons sharing one resolve to the same
  `content/NN.html`, so the build succeeds and both pages silently carry the
  first lesson's text — the one failure every downstream validator still calls
  clean.
- `src/build.rs` — the renderer. Two deliberate departures from the Python:
  - **Appendix `data-page` fixed.** The Python emitted
    `data-page="appendix aria-current="page""`. The browser parses that as a
    single attribute whose value is `appendix aria-current=`, so the
    current-page highlight never applied and read-tracking keyed on the mangled
    string. The reference site's fork had already corrected this by hand.
  - **`nav` escaped consistently.** The Python escaped it in the appendix
    sidebar and not the lesson sidebar.

## Building

```bash
cd engine
cargo build --release          # target/release/clone-site, ~294 KB
cargo test --release
```

Only `x86_64-unknown-linux-gnu` has been exercised. A binary for another
platform needs that target added and a cross-linker; that has not been done, and
"it compiles here" is not evidence about macOS or Windows.

To regenerate the entity tables after a reference change:

```bash
python3 scripts/gen_entities.py
```

## When the port finishes

Delete `scripts/*.py` rather than keeping both. Two implementations of a
renderer drift — that is the entire argument for moving to a binary, and
keeping a Python fallback would reintroduce it in the one place it has already
happened.