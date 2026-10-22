#!/usr/bin/env python3
"""
CSES Problem Set downloader.

Pick a topic (e.g. "Dynamic Programming") and this script downloads EVERY
problem of that topic from https://cses.fi/problemset/ and renders each one as
a PDF, using the same look as codeforces_pdf.py.

IMPORTANT: keep this file in the same folder as codeforces_pdf.py, because it
reuses its fonts, styles and rendering helpers.

Usage examples:
    python cses_pdf.py --list                      # show all topics
    python cses_pdf.py "Dynamic Programming"       # all problems of a topic
    python cses_pdf.py graph                       # partial names work if unique
    python cses_pdf.py                             # interactive topic menu
"""

import argparse
import csv
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin
from xml.sax.saxutils import escape

import requests
from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer

try:
    import codeforces_pdf as cf
except ImportError:  # pragma: no cover
    sys.exit(
        "Could not import codeforces_pdf.py. Put cses_pdf.py in the same "
        "folder as codeforces_pdf.py and run it again."
    )

BASE_URL = "https://cses.fi"
LIST_URL = f"{BASE_URL}/problemset/list/"
cf.SESSION.headers["User-Agent"] = "CSESPDF/1.0 (personal educational project)"

SAMPLE_LABEL_RE = re.compile(r"^(input|output)\s*:?$", re.IGNORECASE)
LATEX_IN_CODE_RE = re.compile(r"\\[A-Za-z]+|\d\^\{?-?\w")


# --------------------------------------------------------------------------- #
# Topic list
# --------------------------------------------------------------------------- #

def parse_topics(html):
    """Return [(topic_name, [{'id': '1068', 'name': 'Weird Algorithm'}, ...])]."""
    soup = BeautifulSoup(html, "html.parser")
    topics, seen = [], set()

    for ul in soup.select("ul.task-list"):
        heading = ul.find_previous("h2")
        name = heading.get_text(" ", strip=True) if heading else "Unknown"
        problems = []
        for link in ul.select('a[href*="/problemset/task/"]'):
            match = re.search(r"/problemset/task/(\d+)", link["href"])
            if not match or match.group(1) in seen:
                continue
            seen.add(match.group(1))
            problems.append({
                "id": match.group(1),
                "name": link.get_text(" ", strip=True),
            })
        if problems:
            topics.append((name, problems))

    return topics


def fetch_topics():
    return parse_topics(cf.http_get(LIST_URL).text)


def choose_topic(topics, query):
    """Match a topic by exact name, then by unique substring (case-insensitive)."""
    q = query.strip().lower()
    exact = [t for t in topics if t[0].lower() == q]
    if exact:
        return exact[0]
    partial = [t for t in topics if q in t[0].lower()]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise ValueError(f'No topic matches "{query}". Use --list to see all topics.')
    names = ", ".join(t[0] for t in partial)
    raise ValueError(f'"{query}" is ambiguous. Matches: {names}')


def print_topics(topics):
    for number, (name, problems) in enumerate(topics, start=1):
        print(f"{number:>2}. {name} ({len(problems)} problems)")


def ask_topic_interactively(topics):
    print_topics(topics)
    answer = input("\nChoose a topic (number or name): ").strip()
    if answer.isdigit() and 1 <= int(answer) <= len(topics):
        return topics[int(answer) - 1]
    return choose_topic(topics, answer)


# --------------------------------------------------------------------------- #
# Problem page -> PDF
# --------------------------------------------------------------------------- #

MATH_DELIMITERS = [
    re.compile(r"\$\$(.+?)\$\$", re.DOTALL),                 # $$ ... $$
    re.compile(r"\\\((.+?)\\\)", re.DOTALL),               # \( ... \)
    re.compile(r"\\\[(.+?)\\\]", re.DOTALL),               # \[ ... \]
    re.compile(r"(?<!\$)\$([^$\n]+?)\$(?!\$)"),            # $ ... $
]


def _strip_math_delimiters(text):
    text = text.strip()
    for left, right in (("\\(", "\\)"), ("\\[", "\\]"), ("$$", "$$"), ("$", "$")):
        if text.startswith(left) and text.endswith(right) and len(text) >= len(left) + len(right):
            return text[len(left):-len(right)].strip()
    return text


