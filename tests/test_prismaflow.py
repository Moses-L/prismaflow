import shutil

import pytest

from prismaflow import PrismaData, example_data, render, to_html
from prismaflow.cli import main

needs_dot = pytest.mark.skipif(shutil.which("dot") is None, reason="Graphviz 'dot' not installed")


def basic():
    return PrismaData(
        counts={
            "identified_databases": 1200,
            "duplicates": 250,
            "excluded_screening": 800,
            "not_retrieved": 5,
            "new_studies": 85,
            "new_reports": 85,
        },
        reasons_db={"Wrong population": 20, "Wrong design": 40},
    )


def test_derived_counts():
    d = basic()
    assert d.screened == 950
    assert d.sought == 150
    assert d.assessed == 145
    assert d.excluded_fulltext == 60
    assert d.validate() == []


def test_previous_and_other_totals():
    d = example_data()
    assert d.use_previous and d.use_other
    assert d.total_studies == 52
    assert d.total_reports == 62
    assert d.other_assessed == 46


def test_negative_counts_rejected():
    d = basic()
    d.counts["duplicates"] = 5000
    with pytest.raises(ValueError):
        d.validate()


def test_exclusions_cannot_exceed_assessed():
    d = basic()
    d.reasons_db["Other"] = 500
    with pytest.raises(ValueError):
        d.validate()


def test_report_mismatch_warns():
    d = basic()
    d.counts["new_reports"] = 99
    assert any("new_reports" in w for w in d.validate())


def test_csv_roundtrip(tmp_path):
    tpl = tmp_path / "t.csv"
    PrismaData.write_template(tpl)
    assert PrismaData.from_csv(tpl).counts == {}
    f = tmp_path / "f.csv"
    f.write_text(
        "data,label,n,url,tooltip\n"
        "identified_databases,,100,https://example.org,Search strategy\n"
        "duplicates,,10,,\n"
        "reason_db,Wrong design,5,,\n"
        "screened,,,https://example.org/screen,\n"
    )
    d = PrismaData.from_csv(f)
    assert d.counts == {"identified_databases": 100, "duplicates": 10}
    assert d.reasons_db == {"Wrong design": 5}
    assert d.urls["screened"].endswith("/screen")
    assert d.tooltips["identified_databases"] == "Search strategy"


