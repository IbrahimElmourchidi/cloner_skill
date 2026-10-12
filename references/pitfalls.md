# Pitfalls

Every entry here is a bug that was actually hit while building a 492-lesson
site. None produced an error — each produced output that looked correct and was
wrong, which is why they are worth writing down.

The general lesson, which is the reason this file exists: **assert the shape of
what you are rewriting before you rewrite it.** Every entry below got past
inspection because the output looked plausible.

---

## Authoring

### A `<b>` closed by `</p>`, or an `<em>` closed by its outer tag

The most common authoring error, and the most expensive, because HTML parsers
do not complain — they cascade. One stray close produces a page with mismatched
nesting, and every validator downstream reports it as something else.

`check_site.py` records the opening line for each mismatch, so the error names
where to start. Fix the *first* error in a file; the rest are usually
consequences.

### Unescaped generics in a code block

`<pre class="code" data-lang="dart"><code>Future<List<File>> read()</code></pre>`

The parser sees `<List<File>` as a tag and swallows the rest of the line. It
does not error — the code just quietly stops rendering. Use `&lt;` and `&gt;`.

### Omitting the `m` flag on a line-anchored rule

Any regular expression using `^` without the `m` flag can only match at offset
0 of the string. In the highlighter that made YAML, shell and Dockerfile
property highlighting silently do nothing — 3 tokens instead of 6, with no
error anywhere. The symptom is "highlighting randomly doesn't work for some
languages", which is very hard to trace back to a missing flag.

### A JS string containing a regex escape

```js
str: ['\$?\'[^\']*\'', …]     //  '\$' is an unknown JS escape → becomes '$'
str: ['\\$?\'[^\']*\'', …]    //  correct: the regex sees \$?
```

`'\$'` silently yields `$`, producing `$?` — an invalid regex that throws at
module load and takes the entire page's highlighting with it. Any backslash in
a JS string that is meant to reach a regular expression needs doubling.

### A regex character class that JavaScript parses differently

`[]}]` is *not* "a class containing `]` and `}`". In JavaScript `[]` is a
valid empty class, so that parses as empty-class, then literal `}`, then
literal `]`. It matches the wrong things and never errors. Write `[\]}]`.

---

## Cross-references and renumbering

### Blind numeric remapping

Rewriting "step 16" to "step 21" by replacing every integer in the document.
`<td>16</td>` was a pixel width. `<td>8</td>` was an item count. Both became
step numbers, and ~150 pages were corrupted in one pass.

Classify each numeric cell by its column's role, and rewrite only reference
columns. Assert the slice equals `<td>N</td>` before writing it.

### Guessing a column's role from a word in it

A column headed "files covered" matched the word "file" and was treated as a
step-reference column, so file *counts* were renumbered as step numbers. Match
explicit reference words only — `lesson`, `step`, `see`, `where` — and exclude
`file`, `covered`, `count`.

### An unhandled `href` fallback

When a link target could not be resolved, the rewriter substituted a
placeholder, producing eight broken links. If the target cannot be resolved,
leave the href alone. An unresolved link is a smaller problem than a wrong one.

### A generated file, hand-edited

Purpose text was written into `pages.py`, which the pipeline regenerates. It
was lost on the next rebuild, with no error.

Anything a script writes must be written by that script. If a value varies per
entry, keep it in a separate data file the generator reads — and key that data
by something stable. Here it is keyed by output slug, because step numbers move
when a lesson is split and a purpose that silently re-attaches to the wrong
file is worse than no purpose at all.

### Restoring a backup over the working tree

The pipeline rewrote `content/` in place, so "restore from backup and re-run"
destroyed hand-authored sources.

Keep authored sources outside the destructive path, in a separate directory the
build copies from. Then "restore and re-run" is a no-op on the sources.

---

## Structure

### Non-greedy block splitting

Splitting HTML on `<div…>.*?</div>` orphans the closing `</div>` whenever divs
nest, because the first `</div>` it finds is the inner one, not the outer.

Match by counting depth. The same applies to `.risk`, which contains `.tbl`,
which contains `table`.

### Cell offsets in a table rewrite

`r.start() + c.start(1)` omits the row's own inner offset, because `r.start(1)`
is already absolute. Every table rewrite then spliced at the wrong place.

Assert the extracted slice looks like what you expected before writing it.

### Padded slug keys

A lookup map keyed by `int` cannot resolve `href="01-…"`, and normalising with
`rstrip('-')` breaks a dash-only filename. Try both spellings; never mutate a
filename while parsing it.

### Ordering derived two different ways

The builder emitted appendix pages in `pages.py` declaration order. The
validator derived the same order by sorting filenames. They agreed by luck
until an appendix was declared out of alphabetical order, at which point every
prev/next check failed at once and it looked like a generator bug.

Both sides now read the same declaration. When two components must agree on an
order, one of them owns it and the other asks.

### Stale output after a lesson is deleted

Renaming a lesson left its old HTML in the output. The site still opened, and
the validator failed with pages whose prev/next chains no longer existed.

The builder now prunes generated pages that `pages.py` no longer claims. Only
files matching the generated name patterns are touched, so a hand-written page
in the same directory survives.

---

## Process

### Validating before building

The validators read the generated pages. Running them after editing a fragment
but before rebuilding reports on the *previous* build — which reads as "my
change passed validation" when it was never checked.

Always build, then validate.

### A saved `TOTAL_STEPS`

`TOTAL_STEPS = 739` survived a rename and change and put the wrong number in
the header of all 739 pages. Nobody noticed for weeks, because 739 is a
plausible number of steps.

Derive totals from the list. A literal is a claim that will rot silently.

### Assuming a file's contents from its name

Writing a `sort` against an assumed structure lost the relative order of `case`
and `default` arms. The code looked right and was wrong.

Re-read the file before trusting an assumption about it — especially one formed
from memory of a different version.