#!/usr/bin/env python3
"""Interactive benchmark dashboard (Plotly Dash).

Serves a local web dashboard for exploring and comparing benchmark results
across hosts, OS families, and benchmark categories with interactive filtering,
normalization, and baseline comparison.

Usage::

    pip install dash pandas
    python3 scripts/benchmark_dashboard.py benchmarks/
    python3 scripts/benchmark_dashboard.py benchmarks/ --port 8051
    python3 scripts/benchmark_dashboard.py benchmarks/ --host 0.0.0.0
    python3 scripts/benchmark_dashboard.py benchmarks/ --host 192.168.1.10 --port 9090
    python3 scripts/benchmark_dashboard.py benchmarks/ --anonymize

Then open http://localhost:8050 in a browser.  Press Ctrl+C to stop.

Features:
- Filter by OS family and/or individual hosts
- Switch benchmark categories
- Normalize times relative to the fastest host per benchmark
- Compare against a fixed baseline host (divide all times by baseline)
- Sort benchmarks by name, fastest mean, or largest spread
- Toggle error bars (stddev) and horizontal bar orientation
- Exportable data table (CSV) below each chart
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Optional dependency check
# ---------------------------------------------------------------------------

try:
    import dash
    import pandas as pd
    import plotly.graph_objects as go
    from dash import Input, Output, dash_table, dcc, html
except ImportError as exc:
    sys.exit(f"ERROR: {exc}\nInstall required packages with:\n    pip install dash pandas\n")

# ---------------------------------------------------------------------------
# Import shared utilities from the sibling report generator
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent))
from generate_benchmark_report import (  # noqa: E402
    CATEGORY_TITLES,
    anonymize_hosts,
    load_results,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DARK = {
    "bg": "#1a1a2e",
    "surface": "#16213e",
    "text": "#e0e0e0",
    "accent": "#0f3460",
    "highlight": "#e94560",
    "border": "#333",
    "blue": "#4dc9f6",
    "green": "#00e676",
}

CHART_COLORS = [
    "#4dc9f6",
    "#f67019",
    "#f53794",
    "#537bc4",
    "#acc236",
    "#166a8f",
    "#00a950",
    "#58595b",
    "#8549ba",
    "#e6194b",
    "#3cb44b",
    "#ffe119",
    "#4363d8",
    "#f58231",
    "#911eb4",
    "#42d4f4",
]

# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------


def build_df(
    hosts: dict[str, dict[str, Any]],
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Build a flat DataFrame and host→os_family mapping.

    DataFrame columns: category, benchmark, host, os_family,
    mean, stddev, min, max, median.
    """
    rows: list[dict] = []
    host_os: dict[str, str] = {}

    for hostname, host_data in hosts.items():
        meta = host_data.get("metadata", {})
        os_family = meta.get("os_family", "Unknown")
        host_os[hostname] = os_family

        for category, results in host_data.get("benchmarks", {}).items():
            for bench in results:
                rows.append(
                    {
                        "category": category,
                        "benchmark": bench.get("command", "unknown"),
                        "host": hostname,
                        "os_family": os_family,
                        "mean": float(bench.get("mean", 0.0)),
                        "stddev": float(bench.get("stddev", 0.0)),
                        "min": float(bench.get("min", 0.0)),
                        "max": float(bench.get("max", 0.0)),
                        "median": float(bench.get("median", 0.0)),
                    }
                )

    df = (
        pd.DataFrame(rows)
        if rows
        else pd.DataFrame(
            columns=[
                "category",
                "benchmark",
                "host",
                "os_family",
                "mean",
                "stddev",
                "min",
                "max",
                "median",
            ]
        )
    )
    return df, host_os


# ---------------------------------------------------------------------------
# Dash application
# ---------------------------------------------------------------------------