def test_unknown_item_raises(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("data,label,n\nnot_a_field,,3\n")
    with pytest.raises(ValueError):
        PrismaData.from_csv(f)


@needs_dot
def test_render_all_formats(tmp_path):
    paths = render(example_data(), tmp_path / "flow", ["png", "svg", "pdf", "html", "dot"])
    assert all(p.exists() and p.stat().st_size > 0 for p in paths)


@needs_dot
def test_html_is_interactive():
    page = to_html(example_data())
    assert "<svg" in page
    assert "https://pubmed.ncbi.nlm.nih.gov/" in page
    assert "PubMed, Embase" in page


@needs_dot
def test_cli_example(tmp_path):
    assert main(["draw", "--example", "-o", str(tmp_path / "x"), "-f", "svg"]) == 0
    assert (tmp_path / "x.svg").exists()


# ---------------------------------------------------------------- regression tests
import re
import xml.etree.ElementTree as ET


def _texts(svg):
    return re.findall(r"<text[^>]*>([^<]*)</text>", svg)


def test_unknown_count_key_rejected():
    with pytest.raises(ValueError, match="Unknown count"):
        PrismaData(counts={"duplicate": 5})


@pytest.mark.parametrize("bad", ["abc", 2.5, True, None])
def test_non_whole_numbers_rejected(bad):
    with pytest.raises(ValueError):
        PrismaData(counts={"duplicates": bad})


def test_numeric_strings_and_integer_floats_accepted():
    d = PrismaData(counts={"identified_databases": "1,200", "duplicates": 10.0})
    assert d.counts == {"identified_databases": 1200, "duplicates": 10}


def test_negative_reason_rejected():
    d = basic()
    d.reasons_db["Bad"] = -3
    with pytest.raises(ValueError):
        d.validate()


def test_csv_errors(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("data,label,n\nduplicates,,abc\n")
    with pytest.raises(ValueError, match="not a number"):
        PrismaData.from_csv(f)
    with pytest.raises(FileNotFoundError):
        PrismaData.from_csv(tmp_path / "missing.csv")


def test_csv_bom_comments_commas(tmp_path):
    f = tmp_path / "bom.csv"
    f.write_bytes(
        "\ufeffdata,label,n\n# a comment row,,\nidentified_databases,,\"1,200\"\n,,\nduplicates,,10\n".encode("utf-8")
    )
    assert PrismaData.from_csv(f).counts == {"identified_databases": 1200, "duplicates": 10}


@needs_dot
@pytest.mark.parametrize(
    "reason",
    ["Path C:\\new\\left", "ends with \\", 'Wrong "design" & <scope>', "a|b {c}", "Étude – 研究"],
)
def test_user_text_rendered_literally(reason):
    from prismaflow import to_svg

    d = basic()
    d.reasons_db = {reason: 10}
    svg = to_svg(d)
    ET.fromstring(svg)  # must stay valid XML
    import html as _h

    assert any(_h.unescape(t).startswith(reason) for t in _texts(svg))


@needs_dot
def test_urls_with_ampersands_and_quotes_give_valid_xml(tmp_path):
    d = basic()
    d.urls = {"identified_databases": 'https://a.org/x?y=1&z=2&w="q"<>'}
    d.tooltips = {"identified_databases": 'T & <t> "q" \\n'}
    paths = render(d, tmp_path / "o", ["svg", "html"])
    ET.fromstring(paths[0].read_text())
    page = paths[1].read_text()
    ET.fromstring(page[page.find("<svg"): page.rfind("</svg>") + 6])
    assert "y=1&amp;z=2" in paths[0].read_text()


@needs_dot
def test_dotted_stem_and_extension_in_stem(tmp_path):
    p1 = render(basic(), tmp_path / "fig.v1", ["svg"])[0]
    assert p1.name == "fig.v1.svg"
    p2 = render(basic(), tmp_path / "fig2.png", ["svg"])[0]
    assert p2.name == "fig2.svg"


@needs_dot
def test_single_format_string_and_bad_format(tmp_path):
    assert render(basic(), tmp_path / "s", "svg")[0].exists()
    with pytest.raises(ValueError, match="Unsupported"):
        render(basic(), tmp_path / "b", ["png", "gif"])
    assert not (tmp_path / "b.png").exists()  # nothing partially written


@needs_dot
@pytest.mark.parametrize(
    "counts",
    [
        {},
        {"identified_registers": 50, "excluded_screening": 10, "new_studies": 30},
        {"identified_databases": 20, "previous_studies": 5, "new_studies": 3},
        {"identified_databases": 20, "other_websites": 10, "other_sought": 8, "new_studies": 3},
    ],
)
def test_arm_combinations_render(tmp_path, counts):
    assert render(PrismaData(counts=counts), tmp_path / "a", ["svg", "png"], dpi=50)


def test_cli_errors(tmp_path, capsys):
    assert main(["draw", str(tmp_path / "nope.csv")]) == 1
    assert "file not found" in capsys.readouterr().err
    bad = tmp_path / "bad.csv"
    bad.write_text("data,label,n\nduplicates,,5000\nidentified_databases,,10\n")
    assert main(["draw", str(bad), "-o", str(tmp_path / "o")]) == 1
    assert "negative" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main(["draw"])


@needs_dot
def test_cli_template_then_draw_example_csv(tmp_path):
    t = tmp_path / "t.csv"
    assert main(["template", "-o", str(t)]) == 0
    assert t.exists()
