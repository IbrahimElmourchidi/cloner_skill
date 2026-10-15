#!/usr/bin/env python3
"""Inventories a repository and drafts a step order for it.

    python3 scripts/scan.py ~/code/some-project
    python3 scripts/scan.py ~/code/some-project --json
    python3 scripts/scan.py ~/code/some-project --write pages_draft.py
    python3 scripts/scan.py ~/code/some-project --max-per-dir 12

Reads the target repository and reports what it is made of: which languages,
how many lines, which manifests, which directories hold the bulk of it, and
where the entry points are. Then it proposes a phase grouping.

It is deliberately a *draft*. It sorts by directory and then by size, which is
a serviceable default, and then — unless `--no-deps` is passed — **re-sorts by
the real import graph**, so a module comes after everything it depends on.
Reading the imports is mechanical for the formats below. A draft that cannot
see that one module imports another is a draft somebody has to fix by hand on a
500-file project, which is the same as not sorting at all.

What the sort cannot do is tell you what a reader needs. Deciding which files
are worth a lesson means reading the repository; this produces the order they go
in once you have.

Language detection is by file extension across ~90 languages. Nothing here is
specific to any ecosystem; the manifest table below is just a list of filenames
that mean "this is how you build and run the thing".
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

# Directories that are never source. Skipping these is the difference between a
# scan that takes two seconds and one that takes two minutes.
SKIP_DIRS = {
    '.git', '.hg', '.svn', '.idea', '.vscode', '.vs', '.gradle', '.dart_tool',
    'node_modules', 'vendor', 'bower_components', 'jspm_packages', 'venv',
    '.venv', 'env', '__pycache__', '.mypy_cache', '.pytest_cache', '.ruff_cache',
    '.tox', '.nox', 'site-packages', 'dist', 'build', 'target', 'out', 'bin',
    'obj', '.next', '.nuxt', '.svelte-kit', '.output', '.turbo', '.parcel-cache',
    '.terraform', 'coverage', '.nyc_output', 'htmlcov', 'Pods', 'DerivedData',
    'build-tools', 'third_party', 'thirdparty', 'external', '.dart', '.bundle',
    'deps', '_build', 'elm-stuff', 'zig-cache', 'zig-out', '.stack-work',
    'cmake-build-debug', 'cmake-build-release', '.serverless', '.aws-sam',
}

# Directories that hold prose and generated output rather than source. These
# are skipped by default because scanning a project that already contains a
# clone-site finds the clone-site: on a real repository that produced 898 HTML
# files against 692 lines of actual code, and the inventory became useless.
# Re-enable one with `--include docs`.
DOC_DIRS = {'docs', 'doc', '_docs', 'documentation', 'site', '_site', 'www',
            'blog', 'man', 'manpages', 'changelog', '.github'}

BINARY_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.avif', '.ico', '.bmp',
              '.tiff', '.svg', '.pdf', '.zip', '.gz', '.bz2', '.xz', '.7z',
              '.tar', '.rar', '.jar', '.war', '.class', '.exe', '.dll', '.so',
              '.dylib', '.a', '.o', '.obj', '.pyc', '.pyo', '.wasm', '.woff',
              '.woff2', '.ttf', '.otf', '.eot', '.mp3', '.mp4', '.mov', '.avi',
              '.wav', '.ogg', '.webm', '.db', '.sqlite', '.sqlite3', '.bin',
              '.dat', '.lock', '.pack', '.idx', '.onnx', '.pt', '.pth', '.h5',
              '.npy', '.npz', '.safetensors', '.gguf', '.model', '.keystore'}

# extension -> data-lang, and extension -> human language name
EXT = {
    '.py': ('python', 'Python'), '.pyi': ('python', 'Python'), '.ipynb': ('json', 'Jupyter'),
    '.js': ('javascript', 'JavaScript'), '.mjs': ('javascript', 'JavaScript'),
    '.cjs': ('javascript', 'JavaScript'), '.jsx': ('jsx', 'JavaScript'),
    '.mjsx': ('jsx', 'JavaScript'), '.ts': ('typescript', 'TypeScript'),
    '.tsx': ('tsx', 'TypeScript'), '.mts': ('typescript', 'TypeScript'),
    '.cts': ('typescript', 'TypeScript'),
    '.dart': ('dart', 'Dart'), '.java': ('java', 'Java'), '.kt': ('kotlin', 'Kotlin'),
    '.kts': ('kotlin', 'Kotlin'), '.scala': ('scala', 'Scala'), '.groovy': ('groovy', 'Groovy'),
    '.clj': ('clojure', 'Clojure'), '.cljs': ('clojure', 'Clojure'),
    '.ex': ('elixir', 'Elixir'), '.exs': ('elixir', 'Elixir'),
    '.erl': ('erlang', 'Erlang'), '.hrl': ('erlang', 'Erlang'),
    '.hs': ('haskell', 'Haskell'), '.ml': ('ocaml', 'OCaml'), '.mli': ('ocaml', 'OCaml'),
    '.fs': ('fsharp', 'F#'), '.fsx': ('fsharp', 'F#'),
    '.swift': ('swift', 'Swift'), '.m': ('objc', 'Objective-C'), '.mm': ('objc', 'Objective-C++'),
    '.c': ('c', 'C'), '.h': ('c', 'C'), '.cc': ('cpp', 'C++'), '.cpp': ('cpp', 'C++'),
    '.cxx': ('cpp', 'C++'), '.hpp': ('cpp', 'C++'), '.hh': ('cpp', 'C++'),
    '.cs': ('csharp', 'C#'), '.vb': ('vbnet', 'VB.NET'),
    '.go': ('go', 'Go'), '.rs': ('rust', 'Rust'), '.zig': ('zig', 'Zig'),
    '.rb': ('ruby', 'Ruby'), '.rake': ('ruby', 'Ruby'), '.gemspec': ('ruby', 'Ruby'),
    '.php': ('php', 'PHP'), '.pl': ('perl', 'Perl'), '.pm': ('perl', 'Perl'),
    '.lua': ('lua', 'Lua'), '.r': ('r', 'R'), '.jl': ('julia', 'Julia'),
    '.nim': ('nim', 'Nim'), '.cr': ('crystal', 'Crystal'), '.sol': ('solidity', 'Solidity'),
    '.sh': ('bash', 'Shell'), '.bash': ('bash', 'Shell'), '.zsh': ('zsh', 'Zsh'),
    '.fish': ('fish', 'Fish'), '.ps1': ('powershell', 'PowerShell'),
    '.psm1': ('powershell', 'PowerShell'), '.bat': ('bash', 'Batch'),
    '.cmd': ('bash', 'Batch'), '.awk': ('awk', 'awk'),
    '.sql': ('sql', 'SQL'), '.psql': ('plsql', 'PL/pgSQL'), '.ddl': ('sql', 'SQL'),
    '.html': ('html', 'HTML'), '.htm': ('html', 'HTML'), '.xhtml': ('xml', 'XHTML'),
    '.xml': ('xml', 'XML'), '.svg': ('xml', 'SVG'), '.xsl': ('xml', 'XSLT'),
    '.vue': ('vue', 'Vue'), '.svelte': ('svelte', 'Svelte'), '.astro': ('astro', 'Astro'),
    '.css': ('css', 'CSS'), '.scss': ('scss', 'SCSS'), '.sass': ('sass', 'Sass'),
    '.less': ('less', 'Less'), '.styl': ('css', 'Stylus'),
    '.json': ('json', 'JSON'), '.json5': ('json5', 'JSON5'), '.jsonc': ('jsonc', 'JSONC'),
    '.yaml': ('yaml', 'YAML'), '.yml': ('yaml', 'YAML'), '.toml': ('toml', 'TOML'),
    '.ini': ('ini', 'INI'), '.cfg': ('ini', 'INI'), '.conf': ('conf', 'Config'),
    '.properties': ('properties', 'Properties'), '.env': ('env', 'dotenv'),
    '.graphql': ('graphql', 'GraphQL'), '.gql': ('gql', 'GraphQL'),
    '.proto': ('proto', 'Protocol Buffers'), '.thrift': ('proto', 'Thrift'),
    '.md': ('markdown', 'Markdown'), '.mdx': ('markdown', 'MDX'),
    '.rst': ('rst', 'reStructuredText'), '.tex': ('tex', 'LaTeX'),
    '.adoc': ('markdown', 'AsciiDoc'),
    '.tf': ('terraform', 'Terraform'), '.tfvars': ('terraform', 'Terraform'),
    '.hcl': ('conf', 'HCL'), '.gradle': ('groovy', 'Gradle'),
    '.cmake': ('cmake', 'CMake'), '.mk': ('makefile', 'Make'),
    '.dockerfile': ('dockerfile', 'Dockerfile'),
    '.tex': ('tex', 'LaTeX'), '.vim': ('vim', 'Vim script'),
    '.sol': ('solidity', 'Solidity'), '.asm': ('asm', 'Assembly'),
    '.s': ('asm', 'Assembly'), '.f90': ('fortran', 'Fortran'),
    '.pas': ('pascal', 'Pascal'), '.vbhtml': ('html', 'VB HTML'),
}

# Filenames that describe how the project is built and run, whatever the
# language. These become the first phase: a reader who cannot run the thing
# cannot check any of the lessons.
MANIFESTS = [
    'package.json', 'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'bun.lockb',
    'tsconfig.json', 'jsconfig.json', 'webpack.config.js', 'vite.config.ts',
    'rollup.config.js', 'esbuild.config.js', 'next.config.js', 'nuxt.config.ts',
    'astro.config.mjs', 'svelte.config.js', 'tailwind.config.js', 'postcss.config.js',
    'pyproject.toml', 'setup.py', 'setup.cfg', 'requirements.txt', 'requirements-dev.txt',
    'Pipfile', 'poetry.lock', 'uv.lock', 'tox.ini', 'pytest.ini', 'conftest.py',
    'Gemfile', 'Gemfile.lock', 'Rakefile', '.rubocop.yml', 'Cargo.toml', 'Cargo.lock',
    'rust-toolchain.toml', 'rustfmt.toml', 'clippy.toml',
    'go.mod', 'go.sum', 'go.work', 'Makefile', 'makefile', 'GNUmakefile',
    'CMakeLists.txt', 'meson.build', 'build.gradle', 'build.gradle.kts',
    'settings.gradle', 'settings.gradle.kts', 'gradle.properties', 'gradlew',
    'pom.xml', 'build.xml', 'build.zig', 'build.sbt', 'mix.exs', 'rebar.config',
    'composer.json', 'composer.lock', 'Gemfile', 'pubspec.yaml', 'pubspec.lock',
    'analysis_options.yaml', 'Package.swift', 'project.pbxproj',
    'Dockerfile', 'docker-compose.yml', 'docker-compose.yaml', 'compose.yaml',
    'Procfile', 'Vagrantfile', 'Justfile', 'Taskfile.yml', '.tool-versions',
    '.editorconfig', '.gitignore', '.gitattributes', '.npmrc', '.nvmrc',
    '.prettierrc', '.eslintrc', '.eslintrc.js', '.eslintrc.json', 'biome.json',
    'rustfmt.toml', '.clang-format', '.clang-tidy', 'codecov.yml',
]

# Filenames that are documentation or metadata, not build inputs.
DOCS = ['README.md', 'README.rst', 'README.txt', 'README', 'CONTRIBUTING.md',
        'CHANGELOG.md', 'LICENSE', 'LICENSE.md', 'LICENSE.txt', 'CODE_OF_CONDUCT.md',
        'SECURITY.md', 'ARCHITECTURE.md', 'Makefile']

# Entry-point-ish basenames, used to flag a likely "first" lesson per language.
ENTRY = {
    'main.py', '__main__.py', 'app.py', 'main.go', 'server.go', 'cmd',
    'main.rs', 'lib.rs', 'main.dart', 'index.js', 'index.ts', 'main.ts',
    'server.js', 'server.ts', 'app.js', 'app.ts', 'index.tsx', 'main.tsx',
    'Main.java', 'Main.kt', 'Program.cs', 'main.c', 'main.cpp', 'main.rs',
    'app.rb', 'config.ru', 'manage.py', 'wsgi.py', 'asgi.py', 'main.go',
    'mod.rs', 'schema.graphql', 'proto.py', 'urls.py', 'settings.py',
}


# --- dependency ordering -----------------------------------------------------
#
# Each entry is (regex, group kind). The regexes are deliberately conservative:
# a missed import costs nothing (the sort falls back to the directory order for
# that file) whereas a wrong one puts a file before something it needs, which
# produces a step the reader cannot complete.

IMPORT_PATTERNS = [
    # python: `from a.b import c`, `import a.b`
    (re.compile(r'^\s*from\s+([.\w]+)\s+import\b', re.M), 'mod'),
    (re.compile(r'^\s*import\s+([.\w]+)', re.M), 'mod'),
    # go / rust / zig: `use a::b`, `mod x;`
    (re.compile(r'^\s*(?:pub\s+)?use\s+([\w:]+)', re.M), 'mod'),
    # java / kotlin / scala: `import a.b.C`
    (re.compile(r'^\s*import\s+(?:static\s+)?([\w.]+)', re.M), 'mod'),
    # js / ts: `from './a'`, `require('./a')`
    (re.compile(r"""from\s+['"]([^'"]+)['"]"""), 'rel'),
    (re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)"""), 'rel'),
    (re.compile(r"""^\s*import\s+['"]([^'"]+)['"]""", re.M), 'rel'),
    # rust `mod foo;` referencing a sibling module
    (re.compile(r'^\s*(?:pub\s+)?mod\s+(\w+)\s*;', re.M), 'mod'),
    # php `use A\B;`
    (re.compile(r'^\s*use\s+([\w\\]+)', re.M), 'mod'),
    # ruby `require_relative 'x'`, `require 'x'`
    (re.compile(r"""^\s*require(?:_relative)?\s+['"]([^'"]+)['"]""", re.M), 'rel'),
    # dart / java-ish `import 'x.dart';`
    (re.compile(r"""^\s*(?:import|export)\s+['"]([^'"]+)['"]""", re.M), 'rel'),
    # swift `import Foo`
    (re.compile(r'^\s*import\s+(\w+)\s*$', re.M), 'mod'),
    # c# `using A.B;`
    (re.compile(r'^\s*using\s+([\w.]+)\s*;', re.M), 'mod'),
    # elixir `alias A.B`
    (re.compile(r'^\s*alias\s+([\w.]+)', re.M), 'mod'),
]

