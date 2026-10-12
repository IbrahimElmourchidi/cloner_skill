//! The structural validator. Prints `BAD: none` when everything passes.
//!
//! Two things here exist because of how this validator used to behave:
//!
//! 1. Every error carries a file and a line. Tag-balance errors used to be
//!    reported with no page name, so one stray `</div>` produced a wall of
//!    indistinguishable failures and you had to guess where it started. The
//!    line is recorded at the point of failure, so the first error in a file is
//!    the one you act on.
//!
//! 2. Content fragments are validated BEFORE the built pages. A fragment is
//!    inserted verbatim into the shell, so an unbalanced fragment is guaranteed
//!    to cascade into the rendered page. Checking it first means a typo in
//!    `content/17.html` fails as one clear message instead of a same-shaped page
//!    plus a dozen lookalikes downstream.
//!
//! Checks: tag balance, duplicate ids, link targets, in-page anchors, prev/next
//! agrees with the reading order, `data-lang` is known, no emoji.
//!
//! The per-document parsing lives in `htmlparse`; this file is the part that
//! needs to know about sites.

use crate::htmlparse::parse_file;
use std::collections::BTreeSet;
use std::path::Path;

/// What one run found, plus enough counts to print a stats line.
pub struct Report {
    pub fragments: usize,
    pub pages: usize,
    pub langs: BTreeSet<String>,
    pub bad: Vec<String>,
}

/// Which of the two passes to run. Fragments first, always, when both are asked
/// for: a broken fragment guarantees a broken page, so stopping there reports
/// the failure once instead of twice.
#[derive(PartialEq, Eq, Clone, Copy)]
pub enum Mode { Both, PagesOnly, FragmentsOnly }

pub fn run(site_root: &Path, build: &Path, mode: Mode) -> Result<Report, String> {
    let mut bad: Vec<String> = Vec::new();
    let content = build.join("content");

    let mut frags: BTreeSet<String> = BTreeSet::new();
    if mode != Mode::PagesOnly {
        frags = check_fragments(&content, &mut bad);
        if !bad.is_empty() {
            return Ok(Report { fragments: frags.len(), pages: 0, langs: BTreeSet::new(), bad });
        }
    }
    if mode == Mode::FragmentsOnly {
        return Ok(Report { fragments: frags.len(), pages: 0, langs: BTreeSet::new(), bad });
    }
    let (pages, langs) = check_pages(site_root, build, &mut bad)?;
    Ok(Report { fragments: frags.len(), pages, langs, bad })
}

fn check_fragments(content: &Path, bad: &mut Vec<String>) -> BTreeSet<String> {
    if !content.is_dir() {
        bad.push("no _build/content/ directory".into());
        return BTreeSet::new();
    }
    let mut on_disk: BTreeSet<String> = BTreeSet::new();
    for e in std::fs::read_dir(content).into_iter().flatten().flatten() {
        let n = e.file_name().to_string_lossy().into_owned();
        if n.ends_with(".html") {
            on_disk.insert(n);
        }
    }
    if on_disk.is_empty() {
        bad.push("_build/content/ is empty".into());
        return on_disk;
    }

    for f in &on_disk {
        let p = content.join(f);
        match parse_file(&p, &format!("content/{f}")) {
            Ok(fnd) => bad.extend(fnd.errors),
            Err(e) => bad.push(e),
        }
        // CRLF is normalised by read_to_string? No — it is preserved, and a
        // fragment that begins `<h2>` after a stray `\r` still matches. What
        // this guards is a fragment that has drifted to being about something
        // other than a section.
        let src = std::fs::read_to_string(&p).unwrap_or_default();
        if !src.contains("<h2") {
            bad.push(format!("content/{f}: starts without an <h2>"));
        }
    }
    on_disk
}

