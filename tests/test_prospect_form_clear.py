"""Add-prospect form clear must not touch widget keys after instantiation."""

from __future__ import annotations

import ast
from pathlib import Path


def test_clear_is_deferred_via_flag():
    """Regression: assigning pl_as_ff after text_area(key=pl_as_ff) crashes Streamlit."""
    src = Path("app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    # Locate page_prospect_list body text slice for a simple string check
    assert "_request_clear_add_sales_form" in src
    assert "_apply_clear_add_sales_form" in src
    assert 'st.session_state["pl_as_clear"] = True' in src
    # Must apply clear before expander / widgets
    apply_at = src.index("_apply_clear_add_sales_form()")
    widget_at = src.index('key="pl_as_ff"')
    assert apply_at < widget_at
    # Must not assign pl_as_ff inside the request helper (only flag)
    req_start = src.index("def _request_clear_add_sales_form")
    req_end = src.index("def _apply_clear_add_sales_form")
    request_body = src[req_start:req_end]
    assert 'st.session_state["pl_as_ff"]' not in request_body
    assert "pl_as_clear" in request_body
    # Apply helper is what resets the template
    apply_body = src[req_end : src.index("with tab_sales:")]
    assert 'st.session_state["pl_as_ff"] = pr.factfind_template()' in apply_body
    # Sanity: file still parses
    assert isinstance(tree, ast.Module)
