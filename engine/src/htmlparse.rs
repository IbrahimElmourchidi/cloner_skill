//! Structural validation over one document.
//!
//! Split out from `check.rs` so the differential test can exercise the parser
//! directly, without needing a whole site on disk.

use crate::lang::KNOWN_LANG;
use html5ever::tokenizer::{
    BufferQueue, Tag, TagKind, Token, TokenSink, TokenSinkResult, Tokenizer,
};
use std::collections::BTreeMap;
use std::path::Path;

/// Elements that never have a closing tag. An `</img>` is a stray close, not a
/// balanced pair, so these must not enter the stack.
pub const VOID: &[&str] = &[
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
    "track", "wbr",
];

/// Everything collected from one document.
#[derive(Default)]
pub struct Findings {
    pub ids: Vec<String>,
    pub links: Vec<String>,
    pub anchors: Vec<String>,
    pub langs: Vec<String>,
    pub errors: Vec<String>,
    pub svg_open: i64,
    /// Open elements, innermost last, each with the line it was opened on.
    pub stack: Vec<(String, u64)>,
}

struct Collect {
    where_: String,
    f: Findings,
    /// The original source, searched to find where each text run came from.
    src: String,
    /// How far through `src` we have walked.
    cursor: usize,
    /// Byte offset of every newline, for turning an offset into a line number.
    newlines: Vec<usize>,
}

impl TokenSink for Collect {
    type Handle = ();

    fn process_token(&mut self, token: Token, line: u64) -> TokenSinkResult<()> {
        match token {
            Token::TagToken(tag) => self.tag(&tag, line),
            Token::CharacterTokens(text) => {
                // Locate this run in the source rather than deriving its offset
                // from the token's length. The tokenizer does not hand out byte
                // offsets, and accumulating lengths drifts: a tag token's length
                // is not its serialised length, so the cursor creeps forward and
                // every later line number is wrong — a wrong number in a
                // file:line message is worse than none, because it sends you to
                // the right file and the wrong row.
                let at = self.locate(&text);
                self.text(&text, at);
            }
            // A parse error is not itself a finding. html5ever recovers and
            // reports malformed markup through the tree builder, which this
            // validator does not use; reporting every recoverable oddity would
            // bury the tag-balance errors that actually matter.
            _ => {}
        }
        TokenSinkResult::Continue
    }
}

/// Lets the tokenizer borrow the collector rather than take it, so the findings
/// are still ours afterwards.
impl<'a> TokenSink for &'a mut Collect {
    type Handle = ();

    fn process_token(&mut self, token: Token, line: u64) -> TokenSinkResult<()> {
        TokenSink::process_token(*self, token, line)
    }
}

impl Collect {
    fn tag(&mut self, tag: &Tag, line: u64) {
        let name = tag.name.as_ref().to_ascii_lowercase();
        let is_start = matches!(tag.kind, TagKind::StartTag);

        for attr in &tag.attrs {
            let key: String = attr.name.local.as_ref().to_ascii_lowercase();
            let val = attr.value.to_string();
            if key == "id" {
                self.f.ids.push(val.clone());
            } else if name == "a" && key == "href" {
                if val.starts_with('#') {
                    self.f.anchors.push(val);
                } else {
                    self.f.links.push(val);
                }
            } else if name == "pre" && key == "data-lang" {
                self.f.langs.push(val.clone());
                if !KNOWN_LANG.contains(&val.as_str()) {
                    self.f.errors.push(format!(
                        "{}: unknown data-lang \"{}\" (add it to KNOWN_LANG in the engine)",
                        self.where_, val
                    ));
                }
            }
        }

        if name == "svg" {
            self.f.svg_open += if is_start { 1 } else { -1 };
        }

        if VOID.contains(&name.as_str()) {
            return;
        }
        if is_start {
            // `<div/>` is a start and an end in one token. Treating it as a bare
            // start leaves an unclosed `<div>` that the author never wrote.
            if tag.self_closing {
                return;
            }
            self.f.stack.push((name, line));
        } else {
            match self.f.stack.pop() {
                Some((open, _)) if open == name => {}
                Some((open, open_line)) => {
                    self.f.errors.push(format!(
                        "{}:{line}: </{name}> closes <{open}> opened on line {open_line}",
                        self.where_
                    ));
                }
                None => {
                    self.f.errors.push(format!("{}:{line}: stray </{name}>", self.where_));
                }
            }
        }
    }

    fn text(&mut self, text: &str, token_start: usize) {
        if let Some((at, c)) = text.char_indices().find(|(_, c)| is_emoji(*c)) {
            let line = self.line_at(token_start + at);
            self.f.errors.push(format!(
                "{}:{line}: emoji {:?} in text",
                self.where_,
                c.to_string()
            ));
        }
    }

