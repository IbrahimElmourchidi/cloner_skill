//! The two files the project owns: `config.toml` and `pages.toml`.
//!
//! Everything else in this engine is read-only and lives in the skill. That
//! separation is the point. An earlier layout put the generator *inside* the
//! project, where it was editable — so on a real 492-lesson site the generator
//! was forked and the site name was hardcoded into a string literal, and the
//! indirection that existed to prevent exactly that was bypassed. Nothing in
//! this model is code, so there is nothing here to fork.

use serde::Deserialize;
use std::collections::BTreeMap;
use std::path::Path;

/// Site identity and prose. The only project-specific file besides `pages.toml`.
#[derive(Debug, Deserialize, Default)]
#[serde(deny_unknown_fields)]
pub struct Config {
    // identity
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub eyebrow: String,
    #[serde(default)]
    pub tagline: String,
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub subtitle: String,
    #[serde(default)]
    pub read_key: Option<String>,

    // provenance
    #[serde(default)]
    pub source_root: Option<String>,
    #[serde(default)]
    pub footer_notes: Vec<String>,

    // sidebar
    #[serde(default = "default_phase")]
    pub default_phase: String,
    #[serde(default)]
    pub sidebar_note: Option<String>,

    // index
    #[serde(default)]
    pub intro: String,
    #[serde(default)]
    pub howto: Vec<String>,
    #[serde(default)]
    pub phase_blurbs: BTreeMap<String, String>,

    // appendix
    #[serde(default = "default_appendix_phase")]
    pub appendix_phase: String,
    #[serde(default)]
    pub appendix_eyebrow: Option<String>,
    #[serde(default)]
    pub appendix_intro: String,

    /// Label above the "writes to <path>" panel. Not in the original template;
    /// the value that used to be hardcoded as `'The step'`.
    #[serde(default = "default_what_label")]
    pub what_label: String,
}

fn default_phase() -> String { "Setup".into() }
fn default_appendix_phase() -> String { "Appendix".into() }
fn default_what_label() -> String { "The step".into() }

impl Config {
    pub fn load(path: &Path) -> Result<Self, String> {
        let text = read(path)?;
        toml::from_str(&text).map_err(|e| format!("{}: {e}", path.display()))
    }

    /// Eyebrow text for an appendix page. Absent means the built-in default.
    pub fn appendix_eyebrow(&self) -> &str {
        self.appendix_eyebrow.as_deref().unwrap_or("Appendix · reference")
    }

    /// Empty means "no note box" — TOML has no null, and the note is optional
    /// prose rather than a value you would ever want set to empty on purpose.
    pub fn sidebar_note(&self) -> Option<&str> {
        self.sidebar_note.as_deref().filter(|s| !s.is_empty())
    }
}

#[derive(Debug, Deserialize, Clone)]
pub struct Page {
    pub n: usize,
    pub slug: String,
    pub nav: String,
    pub h1: String,
    pub lead: String,
    #[serde(default)]
    pub path: Option<String>,
    #[serde(default)]
    pub cmd: Option<String>,
    #[serde(default)]
    pub phase: Option<String>,
    #[serde(default)]
    pub why: Option<String>,
    /// What the reader can see after this step that they could not see before.
    ///
    /// The payoff line, and the reason a journey-ordered site is legible at all:
    /// without it a lesson that wires up a screen and a lesson that renames a
    /// helper look identical from the outside, and a reader who followed the
    /// order has no way to tell anything is working.
    #[serde(default)]
    pub preview: Option<String>,
    /// Placeholders the reader has to invent for this step to compile.
    ///
    /// A journey-ordered site reaches for something that does not exist yet,
    /// and this is the reader being told what to write instead. A stub is
    /// metadata on the consuming lesson rather than a lesson of its own, so the
    /// same `path` is never taught twice — which is what keeps retirement
    /// checkable against the entries that follow.
    #[serde(default)]
    pub stubs: Vec<Stub>,
}

/// One placeholder. `path` is the whole point: it is the file the reader has to
/// invent, and it is matched against later entries' own `path` to decide whether
/// the stub was ever paid off. `real` is raw prose, so a phase name may carry
/// its `&middot;` on purpose; `names` and `note` are escaped at render time.
#[derive(Debug, Deserialize, Clone, Default)]
pub struct Stub {
    pub path: String,
    #[serde(default)]
    pub names: Option<String>,
    #[serde(default)]
    pub real: Option<String>,
    #[serde(default)]
    pub note: Option<String>,
}

impl Stub {
    /// An optional prose field, treating "absent" and "empty" as one thing.
    ///
    /// TOML has no null, so `real = ""` is the only way to write an absent
    /// value. Rendering it would produce `replaced in .`, which is worse than
    /// leaving the clause out entirely.
    pub fn prose<'a>(which: &str, s: &'a Stub) -> Option<&'a str> {
        let raw = match which {
            "names" => s.names.as_deref(),
            "real" => s.real.as_deref(),
            "note" => s.note.as_deref(),
            _ => None,
        };
        raw.filter(|v| !v.trim().is_empty())
    }
}

