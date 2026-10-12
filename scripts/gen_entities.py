#!/usr/bin/env python3
"""Regenerate `engine/src/entities.rs` from the reference entity tables.

    python3 scripts/gen_entities.py

The tables are read out of Python's `html` module rather than transcribed, for
the same reason the Rust tests diff against it: a hand-maintained list of
character references is a list that will be subtly wrong, and being subtly
wrong here is invisible until prose renders as literal source text on every
page of the site.

The one thing this cannot do is check that the reference itself is right. It is
the definition of correct for `unescape`, so the differential test in
`tests/selftest.py` is what actually guards the behaviour; this only guarantees
the table is complete.
"""
import html
import pathlib

ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def lit(text: str) -> str:
    """A Rust string literal for `text`, escaping what a literal cannot hold."""
    out = ['"']
    for c in text:
        if c in ESCAPES:
            out.append(ESCAPES[c])
        elif ord(c) < 0x20 or ord(c) == 0x7F:
            out.append("\\u{%x}" % ord(c))
        else:
            out.append(c)
    out.append('"')
    return "".join(out)


HEADER = """//! Generated tables for `unescape`, taken from the reference implementation
//! so the two cannot drift. See `references/pitfalls.md` for why this file
//! is generated rather than hand-written: a hand-picked subset of entity names
//! resolves `&not` correctly and `&aacute;` not at all, and that failure is
//! invisible until prose renders as literal source text on every page.
//!
//! Do not edit by hand. Regenerate with `scripts/gen_entities.py`.
"""


def main() -> None:
    h, icr, icp = html._html5, html._invalid_charrefs, html._invalid_codepoints
    lines = [
        HEADER,
        "",
        "/// Named character references. Both spellings are separate keys: `&amp`",
        "/// and `&amp;` differ only by the semicolon, and which one was written",
        "/// decides whether a following letter is part of the name.",
        "pub static ENTITIES: &[(&str, &str)] = &[",
    ]
    for k in sorted(h, key=lambda s: (-len(s), s)):
        lines.append(f"    ({lit(k)}, {lit(h[k])}),")
    lines += [
        "];",
        "",
        "/// Numeric references in this range name a Windows-1252 character, not the",
        "/// control character the code point would otherwise suggest.",
        "pub static INVALID_CHARREFS: &[(u32, &str)] = &[",
    ]
    for k in sorted(icr):
        lines.append(f"    ({k}, {lit(icr[k])}),")
    lines += [
        "];",
        "",
        "/// Numeric references to these code points resolve to nothing at all — not",
        "/// to U+FFFD, which is a separate case handled by the surrogate check.",
        "pub static INVALID_CODEPOINTS: &[u32] = &[",
    ]
    sc = sorted(icp)
    for i in range(0, len(sc), 12):
        lines.append("    " + ", ".join(str(x) for x in sc[i : i + 12]) + ",")
    lines += ["];", ""]

    out = pathlib.Path(__file__).resolve().parents[1] / "engine" / "src" / "entities.rs"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"wrote {out}: {len(h)} entities, {len(icr)} charref fixes, "
        f"{len(icp)} dropped codepoints"
    )


if __name__ == "__main__":
    main()
