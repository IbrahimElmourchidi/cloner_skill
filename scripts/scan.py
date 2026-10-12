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
a serviceable default and a poor dependency order — it cannot see that one
module imports another. The point is that you get a starting shape to argue
with, and a directory inventory to argue it with, instead of nothing. Replace
the ordering with a real dependency sort before writing lessons.

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


def draft_phases(a, max_per_dir):
    """A draft ordering: setup first, then each source directory in turn.

    Sorted by depth then name, so `src/auth` comes before `src/billing` and
    `tests` comes last. Within a directory, smallest first: entry points and
    interfaces tend to be small, and a reader meets the shape before the bulk.
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

    n = 0
    for d in src_dirs:
        items = a['files_by_dir'].get(d, [])
        if not items:
            continue
        if len(items) > max_per_dir:
            items = sorted(items, key=lambda t: t[1])[:max_per_dir]
        files = [i[0] for i in items]
        n += 1
        phases.append(('Phase %d &middot; %s' % (n, d), files))
    return phases


def emit(a, phases, out):
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
    w('This is sorted by directory, NOT by dependency. It is a shape to argue\n'
      'with, not an order to publish. Read each file and reorder so that every\n'
      'lesson only refers to things earlier lessons have already introduced.\n\n')
    step = 0
    for phase, files in phases:
        w('%s  (%d steps)\n' % (phase.replace('&middot;', '·'), len(files)))
        for f in files:
            step += 1
            w('  %3d  %s\n' % (step, f))
        w('\n')
    w('%d candidate steps.\n' % step)


def to_pages(phases, name):
    """A pages.py-shaped draft, for pasting in as a starting point."""
    w = sys.stdout.write
    w('# Draft generated by scan.py. Every field except n/slug/path is a\n'
      '# placeholder — replace nav, h1, lead and why with real prose.\n')
    w('PAGES = [\n')
    step = 0
    for phase, files in phases:
        for f in files:
            step += 1
            slug = '%02d-%s' % (step, re.sub(r'[^a-z0-9]+', '-', f.lower())
                                .strip('-')[:60].rstrip('-'))
            w('    dict(n=%d, slug=%r,\n' % (step, slug))
            w('         nav=%r,\n' % os.path.basename(f))
            w('         h1=%r,\n' % os.path.basename(f))
            w('         lead=\'TODO\',\n')
            w('         path=%r,\n' % f)
            w('         phase=%r),\n' % phase)
    w(']\n\nAPPENDIX = []\nTOTAL_STEPS = len(PAGES)\n')


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
    phases = draft_phases(a, args.max_per_dir)

    if args.json:
        print(json.dumps({k: v for k, v in a.items()
                          if k != 'files_by_dir'}, indent=2))
    elif args.write:
        to_pages(phases, a['root'])
    else:
        emit(a, phases, sys.stdout)
    return 0


if __name__ == '__main__':
    sys.exit(main())