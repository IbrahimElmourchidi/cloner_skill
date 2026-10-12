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

/// One open `<table>`, while it is being read.
#[derive(Default)]
struct TableShape {
    /// Column count, taken from the first row. `None` until that row closes.
    cols: Option<usize>,
    /// `(colspan, rowspan)` for each cell of the row currently being read.
    row: Vec<(usize, u32)>,
    /// Per-column countdown of cells still occupying a column from above, via
    /// `rowspan`. One `rowspan="3"` claims ONE column for two further rows.
    pending: Vec<u32>,
    line: u64,
}

impl TableShape {
    fn new(line: u64) -> Self {
        TableShape { line, ..Default::default() }
    }
}

/// Column span of a cell. Absent or unparseable means one, as in a browser.
fn span_of(tag: &Tag, attr: &str) -> usize {
    for a in &tag.attrs {
        if a.name.local.as_ref().eq_ignore_ascii_case(attr) {
            return a
                .value
                .to_string()
                .trim()
                .parse::<usize>()
                .ok()
                .filter(|n| *n > 0)
                .unwrap_or(1);
        }
    }
    1
}

struct Collect {
    where_: String,
    f: Findings,
    /// Open tables, outermost first. A row belongs to the innermost one, so a
    /// table nested inside a cell needs no special handling.
    tables: Vec<TableShape>,
    /// The open `<pre class="code">` block, if any.
    pre: Option<PreBlock>,
    /// `data-lang` seen on the tag currently being read, so the open `<pre>`
    /// can remember it. Attributes are read before the tag opens a block, so
    /// this is set in time; it is cleared on every tag.
    pending_lang: Option<String>,
    /// The original source, searched to find where each text run came from.
    src: String,
    /// How far through `src` we have walked.
    cursor: usize,
    /// Byte offset of every newline, for turning an offset into a line number.
    newlines: Vec<usize>,
}

/// An open `<pre class="code">` block, accumulating brace depth as its source
/// arrives.
struct PreBlock {
    depth: i64,
    line: u64,
    text: String,
    lang: Option<String>,
}

/// Net `{` minus `}` in a run of source, ignoring strings and comments.
///
/// Deliberately crude, and deliberately so in one direction: Dart's string
/// interpolation puts braces back after the string is stripped, so a balanced
/// block can look unbalanced. That costs an author one `// ...` line; the
/// opposite mistake — missing a block that stops mid-class — costs a reader a
/// wrong conclusion. Erring towards reporting is the right way round here.
fn brace_delta(text: &str) -> i64 {
    let mut out = String::with_capacity(text.len());
    let mut chars = text.chars().peekable();
    while let Some(c) = chars.next() {
        match c {
            '/' if chars.peek() == Some(&'/') => {
                for c in chars.by_ref() {
                    if c == '\n' {
                        out.push('\n');
                        break;
                    }
                }
            }
            '/' if chars.peek() == Some(&'*') => {
                chars.next();
                let mut prev = '\0';
                for c in chars.by_ref() {
                    if prev == '*' && c == '/' {
                        break;
                    }
                    prev = c;
                    if c == '\n' {
                        out.push('\n');
                    }
                }
            }
            // Single- or double-quoted: drop the contents, keeping newlines so
            // nothing downstream depends on the collapsed length.
            q @ ('\'' | '"') => {
                out.push(' ');
                let mut escaped = false;
                for c in chars.by_ref() {
                    if c == '\n' {
                        out.push('\n');
                    }
                    if escaped {
                        escaped = false;
                    } else if c == '\\' {
                        escaped = true;
                    } else if c == q {
                        break;
                    }
                }
            }
            _ => out.push(c),
        }
    }
    let opens = out.matches('{').count() as i64;
    let closes = out.matches('}').count() as i64;
    opens - closes
}