    /// Byte offset of a text run in the original source.
    ///
    /// Walks forward from the cursor. Character references are the reason this
    /// cannot be a plain `find`: html5ever resolves `&amp;` before handing over
    /// the text, so the run no longer appears literally in the source. Searching
    /// for a resolved run would either miss it and resume past the real
    /// position, or match a different occurrence further on. Matching the
    /// source's own `&name;` / `&#NN;` spelling instead keeps the cursor honest.
    fn locate(&mut self, text: &str) -> usize {
        let bytes = self.src.as_bytes();
        // The run *starts* here. Returning where the walk ended instead points
        // past the text — which for a run at the end of a line lands on the next
        // one, and silently reports every finding one line too low.
        let start = self.cursor;
        let mut i = self.cursor;
        let mut t = 0;
        while i < bytes.len() && t < text.len() {
            if bytes[i] == b'<' {
                // A tag or comment: everything up to '>' is markup, skip it.
                while i < bytes.len() && bytes[i] != b'>' {
                    i += 1;
                }
                i = (i + 1).min(bytes.len());
                continue;
            }
            if bytes[i] == b'&' {
                // A character reference resolves to one or more characters.
                let mut j = i + 1;
                while j < bytes.len()
                    && j - i <= 32
                    && (bytes[j].is_ascii_alphanumeric() || bytes[j] == b'#')
                {
                    j += 1;
                }
                if j < bytes.len() && bytes[j] == b';' {
                    j += 1;
                }
                if j > i + 1 {
                    // Charge the resolved text at least one character. It can be
                    // several (`&NotEqualTilde;` is one, `&nGt;` is one, but a
                    // numeric reference may resolve to a multi-byte char), and
                    // the exact count does not matter — only that `t` is a valid
                    // char boundary, because slicing at a byte that lands inside
                    // a UTF-8 sequence panics.
                    t += match text[t..].chars().next() {
                        Some(c) => c.len_utf8(),
                        None => break,
                    };
                    i = j;
                    continue;
                }
            }
            // A plain character: advance both together, by whole characters so
            // `t` stays on a boundary. A non-ASCII character occupies several
            // source bytes but one text character, so a byte-wise step here
            // would also desynchronise the two counters.
            let src_char_len = text[t..]
                .chars()
                .next()
                .map(char::len_utf8)
                .unwrap_or(1);
            let mut adv = 1;
            while i + adv < bytes.len() && !text.is_char_boundary(t + adv) {
                adv += 1;
            }
            i += src_char_len;
            t += adv;
        }
        self.cursor = i;
        start
    }

    /// Line number for a byte offset in the original source.
    fn line_at(&self, byte_offset: usize) -> u64 {
        self.newlines.partition_point(|&nl| nl < byte_offset) as u64 + 1
    }
}

/// The ranges the validator rejects. Emoji is only detected in text tokens, so
/// a glyph inside a `data-lang` block is not scanned.
fn is_emoji(c: char) -> bool {
    matches!(c as u32, 0x1F300..=0x1FAFF | 0x2600..=0x27BF | 0x1F000..=0x1F02F)
}

/// Parse one document and return everything found.
pub fn parse_str(text: &str, where_: &str) -> Findings {
    let mut sink = Collect {
        where_: where_.to_string(),
        f: Findings::default(),
        src: text.to_string(),
        cursor: 0,
        newlines: text.match_indices('\n').map(|(i, _)| i).collect(),
    };
    // A fragment is a body slice, so tokenizing it standalone is right: it is
    // not wrapped in a document and then sliced, which would change how the
    // leading `<h2>` is treated.
    let mut input = BufferQueue::default();
    input.push_back(text.into());
    let mut tok = Tokenizer::new(&mut sink, Default::default());
    let _ = tok.feed(&mut input);
    tok.end();

    let mut f = sink.f;
    for (tag, line) in &f.stack {
        f.errors.push(format!("{}:{line}: <{tag}> never closed", where_));
    }
    if f.svg_open != 0 {
        f.errors.push(format!("{}: unbalanced <svg> ({} open)", where_, f.svg_open));
    }
    let mut seen: BTreeMap<&str, usize> = BTreeMap::new();
    for id in &f.ids {
        *seen.entry(id.as_str()).or_insert(0) += 1;
    }
    let dupes: Vec<&str> = seen.iter().filter(|(_, &c)| c > 1).map(|(k, _)| *k).collect();
    if !dupes.is_empty() {
        f.errors.push(format!(
            "{}: duplicate id(s) {}",
            where_,
            dupes.join(", ")
        ));
    }
    f
}