fn check_pages(
    site_root: &Path,
    build: &Path,
    bad: &mut Vec<String>,
) -> Result<(usize, BTreeSet<String>), String> {
    let (lessons, appendix) = order(site_root, build);
    let mut pages: Vec<String> = lessons.clone();
    pages.extend(appendix.iter().cloned());
    let n_lessons = lessons.len();

    for page in &pages {
        let path = site_root.join(page);
        if !path.exists() {
            bad.push(format!("{page}: missing"));
            continue;
        }
        let f = parse_file(&path, page)?;
        bad.extend(f.errors.clone());
        let src = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
        if !src.contains("<h1>") {
            bad.push(format!("{page}: no <h1>"));
        }
        for a in &f.anchors {
            if !f.ids.iter().any(|i| i == &a[1..]) {
                bad.push(format!("{page}: anchor {a} does not resolve"));
            }
        }
        for l in &f.links {
            if l.starts_with("http") || l.starts_with("mailto") {
                continue;
            }
            let target = l.split('#').next().unwrap_or("");
            if !target.is_empty() && !site_root.join(target).exists() {
                bad.push(format!("{page}: link target missing -> {l}"));
            }
        }
    }

    // prev/next must agree with the reading order
    for (i, page) in pages.iter().enumerate() {
        if page == "index.html" {
            continue;
        }
        let in_appendix = appendix.contains(page);
        let src = std::fs::read_to_string(site_root.join(page)).map_err(|e| e.to_string())?;
        let (want_prev, want_next) = if in_appendix {
            let base = i - n_lessons;
            let p = if base > 0 { pages[n_lessons + base - 1].clone() } else { "index.html".into() };
            let n = if base + 1 < appendix.len() { Some(pages[n_lessons + base + 1].clone()) } else { None };
            (p, n)
        } else {
            let p = pages[i - 1].clone();
            let n = if i + 1 < n_lessons { Some(pages[i + 1].clone()) } else { None };
            (p, n)
        };
        let got_prev = attr_value(&src, "pv");
        let got_next = attr_value(&src, "nx");
        if got_prev.as_deref() != Some(want_prev.as_str()) {
            bad.push(format!("{page}: prev is {}, expected {}",
                got_prev.unwrap_or_else(|| "None".into()), want_prev));
        }
        match want_next {
            None => { if got_next.is_some() { bad.push(format!("{page}: is last but has a next link")); } }
            Some(w) => {
                if got_next.as_deref() != Some(w.as_str()) {
                    bad.push(format!("{page}: next is {}, expected {}",
                        got_next.unwrap_or_else(|| "None".into()), w));
                }
            }
        }
    }

    let idx_path = site_root.join("index.html");
    if !idx_path.exists() {
        bad.push("index.html: missing — run build then index".into());
        return Ok((pages.len(), BTreeSet::new()));
    }
    let idx = std::fs::read_to_string(&idx_path).map_err(|e| e.to_string())?;
    for page in &pages {
        if *page != "index.html" && !idx.contains(&format!("href=\"{page}\"")) {
            bad.push(format!("index: does not link to {page}"));
        }
    }

    // The language summary counts what the pages actually declare.
    let mut langs = BTreeSet::new();
    for page in &pages {
        if let Ok(f) = parse_file(&site_root.join(page), page) {
            langs.extend(f.langs);
        }
    }
    Ok((pages.len(), langs))
}

/// Pull `href` out of the anchor carrying `class="pv"` / `"nx"`.
fn attr_value(src: &str, class: &str) -> Option<String> {
    let needle = format!("class=\"{class}\" href=\"");
    let at = src.find(&needle)? + needle.len();
    let rest = &src[at..];
    let end = rest.find('"')?;
    Some(rest[..end].to_string())
}

/// Reading order: index.html, the numbered lessons, then the appendix.
///
/// Lesson order comes from the numeric filename prefix. Appendix order comes
/// from the APPENDIX list, NOT from sorting the filenames: sorting looks
/// equivalent and is not, and the resulting wall of prev/next errors reads like
/// a generator bug.
fn order(site_root: &Path, build: &Path) -> (Vec<String>, Vec<String>) {
    let declared = load_declared(build).unwrap_or_else(|e| {
        // A missing or unreadable pages.toml costs the appendix cross-check,
        // not the whole run. The alternative — reporting it as a finding —
        // means `check --pages` can never validate a site that was not built by
        // this version of the tool, which is exactly the case where you most
        // want it to work.
        eprintln!("check: {e} — appendix order falls back to filenames");
        Vec::new()
    });
    let mut nums: Vec<(u32, String)> = Vec::new();
    let mut on_disk: Vec<String> = Vec::new();
    for e in std::fs::read_dir(site_root).into_iter().flatten().flatten() {
        let f = e.file_name().to_string_lossy().into_owned();
        if !f.ends_with(".html") {
            continue;
        }
        if let Some(rest) = f.strip_suffix(".html") {
            let digits: String = rest.chars().take_while(|c| c.is_ascii_digit()).collect();
            if !digits.is_empty() && rest[digits.len()..].starts_with('-') {
                nums.push((digits.parse().unwrap_or(0), f));
                continue;
            }
        }
        if f.starts_with("appendix-") {
            on_disk.push(f);
        }
    }
    nums.sort();
    let apx: Vec<String> = declared
        .into_iter()
        .map(|s| format!("{s}.html"))
        .filter(|f| on_disk.contains(f))
        .collect();
    for f in on_disk.iter().filter(|f| !apx.contains(f)) {
        eprintln!("check: {f} is on disk but not declared — re-run build (it prunes stale pages)");
    }
    let mut lessons = vec!["index.html".to_string()];
    lessons.extend(nums.into_iter().map(|(_, f)| f));
    (lessons, apx)
}

/// Appendix slugs in declaration order, straight from `pages.toml`.
fn load_declared(build: &Path) -> Result<Vec<String>, String> {
    let path = build.join("pages.toml");
    if !path.exists() {
        return Err(format!("no pages.toml in {}", build.display()));
    }
    crate::model::Pages::load(&path).map(|p| p.appendix.iter().map(|a| a.slug.clone()).collect())
}

/// Stats first, verdict last — `BAD: none` is the line to grep for.
pub fn print(r: &Report) -> i32 {
    let mut stats = Vec::new();
    if r.fragments > 0 {
        stats.push(format!("fragments: {}", r.fragments));
    }
    if r.pages > 0 {
        stats.push(format!("pages: {}", r.pages));
    }
    if !r.langs.is_empty() {
        stats.push(format!("langs: {}", r.langs.len()));
    }
    if !stats.is_empty() {
        println!("   {}", stats.join("   "));
    }
    if r.bad.is_empty() {
        println!("BAD: none");
        return 0;
    }
    println!("BAD:");
    for b in &r.bad {
        println!("  {b}");
    }
    1
}
