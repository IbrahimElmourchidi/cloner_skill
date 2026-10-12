# Splitting one lesson into several

Use when a single source file is too big to teach in one step, or does more than
one thing. This is not a cosmetic edit: the reader has to end each step knowing
something they can use before the next one starts.

Read `references/pitfalls.md` **§ Bulk edits** first. Most of the damage comes
from doing this with the wrong tool.

## Decide whether to split at all

Split when the file has **two or more separable responsibilities** — not merely
because it is long. A long file doing one thing is one lesson; a short file
doing three things is three lessons.

Ask: *after reading only this step, could a reader do something useful?* If the
answer is no, it is too big.

## Find the seams

Split on responsibility boundaries, never on line count. The signals, in order of
reliability:

1. **Section markers.** A `// ── Section` comment, a docstring heading, a
   `# region` block. Someone already did this work.
2. **Declaration groups.** A run of related functions, a struct plus its impl, a
   list of constants that belong together.
3. **Call order.** For a pipeline, the order things are called in — each stage is
   a natural step.
4. **Comment density.** A long commented block is usually one idea that was never
   given a heading.

Do **not** split at a fixed line threshold. It produces a step that ends
mid-argument, which is the thing most likely to confuse.

## Split the lesson content, not just the file

Each new lesson gets its own fragment, and each fragment must stand alone:

- Each has its own `<h2>`, its own `lead` that hooks the *next* step.
- The first carries the **overview**: what the whole file is for and why it is
  being taken apart. The rest do not repeat it.
- `path` on the first step points at the whole file. Later steps point at the
  same path but say what *part* of it they cover — use the `why` field, not
  `path`, since they genuinely write to one file.
- Later steps refer back by what the earlier step *did* ("the parser lesson"),
  never by number. `<refer_by_role>` in `SKILL.md` applies with extra force here,
  because splitting renumbers everything downstream.

## Renumbering is the dangerous part

Splitting step *n* into *n*, *n+1*, *n+2* shifts every later step by one or two,
and every cross-reference that named a number.

Do **not** rewrite numbers with a blind find-and-replace. `<td>16</td>` in a
table is a pixel width. See `references/renumbering.md`.

Safer order of operations:

1. Write the new fragments first, with their intended numbers.
2. Renumber `pages.toml` with the careful method.
3. Fix cross-references, classified by column role.
4. Build, then validate.
5. Re-read one page that straddles the split boundary. That is the page most
   likely to read wrong even when every validator passes.

## Verify

```bash
python3 build.py && python3 index.py
python3 check_site.py && python3 check_svg.py
```

Then read the last step of the first half and the first step of the second. The
boundary is where prose that made sense in one lesson stops making sense, and no
validator can tell you that.