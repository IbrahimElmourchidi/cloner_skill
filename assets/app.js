/* cloner_skill — progressive enhancement only.
   With JS disabled every page still reads; only syntax highlighting and the
   read-tracking stop working. The sidebar is baked in at build time by
   build.py, so navigation never depends on this file. */
(function () {
  'use strict';

  /* Namespace for localStorage. Shared per-origin on purpose: a reader moving
     between two cloned sites on the same host keeps their progress in both.
     Override per site with <body data-read-key="..."> if that is unwanted. */
  var KEY = (typeof document !== 'undefined' && document.body &&
             document.body.getAttribute('data-read-key')) || 'clonedocs.read.v1';

  /* ---------- tiny syntax highlighter ----------
     Operates on RAW source and escapes as it emits, so no token content can
     ever break out of the <span> it lands in. Rules are tried in order at the
     current offset; the first match wins.

     Languages are declared as families rather than one hand-written list each.
     A C-like language is ~90% the same rules with a different keyword list, so
     cLike() builds those; hash-comment languages share a second builder. Adding
     a language is one line, not twenty.

     An unknown data-lang falls through to esc() and renders as plain text, so
     a missing rule degrades to "no colour" rather than broken markup. */

  function esc(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  /* Sticky flag (y) is appended to every rule: the scanner only ever tests a
     rule at the current offset, so a keyword can never latch onto the middle
     of an identifier. That is what makes the flat-rule scanner correct. */
  function rx(src, flags) { return new RegExp(src, (flags || '') + 'y'); }

  function kw(words, ci) {
    var alt = String(words).trim().split(/[\s,|]+/).join('|');
    return rx('\\b(?:' + alt + ')\\b', ci ? 'i' : '');
  }

  var TYPEREF = rx('\\b[A-Z]\\w*\\b');
  var NUMBER = rx('\\b\\d[\\d_]*(?:\\.\\d+)?(?:[eE][+-]?\\d+)?\\b');
  var CALL = rx('\\b[a-z_]\\w*(?=\\s*\\()');
  var CONST_LIT = rx('\\b(?:true|false|null|nil|none|none_|None|True|False|undefined|NULL)\\b');

  /* Quoted-string alternatives, built from the quote characters a language uses.
     Backslash escapes are allowed inside, which is wrong for languages whose
     strings are raw (Python, Rust, shell) — those override `str` instead. */
  function quotes(qs) {
    return qs.map(function (c) { return c + '(?:[^' + c + '\\\\\\n]|\\\\.)*' + c; });
  }

  /* Some options are [source, flags] pairs because the rule needs the `m` flag
     to anchor at a line start. Without `m`, a sticky `^` can only ever match at
     offset 0 — which looks like "highlighting silently does nothing". */
  function rule(o) {
    return Array.isArray(o) ? [rx(o[0], o[1]), o[2]] : [rx(o), 't-prop'];
  }

  /* C-like family: // or # line comments, /* *\/ block comments, bracketed
     strings, keyword + Type keywords, numbers, call sites. */
  function cLike(o) {
    o = o || {};
    var r = [];
    if (o.line !== undefined) {
      r.push([rx((o.line || '//').replace(/[/*]/g, '\\$&') + '[^\\n]*'), 't-com']);
    }
    if (o.block) r.push([rx(o.block[0] + '[\\s\\S]*?' + o.block[1]), 't-com']);
    if (o.pre) r.push([rx(o.pre[0] + '[\\s\\S]*?' + o.pre[1]), 't-com']);
    r.push([rx((o.str || quotes(o.q || ['"', "'"])).join('|')), 't-str']);
    if (o.ann) r.push([rx(o.ann), 't-ann']);
    if (o.prop) r.push(rule(o.prop));
    r.push([CONST_LIT, 't-key']);
    if (o.kw) r.push([kw(o.kw, o.ci), 't-key']);
    if (o.typ !== false) r.push([TYPEREF, 't-typ']);
    r.push([rx(o.num || '\\b\\d[\\d_]*(?:\\.\\d+)?(?:[eE][+-]?\\d+)?\\b'), 't-num']);
    if (o.fn !== false) r.push([CALL, 't-fn']);
    return r;
  }

  /* Hash-comment family: python, ruby, shell, yaml, toml, r, perl, makefile…
     o.str passes straight through — python and ruby need their own string
     shapes (triple quotes, %-literals, regexes) and must not fall back to the
     C-family quote builder. */
  function hashLike(o) {
    var base = cLike({ str: o.str || quotes(o.q || ['"', "'"]), fn: o.fn });
    base.unshift([rx('#[^\\n]*'), 't-com']);
    if (o.prop) base.splice(base.length - 2, 0, rule(o.prop));
    if (o.kw) base.splice(base.length - 2, 0, [kw(o.kw, true), 't-key']);
    return base;
  }

  var RULES = {};

  /* ---------- C-like ---------- */
  RULES.dart = [
    [rx('//[^\\n]*'), 't-com'],
    [rx('\'\'\'[\\s\\S]*?\'\'\'|"""[\\s\\S]*?"""'), 't-str'],
    [rx('(?:r|R)?\'(?:[^\'\\\\\\n]|\\\\.)*\'|(?:r|R)?"(?:[^"\\\\\\n]|\\\\.)*"'), 't-str'],
    [rx('@[A-Za-z_]\\w*'), 't-ann'],
    [kw('abstract as assert async await base break case catch class const continue ' +
        'covariant default deferred do dynamic else enum export extends extension external ' +
        'factory final finally for get hide if implements import in is late library mixin new ' +
        'null on operator part required rethrow return sealed set show static super switch ' +
        'sync this throw true false try typedef var void while with yield'), 't-key'],
    [TYPEREF, 't-typ'], [NUMBER, 't-num'], [CALL, 't-fn']
  ];
  RULES.typescript = RULES.javascript = cLike({
    ann: '@[A-Za-z_$][\\w$]*', prop: '\\b[A-Za-z_$][\\w$]*(?=\\s*:)',
    kw: 'abstract any as asserts async await boolean break case catch class const continue ' +
        'declare default delete do else enum export extends finally for from function get if ' +
        'implements import in instanceof interface is keyof let namespace never new null number ' +
        'of private protected public readonly return static string super switch this throw true ' +
        'false try type typeof undefined unknown var void while with yield'
  });
  RULES.tsx = RULES.jsx = RULES.typescript;
  RULES.react = RULES.typescript;

  RULES.go = cLike({
    block: ['/\\*', '\\*/'], prop: '\\b[A-Z]\\w*(?=\\s*\\()',
    kw: 'break case chan const continue default defer else fallthrough for func go goto if ' +
        'import interface map package range return select struct switch type var nil true false'
  });
  RULES.rust = cLike({
    block: ['/\\*', '\\*/'],
    str: ['r#*"[^"]*"#*', 'b?"(?:[^"\\\\]|\\\\.)*"', "b?'(?:[^'\\\\]|\\\\.)*'"],
    kw: 'as async await break const continue crate dyn else enum extern false fn for if impl in ' +
        'let loop match mod move mut pub ref return self Self static struct super trait true ' +
        'type unsafe use where while'
  });
  RULES.kotlin = cLike({
    str: ['"""[\\s\\S]*?"""', '"(?:[^"\\\\\\n]|\\\\.)*"', "'(?:[^'\\\\\\n]|\\\\.)*'"],
    ann: '@[A-Za-z_]\\w*',
    kw: 'abstract actual annotation as break by catch class companion const constructor ' +
        'continue crossinline data delegate do dynamic else enum expect external false field ' +
        'final finally for fun get if import in infix init inline inner interface internal is ' +
        'lateinit noinline null object open operator out override package param private ' +
        'protected public reified return sealed set super suspend tailrec this throw true try ' +
        'typealias val var vararg when where while'
  });
  RULES.swift = cLike({
    block: ['/\\*', '\\*/'], ann: '@[A-Za-z_]\\w*',
    str: ['"""[\\s\\S]*?"""', '"(?:[^"\\\\\\n]|\\\\.)*"'],
    kw: 'actor any as associatedtype async await break case catch class continue convenience ' +
        'default defer deinit didSet didThrow do dynamic else enum extension fallthrough false ' +
        'fileprivate final for func get guard if import in indirect infix init inout internal ' +
        'is lazy let mutating nil nonmutating open operator optional override postfix ' +
        'precedencegroup prefix private protocol public repeat required rethrows return self ' +
        'Self set some static struct subscript super switch throw throws true try typealias ' +
        'unowned var weak where while willSet'
  });
  RULES.java = cLike({
    block: ['/\\*', '\\*/'], ann: '@[A-Za-z_]\\w*',
    kw: 'abstract assert boolean break byte case catch char class const continue default do ' +
        'double else enum extends final finally float for goto if implements import instanceof ' +
        'int interface long native new package private protected public return short static ' +
        'strictfp super switch synchronized this throw throws transient try var void volatile ' +
        'while true false null record sealed permits yield var'
  });
  RULES.csharp = cLike({
    block: ['/\\*', '\\*/'], ann: '\\[[A-Za-z_][\\w.]*(?:\\([^)]*\\))?\\]',
    kw: 'abstract as base bool break byte case catch char checked class const continue decimal ' +
        'default delegate do double dynamic else enum event explicit extern false finally fixed ' +
        'float for foreach goto if implicit in int interface internal is lock long namespace new ' +
        'null object operator out override params private protected public readonly record ref ' +
        'return sbyte sealed short sizeof stackalloc static string struct switch this throw true ' +
        'try typeof uint ulong unchecked unsafe ushort using var virtual void volatile when where ' +
        'while yield async await nameof'
  });
  RULES.cpp = cLike({
    block: ['/\\*', '\\*/'], pre: ['/\\*\\*', '\\*/'],
    str: ['R"\\([\\s\\S]*?\\)"', '"(?:[^"\\\\\\n]|\\\\.)*"', "'(?:[^'\\\\\\n]|\\\\.)*'"],
    ann: '#\\s*[a-z_]+',
    kw: 'alignas alignof auto bool break case catch char char8_t char16_t char32_t class concept ' +
        'const consteval constexpr constinit const_cast continue co_await co_return co_yield ' +
        'decltype default delete do double dynamic_cast else enum explicit export extern false ' +
        'float for friend goto if inline int long mutable namespace new noexcept nullptr operator ' +
        'private protected public register reinterpret_cast requires return short signed sizeof ' +
        'static static_assert static_cast struct switch template this thread_local throw true ' +
        'try typedef typeid typename union unsigned using virtual void volatile wchar_t while'
  });
  RULES.c = RULES.cpp;
  RULES.php = cLike({
    line: '//', block: ['/\\*', '\\*/'], prop: '\\$[A-Za-z_]\\w*',
    kw: 'abstract and array as break callable case catch class clone const continue declare ' +
        'default do echo else elseif empty enddeclare endfor endforeach endif endswitch endwhile ' +
        'enum extends final finally fn for foreach function global goto if implements include ' +
        'include_once instanceof insteadof interface isset list match namespace new or print ' +
        'private protected public readonly require require_once return static switch throw trait ' +
        'try unset use var while xor yield true false null int float string bool void'
  });
  RULES.scala = cLike({
    block: ['/\\*', '\\*/'], str: ['"""[\\s\\S]*?"""', '"(?:[^"\\\\\\n]|\\\\.)*"'],
    kw: 'abstract case catch class def do else extends false final finally for forSome given if ' +
        'implicit import lazy match new null object override package private protected return sealed ' +
        'super this throw trait try true type val var while with yield'
  });
  RULES.lua = [
    [rx('--\\[\\[[\\s\\S]*?\\]\\]'), 't-com'],
    [rx('--[^\\n]*'), 't-com'],
    [rx('\\[[\\s\\S]*?\\]'), 't-str'],
    [rx('"(?:[^"\\\\\\n]|\\\\.)*"|\'(?:[^\'\\\\\\n]|\\\\.)*\''), 't-str'],
    [CONST_LIT, 't-key'],
    [kw('and break do else elseif end false for function goto if in local nil not or repeat ' +
        'return then true until while self'), 't-key'],
    [rx('\\b[A-Za-z_]\\w*(?=\\s*=)'), 't-var'],
    [CALL, 't-fn']
  ];
  RULES.zig = cLike({
    kw: 'align allowzero and anyframe anytype asm async await break callconv catch comptime ' +
        'const continue defer else enum error extern fn for if inline noalias noinline opaque ' +
        'or orelse packed pub return struct suspend switch test threadlocal try union ' +
        'unreachable usingnamespace var volatile while true false null undefined'
  });
  RULES.solidity = RULES.cpp;

  /* ---------- hash-comment ---------- */
  RULES.python = hashLike({
    str: ['[rbuf]{0,2}"""[\\s\\S]*?"""', '[rbuf]{0,2}\'\'\'[\\s\\S]*?\'\'\'',
          '[rbuf]{0,2}"(?:[^"\\\\\\n]|\\\\.)*"', "[rbuf]{0,2}'(?:[^'\\\\\\n]|\\\\.)*'"],
    ann: '@[A-Za-z_]\\w*',
    kw: 'and as assert async await break class continue def del elif else except finally for ' +
        'from global if import in is lambda nonlocal not or pass raise return try while with ' +
        'yield match case self cls property staticmethod classmethod'
  });
  RULES.ruby = hashLike({
    str: ['%[wWiIqQ]?\\([\\s\\S]*?\\)', '%[wWiIqQ]?[[{][\\s\\S]*?[\\]}]',
          '"(?:[^"\\\\\\n]|\\\\.)*"', "'(?:[^'\\\\\\n]|\\\\.)*'"],
    ann: '@[A-Za-z_]\\w*',
    kw: 'alias and begin break case class def defined do else elsif end ensure for if in module ' +
        'next nil not or redo rescue retry return self super then undef unless until when while ' +
        'yield attr_accessor attr_reader attr_writer include extend require lambda proc raise attr_accessor'
  });
  RULES.bash = RULES.shell = hashLike({
    q: ['"', "'"],
    str: ['\\$?\'[^\']*\'', '\\$?"(?:[^"\\\\]|\\\\.)*"'],
    prop: ['^\\s*[A-Za-z_]\\w*(?==)', 'm', 't-var'],
    fn: false
  });
  RULES.yaml = hashLike({
    str: ['[|>][-+]?\\n(?:[\\s\\S]*?)\\n(?=\\S|$)'],
    prop: ['^[ \\t-]*[A-Za-z_][\\w.-]*(?=\\s*:)', 'm', 't-prop'],
    kw: 'true false null yes no on off ~', fn: false
  });
  RULES.toml = RULES.yaml;
  RULES.ini = RULES.yaml;
  RULES.properties = RULES.yaml;
  RULES.makefile = RULES.make = [
    [rx('#[^\\n]*'), 't-com'], [CALL, 't-fn'], [NUMBER, 't-num'], [CONST_LIT, 't-key']
  ];
  RULES.dockerfile = RULES.docker = hashLike({
    str: ['"(?:[^"\\\\\\n]|\\\\.)*"', "'(?:[^'\\\\\\n]|\\\\.)*'"],
    prop: ['^\\s*[A-Z_]+(?=\\s)', 'm', 't-prop'],
    kw: 'ADD ARG CMD COPY ENTRYPOINT ENV EXPOSE FROM HEALTHCHECK LABEL MAINTAINER ONBUILD RUN ' +
        'SHELL STOPSIGNAL USER VOLUME WORKDIR as build', fn: false
  });
  RULES.r = [
    [rx('#[^\\n]*'), 't-com'],
    [rx('"(?:[^"\\\\\\n]|\\\\.)*"|\'(?:[^\'\\\\\\n]|\\\\.)*\''), 't-str'],
    [CONST_LIT, 't-key'],
    [kw('function if else for while repeat break next return library require source TRUE FALSE ' +
        'NULL Inf NaN NA'), 't-key'],
    [rx('<-|%[a-zA-Z%*/|\\-\\[\\]]+|\\$[A-Za-z_]\\w*'), 't-ann'],
    [CALL, 't-fn']
  ];
  RULES.perl = hashLike({
    str: ['<<[A-Z_]+[\\s\\S]*?\\n[A-Z_]+', 'q[qw]?\\([\\s\\S]*?\\)[qw]?',
          '"(?:[^"\\\\\\n]|\\\\.)*"', "'(?:[^'\\\\\\n]|\\\\.)*'"],
    kw: 'my our local sub if elsif else unless while until for foreach do return last next redo ' +
        'package use require no eval BEGIN END AUTOLOAD wantarray defined undef ref bless scalar'
  });

  /* ---------- markup, data, and everything else ---------- */
  RULES.json = [
    [rx('//[^\\n]*'), 't-com'],
    [rx('"(?:[^"\\\\]|\\\\.)*"(?=\\s*:)'), 't-prop'],
    [rx('"(?:[^"\\\\]|\\\\.)*"'), 't-str'],
    [CONST_LIT, 't-key'], [NUMBER, 't-num']
  ];
  RULES.json5 = RULES.json;
  RULES.jsonc = RULES.json;
  RULES.xml = [
    [rx('<!\\[CDATA\\[[\\s\\S]*?\\]\\]>'), 't-str'],
    [rx('<!--[\\s\\S]*?-->'), 't-com'],
    [rx('<\\/?[A-Za-z][\\w.:-]*'), 't-key'],
    [rx('"(?:[^"\\\\]|\\\\.)*"'), 't-str'],
    [rx('@[A-Za-z_][\\w.:-]*'), 't-ann'],
    [rx('&[a-zA-Z#\\d]+;'), 't-ann']
  ];
  RULES.html = RULES.xml;
  RULES.svg = RULES.xml;
  RULES.vue = RULES.svelte = RULES.xml;
  RULES.css = [
    [rx('/\\*[\\s\\S]*?\\*/'), 't-com'],
    [rx('"(?:[^"\\\\\\n]|\\\\.)*"|\'(?:[^\'\\\\\\n]|\\\\.)*\''), 't-str'],
    [kw('@media @import @supports @keyframes @font-face @charset @layer', true), 't-key'],
    [rx('\\.[A-Za-z_-][\\w-]*|#?[A-Za-z][\\w-]*(?=[\\s,{:.#>\\[]|$)'), 't-prop'],
    [rx('#[0-9a-fA-F]{3,8}\\b'), 't-num'],
    [rx('--[A-Za-z][\\w-]*'), 't-ann'],
    [rx('\\b\\d[\\d.]*(?:px|rem|em|vh|vw|%|s|ms|fr|deg|ch)?\\b'), 't-num']
  ];
  RULES.scss = RULES.css;
  RULES.less = RULES.css;
  RULES.sql = [
    [rx('--[^\\n]*'), 't-com'], [rx('/\\*[\\s\\S]*?\\*/'), 't-com'],
    [rx('"(?:[^"\\\\\\n]|\\\\.)*"|\'(?:[^\'\\\\\\n]|\\\\.)*\''), 't-str'],
    [rx('`[^`]*`'), 't-str'],
    [kw('select insert update delete create drop alter grant revoke merge truncate from where ' +
        'join inner left right full outer cross on as and or not null returning begin end commit ' +
        'rollback exception if then else case when else declare function procedure trigger view ' +
        'table policy index sequence using check constraint default primary key unique references ' +
        'cascade restrict exists with recursive values set security definer invoker ' +
        'true false array boolean char numeric text uuid jsonb interval'), 't-key'],
    [rx('\\b[a-z_][\\w$]*\\b', 'i'), 't-prop']
  ];
  RULES.graphql = [
    [rx('#[^\\n]*'), 't-com'],
    [rx('"(?:[^"\\\\\\n]|\\\\.)*"'), 't-str'],
    [kw('query mutation subscription fragment on type input enum interface union scalar ' +
        'implements schema extend directive repeat'), 't-key'],
    [rx('\\$?[A-Za-z_]\\w*(?=\\s*[:(])'), 't-prop']
  ];
  RULES.proto = RULES.graphql;
  RULES.markdown = RULES.md = [
    [rx('^\\s*#{1,6}[^\\n]*', 'm'), 't-key'],
    [rx('```[\\s\\S]*?```'), 't-str'],
    [rx('`[^`\\n]*'), 't-str'],
    [rx('\\*\\*[^*\\n]+\\*\\*|__[^_\\n]+__'), 't-typ'],
    [rx('\\[[^\\]\\n]*\\]\\([^)\\n]*\\)'), 't-ann'],
    [rx('^\\s*(?:[-*+]|\\d+\\.) ', 'm'), 't-prop']
  ];
  RULES.diff = RULES.patch = [
    [rx('^@@[^\\n]*', 'm'), 't-ann'],
    [rx('^\\+(?!\\+\\+)[^\\n]*', 'm'), 't-ok'],
    [rx('^-(?!--)[^\\n]*', 'm'), 't-bad']
  ];
  RULES.grep = [
    [rx('^[^:\\n]+(?=:)', 'm'), 't-key'],
    [rx('^-\\d|^\\.\\.\\.', 'm'), 't-num'],
    [rx('-[^\\n]+'), 't-str']
  ];
  RULES.log = RULES.text = [];
  RULES.plain = [];

  /* ---------- scan ---------- */
  function highlight(src, lang) {
    var rules = RULES[lang];
    if (!rules || !rules.length) return esc(src);
    var out = '', i = 0, n = src.length;
    while (i < n) {
      var ch = src[i];
      if (ch === '\n') { out += ch; i++; continue; }
      var cls = null, text = null;
      for (var r = 0; r < rules.length; r++) {
        rules[r][0].lastIndex = i;
        var m = rules[r][0].exec(src);
        if (m && m.index === i && m[0].length) { cls = rules[r][1]; text = m[0]; break; }
      }
      if (cls !== null) { out += '<span class="' + cls + '">' + esc(text) + '</span>'; i += text.length; }
      else { out += esc(ch); i++; }
    }
    return out;
  }

  /* ---------- aliases ----------
     People write `py`, not `python`. These cost one line each and stop the
     common spellings from falling through to unhighlighted plain text. */
  RULES.py = RULES.python;
  RULES.rb = RULES.ruby;
  RULES.rs = RULES.rust;
  RULES.kt = RULES.kotlin;
  RULES.ts = RULES.typescript;
  RULES.js = RULES.javascript;
  RULES.cs = RULES.csharp;
  RULES.sh = RULES.bash;
  RULES.zsh = RULES.bash;
  RULES.yml = RULES.yaml;
  RULES.md = RULES.markdown;
  RULES.gql = RULES.graphql;
  RULES.hpp = RULES.cc = RULES.hxx = RULES.cpp;
  RULES.mts = RULES.cts = RULES.typescript;

  /* ---------- apply ---------- */
  function paint() {
    var blocks = document.querySelectorAll('pre.code[data-lang]');
    for (var i = 0; i < blocks.length; i++) {
      var el = blocks[i];
      if (el.getAttribute('data-done') === '1') continue;
      var code = el.querySelector('code');
      if (!code) continue;
      try {
        code.innerHTML = highlight(code.textContent, el.getAttribute('data-lang') || 'text');
      } catch (e) {
        code.textContent = code.textContent;   // never leave the block half-painted
      }
      el.setAttribute('data-done', '1');
    }
  }

  /* ---------- read tracking ---------- */
  function read() {
    try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; }
  }
  function write(o) {
    try { localStorage.setItem(KEY, JSON.stringify(o)); } catch (e) { /* private mode */ }
  }

  function mark(pageId, on) {
    var o = read();
    if (on) { o[pageId] = 1; } else { delete o[pageId]; }
    write(o);
    refresh();
  }

  function currentId() {
    var b = document.body.getAttribute('data-page');
    return b || '';
  }

  function refresh() {
    var done = read();
    var links = document.querySelectorAll('.side a[data-page]');
    var total = 0, isDone = 0;
    for (var i = 0; i < links.length; i++) {
      var id = links[i].getAttribute('data-page');
      if (done[id]) { links[i].querySelector('.tick').hidden = false; isDone++; }
      total++;
    }
    var bars = document.querySelectorAll('[data-progress]');
    var pct = total ? Math.round((isDone / total) * 100) : 0;
    for (var b = 0; b < bars.length; b++) {
      var fill = bars[b].querySelector('i');
      if (fill) fill.style.width = pct + '%';
      var label = bars[b].parentNode.querySelector('[data-progress-label]');
      if (label) label.textContent = isDone + ' of ' + total + ' steps read (' + pct + '%)';
    }
    var btn = document.querySelector('[data-mark]');
    if (btn) {
      var on = !!done[currentId()];
      btn.textContent = on ? 'Mark as unread' : 'Mark as read';
      btn.setAttribute('data-on', on ? '1' : '0');
    }
  }

  function init() {
    paint();
    var btn = document.querySelector('[data-mark]');
    if (btn) {
      btn.addEventListener('click', function () {
        var on = btn.getAttribute('data-on') === '1';
        mark(currentId(), !on);
      });
    }
    refresh();
  }

  if (typeof document === 'undefined') {
    if (typeof module !== 'undefined') {
      module.exports = { highlight: highlight, langs: Object.keys(RULES) };
    }
    return;
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  /* Exposed so a test harness can exercise the highlighter without a DOM. */
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { highlight: highlight, langs: Object.keys(RULES) };
  }
})();