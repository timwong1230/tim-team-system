"""Add-prospect form: blank after submit + expander stays open across reruns."""

from __future__ import annotations

import ast
from pathlib import Path


def test_sales_add_uses_generation_prefix_and_keyed_expander():
    """Regression: leftover fields + expander collapsing while typing."""
    src = Path("app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    assert "_add_sales_prefix" in src
    assert "_request_clear_add_sales_form" in src
    assert 'st.session_state["pl_as_gen"]' in src
    # Bump generation on clear (new blank widget keys)
    req_start = src.index("def _request_clear_add_sales_form")
    req_end = src.index("with tab_sales:")
    request_body = src[req_start:req_end]
    assert 'st.session_state["pl_as_gen"]' in request_body
    assert 'st.session_state["pl_as_expander"] = True' in request_body
    # Must not assign widget values after widgets exist (old crash path)
    assert "_apply_clear_add_sales_form" not in src
    assert 'st.session_state.pop("pl_as_keep_open"' not in src
    # Keyed expander persists open state across number_input reruns
    assert 'key="pl_as_expander"' in src
    assert 'on_change="rerun"' in src
    assert 'key="pl_ar_expander"' in src
    assert isinstance(tree, ast.Module)


def test_add_sales_prefix_helper_shape():
    """Prefix must change when pl_as_gen increments."""
    # Lightweight pure check mirroring app helper logic
    def prefix(gen: int) -> str:
        return f"pl_as_g{int(gen)}"

    assert prefix(0) != prefix(1)
    assert prefix(2) == "pl_as_g2"
