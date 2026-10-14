"""MDRT Progress PDF text can be parsed into Agent Code + Total Credit."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pypdf  # noqa: E402

import tt_core.iris as iris_mod  # noqa: E402
from tt_core.iris import detect_columns, detect_report_kind  # noqa: E402


def test_pdf_text_parser():
    text = (
        "MDRT Progress Report\n"
        "Agent Name Agent Code Total Credit eligible for MDRT\n"
        "Tim 30947 398,944\n"
        "Oscar 59164 162,848\n"
        "Hanes 12345 22,824\n"
    )

    class FakePage:
        def extract_text(self):
            return text

    class FakeReader:
        def __init__(self, *_a, **_k):
            self.pages = [FakePage()]

    orig = pypdf.PdfReader
    pypdf.PdfReader = FakeReader  # type: ignore
    try:
        df = iris_mod._pdf_text_to_df(b"%PDF-fake")
    finally:
        pypdf.PdfReader = orig

    assert not df.empty
    cols = detect_columns(df)
    assert cols["code"] == "Agent Code"
    assert cols["mdrt_credit"] == "Total Credit eligible for MDRT"
    assert detect_report_kind(df, "MDRT Progress.pdf") == "mdrt"
    by_code = {
        str(r["Agent Code"]): float(str(r[cols["mdrt_credit"]]).replace(",", ""))
        for _, r in df.iterrows()
    }
    assert by_code["30947"] == 398944.0
    assert by_code["59164"] == 162848.0
    print("mdrt pdf ok")


def test_auto_build_preview_kwargs_filtered():
    """Old Cloud modules may not accept filename= / report_kind=."""
    import inspect

    def old_auto(df, default_month):
        return df, {"report_kind": "daily"}

    sig = inspect.signature(old_auto)
    kwargs = {"filename": "x.xlsx", "report_kind": "daily"}
    filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
    assert filtered == {}
    print("kwargs filter ok")


if __name__ == "__main__":
    test_pdf_text_parser()
    test_auto_build_preview_kwargs_filtered()
