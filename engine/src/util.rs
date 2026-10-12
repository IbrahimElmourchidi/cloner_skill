//! Escaping helpers that match the reference implementation exactly.
//!
//! Parity is load-bearing rather than cosmetic: `pages.toml` prose is authored
//! once and rendered into every page, and this site renders thousands of them.
//! A difference here is invisible in a diff of the generator and shows up as a
//! stray `&#x27;` in every published page.
//!
//! `escape` mirrors the reference `html.escape(s)` with the default
//! `quote=True`, which turns `'` into `&#x27;` — a hex entity, not `&apos;`
//! and not `&#39;`.
//!
//! `unescape` mirrors `html.unescape(s)`, which implements the HTML5 rules for
//! references that are *invalid* as well as valid ones. Three of those rules
//! are easy to get wrong and each produces plausible output:
//!
//!   1. The longest matching name wins, and it need not end at the semicolon.
//!      `&notarealentity;` is `&not` followed by literal `arealentity;`.
//!   2. The prefix search never considers a one-character name, because the
//!      HTML5 table has none — so the fallback returns the match unchanged
//!      rather than stripping an `&` it cannot resolve.
//!   3. Numeric references in the C1 range name Windows-1252 characters.
//!      `&#128;` is `€`, not a control character. A code point in the surrogate
//!      range becomes U+FFFD; a code point the HTML5 spec says to drop becomes
//!      nothing at all, which is a different outcome.

use crate::entities::{ENTITIES, INVALID_CHARREFS, INVALID_CODEPOINTS};
use std::collections::HashMap;
use std::sync::OnceLock;

/// Equivalent of `html.escape(s)` with the default `quote=True`.
pub fn escape(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + s.len() / 8);
    for c in s.chars() {
        match c {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            '\'' => out.push_str("&#x27;"),
            _ => out.push(c),
        }
    }
    out
}

fn entity_map() -> &'static HashMap<&'static str, &'static str> {
    static MAP: OnceLock<HashMap<&'static str, &'static str>> = OnceLock::new();
    MAP.get_or_init(|| ENTITIES.iter().copied().collect())
}

fn charref_fix(num: u32) -> Option<&'static str> {
    static MAP: OnceLock<HashMap<u32, &'static str>> = OnceLock::new();
    let m = MAP.get_or_init(|| INVALID_CHARREFS.iter().copied().collect());
    m.get(&num).copied()
}

fn is_dropped(num: u32) -> bool {
    static MAP: OnceLock<HashMap<u32, ()>> = OnceLock::new();
    let m = MAP.get_or_init(|| INVALID_CODEPOINTS.iter().map(|&n| (n, ())).collect());
    m.contains_key(&num)
}

/// Is this character one a named reference may contain?
///
/// Mirrors the reference pattern `[^\t\n\f <&#;]{1,32};?`: a name stops at
/// whitespace, `<`, `&`, `#`, or after 32 characters. `;` is *allowed* inside
/// the run, which is what makes `&notarealentity;` scan as one candidate.
fn is_name_char(c: char) -> bool {
    !matches!(c, '\t' | '\n' | '\x0C' | ' ' | '<' | '&' | '#')
}

