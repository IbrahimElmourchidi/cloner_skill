#!/usr/bin/env python3
"""SVG geometry linter for docs/site.

Checks every <figure class="diagram"> for the defects that are invisible in
source but obvious on screen:

  1. text overlapping a <rect> that does not contain it
  2. text overlapping other text
  3. anything outside the viewBox (clipped silently by the renderer)
  4. an edge line crossing a text label

Text bounding boxes are estimated from the font-size implied by the element's
class and the character count. That is approximate, so CLEARANCE is generous
by default; it is tuned to catch real collisions, not to police kerning.

    python3 docs/site/_build/check_svg.py            # every page
    python3 docs/site/_build/check_svg.py 18 35      # pages whose slug starts 18 or 35

Exit code 1 if anything fails.
"""
import os, re, sys, glob
from html.parser import HTMLParser

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# font-size per class, mirroring assets/style.css
FONT = {'.lb': 13.0, '.sb': 11.5, '.el': 11.5, '.fnote': 11.5, '.note': 11.5,
        '.stepno': 11.5, '.tick': 11.5, '.mk-ink': 11.5}
MONO = {'.lb', '.el', '.stepno'}
DEFAULT_FS = 11.5

# width of one character, as a fraction of font-size
W_MONO, W_SANS = 0.605, 0.525
ASCENT, DESCENT = 0.78, 0.22          # above / below the baseline

CLEARANCE = 4.0                        # px; >= 16 is the house rule, we flag less


class Svg(HTMLParser):
    """Collects text / rect / line geometry from one <svg> element."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.viewbox = None
        self.texts, self.rects, self.lines = [], [], []
        self._rectcls = {}
        self._buf = None
        self._cur = None
        self.aria = ''

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == 'figure' and 'diagram' in d.get('class', ''):
            self.depth = 1
            return
        if self.depth:
            if tag == 'svg':
                self.depth = 2
                vb = d.get('viewBox') or d.get('viewbox') or ''
                try:
                    self.viewbox = [float(v) for v in vb.replace(',', ' ').split()]
                except ValueError:
                    self.viewbox = None
                self.aria = d.get('aria-label', '')
            elif tag == 'text':
                self.depth += 1
                anchor = d.get('text-anchor', 'start')
                if anchor == 'middle':
                    self.anchor = 0
                elif anchor == 'end':
                    self.anchor = 1
                else:
                    self.anchor = -1
                self._cur = {'x': float(d.get('x', 0)), 'y': float(d.get('y', 0)),
                             'cls': d.get('class', ''), 'anchor': self.anchor,
                             'text': ''}
            elif tag == 'rect':
                r = {k: float(d.get(k, 0)) for k in ('x', 'y', 'width', 'height')}
                self._rectcls[id(r)] = d.get('class', '')
                self.rects.append(r)
            elif tag == 'line':
                self.lines.append({k: float(d.get(k, 0))
                                   for k in ('x1', 'y1', 'x2', 'y2')})
            elif tag == 'text':
                pass
            elif tag == 'path':
                self.lines.append({'path': True, 'd': d.get('d', ''),
                                   'cls': d.get('class', '')})

    def handle_endtag(self, tag):
        if not self.depth:
            return
        if tag == 'text' and self._cur is not None:
            self._cur['text'] = re.sub(r'\s+', ' ', self._cur['text']).strip()
            if self._cur['text']:
                self.texts.append(self._cur)
            self._cur = None
            self.depth -= 1
        elif tag == 'svg':
            self.depth = 1
        elif tag == 'figure':
            self.depth = 0

    def handle_data(self, data):
        if self.depth >= 3 and self._cur is not None:
            self._cur['text'] += data

    def handle_entityref(self, name):
        if self.depth >= 3 and self._cur is not None:
            self._cur['text'] += {'lt': '<', 'gt': '>', 'amp': '&',
                                  'quot': '"', 'apos': "'"}.get(name, '?')

    def handle_charref(self, name):
        if self.depth >= 3 and self._cur is not None:
            try:
                self._cur['text'] += chr(int(name[1:], 16) if name[:1].lower() == 'x'
                                         else int(name))
            except ValueError:
                pass


def classes_of(c):
    return set(c.split())


def text_bbox(t):
    """Estimate a text element's bounding box."""
    cls = classes_of(t['cls'])
    fs = next((FONT[c] for c in cls if c in FONT), DEFAULT_FS)
    mono = bool(cls & MONO)
    cw = (W_MONO if mono else W_SANS) * fs
    w = len(t['text']) * cw
    x = t['x']
    if t['anchor'] == 0:
        x -= w / 2
    elif t['anchor'] == 1:
        x -= w
    return {'x1': x, 'x2': x + w, 'y1': t['y'] - fs * ASCENT,
            'y2': t['y'] + fs * DESCENT, 'text': t['text'], 'cls': t['cls']}


