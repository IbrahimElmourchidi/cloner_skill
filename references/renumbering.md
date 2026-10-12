# Renumbering lessons safely

Use when inserting, deleting, or splitting changes how many steps there are, so
every later step number and every cross-reference shifts.

> **Never rewrite numbers by replacing every integer in the document.** On a
> 492-lesson site, `<td>16</td>` was a pixel width and `<td>8</td>` was an item
> count. Both became step numbers and ~150 pages were corrupted in one pass. This
> is the single most expensive mistake available in this workflow, and it is
> entirely invisible — every validator still passes.

## The rule

A number is only a step number **if something asserts it is**. Find what asserts
it, and change only those things.

## 1. Write down the shift

Before touching anything, produce the mapping explicitly:

```
old n  ->  new n
```

Splitting step 16 into three steps means every step from 17 up gains two. Say so
in one place and refer back to it.

## 2. Renumber `pages.toml` only

The lesson list is the authority. Walk it in order and reassign `n` so it is
contiguous from 1, then update each `slug`'s numeric prefix to match.

Two things to get right:

- The slug prefix must track `n`. Reading order is recovered from the filename, so
  a slug that does not move with its number silently reorders the sidebar.
- **Nothing else lives in `pages.toml`.** If you find a purpose statement or a
  hand-edited line in there, it is being lost on the next rebuild — move it to a
  file that is not regenerated before you lose it.

## 3. Find cross-references and classify them

Cross-references live in page bodies and in `pages.toml`'s `lead`/`why` fields.
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
them alone entirely — the only files you should edit are `pages.toml` and the
lesson fragments' *prose*.

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

`check_site.py` re-derives reading order from the filenames and compares it to
the declared order, so a missed shift shows up as a prev/next mismatch. It will
not catch a prose cross-reference that now names the wrong lesson — only reading
will.

## 7. Spot-check the boundary

Re-read the last page before the insertion and the first page after it. Those are
the two most likely to be wrong even when everything validates, because their
neighbours moved.