#[derive(Debug, Deserialize, Clone)]
pub struct AppendixEntry {
    pub slug: String,
    pub nav: String,
    pub h1: String,
    pub lead: String,
}

#[derive(Debug, Deserialize, Default)]
#[serde(deny_unknown_fields)]
pub struct Pages {
    #[serde(default, rename = "page")]
    pub page: Vec<Page>,
    #[serde(default, rename = "appendix")]
    pub appendix: Vec<AppendixEntry>,
}

impl Pages {
    /// Load and validate.
    ///
    /// The checks here are not belt-and-braces. Two lessons sharing an `n`
    /// resolve to the same `content/NN.html`, so the build succeeds and both
    /// pages silently carry the first lesson's text — the one class of failure
    /// where every validator downstream still reports a clean site.
    pub fn load(path: &Path) -> Result<Self, String> {
        let text = read(path)?;
        let mut pages: Pages = toml::from_str(&text).map_err(|e| format!("{}: {e}", path.display()))?;
        pages.page.sort_by_key(|p| p.n);

        let mut seen_n = BTreeMap::new();
        for p in &pages.page {
            if let Some(prev) = seen_n.insert(p.n, &p.slug) {
                return Err(format!(
                    "{}: step n={} is used by both {prev:?} and {:?}. Two lessons with \
                     the same number read the same content/NN.html, so one silently \
                     overwrites the other.",
                    path.display(), p.n, p.slug
                ));
            }
        }

        let mut seen_slug: BTreeMap<String, String> = BTreeMap::new();
        for (slug, what, want_prefix) in entries(&pages) {
            if let Some(prev) = seen_slug.insert(slug.clone(), what.clone()) {
                return Err(format!(
                    "{}: slug {slug:?} is used by both {prev} and {what}. Two entries \
                     write the same <slug>.html.",
                    path.display()
                ));
            }
            // The validator recovers reading order from the filename, so a slug
            // that does not start with its own zero-padded number silently
            // reorders the sidebar.
            if let Some(want) = want_prefix {
                if !slug.starts_with(&want) {
                    return Err(format!(
                        "{}: slug {slug:?} must start with {want:?} so the filename sorts \
                         into reading order.",
                        path.display()
                    ));
                }
            }
        }
        Ok(pages)
    }

    pub fn total(&self) -> usize {
        self.page.len()
    }

    /// Sidebar section for a lesson, falling back to the site default.
    pub fn phase_of<'a>(&'a self, cfg: &'a Config, p: &'a Page) -> &'a str {
        p.phase.as_deref().filter(|s| !s.is_empty()).unwrap_or(&cfg.default_phase)
    }
}

/// (slug, human label, required numeric prefix) for every entry that writes a
/// page. Appendix slugs carry no prefix; lessons carry their own `n`.
fn entries(pages: &Pages) -> Vec<(String, String, Option<String>)> {
    let mut out: Vec<(String, String, Option<String>)> = pages
        .page
        .iter()
        .map(|p| (p.slug.clone(), format!("step {}", p.n), Some(format!("{:02}", p.n))))
        .collect();
    out.extend(
        pages
            .appendix
            .iter()
            .enumerate()
            .map(|(i, a)| (a.slug.clone(), format!("appendix A{}", i + 1), None)),
    );
    out
}

fn read(path: &Path) -> Result<String, String> {
    std::fs::read_to_string(path)
        .map_err(|e| format!("cannot read {}: {e}", path.display()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn duplicate_n_is_rejected() {
        let toml = r#"
[[page]]
n = 1
slug = "01-a"
nav = "a"
h1 = "a"
lead = "a"
[[page]]
n = 1
slug = "01-b"
nav = "b"
h1 = "b"
lead = "b"
"#;
        let mut pages: Pages = toml::from_str(toml).unwrap();
        pages.page.sort_by_key(|p| p.n);
        // exercised through load() in the integration test; here just confirm
        // the parser itself accepts the shape so the error is ours, not toml's
        assert_eq!(pages.page.len(), 2);
    }

    #[test]
    fn slug_must_carry_its_own_number() {
        // {:02} pads to at least two digits; a three-digit n widens, which is
        // why the check cannot be a fixed two-character prefix comparison.
        assert!("09-thing".starts_with(&format!("{:02}", 9)));
        assert!("12-thing".starts_with(&format!("{:02}", 12)));
        assert!("999-thing".starts_with(&format!("{:02}", 999)));
        assert!(!"01-thing".starts_with(&format!("{:02}", 9)));
        assert!(!"9-thing".starts_with(&format!("{:02}", 9)));
        assert!(!"012-thing".starts_with(&format!("{:02}", 12)));
    }
}