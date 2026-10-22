#!/usr/bin/env python3
"""
Codeforces problem downloader.

Usage examples:
    python codeforces_pdf.py
    python codeforces_pdf.py --tag dp --min-rating 1500 --max-rating 1700 --limit 20
    python codeforces_pdf.py --tag graphs --tag dfs\\ and\\ similar --overwrite

Tags:
1 - Fundamentals
- implementation
- brute force
- greedy
- constructive algorithms
- two pointers
- sortings
- binary search
- ternary search
- bitmasks

2 - Math & Number Theory
- math
- number theory
- combinatorics
- geometry
- two pointers
- probabilities
- matrices
- fft(Fast Fourier Transform)
- chinese remainder theorem
- games

3 -Data Structure & Advanced Algorithms
- data structures
- dsu
- dp
- strings
- string suffix structures:
- hashing
- expression parsing
- divide and conque
- meet-in-the-middle

4 - Graph
- graphs
- trees
- dfs
- shortest paths
- graph matchings
- flows
- 2-sat

5 - Graph
- interactive: Problemas onde o seu programa deve "interagir" com o corretor (fazer perguntas e ler respostas em tempo real).
- schedules: Escalonamento de tarefas.
- *special: Problemas de maratonas especiais, fora do padrão comum de formato.

Range of rating (800 - 3500)

"""

import argparse
import csv
import io
import random
import re
import time
from collections import namedtuple
from pathlib import Path
from urllib.parse import urljoin
from xml.sax.saxutils import escape
 
import requests
from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    XPreformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
 
# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
 
API_URL = "https://codeforces.com/api/problemset.problems"
BASE_URL = "https://codeforces.com"
HEADERS = {"User-Agent": "CodeforcesPDF/2.0 (personal educational project)"}
 
PAGE_MARGIN = 2.0 * cm
TEXT_WIDTH = A4[0] - 2 * PAGE_MARGIN
 
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
 
# --------------------------------------------------------------------------- #
# Fonts (Codeforces uses a sans-serif body font and monospaced samples)
# --------------------------------------------------------------------------- #
 
# (regular, bold, italic, bold-italic) -- first family found on the system wins.
SANS_CANDIDATES = [
    (  # Windows: Verdana (closest to Codeforces)
        "C:/Windows/Fonts/verdana.ttf", "C:/Windows/Fonts/verdanab.ttf",
        "C:/Windows/Fonts/verdanai.ttf", "C:/Windows/Fonts/verdanaz.ttf",
    ),
    (  # macOS: Verdana
        "/System/Library/Fonts/Supplemental/Verdana.ttf",
        "/System/Library/Fonts/Supplemental/Verdana Bold.ttf",
        "/System/Library/Fonts/Supplemental/Verdana Italic.ttf",
        "/System/Library/Fonts/Supplemental/Verdana Bold Italic.ttf",
    ),
    (  # Linux: DejaVu Sans (very wide Unicode coverage)
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
    ),
    (  # Linux: Liberation Sans
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf",
    ),
    (  # Windows: Arial
        "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/ariali.ttf", "C:/Windows/Fonts/arialbi.ttf",
    ),
]
 
MONO_CANDIDATES = [
    ("C:/Windows/Fonts/cour.ttf", "C:/Windows/Fonts/courbd.ttf"),
    ("/System/Library/Fonts/Supplemental/Courier New.ttf",
     "/System/Library/Fonts/Supplemental/Courier New Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf"),
]
 
Fonts = namedtuple("Fonts", "body mono unicode")
_FONTS = None  # cached after the first call to setup_fonts()
 
 
def _first_complete(candidates):
    for family in candidates:
        if all(Path(p).exists() for p in family):
            return family
    return None
 
 