def overlap(a, b):
    ox = min(a['x2'], b['x2']) - max(a['x1'], b['x1'])
    oy = min(a['y2'], b['y2']) - max(a['y1'], b['y1'])
    return ox, oy


def seg_hits_box(seg, box):
    """Does the segment cross the box?"""
    (x1, y1), (x2, y2) = (seg['x1'], seg['y1']), (seg['x2'], seg['y2'])
    for t in (0.0, 0.25, 0.5, 0.75, 1.0):
        px = x1 + (x2 - x1) * t
        py = y1 + (y2 - y1) * t
        if box['x1'] <= px <= box['x2'] and box['y1'] <= py <= box['y2']:
            return True
    return False


def contains(rect, box, eps=2.0):
    """Is `box` fully inside `rect`? Then it is that rect's own label."""
    rx2, ry2 = rect['x'] + rect['width'], rect['y'] + rect['height']
    return (box['x1'] >= rect['x'] - eps and box['x2'] <= rx2 + eps
            and box['y1'] >= rect['y'] - eps and box['y2'] <= ry2 + eps)


def as_box(r):
    return {'x1': r['x'], 'x2': r['x'] + r['width'],
            'y1': r['y'], 'y2': r['y'] + r['height']}


def check_svg(sv, where, problems):
    if sv.viewbox is None:
        return
    vx, vy, vw, vh = sv.viewbox
    boxes = [text_bbox(t) for t in sv.texts]
    # background strips (.band) are decoration - text on one is fine
    rects = [r for r in sv.rects if 'band' not in classes_of(sv._rectcls.get(id(r), ''))]

    def owner(b):
        """The rect this label belongs to: the SMALLEST one containing it.
        Nested boxes mean the outermost match is not the right answer."""
        best, best_area = None, None
        for r in rects:
            if contains(r, b):
                a = r['width'] * r['height']
                if best_area is None or a < best_area:
                    best, best_area = r, a
        return best

    owners = [owner(b) for b in boxes]

    # 3 - anything outside the viewBox is clipped silently
    for b in boxes:
        if (b['x1'] < vx - 1 or b['x2'] > vx + vw + 1
                or b['y1'] < vy - 1 or b['y2'] > vy + vh + 1):
            problems.append('%s: text outside viewBox %r' % (where, b['text'][:44]))

    # 1 - text crossing into a rect it does not belong to
    for b, ow in zip(boxes, owners):
        for r in rects:
            if r is ow:
                continue
            # the label's own box nested inside this one is layering, not a collision
            if ow is not None and contains(r, as_box(ow)):
                continue
            ox, oy = overlap(b, as_box(r))
            if ox > CLEARANCE and oy > CLEARANCE:
                problems.append(
                    '%s: text %r crosses into the rect at (%g,%g) by %.1fx%.1f px'
                    % (where, b['text'][:36], r['x'], r['y'], ox, oy))

    # 2 - text over text, unless each sits in its own box
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if owners[i] is not None and owners[i] is not owners[j]:
                continue
            ox, oy = overlap(boxes[i], boxes[j])
            if ox > CLEARANCE and oy > CLEARANCE:
                problems.append('%s: text %r overlaps text %r by %.1fx%.1f px'
                                % (where, boxes[i]['text'][:26],
                                   boxes[j]['text'][:26], ox, oy))

    # 4 - an edge crossing a free-standing label
    for ln in sv.lines:
        if ln.get('path'):
            continue
        for b, ow in zip(boxes, owners):
            if ow is not None or 'el' in classes_of(b['cls']):
                continue
            if seg_hits_box(ln, b):
                problems.append('%s: edge crosses label %r' % (where, b['text'][:36]))
                break


def main():
    pats = sys.argv[1:]
    files = sorted(glob.glob(os.path.join(SITE, '*.html')))
    if pats:
        files = [f for f in files if any(os.path.basename(f).startswith(p) for p in pats)]
    total_problems = 0
    for f in files:
        problems = []
        src = open(f, encoding='utf-8').read()
        for m in re.finditer(r'<figure class="diagram">.*?</figure>', src, re.S):
            sv = Svg()
            sv.feed(m.group(0))
            check_svg(sv, os.path.basename(f), problems)
        if problems:
            total_problems += len(problems)
            print(os.path.basename(f))
            for p in problems:
                print('   ' + p)
    print('pages scanned: %d   problems: %d' % (len(files), total_problems))
    return 1 if total_problems else 0


if __name__ == '__main__':
    sys.exit(main())