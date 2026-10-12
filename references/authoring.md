# Authoring a page

One file, `_build/content/NN.html`, inserted verbatim into the shell. It is a
fragment: no `<html>`, no `<head>`, no `<main>`, no `<body>`. Start with an
`<h2>`.

- [Block vocabulary](#block-vocabulary)
- [Page shape](#page-shape)
- [Escaping](#escaping)
- [Diagrams](#diagrams)
- [The purpose statement](#the-purpose-statement)
- [Common failures](#common-failures)

## Block vocabulary

| Block | Use it for |
|---|---|
| `<h2>`, `<h3>` | Section headings. A page must have at least one `<h2>`. |
| `<p>` | Prose. |
| `<ul>`, `<ol>`, `<li>` | Lists. |
| `<pre class="code" data-lang="X">` | Source code. |
| `<pre class="cmd">` | A shell command. Handled by `cmd=` in pages.py. |
| `<div class="tbl">` + `<table>` | A table that may overflow on a narrow screen. |
| `<div class="verdict">` | One judgement about one choice. |
| `<div class="risk">` | What breaks. Red. |
| `<div class="warn">` | What fails *quietly*. Amber. |
| `<div class="tip">` | Something genuinely useful. Green. |
| `<div class="note">` | Context or a citation. Blue. |
| `<div class="key">` | The short version — a summary box. Neutral. |
| `<figure class="diagram">` | Inline SVG. See below. |
| `<span class="n">` | A bare number, monospaced. |

### Verdict blocks

A verdict is a claim about a specific choice, with a badge. One claim per block.

```html
<div class="verdict">
  <span class="badge">Best practice</span>
  <p><b>The claim, bolded, as a sentence.</b>
  Why it is right, and what would make it wrong.</p>
</div>
```

Add `v-partly` for a debatable choice, `v-no` for one to avoid. The badge text
changes with it (`Debatable`, `Avoid`). The left border colour changes too, so
the judgement is legible without reading the badge.

### Callout blocks

```html
<div class="risk"><b class="t">What breaks</b><p>…</p></div>
<div class="warn"><b class="t">What fails quietly</b><p>…</p></div>
<div class="tip"><b class="t">Worth knowing</b><p>…</p></div>
<div class="note"><b class="t">On the naming</b><p>…</p></div>
<div class="key"><b class="t">The short version</b><p>…</p></div>
```

The bolded `<b class="t">` is the label. One or more `<p>` after it.

## Page shape

**Code first.** A reader who came for the file should find it immediately, not
after three paragraphs of framing.

Then, in this order:

1. **How it works.** Walk the actual logic. Name the specific decisions and
   explain the reasoning behind them — the parts a reader could not infer from
   reading the code themselves.
2. **Verdicts.** One per judgement worth making. Not a survey of every line.
3. **Risks.** What breaks, and what fails *without* an error message. These are
   different and the second is more valuable: a failure that prints nothing
   costs hours, a failure that throws costs seconds.
4. **What could be better.** Improvements you did **not** make, with the reason.

That last section is the one people skip and the one that makes the site worth
reading. A guide that only shows what to copy teaches half of nothing. Saying
"this is fine but a context object would be better here, and I did not do it
because it was not worth the churn for a file this size" teaches a judgement,
which transfers.

### Excerpts versus whole files

Early steps show complete files. Once a file grows past the point where
reproducing it helps, show the relevant part — and **mark the cut**. A reader
who cannot tell whether a block is the whole file will assume it is, and will
be wrong about something that matters.

Two ways to be honest, and the second is what the validator requires:

**In the prose**, for a reader skimming:

```html
<h2>The loader</h2>
<p>The <code>load()</code> function below is the whole of
<code>config.py</code> except for the two type aliases at the top.</p>
```

**In the block**, with an elision marker on a line of its own:

```
class ConfigLoader {
  ConfigLoader(this._root);

  // ...
}
```

Use the marker whenever the block leaves a brace open. `check_site.py` counts
braces per `<pre class="code">` and reports any block that ends unbalanced
without one — because an unmarked fragment is the one failure that looks
exactly like success. A block showing a constructor and stopping reads as a
finished class, and the page then discusses fields, getters and `props` that
are nowhere in it.

The check is deliberately crude about braces inside strings and comments: it
strips them, so `"{"` in a Dart literal does not count. It errs towards
reporting, because the cost of a false positive is one `// ...` line and the
cost of a false negative is a reader's wrong conclusion.

Which fix to apply is a judgement, not a rule. Sometimes the honest fix is the
marker; sometimes it is the rest of the class, because the omitted part is the
point of the page. The validator tells you which blocks are ambiguous. It does
not decide what they should say.

### Tables

One cell per `<td>`, one `<tr>` per row, and the first row of the table fixes
the column count for every row after it:

```html
<div class="tbl"><table>
<thead><tr><th>Lesson</th><th>Writes</th></tr></thead>
<tbody>
<tr><td>22</td><td>the three entities</td></tr>
</tbody>
</table></div>
```

The failure to avoid is a doubled tag:

```html
<tr><td><td>22</td></td><td>the three entities</td></tr>
```

That is **balanced markup** — two opens, two closes — so a tag-balance check
has nothing to report. A browser disagrees: it closes the first cell where it
meets the second, so the row renders one column wider than the header and every
cell to its right shifts along with it. The page looks like a styling problem
and the markup looks correct, which is why this survives a build that otherwise
passes. `check_site.py` counts cells per row against the first row of the same
table and reports both faults separately:

- *nested in another* — a `<td>` inside a `<td>`. Delete the inner tag.
- *cell count mismatch* — a row that is genuinely short or long. This one is
  never auto-fixable: deciding what belongs in a missing cell is an authoring
  judgement, not a string operation.

`colspan` and `rowspan` are both honoured, and both are legitimate. A row may be
shorter than the header when a `rowspan` from a row above already occupies the
columns it does not repeat.

## Escaping

The one that bites, every time:

```html
<pre class="code" data-lang="dart"><code>Future&lt;List&lt;File&gt;&gt; read() async {</code></pre>
```

`<String>`, `List<T>`, `a < b`, `->` in prose. Inside `pre.code` an unescaped `<`
starts a tag and the parser eats everything up to the next `>`.

In `pages.py`, `nav`, `h1` and `lead` are HTML-escaped by the builder. Do not
pre-escape them. The prose fields in `config.py` are **not** escaped — those
insert raw HTML, so use entities there (`&rsquo;`, `&middot;`, `&mdash;`).

`data-lang` must be a name in `KNOWN_LANG` in `check_site.py`. The set covers
~110 spellings and common aliases (`py`, `rb`, `rs`, `yml`, `sh`). An unknown
name is almost always a typo, because its only symptom is code that renders
without colour.

### The first line of a code block

Every code block's first line names the path and says whether the file is
generated:

```
// lib/core/config/env.dart — hand-written, committed
```

This is not decoration. A reader working through the project needs to know at a
glance which files they are allowed to edit and which will be overwritten by a
build.

## Diagrams

Inline SVG only — no images, no external references, nothing that needs a
network. `check_svg.py` catches the defects that are invisible in source and
obvious on screen: text overlapping a box it does not belong to, text
overlapping text, anything outside the `viewBox` (silently clipped), and edges
crossing labels.

```html
<figure class="diagram">
<svg viewBox="0 0 520 180" role="img" aria-label="Request path through three layers">
  <!-- rects carry class="node", labels class="lb" (bold) and "sb" (small) -->
</svg>
<figcaption>How a request reaches the database.</figcaption>
</figcaption-note>Source: lib/api/client.ts, lib/db/pool.ts</figcaption-note>
</figure>
```

Useful SVG classes: `.lb` (label, 13px), `.sb` (sub-label, 11.5px), `.el`
(edge label), `.fnote` (figure note), `.band` (background strip — decoration,
never holds the label of a box it overlaps).

Two rules that prevent most failures:

- **Give every `<svg>` a `viewBox` and an `aria-label`.** The linter ignores SVGs
  without a `viewBox`, so a missing one silently disables the check.
- **Do not reach for a diagram unless the structure is genuinely spatial.**
  A table is clearer than a picture for anything you would describe as "A maps
  to B".

## The purpose statement

`why=` in `pages.py` renders as a "Why it exists" line under the step panel.

Write it for configuration files, abstractions, and special-purpose modules —
anything where "what is this" is obvious from the code but "why is this here"
is not. Not every step needs one; a step that writes a data table does not.

Write it in terms of the constraint the file removes, not the thing it holds.

> Holds the database URL. *(Restates the filename.)*

> …it is the one file in this project that cannot be reconstructed from the
> repository, because the value is secret. Everything else can be re-derived by
> reading the code. *(Explains why it must be committed separately, and as a
> template rather than the real thing.)*

## Common failures

These are checked mechanically, so you will hit them:

| Symptom | Cause |
|---|---|
| `unknown data-lang "dartt"` | Typo. Check the spelling against `KNOWN_LANG`. |
| `</div> closes <b> opened on line N` | A `<b>` or `<em>` closed by its outer tag. The error names the opening line — fix the first one. |
| `starts without an <h2>` | The fragment opens with prose instead of a heading. |
| `anchor #foo does not resolve` | An `href="#foo"` with no matching `id`. Check it on the built page, not the fragment — fragments are validated without the shell. |
| `emoji '…' in text` | Remove it. |
| `duplicate id(s)` | Two elements with the same `id` on one page. |
| `pages.py declares a page with no fragment` | You added a `PAGES` entry without creating `content/NN.html`. |
| `content/NN.html has no matching entry in pages.py` | A leftover fragment from a renamed or deleted lesson. |