def setup_fonts():
    """Register the best available fonts (once) and return their names."""
    global _FONTS
    if _FONTS is not None:
        return _FONTS
 
    sans = _first_complete(SANS_CANDIDATES)
    if sans:
        names = ["CF-Sans", "CF-Sans-Bold", "CF-Sans-Italic", "CF-Sans-BoldItalic"]
        for name, path in zip(names, sans):
            pdfmetrics.registerFont(TTFont(name, path))
        pdfmetrics.registerFontFamily(
            "CF-Sans", normal=names[0], bold=names[1],
            italic=names[2], boldItalic=names[3],
        )
        body, unicode_ok = "CF-Sans", True
    else:
        body, unicode_ok = "Helvetica", False  # built-in, ASCII/Latin-1 only
 
    mono_files = _first_complete(MONO_CANDIDATES)
    if mono_files:
        pdfmetrics.registerFont(TTFont("CF-Mono", mono_files[0]))
        pdfmetrics.registerFont(TTFont("CF-Mono-Bold", mono_files[1]))
        pdfmetrics.registerFontFamily(
            "CF-Mono", normal="CF-Mono", bold="CF-Mono-Bold",
            italic="CF-Mono", boldItalic="CF-Mono-Bold",
        )
        mono = "CF-Mono"
    else:
        mono = "Courier"
 
    _FONTS = Fonts(body, mono, unicode_ok)
    return _FONTS
 
 
# Used only when no Unicode TrueType font is available on the machine.
ASCII_FALLBACK = {
    "≤": "<=", "≥": ">=", "≠": "!=", "×": "x", "·": "*", "…": "...",
    "√": "sqrt", "⊕": "xor", "∑": "sum", "∏": "prod", "∞": "inf",
    "→": "->", "←": "<-", "⇒": "=>", "∈": " in ", "∉": " not in ",
    "⌊": "floor(", "⌋": ")", "⌈": "ceil(", "⌉": ")", "−": "-",
    "≈": "~", "≡": "==", "∧": "&&", "∨": "||", "¬": "!", "÷": "/",
}
 
 
def clean(text):
    """Make text safe for the active fonts (no-op with Unicode fonts)."""
    if setup_fonts().unicode:
        return text
    for src, dst in ASCII_FALLBACK.items():
        text = text.replace(src, dst)
    return text.encode("cp1252", "replace").decode("cp1252")
 
 
# --------------------------------------------------------------------------- #
# LaTeX ($$$ ... $$$) -> ReportLab paragraph markup
# --------------------------------------------------------------------------- #
 
MATH_RE = re.compile(r"\${6}(.+?)\${6}|\${3}(.+?)\${3}", re.DOTALL)
 
TEX_SYMBOLS = {
    "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "ne": "≠", "neq": "≠",
    "cdot": "·", "times": "×", "ldots": "…", "dots": "…", "cdots": "…",
    "lfloor": "⌊", "rfloor": "⌋", "lceil": "⌈", "rceil": "⌉",
    "to": "→", "rightarrow": "→", "leftarrow": "←", "Rightarrow": "⇒",
    "infty": "∞", "pm": "±", "oplus": "⊕", "sum": "∑", "prod": "∏",
    "in": "∈", "notin": "∉", "cup": "∪", "cap": "∩", "land": "∧",
    "lor": "∨", "neg": "¬", "equiv": "≡", "approx": "≈", "div": "÷",
    "mid": "|", "lvert": "|", "rvert": "|", "vert": "|", "ll": "≪", "gg": "≫",
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "lambda": "λ", "mu": "μ", "pi": "π", "sigma": "σ", "phi": "φ",
    "theta": "θ", "omega": "ω", "Sigma": "Σ", "Delta": "Δ", "Omega": "Ω",
    "forall": "∀", "exists": "∃", "emptyset": "∅", "langle": "⟨", "rangle": "⟩",
    "lbrace": "{", "rbrace": "}", "quad": "  ", "qquad": "    ",
    "bmod": " mod ", "mod": " mod ",
}
TEX_FUNCTIONS = {
    "min", "max", "log", "ln", "gcd", "lcm", "sin", "cos", "tan", "exp",
    "lim", "sup", "inf", "deg", "det", "arg",
}
TEX_TEXT_COMMANDS = {
    "text", "mathrm", "textrm", "mbox", "operatorname", "mathit",
    "mathcal", "mathbb", "overline", "bar", "hat", "boldsymbol",
}
TEX_IGNORED = {
    "left", "right", "big", "Big", "bigl", "bigr", "Bigl", "Bigr",
    "displaystyle", "limits", "nolimits", "textstyle",
}
_CMD_RE = re.compile(r"\\([A-Za-z]+)")
 
 
def _read_arg(s, i):
    """Read one TeX argument starting at s[i]; return (content, next_index)."""
    while i < len(s) and s[i] == " ":
        i += 1
    if i >= len(s):
        return "", i
    if s[i] == "{":
        depth, j = 0, i
        while j < len(s):
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0:
                    return s[i + 1:j], j + 1
            j += 1
        return s[i + 1:], len(s)
    m = _CMD_RE.match(s, i)
    if m:
        return m.group(0), m.end()
    return s[i], i + 1
 
 