/// True when the block marks its own gap with a line that is only an ellipsis,
/// in any of the comment spellings an author reaches for.
fn has_elision(text: &str) -> bool {
    text.lines().any(|line| {
        let s = line.trim();
        let s = s
            .trim_start_matches("///")
            .trim_start_matches("//")
            .trim_start_matches("/*")
            .trim_start_matches('*')
            .trim()
            .trim_end_matches("*/")
            .trim();
        matches!(s, "..." | "…" | "omitted" | "rest of" | "and more")
    })
}

/// True when a first line names a source file: `// lib/x.dart`, `# x.sql`,
/// `x.arb`. Returns the line, so the finding can name what it found.
fn path_header(line: &str) -> Option<&str> {
    let s = line.trim();
    let s = s
        .strip_prefix("//")
        .or_else(|| s.strip_prefix('#'))
        .unwrap_or(s)
        .trim_start();
    // Only an extension is enough: `dart`, `arb`, `yaml`, `yml`, `sql`,
    // `json`, `md` are the ones a fragment carries.
    let ext = s.rsplit_once('.')?.1;
    let known = matches!(
        ext,
        "dart" | "arb" | "yaml" | "yml" | "sql" | "json" | "md"
    );
    if !known {
        return None;
    }
    // The stem must not be empty, and must not contain whitespace — a sentence
    // that happens to end in ".md" is prose, not a header.
    let stem = &s[..s.len() - ext.len() - 1];
    if stem.is_empty() || stem.contains(char::is_whitespace) {
        return None;
    }
    Some(s)
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
                self.pending_lang = Some(val.clone());
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
        if !is_start && (name == "pre" || name == "code") && self.pre.is_some() {
            self.close_pre();
        }
        if is_start && (name == "pre" || name == "code") && self.pre.is_none() {
            self.pre = Some(PreBlock {
                depth: 0,
                line,
                text: String::new(),
                lang: self.pending_lang.take(),
            });
        }
        // Cleared unconditionally: a nested or malformed `<pre>` that never
        // reaches the line above must not leave its language behind for the
        // next block to inherit.
        self.pending_lang = None;
        self.table_shape(&name, tag, is_start, line);
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

    // ---- partial code blocks ----------------------------------------------
    //
    // A block that leaves a brace open has either been cut off or is a
    // deliberate fragment, and the reader cannot tell which — so the block has
    // to say. One `// ...` line is the whole cost of that, and it is the only
    // thing standing between "this is the class" and "here is part of it".
    //
    // Reported, never repaired. Where an excerpt should end is an authoring
    // judgement: sometimes the honest fix is the marker, sometimes it is the
    // rest of the class, and only the author knows which.
    fn close_pre(&mut self) {
        let Some(p) = self.pre.take() else { return };
        if p.depth > 0 && !has_elision(&p.text) {
            self.f.errors.push(format!(
                "{}:{}: <pre class=\"code\"> ends with {} unclosed brace{} and no \
                 elision marker — a reader cannot tell a fragment from the whole \
                 file. Add a `// ...` line, or show the rest of the declaration.",
                self.where_,
                p.line,
                p.depth,
                if p.depth == 1 { "" } else { "s" },
            ));
        }
        self.check_stub(&p);
    }

    // ---- stub code blocks --------------------------------------------------
    //
    // A block whose entire body is its own path comment. Authoring a "The
    // file" section is two steps — emit the path comment, then fill the body
    // with the code — and the second is easy to miss. When it is, every other
    // check still passes: the nesting is correct, the language is known, and
    // the page shows an empty container where it promised the file.
    fn check_stub(&mut self, p: &PreBlock) {
        // `text` and `bash` blocks are commentary inside a terminal
        // transcript, or a cross-reference caption naming another file.
        if matches!(p.lang.as_deref(), Some("text") | Some("bash")) {
            return;
        }
        let mut lines = p.text.lines().filter(|l| !l.trim().is_empty());
        let (Some(head), None) = (lines.next(), lines.next()) else {
            return;
        };
        if path_header(head).is_none() {
            return;
        }
        self.f.errors.push(format!(
            "{}:{}: <pre class=\"code\"> holds only its path header ({}) — fill it \
             with the file, or delete the block",
            self.where_,
            p.line,
            head.trim(),
        ));
    }

    // ---- table shape -------------------------------------------------------
    //
    // Two independent faults produce the same symptom and need different fixes,
    // so they are reported separately rather than as one "bad row" count:
    //
    //   nested  <tr><td><td>x</td></tr>  — a cell inside a cell. Delete the
    //          inner tag; the outer one was never meant to be there. Tag
    //          balance cannot see this: it is two opens and two closes.
    //   arity   <tr><td>x</td></tr>       — a genuine cell-count mismatch. The
    //          author has to decide what belongs in the missing cell, so this
    //          is never auto-fixable and never should be.
    fn table_shape(&mut self, name: &str, tag: &Tag, is_start: bool, line: u64) {
        if !is_start {
            self.end_table_shape(name, line);
            return;
        }
        match name {
            "table" => self.tables.push(TableShape::new(line)),
            "tr" => {
                if let Some(t) = self.tables.last_mut() {
                    t.row.clear();
                }
            }
            "td" | "th" => {
                // The stack is appended after this runs, so its top is the
                // enclosing element — which is what tells us the cell is nested.
                if let Some((open, open_line)) = self.f.stack.last() {
                    if open == "td" || open == "th" {
                        self.f.errors.push(format!(
                            "{}:{line}: <{name}> inside <{open}> on line {open_line} — \
                             one cell is nested in another; delete the inner tag",
                            self.where_
                        ));
                    }
                }
                if let Some(t) = self.tables.last_mut() {
                    t.row.push((span_of(tag, "colspan"), span_of(tag, "rowspan") as u32));
                }
            }
            _ => {}
        }
    }

    fn end_table_shape(&mut self, name: &str, line: u64) {
        let Some(t) = self.tables.last_mut() else { return };
        match name {
            "tr" if !t.row.is_empty() => {
                // Columns claimed by a rowspan from above still count towards
                // this row's width — they are simply not written twice.
                let span: usize = t.row.iter().map(|(cs, _)| *cs).sum::<usize>() + t.pending.len();
                match t.cols {
                    // The first row of a table defines its arity. Looking for the
                    // header row by <th> instead would miss a table with no
                    // thead, which is legal and common.
                    None => t.cols = Some(span),
                    Some(cols) if span != cols => {
                        let (w, n, cols_s) = (self.where_.clone(), span, cols);
                        self.f.errors.push(format!(
                            "{}:{}: <tr> has {n} cell{s} but the first row of \
                             its table declares {cols_s} (table opened line {opened})",
                            w,
                            line,
                            s = if n == 1 { "" } else { "s" },
                            opened = t.line,
                        ));
                    }
                    Some(_) => {}
                }
                // Age the claims already in flight, then add this row's own.
                // The new ones start at rowspan-1: the row declaring them has
                // already been counted.
                let aged: Vec<u32> = t.pending.iter().filter(|p| **p > 1).map(|p| p - 1).collect();
                let fresh: Vec<u32> = t
                    .row
                    .iter()
                    .map(|(_, rs)| *rs)
                    .filter(|rs| *rs > 1)
                    .map(|rs| rs - 1)
                    .collect();
                let mut next = fresh;
                next.extend(aged);
                t.pending = next;
                t.row.clear();
            }
            "table" => {
                self.tables.pop();
            }
            _ => {}
        }
    }

    fn text(&mut self, text: &str, token_start: usize) {
        // Only the text between <pre> and <code> is markup-free source, so the
        // brace count is taken here rather than across the whole document.
        if let Some(p) = self.pre.as_mut() {
            p.depth += brace_delta(text);
            p.text.push_str(text);
        }
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
        tables: Vec::new(),
        pre: None,
        pending_lang: None,
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
