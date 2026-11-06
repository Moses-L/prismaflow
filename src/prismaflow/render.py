"""Render PRISMA 2020 flow diagrams with Graphviz."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Iterable, List, Optional, Union

from graphviz import Digraph

from .data import PrismaData

STATIC_FORMATS = ("png", "svg", "pdf")
ALL_FORMATS = STATIC_FORMATS + ("html", "dot")

BLUE = "#cfe2f3"
GREY = "#eeeeee"
WHITE = "#ffffff"

# node id -> key used to look up url / tooltip in PrismaData
_LINK_KEYS = {
    "prev": "previous_studies",
    "ident": "identified_databases",
    "removed": "duplicates",
    "scr": "screened",
    "exc": "excluded_screening",
    "sought": "sought",
    "notret": "not_retrieved",
    "assessed": "assessed",
    "ftexc": "excluded_fulltext",
    "final": "total_studies",
    "o_ident": "other_websites",
    "o_sought": "other_sought",
    "o_notret": "other_not_retrieved",
    "o_assessed": "other_assessed",
    "o_ftexc": "other_excluded",
}


def _left(lines: List[str]) -> str:
    """Left-aligned multi-line label (Graphviz \\l line terminators)."""
    return "".join(f"{ln}\\l" for ln in lines)


def _centre(lines: List[str]) -> str:
    return "\\n".join(lines)


def build_graph(data: PrismaData, dpi: Optional[int] = None, title: Optional[str] = None) -> Digraph:
    """Build the Graphviz graph for ``data`` (validates the counts first)."""
    data.validate()
    g = Digraph("PRISMA2020")
    g.attr(rankdir="TB", splines="ortho", nodesep="0.35", ranksep="0.55", newrank="true", pad="0.2")
    if dpi:
        g.attr(dpi=str(dpi))
    if title:
        g.attr(label=title, labelloc="t", fontname="Helvetica-Bold", fontsize="16")
    g.attr("node", shape="box", fontname="Helvetica", fontsize="11", margin="0.15,0.08", width="3.1")
    g.attr("edge", arrowsize="0.7", penwidth="1.1")

    def node(nid: str, label: str, fill: str = WHITE, **kw) -> None:
        attrs = dict(label=label, style="filled", fillcolor=fill, **kw)
        key = _LINK_KEYS.get(nid)
        if key and key in data.urls:
            attrs["URL"] = data.urls[key]
            attrs["target"] = "_blank"
        if key and key in data.tooltips:
            attrs["tooltip"] = data.tooltips[key]
        elif key and key in data.urls:
            attrs["tooltip"] = data.urls[key]
        g.node(nid, **attrs)

    def reasons(title_line: str, mapping) -> str:
        lines = [title_line] + [f"{k} (n = {v})" for k, v in mapping.items()]
        return _left(lines)

    # --- phase labels ---------------------------------------------------
    for pid, text in (("ph_id", "Identification"), ("ph_scr", "Screening"), ("ph_inc", "Included")):
        node(pid, text, BLUE, width="1.4", fontname="Helvetica-Bold")

    # --- row 0: identification -----------------------------------------
    ident_lines = ["Records identified from:"]
    ident_lines.append(f"Databases (n = {data.get('identified_databases')})")
    ident_lines.append(f"Registers (n = {data.get('identified_registers')})")
    node("ident", _centre(ident_lines))
    node(
        "removed",
        _left(
            [
                "Records removed before screening:",
                f"Duplicate records (n = {data.get('duplicates')})",
                f"Automation tools (n = {data.get('excluded_automatic')})",
                f"Other reasons (n = {data.get('excluded_other')})",
            ]
        ),
        GREY,
    )
    if data.use_previous:
        node(
            "prev",
            _centre(
                [
                    "Previous studies",
                    "Studies included in previous",
                    f"version of review (n = {data.get('previous_studies')})",
                    "Reports of studies included in",
                    f"previous version (n = {data.get('previous_reports')})",
                ]
            ),
            width="2.4",
        )
    if data.use_other:
        node(
            "o_ident",
            _centre(
                [
                    "Records identified from:",
                    f"Websites (n = {data.get('other_websites')})",
                    f"Organisations (n = {data.get('other_organisations')})",
                    f"Citation searching (n = {data.get('other_citation_searching')})",
                ]
            ),
        )

    # --- row 1: screening ----------------------------------------------
    node("scr", _centre(["Records screened", f"(n = {data.screened})"]))
    node("exc", _centre(["Records excluded", f"(n = {data.get('excluded_screening')})"]), GREY)

    # --- row 2: retrieval -----------------------------------------------
    node("sought", _centre(["Reports sought for retrieval", f"(n = {data.sought})"]))
    node("notret", _centre(["Reports not retrieved", f"(n = {data.get('not_retrieved')})"]), GREY)
    if data.use_other:
        node("o_sought", _centre(["Reports sought for retrieval", f"(n = {data.other_sought})"]))
        node("o_notret", _centre(["Reports not retrieved", f"(n = {data.get('other_not_retrieved')})"]), GREY)

    # --- row 3: eligibility ---------------------------------------------
    node("assessed", _centre(["Reports assessed for eligibility", f"(n = {data.assessed})"]))
    node("ftexc", reasons(f"Reports excluded (n = {data.excluded_fulltext}):", data.reasons_db), GREY)
    if data.use_other:
        node("o_assessed", _centre(["Reports assessed for eligibility", f"(n = {data.other_assessed})"]))
        node(
            "o_ftexc",
            reasons(f"Reports excluded (n = {data.other_excluded}):", data.reasons_other),
            GREY,
        )

    # --- row 4: included ------------------------------------------------
    if data.use_previous:
        final = [
            "Studies included in review",
            f"(n = {data.total_studies})",
            "Reports of included studies",
            f"(n = {data.total_reports})",
        ]
    else:
        final = ["Studies included in review", f"(n = {data.new_studies})"]
        if data.has("new_reports"):
            final += ["Reports of included studies", f"(n = {data.get('new_reports')})"]
    node("final", _centre(final), BLUE)

    # --- structure: rows and left-to-right order ------------------------
    def row(ids: Iterable[str]) -> None:
        ids = [i for i in ids if i in g_nodes]
        with g.subgraph() as s:
            s.attr(rank="same")
            for i in ids:
                s.node(i)
        for a, b in zip(ids, ids[1:]):
            g.edge(a, b, style="invis")

    g_nodes = {"ph_id", "ph_scr", "ph_inc", "ident", "removed", "scr", "exc", "sought", "notret", "assessed", "ftexc", "final"}
    if data.use_previous:
        g_nodes.add("prev")
    if data.use_other:
        g_nodes |= {"o_ident", "o_sought", "o_notret", "o_assessed", "o_ftexc"}

    row(["ph_id", "prev", "ident", "removed", "o_ident"])
    row(["ph_scr", "scr", "exc"])
    row(["sought", "notret", "o_sought", "o_notret"])
    row(["assessed", "ftexc", "o_assessed", "o_ftexc"])
    row(["ph_inc", "final"])
    g.edge("ph_id", "ph_scr", style="invis", weight="100")
    g.edge("ph_scr", "ph_inc", style="invis", weight="100")

    # --- visible flow ----------------------------------------------------
    for a, b in (("ident", "scr"), ("scr", "sought"), ("sought", "assessed"), ("assessed", "final")):
        g.edge(a, b, weight="10")
    for a, b in (("ident", "removed"), ("scr", "exc"), ("sought", "notret"), ("assessed", "ftexc")):
        g.edge(a, b, weight="1")
    if data.use_previous:
        g.edge("prev", "final")
    if data.use_other:
        g.edge("o_ident", "o_sought", weight="10")
        g.edge("o_sought", "o_assessed", weight="10")
        g.edge("o_sought", "o_notret")
        g.edge("o_assessed", "o_ftexc")
        g.edge("o_assessed", "final")
    return g


def to_svg(data: PrismaData, title: Optional[str] = None) -> str:
    """Return the diagram as an SVG string (hyperlinks and tooltips included)."""
    return build_graph(data, title=title).pipe(format="svg").decode("utf-8")


def to_html(data: PrismaData, title: str = "PRISMA 2020 flow diagram") -> str:
    """Self-contained interactive HTML page: hover for tooltips, click for links."""
    svg = to_svg(data)
    svg = svg[svg.find("<svg"):]
    return (
        "<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title>"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<style>body{margin:1.5rem;font-family:Helvetica,Arial,sans-serif;background:#fff}"
        "svg{max-width:100%;height:auto}a:hover polygon{stroke:#1a5fb4;stroke-width:2}"
        "a{cursor:pointer}</style></head><body>"
        f"<h2>{html.escape(title)}</h2>{svg}"
        "<p style=\"font-size:.8rem;color:#555\">Hover over a box for details; click linked boxes to open "
        "supporting material. Generated with prismaflow.</p></body></html>"
    )


def render(
    data: PrismaData,
    out: Union[str, Path],
    formats: Iterable[str] = ("png",),
    dpi: int = 300,
    title: Optional[str] = None,
) -> List[Path]:
    """Write the diagram to ``out`` + extension for each requested format.

    ``out`` is a path stem such as ``results/prisma_flow``. Supported formats:
    png, svg, pdf, html (interactive) and dot (Graphviz source).
    """
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for fmt in formats:
        fmt = fmt.lower().lstrip(".")
        if fmt not in ALL_FORMATS:
            raise ValueError(f"Unsupported format '{fmt}'. Choose from: {', '.join(ALL_FORMATS)}")
        path = out.with_suffix(f".{fmt}")
        if fmt == "html":
            path.write_text(to_html(data, title or "PRISMA 2020 flow diagram"), encoding="utf-8")
        elif fmt == "dot":
            path.write_text(build_graph(data, title=title).source, encoding="utf-8")
        else:
            g = build_graph(data, dpi=dpi if fmt == "png" else None, title=title)
            path.write_bytes(g.pipe(format=fmt))
        written.append(path)
    return written