def _wrap(raw, rendered):
    """Parenthesize multi-character fraction parts."""
    return f"({rendered})" if len(raw.strip()) > 1 else rendered
 
 
def _parse_tex(s, italic=True):
    out, i = [], 0
    while i < len(s):
        c = s[i]
 
        if c == "\\":
            m = _CMD_RE.match(s, i)
            if m:
                name, i = m.group(1), m.end()
                if name in ("frac", "dfrac", "tfrac"):
                    a, i = _read_arg(s, i)
                    b, i = _read_arg(s, i)
                    out.append(
                        f"{_wrap(a, _parse_tex(a, italic))}/"
                        f"{_wrap(b, _parse_tex(b, italic))}"
                    )
                elif name == "binom":
                    a, i = _read_arg(s, i)
                    b, i = _read_arg(s, i)
                    out.append(f"C({_parse_tex(a, italic)}, {_parse_tex(b, italic)})")
                elif name == "sqrt":
                    if i < len(s) and s[i] == "[":  # ignore the root index
                        i = s.find("]", i) + 1 or len(s)
                    a, i = _read_arg(s, i)
                    out.append("√" + _wrap(a, _parse_tex(a, italic)))
                elif name in ("textbf", "mathbf"):
                    a, i = _read_arg(s, i)
                    out.append(f"<b>{_parse_tex(a, False)}</b>")
                elif name == "texttt":
                    a, i = _read_arg(s, i)
                    face = setup_fonts().mono
                    out.append(f'<font face="{face}">{_parse_tex(a, False)}</font>')
                elif name in TEX_TEXT_COMMANDS:
                    a, i = _read_arg(s, i)
                    out.append(_parse_tex(a, False))
                elif name in TEX_IGNORED:
                    if name in ("left", "right") and i < len(s) and s[i] == ".":
                        i += 1
                elif name in TEX_SYMBOLS:
                    out.append(TEX_SYMBOLS[name])
                elif name in TEX_FUNCTIONS:
                    out.append(name)
                else:
                    out.append(escape(name))
            else:
                nxt = s[i + 1] if i + 1 < len(s) else ""
                i += 2
                if nxt in ",;:!":
                    out.append(" " if nxt != "!" else "")
                elif nxt == "\\":
                    out.append("<br/>")
                elif nxt:
                    out.append(escape(nxt))
 
        elif c in "^_":
            arg, i = _read_arg(s, i + 1)
            tag = "super" if c == "^" else "sub"
            out.append(f"<{tag}>{_parse_tex(arg, italic)}</{tag}>")
 
        elif c == "{":
            arg, i = _read_arg(s, i)
            out.append(_parse_tex(arg, italic))
 
        elif c == "}":
            i += 1
 
        elif c.isalpha():
            out.append(f"<i>{c}</i>" if italic else c)
            i += 1
 
        elif c == "~":
            out.append(" ")
            i += 1
 
        else:
            out.append(escape(c))
            i += 1
 
    return "".join(out).replace("</i><i>", "")
 
 
def tex_to_markup(tex):
    return _parse_tex(tex.strip())
 
 
