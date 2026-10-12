//! clone-site — builds a step-by-step teaching site from a repository.
//!
//! One HTML page per source file, in dependency order, each carrying the real
//! file contents plus a plain assessment of whether its choices are good ones.
//!
//! The site directory holds only content and data (`config.toml`,
//! `pages.toml`, `content/NN.html`). The engine lives here, in the skill, and
//! is never copied into a project — so there is nothing in a project that can
//! be forked and drift, which is exactly what happened when the generator used
//! to live inside the project's `_build/` directory.

mod build;
mod entities;
mod model;
mod util;

use model::{Config, Pages};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

const VERSION: &str = env!("CARGO_PKG_VERSION");

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let cmd = args.first().map(String::as_str).unwrap_or("help");
    let rest = if args.is_empty() { &[][..] } else { &args[1..] };

    let result = match cmd {
        "build" => run_build(rest),
        "version" | "--version" | "-V" => {
            println!("clone-site {VERSION}");
            Ok(())
        }
        "help" | "--help" | "-h" => {
            print_help();
            Ok(())
        }
        // Hidden. Reads one string per line on stdin, prints escaped and
        // unescaped forms separated by a tab, so escaping can be diffed against
        // a reference implementation instead of eyeballed. Parity is
        // load-bearing here: every page in the site renders through it.
        "__escape-diff" => {
            use std::io::BufRead;
            // main() returns ExitCode, not Result, so `?` is not available here.
            let mut failure = None;
            for line in std::io::stdin().lock().lines() {
                match line {
                    Ok(s) => println!("{}\t{}", util::escape(&s), util::unescape(&s)),
                    Err(e) => {
                        failure = Some(e.to_string());
                        break;
                    }
                }
            }
            match failure {
                Some(e) => Err(e),
                None => Ok(()),
            }
        }
        other => Err(format!(
            "unknown command {other:?} — run `clone-site help` for the list"
        )),
    };

    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(msg) => {
            eprintln!("clone-site: {msg}");
            ExitCode::FAILURE
        }
    }
}

fn print_help() {
    println!(
        "clone-site {VERSION} — build a step-by-step teaching site from a repository\n\
\n  \
Usage: clone-site <command> [options]\n\
\n  \
build <site-dir>      Render every page from the site's data + content\n\
\n\
A site directory is one that contains config.toml and pages.toml, or that has\n\
them in a _build/ subdirectory. Both layouts work.\n\
\n\
Runs on the binary alone: no interpreter, no runtime, no network."
    );
}

/// Find `config.toml` / `pages.toml` for a site directory.
///
/// Two accepted layouts, because the project-facing one is the new default and
/// the other is what a directory scaffolded by an earlier version of this skill
/// looks like:
///
///   docs/site/_build/config.toml   (new — data only)
///   docs/site/config.toml          (also accepted — flatter)
pub struct Layout {
    pub config: PathBuf,
    pub pages: PathBuf,
    pub content: PathBuf,
    pub root: PathBuf,
    pub build: PathBuf,
}

pub fn locate(site_dir: &Path) -> Result<Layout, String> {
    let nested = site_dir.join("_build");
    let base = if nested.join("config.toml").exists() { nested.clone() } else { site_dir.to_path_buf() };
    let root = if base == nested { site_dir.to_path_buf() } else { site_dir.to_path_buf() };
    Ok(Layout {
        config: base.join("config.toml"),
        pages: base.join("pages.toml"),
        content: base.join("content"),
        root,
        build: base,
    })
}

fn load_site(site_dir: &Path) -> Result<(Config, Pages, Layout), String> {
    let layout = locate(site_dir)?;
    if !layout.config.exists() {
        return Err(format!(
            "no config.toml in {} — is this a site directory? \
             Expected {} or {}/_build/config.toml",
            site_dir.display(),
            site_dir.join("config.toml").display(),
            site_dir.display()
        ));
    }
    if !layout.pages.exists() {
        return Err(format!(
            "no pages.toml in {} — every lesson needs an entry, even an empty list",
            layout.build.display()
        ));
    }
    let cfg = Config::load(&layout.config)?;
    let pages = Pages::load(&layout.pages)?;
    Ok((cfg, pages, layout))
}

fn run_build(args: &[String]) -> Result<(), String> {
    let dir = args.first().map(PathBuf::from).unwrap_or_else(|| PathBuf::from("."));
    let (cfg, pages, layout) = load_site(&dir)?;
    let site = build::Site { cfg: &cfg, pages: &pages, build: layout.build, root: layout.root };
    build::build(&site)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn locate_prefers_nested_layout() {
        let dir = std::env::temp_dir().join(format!("cs-loc-{}", std::process::id()));
        let _ = std::fs::create_dir_all(dir.join("_build"));
        std::fs::write(dir.join("_build/config.toml"), "name='x'").unwrap();
        let l = locate(&dir).unwrap();
        assert!(l.config.ends_with("_build/config.toml"));
        assert_eq!(l.root, dir);
    }

    #[test]
    fn locate_accepts_flat_layout() {
        let dir = std::env::temp_dir().join(format!("cs-flat-{}", std::process::id()));
        let _ = std::fs::create_dir_all(&dir);
        std::fs::write(dir.join("config.toml"), "name='x'").unwrap();
        let l = locate(&dir).unwrap();
        assert_eq!(l.config, dir.join("config.toml"));
    }
}