def prepare_math(root):
    """Normalize every kind of math markup into $$$...$$$ (rendered by codeforces_pdf)."""
    # 1) MathJax/pandoc containers: <span class="math inline">\(...\)</span>, <script type="math/tex">
    for el in root.find_all(True):
        if el.parent is None:
            continue
        classes = {c.lower() for c in el.get("class", [])}
        is_math = (
            "math" in classes
            or any(c.startswith("math-") for c in classes)
            or (el.name == "script" and str(el.get("type", "")).startswith("math/tex"))
        )
        if is_math and el.find_parent("pre") is None:
            text = _strip_math_delimiters(el.get_text())
            el.replace_with(NavigableString(f"$$${text}$$$"))

    # 2) Inline <code> that contains LaTeX or exponents (not inside <pre>)
    for code in root.find_all("code"):
        if code.find_parent("pre") is None and LATEX_IN_CODE_RE.search(code.get_text()):
            code.replace_with(NavigableString(f"$$${code.get_text()}$$$"))

    # 3) Raw delimiters sitting in plain text nodes
    for node in list(root.find_all(string=True)):
        if isinstance(node, Comment) or node.parent is None:
            continue
        if node.find_parent(["pre", "code", "script", "style"]) is not None:
            continue
        text = str(node)
        if "$$$" in text:
            continue
        new_text = text
        for pattern in MATH_DELIMITERS:
            new_text = pattern.sub(lambda m: f"$$${m.group(1).strip()}$$$", new_text)
        if new_text != text:
            node.replace_with(NavigableString(new_text))


def problem_header(soup, problem, topic, url, st):
    title_el = soup.select_one(".title-block h1") or soup.select_one(".content h1")
    title = title_el.get_text(" ", strip=True) if title_el else problem["name"]

    story = [Paragraph(cf.clean(escape(title)), st["Title"])]

    constraints = soup.select(".task-constraints li")
    if constraints:
        lines = []
        for li in constraints:
            label_el = li.select_one(".task-constraint-label")
            label = label_el.get_text(strip=True) if label_el else ""
            if label_el:
                label_el.extract()
            lines.append((label, li.get_text(" ", strip=True)))
    else:  # fallback: search the page text
        text = soup.get_text(" ")
        lines = []
        for label in ("Time limit:", "Memory limit:"):
            m = re.search(re.escape(label) + r"\s*([\d.,]+\s*\w+)", text)
            if m:
                lines.append((label, m.group(1)))

    for label, value in lines:
        story.append(Paragraph(
            cf.clean(f'<font color="#666666">{escape(label)}</font> {escape(value)}'),
            st["Meta"],
        ))

    story.append(Spacer(1, 6))
    story.append(Paragraph(
        cf.clean(
            f"CSES {problem['id']} | {escape(topic)} | "
            f'<link href="{url}" color="#0000cc">{url}</link>'
        ),
        st["Info"],
    ))
    story.append(Spacer(1, 10))
    return story, title


def is_bold_only(tag):
    """True for <p><b>Heading</b></p>-style pseudo headings."""
    if tag.name != "p":
        return False
    parts = [c for c in tag.children
             if not (isinstance(c, NavigableString) and not c.strip())]
    return len(parts) == 1 and isinstance(parts[0], Tag) and parts[0].name in ("b", "strong")


def statement_flowables(soup, renderer, st):
    """Convert the statement body (.md) into flowables."""
    md = soup.select_one(".md") or soup.select_one(".content")
    if md is None:
        raise ValueError("Could not find the problem statement.")
    prepare_math(md)

    story, pending_label = [], None

    for node in list(md.children):
        if isinstance(node, Comment):
            continue
        if isinstance(node, NavigableString):
            if not node.strip():
                continue
        elif not isinstance(node, Tag):
            continue

        name = getattr(node, "name", None)
        text = node.get_text(" ", strip=True)

        # Section headings (Input, Output, Constraints, Example, ...).
        if name in ("h1", "h2", "h3", "h4", "h5", "h6") or (name and is_bold_only(node)):
            title = text.rstrip(":").strip()
            if title:
                story.append(Paragraph(cf.clean(escape(title)), st["SectionTitle"]))
            continue

        # "Input:" / "Output:" labels directly above a <pre> sample.
        if name == "p" and SAMPLE_LABEL_RE.match(text):
            following = node.find_next_sibling()
            if following is not None and following.name == "pre":
                pending_label = text.rstrip(":").strip().capitalize()
                continue

        if name == "pre":
            block = renderer.code_block(cf.pre_to_text(node))
            if pending_label:
                story.append(KeepTogether([
                    Paragraph(pending_label, st["SampleTitle"]), block,
                ]))
                pending_label = None
            else:
                story.append(block)
            story.append(Spacer(1, 4))
            continue

        # Everything else (paragraphs, lists, tables, images, loose text).
        wrapper = soup.new_tag("div")
        wrapper.append(node.extract() if isinstance(node, Tag) else NavigableString(str(node)))
        story.extend(renderer.blocks(wrapper))

    return story