# --------------------------------------------------------------------------- #
# HTML -> ReportLab markup / flowables
# --------------------------------------------------------------------------- #
 
INLINE_TAGS = {
    "span", "i", "b", "em", "strong", "a", "code", "tt", "kbd", "sub",
    "sup", "br", "img", "u", "small", "big", "font",
}
 
 
def classes_of(tag):
    return set(tag.get("class", []))
 
 
def text_to_markup(text):
    """Escape plain text, converting any $$$ math segments."""
    parts, pos = [], 0
    for m in MATH_RE.finditer(text):
        parts.append(escape(re.sub(r"\s+", " ", text[pos:m.start()])))
        parts.append(tex_to_markup(m.group(1) or m.group(2)))
        pos = m.end()
    parts.append(escape(re.sub(r"\s+", " ", text[pos:])))
    return "".join(parts)
 
 
def inline_markup(node):
    """Convert an HTML node into ReportLab inline markup."""
    if isinstance(node, Comment):
        return ""
    if isinstance(node, NavigableString):
        return text_to_markup(str(node))
    if not isinstance(node, Tag) or node.name in ("script", "style", "img"):
        return ""
    if node.name == "br":
        return "<br/>"
 
    inner = "".join(inline_markup(child) for child in node.children)
    cls = classes_of(node)
 
    if node.name in ("i", "em") or "tex-font-style-it" in cls:
        return f"<i>{inner}</i>"
    if node.name in ("b", "strong") or "tex-font-style-bf" in cls:
        return f"<b>{inner}</b>"
    if node.name in ("code", "tt", "kbd") or "tex-font-style-tt" in cls:
        return f'<font face="{setup_fonts().mono}">{inner}</font>'
    if node.name == "u":
        return f"<u>{inner}</u>"
    if node.name == "sub":
        return f"<sub>{inner}</sub>"
    if node.name == "sup":
        return f"<super>{inner}</super>"
    return inner
 
 
def make_image(src, page_url, max_w=TEXT_WIDTH * 0.8, max_h=9 * cm):
    """Download an image and return a scaled flowable (or None on failure)."""
    try:
        response = SESSION.get(urljoin(page_url, src), timeout=30)
        response.raise_for_status()
        width, height = ImageReader(io.BytesIO(response.content)).getSize()
        scale = min(1.0, max_w / width, max_h / height)
        return Image(
            io.BytesIO(response.content),
            width=width * scale, height=height * scale, hAlign="CENTER",
        )
    except Exception:
        return None
 
 
def pre_to_text(pre):
    """Extract preformatted text, honoring <br> and Codeforces' line divs."""
    for br in pre.find_all("br"):
        br.replace_with("\n")
    lines = pre.select(".test-example-line")
    if lines:
        text = "\n".join(line.get_text() for line in lines)
    else:
        text = pre.get_text()
    return text.replace("\r", "").strip("\n")
 
 
