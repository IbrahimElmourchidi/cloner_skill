//! Renders every page from `config.toml` + `pages.toml` + `content/NN.html`.
//!
//! Lesson pages and appendix pages share one shell on purpose: a fix to the
//! shell then reaches both, instead of leaving two templates to drift.

use crate::model::{Config, Page, Pages};
use crate::util::{escape, unescape};
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

pub struct Site<'a> {
    pub cfg: &'a Config,
    pub pages: &'a Pages,
    /// `_build/`
    pub build: PathBuf,
    /// the site directory — the parent of `_build/`
    pub root: PathBuf,
}

impl<'a> Site<'a> {
    pub fn content(&self) -> PathBuf {
        self.build.join("content")
    }
}

fn sidebar(site: &Site, active_n: Option<usize>, active_slug: Option<&str>) -> String {
    let mut out: Vec<String> = Vec::new();
    let mut phase: Option<&str> = None;

    for p in &site.pages.page {
        let ph = site.pages.phase_of(site.cfg, p);
        if phase != Some(ph) {
            phase = Some(ph);
            out.push(format!("  <h4>{}</h4>", unescape(ph)));
        }
        let cur = if Some(p.n) == active_n { " aria-current=\"page\"" } else { "" };
        out.push(format!(
            "    <li><a href=\"{}.html\" data-page=\"step-{}\"{}>\
             <span class=\"n\">{:02}</span><span>{}</span>\
             <span class=\"tick\" hidden>read</span></a></li>",
            escape(&p.slug),
            p.n,
            cur,
            p.n,
            escape(&p.nav),
        ));
    }

    if !site.pages.appendix.is_empty() {
        out.push(format!("  <h4>{}</h4>", unescape(&site.cfg.appendix_phase)));
        for (i, a) in site.pages.appendix.iter().enumerate() {
            let cur = if Some(a.slug.as_str()) == active_slug { " aria-current=\"page\"" } else { "" };
            // `cur` is a sibling attribute, not part of the data-page value.
            // Putting it inside the quotes produced
            // data-page="appendix aria-current="page"", which the browser
            // parses as one attribute whose value is `appendix aria-current=`
            // — so the current-page highlight never applied and read-tracking
            // keyed on the mangled string.
            out.push(format!(
                "    <li><a href=\"{}.html\" data-page=\"appendix\"{}>\
                 <span class=\"n\">A{}</span><span>{}</span>\
                 <span class=\"tick\" hidden>read</span></a></li>",
                escape(&a.slug),
                cur,
                i + 1,
                escape(&a.nav),
            ));
        }
    }

    if let Some(note) = site.cfg.sidebar_note() {
        out.push(format!("  <div class=\"note-box\"><p>{note}</p></div>"));
    }
    out.join("\n")
}

/// The panel above the lesson body: what this step writes, and why it exists.
fn steptop(site: &Site, p: &Page) -> String {
    let mut body = String::new();
    if let Some(cmd) = p.cmd.as_deref().filter(|c| !c.is_empty()) {
        let esc = escape(cmd);
        if esc.starts_with('$') {
            body.push_str("<pre class=\"cmd\"><code><span class=\"c-prompt\">$</span> ");
            body.push_str(esc[1..].trim());
            body.push_str("</code></pre>");
        } else {
            body.push_str("<pre class=\"cmd\"><code>");
            body.push_str(&esc);
            body.push_str("</code></pre>");
        }
    }
    if let Some(path) = p.path.as_deref().filter(|p| !p.is_empty()) {
        body.push_str(&format!("<div class=\"srcpath\">writes to <b>{}</b></div>", escape(path)));
    } else if body.is_empty() {
        body.push_str("<div class=\"srcpath\">This lesson writes <b>no file</b>.</div>");
    }
    if let Some(why) = p.why.as_deref().filter(|w| !w.is_empty()) {
        // `why` is prose, not a path: entities in it are intentional, so it is
        // inserted raw exactly as the file contents are.
        body.push_str(&format!("<div class=\"why\"><b>Why it exists.</b> {why}</div>"));
    }
    let _ = site;
    body
}