COMMENT_PREFIX = ('#', '//', '--', ';', '%')


def strip_comments(text):
    """Drop comment lines so a commented-out import is not a dependency."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(COMMENT_PREFIX) or s.startswith('*') or s.startswith('/*'):
            continue
        out.append(line)
    return '\n'.join(out)


def imports_of(path, ext):
    """The module specifiers a file imports, as a set of strings."""
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            text = strip_comments(f.read())
    except OSError:
        return set()
    found = set()
    for rx, kind in IMPORT_PATTERNS:
        for m in rx.finditer(text):
            spec = m.group(1)
            if spec:
                found.add((kind, spec))
    return found


def _candidates(rel, spec, kind, index):
    """Every file this specifier could plausibly mean.

    Resolution is ambiguous by nature — `import lib.api` names a module, not a
    file — so this returns every candidate and lets the caller intersect with
    the files actually in the repo. Guessing one answer and being wrong silently
    drops a dependency, which is the failure this whole mechanism exists to
    prevent.
    """
    if kind == 'rel':
        base = os.path.normpath(os.path.join(os.path.dirname(rel), spec))
        out = set()
        for cand in (base, base + '.dart', base + '.py', base + '.js', base + '.ts'):
            out.add(cand.replace(os.sep, '/'))
            out.add(os.path.join(cand + '/index').replace(os.sep, '/'))
        out.add(os.path.join(cand + '.dart').replace(os.sep, '/'))
        return {c for c in out if c in index}
    # dotted / colon-separated module name: try suffixes of each segment
    parts = [p for p in re.split(r'[.:/\\]+', spec) if p and p != '.' and p != '..']
    out = set()
    for i in range(len(parts)):
        tail = '/'.join(parts[i:])
        for stem in (tail, tail.replace('/', '.')):
            if stem in index:
                out.add(stem)
            for ext_ in ('.dart', '.py', '.ts', '.js', '.rs', '.go', '.rb', '.php'):
                if stem + ext_ in index:
                    out.add(stem + ext_)
    return {c for c in out if c in index}


def build_graph(files, root):
    """{file: {files it imports}} over the candidate set, plus a cycle report."""
    index = {rel: rel for rel, _ap, _e, _s in files}
    stem_index = {}
    for rel, _ap, _e, _s in files:
        stem_index.setdefault(os.path.splitext(rel)[0], rel)
        stem_index.setdefault(rel, rel)
    index.update(stem_index)

    graph, cycles = {}, []
    for rel, ap, _e, _s in files:
        deps = set()
        for kind, spec in imports_of(ap, _e):
            deps |= _candidates(rel, spec, kind, index)
        deps.discard(rel)
        graph[rel] = deps
    return graph, cycles


def topo_sort(order, graph):
    """Kahn's algorithm, keeping `order` as the tie-break.

    The seed order matters: files with no dependency relationship between them
    stay in directory/size order rather than in whatever order a set happened
    to yield, so two scans of an unchanged repository produce the same page
    list. A deterministic draft is worth more than a clever one.

    Cycles are broken rather than raised on. A mutual import is legal in most of
    these languages, so refusing to order the project would be refusing to
    describe it. The members are emitted in seed order and the cycle is
    returned so the caller can tell the author, which matters because a cycle
    is a design fact the reader should be told about rather than something the
    generator silently picks a side on.
    """
    pos = {f: i for i, f in enumerate(order)}
    nodes = [f for f in order if f in graph]
    indeg = {f: len([d for d in graph[f] if d in nodes and d != f]) for f in nodes}
    deps = {f: {d for d in graph[f] if d in nodes and d != f} for f in nodes}
    ready = sorted([f for f in nodes if indeg[f] == 0], key=pos.get)
    out, cycles = [], []

    while len(out) < len(nodes):
        if not ready:
            remaining = sorted([f for f in nodes if f not in out], key=pos.get)
            cycles.append(remaining)
            ready = [remaining[0]]
            for f in remaining:
                indeg[f] = 0
        cur = ready.pop(0)
        out.append(cur)
        for f in sorted(nodes, key=pos.get):
            if f in out or f not in deps:
                continue
            if cur in deps[f]:
                deps[f].discard(cur)
                indeg[f] -= 1
                if indeg[f] == 0:
                    ready.append(f)
        ready.sort(key=pos.get)
    return out, cycles


def walk(root, skip, include, limit_depth=12):
    """Yield (relpath, abspath, ext, size) for text-ish files, skipping noise."""
    root_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        if dirpath.count(os.sep) - root_depth >= limit_depth:
            dirnames[:] = []
            continue
        dirnames[:] = sorted(
            d for d in dirnames
            if (d in include)
            or (d not in skip and (not d.startswith('.') or d == '.github')))
        for fn in sorted(filenames):
            ext = os.path.splitext(fn)[1].lower()
            if fn.lower() in ('makefile', 'dockerfile', 'rakefile', 'gemfile',
                              'procfile', 'justfile', 'cmakelists.txt'):
                ext = ext or '.' + fn.lower()
            if ext in BINARY_EXT or ext in ('.lock', '.sum'):
                continue
            ap = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(ap)
            except OSError:
                continue
            if size > 400_000:
                continue
            yield os.path.relpath(ap, root), ap, ext, size


def count_lines(path):
    try:
        with open(path, 'rb') as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def human(n):
    for unit in ('B', 'KB', 'MB'):
        if n < 1024 or unit == 'MB':
            return '%.0f %s' % (n, unit)
        n /= 1024.0


def analyse(root, skip=None, include=None):
    skip = set(SKIP_DIRS) if skip is None else set(skip)
    skip |= DOC_DIRS
    lang_files = Counter()
    lang_lines = Counter()
    files_by_dir = defaultdict(list)
    root_files = []
    manifests = []
    docs = []
    entries = []
    total = 0
    unmapped = 0

    for rel, ap, ext, size in walk(root, skip, include or ()):
        total += 1
        base = os.path.basename(rel)
        if base in DOCS and os.path.dirname(rel) == '':
            docs.append(rel)
        if base in MANIFESTS:
            manifests.append(rel)
        if base in ENTRY:
            entries.append(rel)
        if os.path.dirname(rel) == '':
            root_files.append(rel)

        lang = EXT.get(ext)
        if not lang:
            unmapped += 1
            continue
        lang_files[lang[1]] += 1
        lang_lines[lang[1]] += count_lines(ap)
        files_by_dir[os.path.dirname(rel) or '.'].append((rel, size, lang[0]))

    return {
        'root': root,
        'files_scanned': total,
        'unmapped': unmapped,
        'languages': [
            {'language': l, 'files': c, 'lines': lang_lines[l]}
            for l, c in lang_files.most_common()
        ],
        'manifests': sorted(set(manifests)),
        'docs': sorted(set(docs)),
        'entries': sorted(set(entries)),
        'root_files': sorted(set(root_files)),
        'dirs': sorted(files_by_dir.keys()),
        'files_by_dir': {d: sorted(v) for d, v in files_by_dir.items()},
    }


def journey_order(teachable, graph, seed):
    """Breadth-first from the entry points, following what they import.

    The topological sort answers "what has to exist first", which is the right
    question for a library and the wrong one for an application. In an
    application the file that runs imports everything, so leaf-first ordering
    teaches the bottom of the stack for two hundred lessons and the reader does
    not see the program work until the end.

    A developer does not work that way. They get something on screen, then
    replace the placeholder underneath it, then get more on screen. That is a
    breadth-first walk of the import graph starting at the entry point, and
    this function produces it.

    `seed` is the tie-break, so two scans of an unchanged repository produce the
    same list. Returns `(order, debt)`, where `debt` is one row per step that
    reaches for a file taught later: `(index, file, [files to invent])`, worst
    debt first within a step.

    Almost every step has some. That is not a defect of the walk, it is the
    bill for choosing it: in a breadth-first order from the entry point, a file
    is always taught before anything it imports, because what it imports is
    what sits underneath it. The order is worth that bill precisely because the
    reader sees the program run early — and only if every one of those rows is
    declared as a `stubs=` placeholder. An undeclared one is a step that does
    not compile, which check_site.py reports.
    """
    pos = {f: i for i, f in enumerate(seed)}
    nodes = [f for f in teachable if f in graph]
    # The graph spans every candidate file, but only `nodes` is being ordered,
    # and a node's edges can point at a file that was filtered out of the
    # teaching set — a vendored directory, a skipped test folder. Rank those
    # last rather than crashing the sort: they are not taught, so where they
    # would have landed cannot affect the order.
    rank = lambda f: pos.get(f, len(pos))
    start = [f for f in nodes if f in ENTRY_SEEDS]
    if not start:
        # No entry point matched by name. Fall back to whatever nothing else
        # depends on, which is the closest honest guess the graph can make.
        depended = {d for f in nodes for d in graph[f] if d in nodes}
        roots = [f for f in nodes if f not in depended]
        start = [min(roots or nodes, key=rank)]

    order, seen = [], set(start)
    frontier = sorted(start, key=rank)
    while frontier:
        cur = frontier.pop(0)
        order.append(cur)
        for d in sorted(graph.get(cur, ()), key=rank):
            if d in nodes and d not in seen:
                seen.add(d)
                frontier.append(d)

    # Anything the entry points cannot reach is appended in seed order rather
    # than dropped: an unreachable file is usually a build script or a second
    # binary, and dropping it silently loses it from the inventory.
    order += [f for f in nodes if f not in seen]

    # A stub candidate is a node the walk reached before one of its own
    # dependencies. Walking depth-first would find many; walking breadth-first
    # from the entry point finds exactly the place the reader would hit a
    # missing name, which is the one gap worth naming.
    at = {f: i for i, f in enumerate(order)}
    debt = []
    for i, f in enumerate(order):
        late = [d for d in graph.get(f, ()) if d in nodes and at[d] > i]
        if late:
            # Sorted by how far away the real lesson is, worst first: the debt
            # that lasts two hundred lessons is the one worth planning for.
            late.sort(key=lambda d: -at[d])
            debt.append((i, f, late))
    return order, debt


ENTRY_SEEDS = set()


def draft_phases(a, max_per_dir, files=None, root=None, use_deps=True,
                 journey=False):
    """A draft ordering: setup first, then each source directory in turn.

    Seeded by depth then name, so `src/auth` comes before `src/billing` and
    `tests` comes last. Within a directory, smallest first: entry points and
    interfaces tend to be small, and a reader meets the shape before the bulk.

    That seed order is then overridden by one of two graphs, chosen by `journey`:

    - **dependency order (default)** — where B imports A, A is emitted first
      whatever their directories or sizes. Correct for a library. For an
      application it means teaching the bottom of the stack first and the
      reader seeing nothing run until the last lesson.
    - **journey order (`--journey`)** — breadth-first from the entry point,
      which is the order a developer actually works in. Stub candidates are
      reported alongside, so the gaps are visible in the draft rather than
      discovered at build time.

    The seed survives as the tie-break so the output stays deterministic between
    runs.
    """
    phases = []

    setup = list(a['manifests'])
    if a['docs']:
        setup += a['docs']
    if setup:
        phases.append(('Phase 0 &middot; Toolchain', sorted(set(setup))))

    src_dirs = [d for d in a['dirs']
                if d != '.' and not d.startswith('test')
                and not d.startswith('spec')
                and not d.startswith('example')
                and not d.startswith('doc')]
    if '.' in a['files_by_dir']:
        src_dirs = ['.'] + src_dirs
    src_dirs += [d for d in a['dirs'] if d not in src_dirs and d != '.']

    ordered = []
    n = 0
    for d in src_dirs:
        items = a['files_by_dir'].get(d, [])
        if not items:
            continue
        if len(items) > max_per_dir:
            items = sorted(items, key=lambda t: t[1])[:max_per_dir]
        ordered.extend(i[0] for i in items)

    seed = list(ordered)
    cycles = []
    stub_candidates = []
    if files and root:
        graph, _ = build_graph(files, root)
        teachable = [f for f in seed if f in graph]
        if journey and teachable:
            global ENTRY_SEEDS
            ENTRY_SEEDS = set(a['entries'])
            ranked, stub_candidates = journey_order(teachable, graph, seed)
            rest = [f for f in seed if f not in teachable]
            ordered = ranked + rest
        elif use_deps and teachable:
            ranked, cycles = topo_sort(teachable, graph)
            ranked += [f for f in teachable if f not in ranked]
            rest = [f for f in seed if f not in teachable]
            ordered = ranked + rest

    phases = []
    last_dir = None
    for f in ordered:
        d = os.path.dirname(f) or '.'
        if d != last_dir:
            n += 1
            phases.append(('Phase %d &middot; %s' % (n, d), []))
            last_dir = d
        phases[-1][1].append(f)
    return phases, cycles, stub_candidates


def emit(a, phases, out, cycles=(), journey=False, stubs=()):
    """`stubs` is the debt table from journey_order: (index, file, [to invent])."""
    w = out.write
    w('%s\n' % a['root'])
    w('=' * (len(a['root']) + 2) + '\n\n')
    w('%d files scanned, %d unmapped (binary or unrecognised extension)\n\n'
      % (a['files_scanned'], a['unmapped']))

    if not a['languages']:
        w('No recognised source files. Check the path, or add the extension to\n'
          'EXT in scan.py.\n')
        return

    w('Languages\n---------\n\n')
    w('  %-18s %7s %9s\n' % ('language', 'files', 'lines'))
    for l in a['languages']:
        w('  %-18s %7d %9d\n' % (l['language'], l['files'], l['lines']))
    w('\n')

    for title, items in (('Manifests (Phase 0 candidates)', a['manifests']),
                         ('Documentation', a['docs']),
                         ('Likely entry points', a['entries'])):
        if not items:
            continue
        w('%s\n%s\n' % (title, '-' * len(title)))
        for i in items[:25]:
            w('  %s\n' % i)
        if len(items) > 25:
            w('  ... and %d more\n' % (len(items) - 25))
        w('\n')

    w('Draft step order\n----------------\n\n')
    if journey:
        w('Breadth-first from the entry points, so a reader gets something that\n'
          'runs early and replaces what is underneath it as they go. That is the\n'
          'order a developer works in, not the order the import graph is\n'
          'readable in. Where two files have no dependency between them the\n'
          'order is by directory, then by size, so two scans of an unchanged\n'
          'repository produce the same list. It is a draft: it cannot tell you\n'
          'which files deserve a lesson, and it knows nothing about which ones\n'
          'are worth the reader\'s time. Read it, and argue with it.\n\n')
        if stubs:
            total = sum(len(row[2]) for row in stubs)
            deepest = max(len(row[2]) for row in stubs)
            w('Stub debt\n---------\n\n')
            w('This order reaches the entry point first and works outward, so a\n'
              'step almost always reaches for a file taught later. That is the price\n'
              'of the order, not a defect in it, and it is only affordable if every\n'
              'one of those placeholders is declared in `stubs=` on the lesson that\n'
              'uses it. An undeclared one is a step the reader cannot finish —\n'
              'check_site.py reports it.\n\n')
            w('A step needing a dozen or more is not a step to teach here. It is a\n'
              'dependency-wiring file — a DI module, a router, a bootstrap — and\n'
              'the usual answer is to leave the whole file stubbed behind one\n'
              'placeholder and teach it near the end, when the things it wires\n'
              'already exist. Judge each one; the count is the cost, not the plan.\n\n')
            w('  %d of %d steps need a placeholder; %d placeholders in total, at\n'
              '  worst %d on a single step.\n\n'
              % (len(stubs), sum(len(f) for _, f in phases), total, deepest))
            w('  %5s  %-58s %s\n' % ('step', 'file', 'invent now, real lesson at'))
            for i, f, late in stubs[:25]:
                far = len(late) - 1
                w('  %5d  %-58s %d placeholders%s\n'
                  % (i + 1, f[:58], len(late),
                     ', furthest +%d steps' % far if far else ', next step'))
            if len(stubs) > 25:
                w('\n  ... and %d more steps with a placeholder to declare.\n'
                  % (len(stubs) - 25))
            w('\n')
    else:
        w('Sorted by the real import graph, so a module comes after everything it\n'
          'depends on. Where two files have no dependency between them the order is\n'
          'by directory, then by size. It is a draft: it cannot tell you which files\n'
          'deserve a lesson, and it does not know that a reader needs the domain\n'
          'before the wiring. Read it, and argue with it. For an application, try\n'
          '--journey, which starts at the entry point instead.\n\n')
    if cycles:
        w('Import cycles found (%d) — ordered by seed, and worth saying so on the\n'
          'later page of each pair, because a reader who hits a mutual import\n'
          'should know the author saw it too:\n\n' % len(cycles))
        for c in cycles:
            w('  %s\n' % ' -> '.join(c))
        w('\n')
    step = 0
    for phase, files in phases:
        w('%s  (%d steps)\n' % (phase.replace('&middot;', '·'), len(files)))
        for f in files:
            step += 1
            w('  %3d  %s\n' % (step, f))
        w('\n')
    w('%d candidate steps.\n' % step)


def to_pages(phases, name):
    """A pages.py-shaped draft, for pasting in as a starting point.

    Written in the shape the toolchain now expects, which means two things a
    number-prefixed draft used to get wrong: no `n=`, because the step number is
    derived from position and a stored one that disagrees stops the build; and
    no number in the slug, because a slug that encodes its step number stops
    matching it the moment a lesson is inserted, and nothing reports that.
    Both used to be emitted here while the validators refused them, so the draft
    could not be pasted into a site and built without editing it first.
    """
    w = sys.stdout.write
    w('# Draft generated by scan.py. Every field except slug and path is a\n'
      '# placeholder — replace nav, h1, lead, why and preview with real prose.\n'
      '# For a large curriculum, split these into _build/_parts/NN.py and let\n'
      '# join.py assemble them rather than pasting hundreds of entries at once.\n')
    w('PAGES = [\n')
    step = 0
    taken = set()
    for phase, files in phases:
        for f in files:
            step += 1
            slug = slug_for(f, taken)
            w('    dict(slug=%r,\n' % slug)
            w('         nav=%r,\n' % os.path.basename(f))
            w('         h1=%r,\n' % os.path.basename(f))
            w('         lead=\'TODO\',\n')
            w('         path=%r,\n' % f)
            w('         phase=%r,\n' % phase)
            w('         why=\'TODO\'),\n')
    w(']\n\nAPPENDIX = []\nTOTAL_STEPS = len(PAGES)\n')


def slug_for(path, taken):
    """A slug from a source path: no number prefix, and never a duplicate.

    The prefix is what makes a slug wrong: `01-main` looks tidy in a draft and
    is a lie the moment a lesson is inserted, because the filename, the URL and
    the saved-progress key all stay valid and all now name the wrong step.

    Deduping matters for the same reason the prefix is dropped — several source
    paths can flatten to one slug, and a repeated slug is a repeated filename.
    """
    base = re.sub(r'[^a-z0-9]+', '-', path.lower()).strip('-')[:60].rstrip('-')
    if not base:
        base = 'file'
    slug, n = base, 2
    while slug in taken:
        suffix = '-%d' % n
        slug = base[:60 - len(suffix)].rstrip('-') + suffix
        n += 1
    taken.add(slug)
    return slug


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('project', help='path to the repository to inventory')
    ap.add_argument('--json', action='store_true', help='machine-readable report')
    ap.add_argument('--write', action='store_true',
                    help='emit a pages.py-shaped draft instead of the report')
    ap.add_argument('--max-per-dir', type=int, default=25,
                    help='max candidate steps per directory (default: 25)')
    ap.add_argument('--skip', action='append', default=[], metavar='DIR',
                    help='also skip this directory (repeatable). Replaces the '
                         'built-in list rather than adding to it.')
    ap.add_argument('--no-deps', action='store_true',
                    help='keep the directory/size order and skip the import sort')
    ap.add_argument('--journey', action='store_true',
                    help='order breadth-first from the entry point instead of '
                         'leaf-first, and report the files that order reaches '
                         'before their own dependencies (the stub candidates). '
                         'Use this for an application; the default is better '
                         'for a library.')
    ap.add_argument('--include', action='append', default=[], metavar='DIR',
                    help='re-enable a directory that is skipped by default, '
                         'e.g. --include docs (repeatable)')
    args = ap.parse_args()

    root = os.path.abspath(os.path.expanduser(args.project))
    if not os.path.isdir(root):
        print('scan: no such directory: ' + root, file=sys.stderr)
        return 1

    skip = set(args.skip) if args.skip else None
    a = analyse(root, skip, set(args.include))
    allfiles = list(walk(root, skip or set(), set(args.include)))
    phases, cycles, stubs = draft_phases(a, args.max_per_dir, allfiles, root,
                                         use_deps=not args.no_deps,
                                         journey=args.journey)

    if args.json:
        print(json.dumps({k: v for k, v in a.items()
                          if k != 'files_by_dir'}, indent=2))
    elif args.write:
        to_pages(phases, a['root'])
    else:
        emit(a, phases, sys.stdout, cycles, journey=args.journey, stubs=stubs)
    return 0


if __name__ == '__main__':
    sys.exit(main())