class Renderer:
    """Turns Codeforces HTML fragments into ReportLab flowables."""
 
    def __init__(self, styles, page_url):
        self.st = styles
        self.page_url = page_url
        fonts = setup_fonts()
        self.mono_char_width = pdfmetrics.stringWidth("0", fonts.mono, 8.5)
 
    # -- helpers ----------------------------------------------------------- #
    def para(self, markup, style):
        markup = markup.strip()
        return Paragraph(clean(markup), style) if markup else None
 
    def images_in(self, node, only=None):
        found = []
        for img in ([only] if only is not None else node.find_all("img")):
            flowable = make_image(img.get("src", ""), self.page_url)
            if flowable is not None:
                found.append(Spacer(1, 4))
                found.append(flowable)
                found.append(Spacer(1, 6))
        return found
 
    def code_block(self, text):
        max_chars = int((TEXT_WIDTH - 16) / self.mono_char_width)
        lines = []
        for line in text.split("\n"):
            while len(line) > max_chars:  # wrap long lines, preferably at spaces
                cut = line.rfind(" ", 0, max_chars)
                cut = cut if cut > 0 else max_chars
                lines.append(line[:cut])
                line = line[cut:].lstrip(" ") if line[cut:cut + 1] == " " else line[cut:]
            lines.append(line)
        return XPreformatted(clean(escape("\n".join(lines))), self.st["SampleCode"])
 
    # -- block conversion -------------------------------------------------- #
    def blocks(self, element):
        flowables, buffer, buffer_imgs = [], [], []
 
        def flush():
            nonlocal buffer, buffer_imgs
            p = self.para("".join(buffer), self.st["Body"])
            if p:
                flowables.append(p)
            flowables.extend(buffer_imgs)
            buffer, buffer_imgs = [], []
 
        for child in element.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                buffer.append(inline_markup(child))
                continue
            if not isinstance(child, Tag):
                continue
 
            if child.name in INLINE_TAGS:
                buffer.append(inline_markup(child))
                if child.name == "img":
                    buffer_imgs.extend(self.images_in(child.parent, only=child))
                elif child.find("img"):
                    buffer_imgs.extend(self.images_in(child))
                continue
 
            flush()
 
            if child.name in ("script", "style"):
                continue
            if child.name == "p":
                p = self.para(inline_markup(child), self.st["Body"])
                if p:
                    flowables.append(p)
                flowables.extend(self.images_in(child))
            elif child.name in ("ul", "ol"):
                flowables.extend(self.list_items(child))
            elif child.name == "pre":
                flowables.append(self.code_block(pre_to_text(child)))
                flowables.append(Spacer(1, 6))
            elif child.name == "table":
                table = self.table(child)
                if table is not None:
                    flowables.append(table)
                    flowables.append(Spacer(1, 8))
            elif child.name in ("h1", "h2", "h3", "h4"):
                p = self.para(f"<b>{inline_markup(child)}</b>", self.st["Body"])
                if p:
                    flowables.append(p)
            else:  # div, center, blockquote, ...
                flowables.extend(self.blocks(child))
 
        flush()
        return flowables
 
    def list_items(self, list_tag):
        items = []
        ordered = list_tag.name == "ol"
        for number, li in enumerate(list_tag.find_all("li", recursive=False), 1):
            bullet = f"{number}." if ordered else "•"
            markup = "".join(
                inline_markup(c) for c in li.children
                if not (isinstance(c, Tag) and c.name in ("ul", "ol"))
            )
            p = Paragraph(
                clean(markup.strip()), self.st["ListItem"],
                bulletText=clean(bullet),
            )
            items.append(p)
            for nested in li.find_all(["ul", "ol"], recursive=False):
                items.extend(self.list_items(nested))
        items.append(Spacer(1, 3))
        return items
 
    def table(self, table_tag):
        rows = []
        for tr in table_tag.find_all("tr"):
            cells = [
                Paragraph(clean(inline_markup(td).strip() or " "), self.st["TableCell"])
                for td in tr.find_all(["td", "th"])
            ]
            if cells:
                rows.append(cells)
        if not rows:
            return None
        columns = max(len(r) for r in rows)
        for r in rows:
            r.extend([""] * (columns - len(r)))
        table = Table(rows, colWidths=[TEXT_WIDTH / columns] * columns, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        return table
 
    # -- Codeforces-specific pieces ---------------------------------------- #
    def section(self, title, content):
        """A titled section; the title stays attached to the first block."""
        if not content:
            return []
        head = Paragraph(clean(escape(title)), self.st["SectionTitle"])
        return [KeepTogether([head, content[0]])] + content[1:]
 
    def samples(self, sample_tests_div):
        """Render EVERY input/output pair, in the original order."""
        containers = sample_tests_div.select(".sample-test") or [sample_tests_div]
        boxes = []
        for container in containers:
            # One .sample-test normally holds several .input/.output divs.
            direct = [
                d for d in container.find_all("div", recursive=False)
                if classes_of(d) & {"input", "output"}
            ]
            boxes.extend(direct or container.select("div.input, div.output"))
 
        flowables, count = [], 0
        for box in boxes:
            pre = box.select_one("pre")
            if pre is None:
                continue
            kind = "Input" if "input" in classes_of(box) else "Output"
            count += kind == "Input"
            flowables.append(KeepTogether([
                Paragraph(kind, self.st["SampleTitle"]),
                self.code_block(pre_to_text(pre)),
            ]))
            if kind == "Output":
                flowables.append(Spacer(1, 6))
 
        if not flowables:
            return []
        title = "Example" if count <= 1 else "Examples"
        return [Paragraph(title, self.st["SectionTitle"])] + flowables
 
 
# --------------------------------------------------------------------------- #
# Styles
# --------------------------------------------------------------------------- #
 
def make_styles():
    fonts = setup_fonts()
    base = getSampleStyleSheet()["Normal"]
    bold = fonts.body + "-Bold"
    gray = colors.HexColor("#666666")
    box_border = colors.HexColor("#c8c8c8")
 
    def style(name, **kw):
        kw.setdefault("parent", base)
        return ParagraphStyle(name, **kw)
 
    return {
        "Body": style(
            "Body", fontName=fonts.body, fontSize=10, leading=15,
            spaceAfter=7, alignment=TA_LEFT,
        ),
        "Title": style(
            "ProblemTitle", fontName=bold, fontSize=20, leading=26,
            alignment=TA_CENTER, spaceAfter=6,
        ),
        "Meta": style(
            "Meta", fontName=fonts.body, fontSize=9.5, leading=13.5,
            alignment=TA_CENTER,
        ),
        "Info": style(
            "Info", fontName=fonts.body, fontSize=8, leading=11,
            alignment=TA_CENTER, textColor=gray,
        ),
        "SectionTitle": style(
            "SectionTitle", fontName=bold, fontSize=13, leading=17,
            spaceBefore=12, spaceAfter=6, keepWithNext=1,
        ),
        "ListItem": style(
            "ListItem", fontName=fonts.body, fontSize=10, leading=15,
            leftIndent=22, bulletIndent=8, spaceAfter=3,
            bulletFontName=fonts.body,
        ),
        "TableCell": style(
            "TableCell", fontName=fonts.body, fontSize=9, leading=12,
        ),
        "SampleTitle": style(
            "SampleTitle", fontName=bold, fontSize=9, leading=12,
            leftIndent=3, rightIndent=3, backColor=colors.HexColor("#e9e9e9"),
            borderColor=box_border, borderWidth=0.5, borderPadding=3,
            spaceBefore=8, spaceAfter=3, keepWithNext=1,
        ),
        "SampleCode": style(
            "SampleCode", fontName=fonts.mono, fontSize=8.5, leading=11,
            leftIndent=3, rightIndent=3, backColor=colors.HexColor("#f6f6f6"),
            borderColor=box_border, borderWidth=0.5, borderPadding=3,
            spaceBefore=3, spaceAfter=4,
        ),
    }
 
 
# --------------------------------------------------------------------------- #
# Filtering / file naming
# --------------------------------------------------------------------------- #
 
def safe_name(text):
    """Remove characters that are problematic in file names."""
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text)
    return re.sub(r"\s+", "_", text).strip("_")[:100]
 
 