fn navbottom(site: &Site, idx: usize) -> String {
    let pages = &site.pages.page;
    let mut parts: Vec<String> = Vec::new();
    if idx > 0 {
        let q = &pages[idx - 1];
        parts.push(format!(
            "    <a class=\"pv\" href=\"{}.html\"><span class=\"lbl\">Previous</span>Step {} &middot; {}</a>",
            escape(&q.slug), q.n, escape(&q.nav)
        ));
    } else {
        parts.push("    <a class=\"pv\" href=\"index.html\"><span class=\"lbl\">Back</span>Overview</a>".into());
    }
    if idx + 1 < pages.len() {
        let q = &pages[idx + 1];
        parts.push(format!(
            "    <a class=\"nx\" href=\"{}.html\"><span class=\"lbl\">Next</span>Step {} &middot; {}</a>",
            escape(&q.slug), q.n, escape(&q.nav)
        ));
    }
    parts.join("\n")
}

fn navbottom_appendix(site: &Site, idx: usize) -> String {
    let ap = &site.pages.appendix;
    let mut parts: Vec<String> = Vec::new();
    if idx > 0 {
        let q = &ap[idx - 1];
        parts.push(format!(
            "    <a class=\"pv\" href=\"{}.html\"><span class=\"lbl\">Previous</span>A{} &middot; {}</a>",
            escape(&q.slug), idx, escape(&q.nav)
        ));
    } else {
        parts.push("    <a class=\"pv\" href=\"index.html\"><span class=\"lbl\">Back</span>Overview</a>".into());
    }
    if idx + 1 < ap.len() {
        let q = &ap[idx + 1];
        parts.push(format!(
            "    <a class=\"nx\" href=\"{}.html\"><span class=\"lbl\">Next</span>A{} &middot; {}</a>",
            escape(&q.slug), idx + 2, escape(&q.nav)
        ));
    }
    parts.join("\n")
}

fn footer_html(cfg: &Config) -> String {
    let mut lines: Vec<String> = Vec::new();
    if let Some(root) = cfg.source_root.as_deref().filter(|r| !r.is_empty()) {
        lines.push(format!(
            "    <p><b>Sources.</b> Every path on this page was read from the \
             repository at <code>{}</code>.</p>",
            escape(root)
        ));
    }
    for line in &cfg.footer_notes {
        lines.push(format!("    <p>{line}</p>"));
    }
    lines.join("\n")
}

#[allow(clippy::too_many_arguments)]
fn shell(
    site: &Site,
    doctitle: String,
    n: usize,
    h1: &str,
    lead: &str,
    phase: &str,
    sidebar_html: String,
    readkey: String,
    pill: String,
    steptop_html: &str,
    content: String,
    navbottom: String,
    footer: String,
) -> String {
    let cfg = site.cfg;
    format!(
        "<!doctype html>\n\
<html lang=\"en\" dir=\"ltr\">\n\
<head>\n\
<meta charset=\"utf-8\">\n\
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n\
<title>{doctitle}</title>\n\
<link rel=\"stylesheet\" href=\"assets/style.css\">\n\
</head>\n\
<body data-page=\"step-{n}\"{readkey}>\n\
<div class=\"shell\">\n\
<nav class=\"side\" aria-label=\"Steps\">\n  \
<a class=\"brand\" href=\"index.html\">{brand}<small>{tagline}</small></a>\n  \
<ol>\n{sidebar}\n  </ol>\n\
</nav>\n\
<main>\n  \
<div class=\"eyebrow\">\n    \
<span class=\"ep\">{eyebrow}</span>\n    \
{pill}\n    \
<span>{phase}</span>\n  \
</div>\n\
  <h1>{h1}</h1>\n\
  <p class=\"lede\">{lead}</p>\n\n  \
<div class=\"steptop\">\n    \
<div class=\"what\">{what_label}</div>\n{steptop}\n  \
</div>\n\n{content}\n\n  \
<div class=\"nav-bottom\">\n{navbottom}\n  \
</div>\n\n  \
<footer>\n{footer}\n  \
</footer>\n\
</main>\n\
</div>\n\
<script src=\"assets/app.js\"></script>\n\
</body>\n\
</html>\n",
        doctitle = doctitle,
        n = n,
        readkey = readkey,
        brand = escape(&cfg.name),
        tagline = escape(&cfg.tagline),
        sidebar = sidebar_html,
        eyebrow = escape(&cfg.eyebrow),
        pill = pill,
        phase = phase,
        h1 = escape(h1),
        lead = escape(lead),
        what_label = escape(&cfg.what_label),
        steptop = steptop_html,
        content = content,
        navbottom = navbottom,
        footer = footer,
    )
}

