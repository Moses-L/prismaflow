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