def problem_url(problem):
    return f"{BASE_URL}/problemset/problem/{problem['contestId']}/{problem['index']}"
 
 
def pdf_path_for(problem, folder):
    return folder / (
        f"[{problem['rating']}]_{problem['contestId']}{problem['index']}_"
        f"{safe_name(problem['name'])}.pdf"
    )
 
 
def http_get(url, retries=4):
    """GET with retry/backoff for rate limits and transient server errors."""
    for attempt in range(1, retries + 1):
        try:
            response = SESSION.get(url, timeout=30)
            if response.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            return response
        except (requests.ConnectionError, requests.Timeout):
            if attempt == retries:
                raise
            time.sleep(2 ** attempt)
 
 
def fetch_problems():
    """Fetch problem metadata from the official API."""
    data = http_get(API_URL).json()
    if data.get("status") != "OK":
        raise RuntimeError(data.get("comment", "API error"))
    return data["result"]["problems"]
 
 
def filter_problems(problems, tags, rating_min, rating_max):
    """Keep problems that have ALL the given tags and a rating in range."""
    wanted = {t.lower() for t in tags}
    result = []
    for p in problems:
        rating = p.get("rating")
        if rating is None or p.get("contestId") is None:
            continue
        if not wanted <= {t.lower() for t in p.get("tags", [])}:
            continue
        if rating_min <= rating <= rating_max:
            result.append(p)
    result.sort(key=lambda p: (p["rating"], p["contestId"], p["index"]))
    return result
 
 
