# Pitfalls

The failures that produce output which looks correct and is not. Each is a
pattern, the reason it is dangerous, and what to do instead.

- [Every fragment](#every-fragment)
- [Bulk edits](#bulk-edits)
- [The highlighter](#the-highlighter)
- [The pipeline](#the-pipeline)
- [Identity](#identity)
- [Completeness](#completeness)

Every entry is a bug that was actually hit while building a 492-lesson site.
None produced an error — each produced output that looked correct and was wrong,
which is the only kind worth writing down.

Each is stated as a match-and-refuse: what to look for, what it costs, and what
to do instead. The invariants in `SKILL.md` are the short form of the ones
marked **every fragment**; this is the long form, with the symptom each produced.

> Assert the shape of what you are rewriting before you rewrite it. Every entry
> below got past inspection because the output looked plausible.

---

## Every fragment

These bite every time you write a page. They are inlined in `SKILL.md`; they are
repeated here with the failure.

### Unbalanced tags

**PATTERN**: a `<b>` closed by `</p>`, an `<em>` closed by its outer tag, any
element closed by something other than what opened it.

**WHY**: HTML parsers do not complain, they cascade. One stray close produces a
page with mismatched nesting and every validator downstream reports it as
something else entirely.

**REWRITE**: fix the **first** error in a file — `check_site.py` records the
opening line for each mismatch, and the rest are usually consequences.

### Unescaped generics in a code block

**PATTERN**: `<pre class="code" data-lang="dart"><code>Future<List<File>> read()`

**FORBIDDEN**: a bare `<` or `>` inside a code block. Also `</code>`, which
closes the block early, and a literal `&` that was meant as an ampersand.

**WHY**: the parser reads `<List<File>` as a tag and swallows the rest of the
line. No error — the code just quietly stops rendering.

**REWRITE**: `&lt;List&lt;File&gt;&gt;`.

### A code block with no path header

**PATTERN**: a fragment opening with a bare ` ``` ` block, or a comment that
names nothing outside the file.

**WHY**: a reader cannot tell which files they are allowed to edit, and a
generated file looks hand-written.

**REWRITE**: the first line names the path and says whether it is generated —
`// lib/core/config/env.dart — hand written`.

### A saved total

**PATTERN**: `TOTAL_STEPS = 739` as a literal.

**WHY**: it survived a rename and a change, and put the wrong number in the
header of all 739 pages. Nobody noticed for weeks, because 739 is a plausible
number of steps.

**REWRITE**: derive it — `len(PAGES)`. A literal is a claim that rots silently.

### A cross-reference by number

**PATTERN**: "see step 16", "as in step 8".

**WHY**: inserting or splitting a lesson renumbers everything after it, and the
reference silently becomes a lie with nothing to detect it.

**REWRITE**: refer by what the lesson does — "the routing lesson". The step
count is in the page header anyway.

---

## Bulk edits

These bite when renumbering, retargeting, or restructuring — not when writing a
page. Read this section before any scripted edit over `content/` or `pages.py`.

### Blind numeric remapping

**PATTERN**: rewriting "step 16" to "step 21" by replacing every integer in the
document.

**WHY**: `<td>16</td>` was a pixel width and `<td>8</td>` was an item count.
Both became step numbers, and ~150 pages were corrupted in one pass.

**REWRITE**: classify each numeric cell by its column's role and rewrite only
reference columns. Assert the slice equals `<td>N</td>` before writing it.

### Guessing a column's role from a word in it

**PATTERN**: matching a header against `file`, `count`, or `covered` to decide
it is a step-reference column.

**WHY**: a column headed "files covered" matched `file` and its file *counts*
were renumbered as step numbers.

**REWRITE**: match explicit reference words only — `lesson`, `step`, `see`,
`where` — and exclude `file`, `covered`, `count`.

### An unhandled `href` fallback

**PATTERN**: substituting a placeholder when a link target cannot be resolved.

**WHY**: produced eight broken links.

**REWRITE**: leave the href alone. An unresolved link is a smaller problem than
a wrong one.

### Restoring a backup over the working tree

**PATTERN**: "restore from backup and re-run" when the pipeline rewrote
`content/` in place.

**WHY**: it destroyed hand-authored sources, because they were inside the
destructive path.

**REWRITE**: keep authored sources outside it, in a directory the build copies
from. Then restore-and-re-run is a no-op on the sources.

---

## The highlighter

### Omitting the `m` flag on a line-anchored rule

**PATTERN**: a regular expression using `^` or `$` without the `m` flag.

**WHY**: it can only match at offset 0 of the string. In the highlighter this
made YAML, shell and Dockerfile property highlighting silently do nothing — 3
tokens instead of 6, no error anywhere. The symptom is "highlighting randomly
doesn't work for some languages", which is very hard to trace to a missing flag.

**REWRITE**: add the flag. Assert a known construct in the target language
produces the expected token count.

### A JS string containing a regex escape

```js
str: ['\$?\'[^\']*\'', …]     //  '\$' is an unknown JS escape → becomes '$'
str: ['\\$?\'[^\']*\'', …]    //  correct: the regex sees \$?
```

**WHY**: `'\$'` silently yields `$`, producing `$?` — an invalid regex that
throws at module load and takes the whole page's highlighting with it.

**REWRITE**: double every backslash meant to reach a regex.

### A character class JavaScript parses differently

**PATTERN**: `[]}]`

**FORBIDDEN**: treating it as "a class containing `]` and `}`". In JavaScript
`[]` is a valid **empty** class, so it parses as empty-class, then literal `}`,
then literal `]`. It matches the wrong things and never errors.

**REWRITE**: `[\]}]`.

---

## The pipeline

### Validating before building

**PATTERN**: running the validators after editing a fragment but before
rebuilding.

**WHY**: they read the generated pages, so they report on the *previous* build
— which reads as "my change passed validation" when it was never checked.

**REWRITE**: always build, then validate.

### Non-greedy block splitting

**PATTERN**: splitting HTML on `<div…>.*?</div>`.

**WHY**: orphans the closing `</div>` whenever divs nest, because the first
`</div>` it finds is the inner one. The same applies to `.risk` containing
`.tbl` containing `table`.

**REWRITE**: count depth.

### Cell offsets in a table rewrite

**PATTERN**: `r.start() + c.start(1)`.

**WHY**: omits the row's own inner offset, because `r.start(1)` is already
absolute. Every table rewrite spliced at the wrong place.

**REWRITE**: assert the extracted slice looks like what you expected before
writing it.

### Padded slug keys

**PATTERN**: a lookup map keyed by `int`; normalising with `rstrip('-')`.

**WHY**: an `int` key cannot resolve `href="01-…"`, and `rstrip('-')` breaks a
dash-only filename.

**REWRITE**: try both spellings. Never mutate a filename while parsing it.

### Ordering derived two different ways

**PATTERN**: the builder emitting appendix pages in `pages.py` declaration
order while the validator derives the same order by sorting filenames.

**WHY**: they agreed by luck until an appendix was declared out of alphabetical
order, at which point every prev/next check failed at once and it looked like a
generator bug.

**REWRITE**: both sides read the same declaration. When two components must
agree on an order, one of them owns it and the other asks.

### Stale output after a lesson is deleted

**PATTERN**: renaming a lesson without pruning the old file.

**WHY**: the site still opened, and the validator failed with pages whose
prev/next chains no longer existed — an error that reads as a builder bug.

**REWRITE**: `build.py` prunes generated pages `pages.py` no longer claims, and
only touches the generated name patterns, so a hand-written page survives.

### A generated file, hand-edited

**PATTERN**: writing purpose text into `pages.py`, which the pipeline
regenerates.

**WHY**: it was lost on the next rebuild, with no error.

**REWRITE**: anything a script writes must be written by that script. If a value
varies per entry, keep it in a separate data file keyed by something stable —
here, the output slug, because step numbers move when a lesson is split and a
purpose that silently re-attaches to the wrong file is worse than no purpose.

### Assuming a file's contents from its name

**PATTERN**: writing a `sort` against an assumed structure.

**WHY**: it lost the relative order of `case` and `default` arms. The code
looked right and was wrong.

**REWRITE**: re-read the file before trusting an assumption about it —
especially one formed from memory of a different version.

## Identity

### A display number doubling as a storage key

**PATTERN**: using one field for two jobs — what the reader is shown, and what
something on disk or in a browser is named after.

**WHY**: the step number was the order *and* the fragment filename
(`content/%02d.html`) *and* the read-tracking key (`data-page="step-<n>"`).
Three consequences, none of them visible at the time it was introduced:

- reordering lessons handed each one a different body, because the fragment was
  addressed by position. The site built clean and passed validation with the
  wrong content on every page after the edit point;
- a `n=` that disagreed with its position silently won in one place and lost in
  the other, so the sidebar, the step pill and the filename disagreed;
- inserting one lesson near the front reset every reader's saved progress from
  that point on. `menu.py` carried a comment saying the key was deliberately
  independent of the number, two lines above code that read the number.

**REWRITE**: one field, one job. Display values are derived from position at
render time and never stored; storage keys are derived from the slug, which is
the one identifier that survives reordering. If a comment claims a property, the
test that proves it should exist before the comment does.

### A filename pattern that quietly stopped matching

**PATTERN**: deciding what is generated by matching its name — `^\d+-.*\.html$`.

**WHY**: pruning used that pattern. It worked because slugs had to start with
the step number. Removing that coupling (see above) left the pattern matching
almost nothing, so no orphan page was ever deleted again, and no test failed:
deleting a lesson simply left its HTML on disk, still rendering, still linked
from the index. The pruning code had not changed and did not look wrong.

**REWRITE**: ask what you actually want to know, and record the answer. The
manifest already lists every file the builder emitted, so that — not a pattern —
is what says a file is a candidate for deletion. Prefer a positive record over
an inferred pattern, because an inferred one stops matching when something
unrelated changes and nothing says so.

## Completeness

### Marking a cut instead of removing it

**PATTERN**: showing part of a file and adding a `// ...` marker so the reader
can tell it is a cut.

**WHY**: it is the honest move and it still breaks the site. On a `sealed` class
the elided subclasses were required for the file to compile, and four of them
were in a sentence of prose instead of in the code. The lesson was unbuildable
while looking well-disclosed.

**REWRITE**: the honesty requirement was real and the response was wrong. If a
block must be unbuildable when copied, it is not a file — split the file. Keep
markers for hand-written prose fragments, where nothing is expected to compile.

### An optional field nobody populates

**PATTERN**: making a field optional, then never checking it.

**WHY**: `why=` was documented, styled, and rendered — and on a 511-lesson site
every entry carried a purpose statement while *zero* pages showed one, because
nothing required the field and nothing reported it missing. A dedicated
`why.py` held all 511 and its own docstring claimed build.py rendered it; a
refactor had dropped the code. The work looked done.

**REWRITE**: an optional field is an unmonitored one. Either require it and
validate that, or delete it. If it needs an opt-out, make the opt-out explicit
(`why=None`) so that "not written yet" and "not applicable" stay different
facts — and check for the first, not the second.