/// Parse a file from disk, so callers do not each re-derive the error shape.
pub fn parse_file(path: &Path, label: &str) -> Result<Findings, String> {
    let text = std::fs::read_to_string(path)
        .map_err(|e| format!("cannot read {}: {e}", path.display()))?;
    Ok(parse_str(&text, label))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn errs(src: &str) -> Vec<String> {
        parse_str(src, "t").errors
    }

    #[test]
    fn balanced_is_clean() {
        assert!(errs("<h2>a</h2>\n<div><p>b</p></div>").is_empty());
    }

    #[test]
    fn reports_the_opening_line() {
        let e = errs("<h2>a</h2>\n<div>\n<b>x</p>");
        assert_eq!(e.len(), 2, "{e:?}");
        assert!(e[0].contains(":3: </p> closes <b> opened on line 3"), "{e:?}");
        assert!(e[1].contains(":2: <div> never closed"), "{e:?}");
    }

    #[test]
    fn void_elements_never_enter_the_stack() {
        assert!(errs("<img src=x><br><hr>").is_empty());
    }

    #[test]
    fn self_closing_is_a_start_and_an_end() {
        assert!(errs("<div/>\n<p>after</p>").is_empty());
    }

    #[test]
    fn tags_inside_a_comment_are_not_markup() {
        assert!(errs("<!-- <div> unclosed -->\n<p>ok</p>").is_empty());
    }

    // NOTE: these cases are also asserted in tests/selftest.py, which drives the
    // real binary. That matters because the first version of this parser passed
    // these in-process while the binary was wrong — the difference was which
    // string the two paths tokenized, not the offset arithmetic.
    #[test]
    fn emoji_reports_its_own_line_not_the_data_run() {
        // The reference implementation reports the line the data run *began*,
        // because its parser hands `getpos()` back when the run starts. Here the
        // run starts on line 1 and the emoji is on line 3.
        //
        // The engine reports line 3, which is the line to actually look at.
        // That is a deliberate divergence, and it is the better answer: a
        // finding that names the right row is worth more than one that agrees
        // with the older implementation.
        let e = errs("<p>\ntext\nfire 🎉\n</p>");
        assert_eq!(e.len(), 1, "{e:?}");
        assert!(e[0].contains(":3: emoji"), "{e:?}");

        // A blank line must not be miscounted either.
        let e = errs("<h2>a</h2>\n<p>\n\n🎉\n</p>");
        assert_eq!(e.len(), 1, "{e:?}");
        assert!(e[0].contains(":4: emoji"), "{e:?}");
    }

    #[test]
    fn unknown_lang_is_reported_but_known_is_not() {
        assert_eq!(errs("<pre class=code data-lang=dartt>x</pre>").len(), 1);
        assert!(errs("<pre class=code data-lang=python>x</pre>").is_empty());
    }

    #[test]
    fn duplicate_ids_are_reported_once() {
        let e = errs("<p id=a>1</p><p id=a>2</p>");
        assert_eq!(e.len(), 1, "{e:?}");
        assert!(e[0].contains("duplicate id(s) a"), "{e:?}");
    }

    #[test]
    fn anchors_and_links_are_separated() {
        let f = parse_str("<a href=\"#here\">a</a><a href=\"other.html\">b</a>", "t");
        assert_eq!(f.anchors, vec!["#here"]);
        assert_eq!(f.links, vec!["other.html"]);
    }

    #[test]
    fn unbalanced_svg_is_reported() {
        assert!(errs("<svg><path d=\"M0 0\"/></svg>").is_empty());
        // Two findings, not one: </svg> closes <g>, and that leaves <svg> open.
        let e = errs("<svg><g></svg>");
        assert_eq!(e.len(), 2, "{e:?}");
        assert!(e[0].contains("</svg> closes <g>"), "{e:?}");
        assert!(e[1].contains("<svg> never closed"), "{e:?}");
    }

    #[test]
    fn line_numbers_survive_character_references() {
        // `&amp;` is resolved by the tokenizer before we see the text, so the
        // cursor has to skip the source spelling without losing its place.
        let e = errs("<h2>a</h2>\n<p>one &amp; two</p>\n<p>🎉</p>");
        assert_eq!(e.len(), 1, "{e:?}");
        assert!(e[0].contains(":3: emoji"), "{e:?}");
    }
}
/// Parse a source string and return only the findings. This is the shape the
/// differential test consumes.
pub fn parse(text: &str, label: &str) -> Findings {
    parse_str(text, label)
}