# --------------------------------------------------------------------------- #
# PDF generation
# --------------------------------------------------------------------------- #
 
def build_header(problem, statement, st):
    """Title + limits block, centered like the Codeforces page header."""
    story = [Paragraph(
        clean(escape(f"{problem['index']}. {problem['name']}")), st["Title"]
    )]
 
    header = statement.select_one(".header")
    if header is not None:
        for cls in ("time-limit", "memory-limit", "input-file", "output-file"):
            el = header.select_one(f".{cls}")
            if el is None:
                continue
            title_el = el.select_one(".property-title")
            label = title_el.get_text(" ", strip=True) if title_el else ""
            if title_el:
                title_el.extract()
            value = el.get_text(" ", strip=True)
            story.append(Paragraph(
                clean(f'<font color="#666666">{escape(label)}</font> {escape(value)}'),
                st["Meta"],
            ))
 
    url = problem_url(problem)
    tags = ", ".join(problem.get("tags", [])) or "-"
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        clean(
            f"Rating: {problem['rating']} | Tags: {escape(tags)} | "
            f'<link href="{url}" color="#0000cc">{url}</link>'
        ),
        st["Info"],
    ))
    story.append(Spacer(1, 10))
    return story
 
 
def build_pdf(problem, html, pdf_path):
    """Render the problem HTML into a PDF file."""
    soup = BeautifulSoup(html, "html.parser")
    statement = soup.select_one(".problem-statement")
    if statement is None:
        raise ValueError("Could not find the problem statement.")
 
    st = make_styles()
    renderer = Renderer(st, problem_url(problem))
    story = build_header(problem, statement, st)
 
    for div in statement.find_all("div", recursive=False):
        cls = classes_of(div)
 
        if "header" in cls:
            continue
        if not cls:  # the legend (main description) has no class
            story.extend(renderer.blocks(div))
        elif "sample-tests" in cls:
            story.extend(renderer.samples(div))
        else:  # input-specification, output-specification, note, interaction...
            title_el = div.select_one(".section-title")
            title = (
                title_el.get_text(strip=True) if title_el
                else next(iter(cls)).replace("-", " ").title()
            )
            if title_el:
                title_el.decompose()
            story.extend(renderer.section(title, renderer.blocks(div)))
 
    footer_left = f"Codeforces {problem['contestId']}{problem['index']} - {problem['name']}"
 
    def draw_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(setup_fonts().body, 8)
        canvas.setFillColor(colors.HexColor("#888888"))
        canvas.drawString(PAGE_MARGIN, 1.0 * cm, clean(footer_left))
        canvas.drawRightString(A4[0] - PAGE_MARGIN, 1.0 * cm, f"Page {doc.page}")
        canvas.restoreState()
 
    document = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=PAGE_MARGIN, rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN, bottomMargin=2.0 * cm,
        title=f"{problem['index']}. {problem['name']}",
        author="Codeforces PDF Generator",
    )
    document.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    return pdf_path
 
 
def create_pdf(problem, folder):
    """Download a problem statement and generate its PDF."""
    response = http_get(problem_url(problem))
    return build_pdf(problem, response.text, pdf_path_for(problem, folder))
 
 
# --------------------------------------------------------------------------- #
# Main workflow
# --------------------------------------------------------------------------- #
 