pub fn unescape(s: &str) -> String {
    if !s.contains('&') {
        return s.to_string();
    }
    let map = entity_map();
    let chars: Vec<char> = s.chars().collect();
    let mut out = String::with_capacity(s.len());
    let mut i = 0;

    while i < chars.len() {
        if chars[i] != '&' {
            out.push(chars[i]);
            i += 1;
            continue;
        }

        // --- numeric reference: &#123; or &#x7B; ---
        if chars.get(i + 1) == Some(&'#') {
            let hex = matches!(chars.get(i + 2), Some('x') | Some('X'));
            let ds = if hex { i + 3 } else { i + 2 };
            let mut k = ds;
            while k < chars.len() && (if hex { chars[k].is_ascii_hexdigit() } else { chars[k].is_ascii_digit() }) {
                k += 1;
            }
            if k > ds {
                let digits: String = chars[ds..k].iter().collect();
                if let Ok(num) = u32::from_str_radix(&digits, if hex { 16 } else { 10 }) {
                    let mut end = k;
                    if chars.get(end) == Some(&';') {
                        end += 1;
                    }
                    match charref_fix(num) {
                        Some(fixed) => out.push_str(fixed),
                        None if (0xD800..=0xDFFF).contains(&num) || num > 0x10FFFF => {
                            out.push('\u{FFFD}')
                        }
                        // The spec drops these outright rather than substituting,
                        // which is a different outcome from U+FFFD.
                        None if is_dropped(num) => {}
                        None => {
                            if let Some(c) = char::from_u32(num) {
                                out.push(c);
                            }
                        }
                    }
                    i = end;
                    continue;
                }
            }
        }

        // --- named reference: 1..=32 name chars, then an optional ';' ---
        let start = i + 1;
        let mut k = start;
        while k < chars.len() && (k - start) < 32 && is_name_char(chars[k]) {
            k += 1;
        }
        if k == start {
            out.push('&');
            i += 1;
            continue;
        }
        // The optional trailing semicolon is only a candidate on its own if the
        // run did not already absorb it — `&amp;` scans as the two-char name
        // `&amp` plus `;`, but `&aacute;` scans as one six-char run.
        let run: String = chars[start..k].iter().collect();
        let with_semi = if chars.get(k) == Some(&';') { Some(format!("{run};")) } else { None };

        let mut resolved = None;
        if let Some(cand) = with_semi.as_deref().and_then(|c| map.get(c)) {
            resolved = Some((*cand, run.len() + 1));
        }
        if resolved.is_none() {
            if let Some(c) = map.get(run.as_str()) {
                resolved = Some((*c, run.len()));
            }
        }
        // Longest matching prefix. The bound is 2, never 1: the HTML5 table has
        // no single-character names, so a one-character "match" would be a bug.
        if resolved.is_none() {
            let units: Vec<&str> = run.split("").skip(1).collect(); // ["", c0, c1, ...]
            for len in (2..=units.len()).rev() {
                let prefix: String = units[..len].concat();
                if let Some(c) = map.get(prefix.as_str()) {
                    resolved = Some((*c, len));
                    break;
                }
            }
        }

        match resolved {
            Some((text, used)) => {
                out.push_str(text);
                i = start + used;
            }
            // Unresolvable: the whole reference is left exactly as written.
            None => {
                out.push('&');
                out.push_str(&run);
                if let Some(cand) = with_semi {
                    out.push_str(&cand[run.len()..]);
                }
                i = k;
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn escape_matches_reference() {
        assert_eq!(escape("a&b"), "a&amp;b");
        assert_eq!(escape("<div>"), "&lt;div&gt;");
        assert_eq!(escape("\"q\""), "&quot;q&quot;");
        assert_eq!(escape("it's"), "it&#x27;s");
        assert_eq!(escape("&amp;"), "&amp;amp;");
        assert_eq!(escape("café ·"), "café ·");
    }

    #[test]
    fn unescape_matches_reference() {
        // the three rules called out at the top of the file
        assert_eq!(unescape("&notarealentity;"), "¬arealentity;");
        assert_eq!(unescape("&ampx"), "&x");
        assert_eq!(unescape("&#128;"), "€");
        // ordinary cases
        assert_eq!(unescape("Phase 0 &middot; Toolchain"), "Phase 0 · Toolchain");
        assert_eq!(unescape("it&rsquo;s"), "it’s");
        assert_eq!(unescape("&aacute;&eacute;&uuml;"), "áéü");
        assert_eq!(unescape("&amp"), "&");
        assert_eq!(unescape("&notreal"), "¬real");
        // unresolvable references survive intact. `&notareal;` is NOT one of
        // them — `not` is a real entity, so it resolves and leaves `areal;`.
        assert_eq!(unescape("&zzz;"), "&zzz;");
        assert_eq!(unescape("&notareal;"), "¬areal;");
        assert_eq!(unescape("100% & more"), "100% & more");
        // numeric edge cases
        assert_eq!(unescape("&#0;"), "\u{FFFD}");
        assert_eq!(unescape("&#xD800;"), "\u{FFFD}");
        assert_eq!(unescape("&#1;"), "");
    }

    #[test]
    fn round_trips() {
        for s in ["a&b", "<x>", "\"q\"", "it's", "plain", "café ·"] {
            assert_eq!(unescape(&escape(s)), s, "round trip failed for {s:?}");
        }
    }
}