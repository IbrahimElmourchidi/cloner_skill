/// Languages a `<pre class="code" data-lang="…">` may declare.
///
/// Anything outside this set is almost always a typo — `data-lang="dartt"`
/// renders as unhighlighted plain text with no other symptom, which is what
/// makes it worth catching mechanically.
///
/// A name listed here but absent from `assets/app.js` is fine: it renders as
/// plain text. To add one, append the name here AND add a `RULES` entry there.
pub static KNOWN_LANG: &[&str] = &[
    "astro", "awk", "bash", "c", "cc", "cfg", "clojure", "cmake", "conf",
    "cpp", "crystal", "cs", "csharp", "css", "csv", "cts", "d", "dart",
    "diff", "docker", "dockerfile", "dotenv", "elixir", "env", "erlang",
    "fish", "fsharp", "go", "gql", "graphql", "grep", "groovy", "haskell",
    "hpp", "html", "http", "hxx", "ini", "java", "javascript", "jl", "js",
    "json", "json5", "jsonc", "jsx", "julia", "kotlin", "kt", "latex", "less",
    "log", "lua", "make", "makefile", "markdown", "md", "mts", "nim", "objc",
    "ocaml", "patch", "perl", "php", "pl", "plain", "plsql", "powershell",
    "properties", "proto", "ps1", "py", "python", "r", "rb", "react", "reg",
    "regex", "rs", "rst", "ruby", "rust", "sass", "scala", "scss", "sh",
    "shell", "solidity", "sql", "sqlite", "svelte", "svg", "swift", "tcl",
    "tex", "text", "toml", "ts", "tsv", "tsx", "txt", "typescript", "vb",
    "vbnet", "vue", "xml", "yaml", "yml", "zig", "zsh",
];