def pick_problems(problems, limit, shuffle=True, seed=None):
    """Pick `limit` problems; random across the whole range unless shuffle=False."""
    if not shuffle or len(problems) <= limit:
        return problems[:limit], None
    if seed is None:
        seed = random.randrange(10 ** 9)
    chosen = random.Random(seed).sample(problems, limit)
    chosen.sort(key=lambda p: (p["rating"], p["contestId"], p["index"]))
    return chosen, seed
 
 
def download_problems(tags, rating_min, rating_max, limit=10,
                      output_dir=None, delay=2.0, overwrite=False,
                      shuffle=True, seed=None):
    if rating_min < 0 or rating_max < rating_min:
        raise ValueError("Invalid rating range.")
    if limit < 1:
        raise ValueError("The limit must be at least 1.")
 
    print(f"Fetching problems with tag(s): {', '.join(tags)}")
    try:
        problems = fetch_problems()
    except (requests.RequestException, ValueError, RuntimeError) as error:
        print(f"Failed to fetch problems: {error}")
        return
 
    filtered = filter_problems(problems, tags, rating_min, rating_max)
    selected, used_seed = pick_problems(filtered, limit, shuffle, seed)
    print(f"Found: {len(filtered)}")
    print(f"Selected: {len(selected)}"
          + (f" (random, seed={used_seed})" if used_seed is not None else ""))
 
    if not selected:
        print("No problems match these criteria.")
        return
 
    folder = Path(output_dir) if output_dir else Path(
        f"Codeforces_{safe_name('+'.join(tags))}_{rating_min}_to_{rating_max}"
    )
    folder.mkdir(parents=True, exist_ok=True)
 
    with (folder / "index.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["contestId", "index", "name", "rating", "tags", "url", "pdf", "status"]
        )
 
        for position, problem in enumerate(selected, start=1):
            label = f"{problem['contestId']}{problem['index']}"
            print(f"[{position}/{len(selected)}] {label}: {problem['name']}")
 
            target = pdf_path_for(problem, folder)
            pdf_name, status, fetched = "", "OK", False
 
            if target.exists() and not overwrite:
                pdf_name, status = target.name, "OK (already existed)"
                print("  Skipped (PDF already exists)")
            else:
                try:
                    pdf_name = create_pdf(problem, folder).name
                    fetched = True
                    print(f"  PDF created: {pdf_name}")
                except (requests.RequestException, ValueError, OSError) as error:
                    status = f"ERROR: {error}"
                    print(f"  Failed: {error}")
 
            writer.writerow([
                problem["contestId"], problem["index"], problem["name"],
                problem["rating"], ";".join(problem.get("tags", [])),
                problem_url(problem), pdf_name, status,
            ])
 
            # Be polite to the server between page downloads.
            if fetched and position < len(selected):
                time.sleep(delay)
 
    print(f"\nDone! Files saved in: {folder.resolve()}")
 
 
def parse_args():
    parser = argparse.ArgumentParser(
        description="Download Codeforces problems as Codeforces-styled PDFs."
    )
    parser.add_argument("--tag", action="append", default=None,
                        help="Problem tag (repeat to require several). Default: graphs")
    parser.add_argument("--min-rating", type=int, default=1200)
    parser.add_argument("--max-rating", type=int, default=1400)
    parser.add_argument("--limit", type=int, default=10,
                        help="Maximum number of problems to download.")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Seconds to wait between downloads.")
    parser.add_argument("--seed", type=int, default=None,
                        help="Seed for the random selection (reproducible picks).")
    parser.add_argument("--no-shuffle", action="store_true",
                        help="Take the first N problems (lowest rating first) "
                             "instead of a random sample.")
    parser.add_argument("--overwrite", action="store_true",
                        help="Regenerate PDFs that already exist.")
    return parser.parse_args()
 
 
if __name__ == "__main__":
    args = parse_args()
    download_problems(
        tags=args.tag,
        rating_min=args.min_rating,
        rating_max=args.max_rating,
        limit=args.limit,
        output_dir=args.output_dir,
        delay=args.delay,
        overwrite=args.overwrite,
        shuffle=not args.no_shuffle,
        seed=args.seed,
    )
 