def build_pdf(problem, topic, html, pdf_path):
    soup = BeautifulSoup(html, "html.parser")
    url = f"{BASE_URL}/problemset/task/{problem['id']}"

    st = cf.make_styles()
    renderer = cf.Renderer(st, url)

    story, title = problem_header(soup, problem, topic, url, st)
    story.extend(statement_flowables(soup, renderer, st))

    footer_left = f"CSES {problem['id']} - {title}"

    def draw_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(cf.setup_fonts().body, 8)
        canvas.setFillColor(colors.HexColor("#888888"))
        canvas.drawString(cf.PAGE_MARGIN, 1.0 * cm, cf.clean(footer_left))
        canvas.drawRightString(A4[0] - cf.PAGE_MARGIN, 1.0 * cm, f"Page {doc.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(pdf_path), pagesize=A4,
        leftMargin=cf.PAGE_MARGIN, rightMargin=cf.PAGE_MARGIN,
        topMargin=cf.PAGE_MARGIN, bottomMargin=2.0 * cm,
        title=title, author="CSES PDF Generator",
    )
    document.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    return pdf_path


def pdf_path_for(position, problem, folder):
    return folder / f"{position:02d}_{problem['id']}_{cf.safe_name(problem['name'])}.pdf"


# --------------------------------------------------------------------------- #
# Main workflow
# --------------------------------------------------------------------------- #

def download_topic(topic_name, problems, output_dir=None, delay=1.5,
                   overwrite=False, save_html=False):
    folder = Path(output_dir) if output_dir else Path(f"CSES_{cf.safe_name(topic_name)}")
    folder.mkdir(parents=True, exist_ok=True)
    print(f"Topic: {topic_name} ({len(problems)} problems)")

    with (folder / "index.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["position", "id", "name", "topic", "url", "pdf", "status"])

        for position, problem in enumerate(problems, start=1):
            url = f"{BASE_URL}/problemset/task/{problem['id']}"
            print(f"[{position}/{len(problems)}] {problem['id']}: {problem['name']}")

            target = pdf_path_for(position, problem, folder)
            pdf_name, status, fetched = "", "OK", False

            if target.exists() and not overwrite:
                pdf_name, status = target.name, "OK (already existed)"
                print("  Skipped (PDF already exists)")
            else:
                try:
                    html = cf.http_get(url).text
                    if save_html:
                        target.with_suffix(".html").write_text(html, encoding="utf-8")
                    pdf_name = build_pdf(problem, topic_name, html, target).name
                    fetched = True
                    print(f"  PDF created: {pdf_name}")
                except (requests.RequestException, ValueError, OSError) as error:
                    status = f"ERROR: {error}"
                    print(f"  Failed: {error}")

            writer.writerow([position, problem["id"], problem["name"],
                             topic_name, url, pdf_name, status])

            if fetched and position < len(problems):
                time.sleep(delay)

    print(f"\nDone! Files saved in: {folder.resolve()}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download all CSES problems of a topic as PDFs."
    )
    parser.add_argument("topic", nargs="?", default=None,
                        help='Topic name, e.g. "Dynamic Programming" (partial names work).')
    parser.add_argument("--list", action="store_true", help="List all topics and exit.")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--delay", type=float, default=1.5,
                        help="Seconds to wait between downloads.")
    parser.add_argument("--overwrite", action="store_true",
                        help="Regenerate PDFs that already exist.")
    parser.add_argument("--save-html", action="store_true",
                        help="Also save each problem's raw HTML next to its PDF (for debugging).")
    return parser.parse_args()


def main():
    args = parse_args()

    try:
        topics = fetch_topics()
    except requests.RequestException as error:
        sys.exit(f"Failed to fetch the CSES problem list: {error}")

    if not topics:
        sys.exit("No topics found. The CSES page layout may have changed.")

    if args.list:
        print_topics(topics)
        return

    try:
        name, problems = (
            choose_topic(topics, args.topic) if args.topic
            else ask_topic_interactively(topics)
        )
    except ValueError as error:
        sys.exit(str(error))

    download_topic(name, problems, args.output_dir, args.delay,
                   args.overwrite, args.save_html)


if __name__ == "__main__":
    main()
