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

/// One row of the menu: a destination, a label, a read-tracking key, a number.
///
/// `page_id` is the read-tracking key (`data-page`). It is deliberately
/// independent of the displayed number so renumbering cannot invalidate a
/// reader's saved progress.
struct MenuItem<'a> {
    href: &'a str,
    nav: &'a str,
    page_id: String,
    number: String,
}

/// A run of consecutive items that share a heading, rendered as one
/// collapsible group.
///
/// The `<summary>` is the whole interaction: native, keyboard-reachable, and it
/// reports its own open/closed state to assistive technology. The heading this
/// replaced was an `<h4>` written *between* `<li>` elements, which is invalid
/// HTML inside `<ol>` and only ever worked because the CSS hid the bullets.
struct MenuGroup<'a> {
    title: String,
    kind: &'static str,
    items: Vec<MenuItem<'a>>,
}

impl<'a> MenuGroup<'a> {
    /// The range this group covers, shown in its summary: `21&ndash;52`.
    ///
    /// Derived from the items, so it is right for a group of any size and needs
    /// no bookkeeping when a lesson is inserted.
    fn label(&self) -> String {
        match (self.items.first(), self.items.last()) {
            (None, _) => String::new(),
            (Some(a), None) => a.number.clone(),
            (Some(a), Some(b)) => format!("{}&ndash;{}", a.number, b.number),
        }
    }

    fn holds(&self, page_id: &str) -> bool {
        self.items.iter().any(|i| i.page_id == page_id)
    }

    fn render(&self, active: Option<&str>, force_open: bool) -> String {
        let open = if self.holds(active.unwrap_or("")) || force_open {
            " open"
        } else {
            ""
        };
        // `<ol start>` is how the number stays semantic rather than decorative:
        // the list itself knows it begins at the group's first lesson, so the
        // rendered row and the `<ol>` cannot disagree about what "step 21" is.
        let start = match (self.kind, self.items.first()) {
            ("lesson", Some(i)) => match i.number.parse::<usize>() {
                Ok(n) => format!(" start=\"{n}\""),
                Err(_) => String::new(),
            },
            _ => String::new(),
        };
        let rows: Vec<String> = self.items.iter().map(|i| i.render(active)).collect();
        format!(
            "    <details class=\"grp\" data-kind=\"{kind}\"{open}>\n\
             \x20     <summary><span class=\"gt\">{title}</span>\
             <span class=\"gr\">{label}</span></summary>\n\
             \x20     <ol{start}>\n{rows}\n      </ol>\n\
             \x20   </details>",
            kind = self.kind,
            open = open,
            title = unescape(&self.title).replace('\u{b7}', "&middot;"),
            label = self.label(),
            rows = rows.join("\n"),
        )
    }
}

impl<'a> MenuItem<'a> {
    fn render(&self, active: Option<&str>) -> String {
        // `cur` is a sibling attribute, not part of the data-page value.
        // Putting it inside the quotes produced
        // data-page="appendix aria-current="page"", which the browser
        // parses as one attribute whose value is `appendix aria-current=`
        // — so the current-page highlight never applied and read-tracking
        // keyed on the mangled string.
        let cur = if Some(self.page_id.as_str()) == active {
            " aria-current=\"page\""
        } else {
            ""
        };
        format!(
            "      <li><a href=\"{href}.html\" data-page=\"{page_id}\"{cur}>\
             <span class=\"n\">{number}</span><span class=\"t\">{nav}</span>\
             <span class=\"tick\" hidden>read</span></a></li>",
            href = escape(self.href),
            page_id = self.page_id,
            cur = cur,
            number = self.number,
            nav = escape(self.nav),
        )
    }
}

/// The whole menu as data: groups in reading order, numbers by index.
///
/// Two rules, and everything else falls out of them:
///
///   * A new group starts wherever the phase changes — so grouping is a
///     consequence of the list, not a second list to maintain.
///   * The number is a running counter across *all* groups, not per group, so
///     "step 21" means the same thing in the sidebar, in the filename and in the
///     page's own pill. Inserting a lesson renumbers the rest for free, and no
///     row can disagree with its own file name.
fn build_menu_groups<'a>(site: &'a Site<'a>) -> Vec<MenuGroup<'a>> {
    let cfg = site.cfg;
    let mut groups: Vec<MenuGroup<'a>> = Vec::new();
    for (position, p) in site.pages.page.iter().enumerate() {
        let phase = site.pages.phase_of(cfg, p).to_string();
        let item = MenuItem {
            href: &p.slug,
            nav: &p.nav,
            page_id: format!("step-{}", p.n),
            number: format!("{:02}", position + 1),
        };
        match groups.last_mut() {
            Some(g) if g.title == phase => g.items.push(item),
            _ => groups.push(MenuGroup {
                title: phase,
                kind: "lesson",
                items: vec![item],
            }),
        }
    }

    // The appendix is reference material, not part of the order, so it gets its
    // own group and its own A-numbering rather than continuing the step count.
    if !site.pages.appendix.is_empty() {
        groups.push(MenuGroup {
            title: site.cfg.appendix_phase.clone(),
            kind: "appendix",
            items: site
                .pages
                .appendix
                .iter()
                .enumerate()
                .map(|(i, a)| MenuItem {
                    href: &a.slug,
                    nav: &a.nav,
                    page_id: "appendix".to_string(),
                    number: format!("A{}", i + 1),
                })
                .collect(),
        });
    }
    groups
}

/// The complete `<nav class="side">` element.
fn sidebar(site: &Site, active_n: Option<usize>, active_slug: Option<&str>) -> String {
    let active: Option<String> = match (active_n, active_slug) {
        (Some(n), _) => Some(format!("step-{n}")),
        (None, Some(_)) => Some("appendix".to_string()),
        (None, None) => None,
    };
    let active = active.as_deref();
    let groups = build_menu_groups(site);

    // On the overview nothing is active, so no group would be open and the menu
    // would read as a wall of collapsed headings. Force the first one open
    // instead: enough to show the component works, and the reader has
    // one-click routes to the rest.
    let body: Vec<String> = groups
        .iter()
        .enumerate()
        .map(|(i, g)| g.render(active, active.is_none() && i == 0))
        .collect();

    let note = match site.cfg.sidebar_note() {
        Some(n) => format!("\n  <div class=\"note-box\">\n    <p>{n}</p>\n  </div>"),
        None => String::new(),
    };
    format!(
        "<nav class=\"side\" aria-label=\"Steps\">\n\
         \x20 <a class=\"brand\" href=\"index.html\">{brand}<small>{tagline}</small></a>\n\
         \x20 <div class=\"menu\" data-menu>\n{body}\n  </div>{note}\n\
         </nav>",
        brand = escape(&site.cfg.name),
        tagline = escape(&site.cfg.tagline),
        body = body.join("\n"),
        note = note,
    )
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
{sidebar}\n\
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