def make_app(df: pd.DataFrame, host_os: dict[str, str]) -> dash.Dash:
    """Build and return the configured Dash app (no data stored globally)."""
    os_families = sorted(df["os_family"].unique().tolist()) if not df.empty else []
    all_hosts = sorted(df["host"].unique().tolist()) if not df.empty else []
    categories = sorted(df["category"].unique().tolist()) if not df.empty else []
    host_colors = {h: CHART_COLORS[i % len(CHART_COLORS)] for i, h in enumerate(all_hosts)}

    # ----- style helpers -----
    sidebar_style: dict = {
        "width": "240px",
        "minWidth": "200px",
        "flexShrink": "0",
        "background": DARK["surface"],
        "padding": "1.2rem",
        "height": "100vh",
        "overflowY": "auto",
        "position": "sticky",
        "top": "0",
        "borderRight": f"1px solid {DARK['border']}",
    }
    content_style: dict = {
        "flex": "1",
        "padding": "1.5rem",
        "overflowX": "hidden",
        "minWidth": "0",
    }
    label_style: dict = {
        "color": DARK["blue"],
        "fontSize": "0.75rem",
        "fontWeight": "bold",
        "textTransform": "uppercase",
        "marginBottom": "0.3rem",
        "marginTop": "1rem",
        "display": "block",
    }
    dropdown_style: dict = {"background": DARK["accent"], "color": DARK["text"]}
    checklist_label: dict = {
        "display": "block",
        "marginBottom": "4px",
        "cursor": "pointer",
        "fontSize": "0.85rem",
    }

    # ----- category options -----
    cat_options = [
        {
            "label": CATEGORY_TITLES.get(c, c.replace("_", " ").title()),
            "value": c,
        }
        for c in categories
    ]

    # ----- app -----
    app = dash.Dash(
        __name__,
        title="Benchmark Dashboard",
        suppress_callback_exceptions=True,
    )

    app.layout = html.Div(
        [
            # Header
            html.Div(
                [
                    html.H1(
                        "🖥️ Benchmark Dashboard",
                        style={
                            "color": DARK["highlight"],
                            "margin": "0",
                            "fontSize": "1.5rem",
                        },
                    ),
                    html.Span(
                        f"  —  {len(all_hosts)} hosts, {len(categories)} categories",
                        style={"color": "#888", "fontSize": "0.9rem", "marginLeft": "1rem"},
                    ),
                ],
                style={
                    "background": DARK["surface"],
                    "padding": "0.8rem 1.5rem",
                    "borderBottom": f"1px solid {DARK['border']}",
                    "display": "flex",
                    "alignItems": "center",
                },
            ),
            # Body
            html.Div(
                [
                    # ── Sidebar ──────────────────────────────────────────────
                    html.Div(
                        [
                            html.Span("OS Family", style=label_style),
                            dcc.Checklist(
                                id="os-filter",
                                options=[{"label": f"  {o}", "value": o} for o in os_families],
                                value=os_families,
                                inputStyle={"marginRight": "6px"},
                                labelStyle=checklist_label,
                            ),
                            html.Span("Hosts", style=label_style),
                            dcc.Dropdown(
                                id="host-filter",
                                options=[{"label": h, "value": h} for h in all_hosts],
                                value=all_hosts,
                                multi=True,
                                placeholder="Select hosts…",
                                style=dropdown_style,
                            ),
                            html.Span("Category", style=label_style),
                            dcc.Dropdown(
                                id="category-select",
                                options=cat_options,
                                value=categories[0] if categories else None,
                                clearable=False,
                                style=dropdown_style,
                            ),
                            html.Hr(
                                style={
                                    "borderColor": DARK["border"],
                                    "marginTop": "1.2rem",
                                }
                            ),
                            dcc.Checklist(
                                id="normalize-toggle",
                                options=[
                                    {
                                        "label": "  Normalize (÷ fastest)",
                                        "value": "normalize",
                                    }
                                ],
                                value=[],
                                inputStyle={"marginRight": "6px"},
                                labelStyle={"fontSize": "0.85rem", "cursor": "pointer"},
                            ),
                            html.Span("Baseline host", style=label_style),
                            dcc.Dropdown(
                                id="baseline-select",
                                options=[{"label": "— none —", "value": ""}]
                                + [{"label": h, "value": h} for h in all_hosts],
                                value="",
                                clearable=False,
                                style=dropdown_style,
                                placeholder="Divide all times by…",
                            ),
                            html.Span("Sort benchmarks by", style=label_style),
                            dcc.Dropdown(
                                id="sort-select",
                                options=[
                                    {"label": "Name (A→Z)", "value": "name"},
                                    {"label": "Fastest mean first", "value": "fastest"},
                                    {"label": "Largest spread first", "value": "spread"},
                                ],
                                value="name",
                                clearable=False,
                                style=dropdown_style,
                            ),
                            html.Hr(
                                style={
                                    "borderColor": DARK["border"],
                                    "marginTop": "1.2rem",
                                }
                            ),
                            dcc.Checklist(
                                id="errorbars-toggle",
                                options=[
                                    {"label": "  Show error bars (stddev)", "value": "errorbars"}
                                ],
                                value=["errorbars"],
                                inputStyle={"marginRight": "6px"},
                                labelStyle={"fontSize": "0.85rem", "cursor": "pointer"},
                            ),
                            dcc.Checklist(
                                id="horiz-toggle",
                                options=[{"label": "  Horizontal bars", "value": "horiz"}],
                                value=[],
                                inputStyle={"marginRight": "6px"},
                                labelStyle={
                                    "fontSize": "0.85rem",
                                    "cursor": "pointer",
                                    "marginTop": "4px",
                                },
                            ),
                        ],
                        style=sidebar_style,
                    ),
                    # ── Content ──────────────────────────────────────────────
                    html.Div(
                        [
                            dcc.Graph(
                                id="main-chart",
                                style={"height": "520px"},
                                config={"displayModeBar": True, "displaylogo": False},
                            ),
                            html.Div(id="results-table-container"),
                        ],
                        style=content_style,
                    ),
                ],
                style={"display": "flex", "alignItems": "flex-start"},
            ),
        ],
        style={
            "background": DARK["bg"],
            "color": DARK["text"],
            "fontFamily": "'Segoe UI', system-ui, -apple-system, sans-serif",
            "minHeight": "100vh",
        },
    )

    # ── Callbacks ────────────────────────────────────────────────────────────

    @app.callback(
        Output("host-filter", "options"),
        Output("host-filter", "value"),
        Input("os-filter", "value"),
        prevent_initial_call=True,
    )
    def update_host_options(selected_os: list[str]) -> tuple[list, list]:
        if not selected_os:
            return [], []
        filtered = sorted(df[df["os_family"].isin(selected_os)]["host"].unique().tolist())
        return [{"label": h, "value": h} for h in filtered], filtered

    @app.callback(
        Output("main-chart", "figure"),
        Output("results-table-container", "children"),
        Input("category-select", "value"),
        Input("host-filter", "value"),
        Input("normalize-toggle", "value"),
        Input("baseline-select", "value"),
        Input("sort-select", "value"),
        Input("errorbars-toggle", "value"),
        Input("horiz-toggle", "value"),
    )
    def update_chart(
        category: str | None,
        selected_hosts: list[str] | None,
        normalize_opts: list[str],
        baseline: str,
        sort_by: str,
        errorbars_opts: list[str],
        horiz_opts: list[str],
    ) -> tuple[go.Figure, Any]:
        def _empty_fig(msg: str) -> go.Figure:
            fig = go.Figure()
            fig.update_layout(
                paper_bgcolor=DARK["bg"],
                plot_bgcolor=DARK["surface"],
                font_color=DARK["text"],
                annotations=[
                    {
                        "text": msg,
                        "xref": "paper",
                        "yref": "paper",
                        "x": 0.5,
                        "y": 0.5,
                        "showarrow": False,
                        "font": {"size": 16, "color": "#888"},
                    }
                ],
            )
            return fig

        normalize = "normalize" in (normalize_opts or [])
        show_errorbars = "errorbars" in (errorbars_opts or [])
        horizontal = "horiz" in (horiz_opts or [])

        if not category or not selected_hosts:
            return _empty_fig("No data selected."), html.P(
                "Select a category and at least one host.",
                style={"color": "#888"},
            )

        cat_df = df[(df["category"] == category) & (df["host"].isin(selected_hosts))].copy()

        if cat_df.empty:
            return _empty_fig("No data for this selection."), html.P(
                "No benchmark data available for the selected category and hosts.",
                style={"color": "#888"},
            )

        # Apply baseline normalization (takes precedence over normalize)
        if baseline and baseline in selected_hosts:
            baseline_df = (
                cat_df[cat_df["host"] == baseline][["benchmark", "mean"]]
                .copy()
                .rename(columns={"mean": "baseline_mean"})
            )
            cat_df = cat_df.merge(baseline_df, on="benchmark", how="left")
            denom = cat_df["baseline_mean"].replace(0.0, float("nan"))
            cat_df["mean"] = cat_df["mean"] / denom
            cat_df["stddev"] = cat_df["stddev"] / denom
            cat_df = cat_df.drop(columns=["baseline_mean"])
        elif normalize:
            min_per_bench = cat_df.groupby("benchmark")["mean"].min().rename("min_mean")
            cat_df = cat_df.merge(min_per_bench, on="benchmark")
            denom = cat_df["min_mean"].replace(0.0, float("nan"))
            cat_df["mean"] = cat_df["mean"] / denom
            cat_df["stddev"] = cat_df["stddev"] / denom
            cat_df = cat_df.drop(columns=["min_mean"])

        # Sort benchmarks
        benchmarks = sorted(cat_df["benchmark"].unique().tolist())
        if sort_by == "fastest":
            benchmarks = cat_df.groupby("benchmark")["mean"].min().sort_values().index.tolist()
        elif sort_by == "spread":
            benchmarks = (
                cat_df.groupby("benchmark")["mean"]
                .apply(lambda x: x.max() - x.min())
                .sort_values(ascending=False)
                .index.tolist()
            )

        # Build Plotly traces
        category_title = CATEGORY_TITLES.get(category, category.replace("_", " ").title())
        traces = []
        for host in selected_hosts:
            host_df = cat_df[cat_df["host"] == host].set_index("benchmark")
            y_vals = [
                float(host_df.loc[b, "mean"]) if b in host_df.index else None for b in benchmarks
            ]
            err_vals = [
                float(host_df.loc[b, "stddev"]) if b in host_df.index else 0.0 for b in benchmarks
            ]
            color = host_colors.get(host, "#888")

            if horizontal:
                trace: go.Bar = go.Bar(
                    name=host,
                    y=benchmarks,
                    x=y_vals,
                    orientation="h",
                    marker_color=color,
                    error_x=(
                        dict(type="data", array=err_vals, visible=True, color="#666")
                        if show_errorbars
                        else None
                    ),
                )
            else:
                trace = go.Bar(
                    name=host,
                    x=benchmarks,
                    y=y_vals,
                    marker_color=color,
                    error_y=(
                        dict(type="data", array=err_vals, visible=True, color="#666")
                        if show_errorbars
                        else None
                    ),
                )
            traces.append(trace)

        # Axis label depends on normalization mode
        if baseline and baseline in selected_hosts:
            value_label = f"Relative to {baseline} (1.0 = same speed)"
        elif normalize:
            value_label = "Relative to fastest (1.0 = fastest)"
        else:
            value_label = "Time (seconds)"

        fig = go.Figure(data=traces)
        fig.update_layout(
            title=dict(
                text=category_title,
                font=dict(color=DARK["text"], size=16),
            ),
            barmode="group",
            paper_bgcolor=DARK["bg"],
            plot_bgcolor=DARK["surface"],
            font=dict(color=DARK["text"]),
            legend=dict(
                bgcolor=DARK["accent"],
                bordercolor=DARK["border"],
                font=dict(color=DARK["text"]),
            ),
            xaxis=dict(
                gridcolor=DARK["border"],
                title=dict(text=value_label if horizontal else "Benchmark"),
            ),
            yaxis=dict(
                gridcolor=DARK["border"],
                title=dict(text="Benchmark" if horizontal else value_label),
            ),
            margin=dict(l=20, r=20, t=50, b=20),
        )

        # Build data table
        table_rows = []
        for bench in benchmarks:
            row: dict = {"Benchmark": bench}
            bench_df = cat_df[cat_df["benchmark"] == bench]
            host_means: list[float] = []
            for host in selected_hosts:
                host_row = bench_df[bench_df["host"] == host]
                if not host_row.empty:
                    m = float(host_row.iloc[0]["mean"])
                    s = float(host_row.iloc[0]["stddev"])
                    row[host] = f"{m:.4f} ± {s:.4f}"
                    host_means.append(m)
                else:
                    row[host] = "—"
            table_rows.append(row)

        columns = [{"name": "Benchmark", "id": "Benchmark"}] + [
            {"name": h, "id": h} for h in selected_hosts
        ]

        table = dash_table.DataTable(
            data=table_rows,
            columns=columns,
            style_header={
                "backgroundColor": DARK["accent"],
                "color": DARK["text"],
                "fontWeight": "bold",
                "border": f"1px solid {DARK['border']}",
                "textAlign": "left",
            },
            style_cell={
                "backgroundColor": DARK["surface"],
                "color": DARK["text"],
                "border": f"1px solid {DARK['border']}",
                "padding": "6px 12px",
                "fontFamily": "monospace",
                "fontSize": "0.82rem",
                "textAlign": "left",
                "minWidth": "110px",
            },
            style_data_conditional=[
                {
                    "if": {"row_index": "odd"},
                    "backgroundColor": DARK["bg"],
                }
            ],
            page_size=60,
            sort_action="native",
            export_format="csv",
            export_headers="display",
        )

        table_section = html.Div(
            [
                html.H3(
                    "Data Table",
                    style={
                        "color": DARK["blue"],
                        "marginTop": "1.5rem",
                        "marginBottom": "0.5rem",
                    },
                ),
                html.P(
                    "Click a column header to sort. Use the export button to download CSV.",
                    style={"color": "#888", "fontSize": "0.8rem", "marginBottom": "0.5rem"},
                ),
                table,
            ]
        )

        return fig, table_section

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactive benchmark dashboard (Plotly Dash).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "benchmarks_dir",
        type=Path,
        help="Directory containing results/<host>/*.json",
    )
    parser.add_argument("--port", type=int, default=8050, help="Port to listen on")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help=(
            "Interface address to bind (default: 127.0.0.1). "
            "Use 0.0.0.0 to listen on all interfaces."
        ),
    )
    parser.add_argument(
        "--anonymize",
        action="store_true",
        help="Replace hostnames with Greek mythology names",
    )
    args = parser.parse_args()

    hosts = load_results(args.benchmarks_dir)
    if not hosts:
        print("ERROR: no results found", file=sys.stderr)
        sys.exit(1)

    if args.anonymize:
        hosts = anonymize_hosts(hosts)
        print("Anonymized hostnames with Greek mythology names")

    print(f"Loaded results for {len(hosts)} hosts: {', '.join(sorted(hosts))}")

    df, host_os = build_df(hosts)
    if df.empty:
        print("ERROR: no benchmark data found", file=sys.stderr)
        sys.exit(1)

    app = make_app(df, host_os)

    print(f"\nDashboard running at http://{args.host}:{args.port}/")
    if args.host == "0.0.0.0":
        print(f"  Listening on all interfaces — reachable at http://<your-ip>:{args.port}/")
    print("Press Ctrl+C to stop.\n")
    app.run(debug=False, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
