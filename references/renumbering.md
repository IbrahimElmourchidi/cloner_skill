# Renumbering lessons safely

Use when inserting, deleting, or splitting changes how many steps there are, so
every later step number and every cross-reference shifts.

> **Most of this file no longer applies.** Since v2.0 there is no `n` field to
> renumber: the step number is derived from the position in `PAGES`, and the slug
> does not track it. Inserting, moving or deleting a lesson is a move within that
> list and nothing else — no mapping to compute, no slug prefixes to update, and
> `check_site.py` takes reading order from `pages.py` rather than from filenames.
>
> What survives is the part that was always the hard part: **numbers written in
> prose.** That is what this file is now for.

> **Never rewrite numbers by replacing every integer in the document.** On a
> 492-lesson site, `<td>16</td>` was a pixel width and `<td>8</td>` was an item
> count. Both became step numbers and ~150 pages were corrupted in one pass. This
> is the single most expensive mistake available in this workflow, and it is
> entirely invisible — every validator still passes.

## The rule

A number is only a step number **if something asserts it is**. Find what asserts
it, and change only those things.

## 1. Prefer not to reference steps at all

Before touching anything, produce the mapping explicitly:

```
old n  ->  new n
```

Splitting step 16 into three steps means every step from 17 up gains two. Say so
in one place and refer back to it.

## 2. Write down the shift

Before touching anything, produce the mapping explicitly:

```
old n  ->  new n
```

Splitting step 16 into three steps means every step from 17 up gains two. Say so
in one place and refer back to it. Nothing in `pages.py` needs this map any
more — it is for the prose below.

**`pages.py` itself needs nothing.** There is no `n` field to reassign and the
slug does not track the number. To move or delete a lesson, move or delete its
entry in the list and rebuild.

## 3. Find cross-references and classify them

Cross-references live in page bodies, and in `pages.py`'s `lead` and `why` fields.
For each candidate, decide which of three it is:

| Looks like | Actually is | Action |
|---|---|---|
| "step 16", "lesson 16", "see 16" | a step reference | shift it |
| `<td>16</td>` under a width/padding heading | a measurement | leave it |
| "8 files", `<td>8</td>` under a count heading | a quantity | leave it |

Match the **column's role**, not a word inside it. A column headed "files
covered" contains the word `file` and is not a reference column — matching on
`file` renumbers file counts as step numbers.

Use explicit reference words only: `lesson`, `step`, `see`, `where`. Exclude
`file`, `covered`, `count`, `line`, `px`, `width`.

Before writing any replacement, assert the slice looks like what you expect:

```python
m = re.search(r'<td>(\d+)</td>', cell)
assert m and 1 <= int(m.group(1)) <= total_steps
```

If that assertion fails, you are looking at the wrong cell. Do not proceed.

## 4. Do not touch the HTML's numeric attributes

Widths, grid columns, font sizes, and viewBox coordinates are numbers too. Leave
them alone entirely — the only thing you should edit is the lesson fragments'
prose.

## 5. Resolve generated output, not the source

If a link target could not be resolved, leave the `href` alone. A broken link is
a smaller problem than a link pointing confidently at the wrong lesson.

Then run `build`, which prunes pages no longer declared, so a deleted lesson
leaves no orphan HTML that fails the prev/next chain later.

## 6. Verify

```bash
python3 build.py && python3 index.py
python3 check_site.py        # prev/next chains are the real check
```

`check_site.py` re-derives reading order from `pages.py` and compares it to what
was built, so a mismatch shows up as a prev/next error. It will
not catch a prose cross-reference that now names the wrong lesson — only reading
will.

## 7. Spot-check the boundary

Re-read the last page before the insertion and the first page after it. Those are
the two most likely to be wrong even when everything validates, because their
neighbours moved.