/// Delete generated pages the build no longer produces.
///
/// Without this, renaming or dropping a lesson leaves its HTML behind, and the
/// validator then fails with prev/next chains pointing at pages that are no
/// longer in the order — an error that reads like a generator bug.
///
/// Only the two generated filename patterns are touched, so a hand-written
/// page in the same directory survives.
fn prune(root: &Path, written: &BTreeSet<String>) -> Vec<String> {
    let mut removed = Vec::new();
    let Ok(entries) = std::fs::read_dir(root) else { return removed };
    for e in entries.flatten() {
        let name = e.file_name().to_string_lossy().into_owned();
        if written.contains(&name) || name == "index.html" || !name.ends_with(".html") {
            continue;
        }
        let generated = (name.starts_with(|c: char| c.is_ascii_digit()) && name.contains('-'))
            || name.starts_with("appendix-");
        if generated && std::fs::remove_file(e.path()).is_ok() {
            removed.push(name);
        }
    }
    removed.sort();
    removed
}

pub fn build(site: &Site) -> Result<(), String> {
    let cfg = site.cfg;
    let brand = escape(&cfg.name);
    let readkey = match cfg.read_key.as_deref().filter(|k| !k.is_empty()) {
        Some(k) => format!(" data-read-key=\"{}\"", escape(k)),
        None => String::new(),
    };
    let total = site.pages.total();
    let mut written: BTreeSet<String> = BTreeSet::new();

    for (idx, p) in site.pages.page.iter().enumerate() {
        let src = site.content().join(format!("{:02}.html", p.n));
        let content = std::fs::read_to_string(&src)
            .map_err(|_| format!("missing content fragment: {}", src.display()))?;
        let page = shell(
            site,
            format!("{brand} · Step {} · {}", p.n, p.nav),
            p.n,
            &p.h1,
            &p.lead,
            &unescape(site.pages.phase_of(cfg, p)),
            sidebar(site, Some(p.n), None),
            readkey.clone(),
            format!("<span class=\"step-pill\">Step {} of {total}</span>", p.n),
            &steptop(site, p),
            content,
            navbottom(site, idx),
            footer_html(cfg),
        );
        let out = site.root.join(format!("{}.html", p.slug));
        std::fs::write(&out, page).map_err(|e| format!("cannot write {}: {e}", out.display()))?;
        written.insert(format!("{}.html", p.slug));
    }

    for (i, a) in site.pages.appendix.iter().enumerate() {
        let src = site.content().join(format!("{}.html", a.slug));
        let content = std::fs::read_to_string(&src)
            .map_err(|_| format!("missing appendix fragment: {}", src.display()))?;
        let page = shell(
            site,
            format!("{brand} · Appendix · {}", a.nav),
            i + 1,
            &a.h1,
            &a.lead,
            &unescape(cfg.appendix_eyebrow()),
            sidebar(site, None, Some(&a.slug)),
            readkey.clone(),
            "<span class=\"step-pill\">Appendix · not in the lesson order</span>".into(),
            "",
            content,
            navbottom_appendix(site, i),
            footer_html(cfg),
        );
        let out = site.root.join(format!("{}.html", a.slug));
        std::fs::write(&out, page).map_err(|e| format!("cannot write {}: {e}", out.display()))?;
        written.insert(format!("{}.html", a.slug));
    }

    let removed = prune(&site.root, &written);
    if !removed.is_empty() {
        println!(
            "pruned {} stale page(s): {}",
            removed.len(),
            removed.join(", ")
        );
    }
    println!("built {} pages + {} appendix", site.pages.page.len(), site.pages.appendix.len());
    Ok(())
}