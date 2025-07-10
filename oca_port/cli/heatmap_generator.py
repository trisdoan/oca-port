import sys
import json

import pandas as pd
import plotly.express as px
from dash import Dash, html, dcc


def run_heatmap_app(data_path, category):
    """
    Runs a Dash application to display a heatmap of line changes.

    Args:
        data_path (str): Path to a JSON file containing the heatmap data.
                         Expected format: {addon: {version_transition: line_changes}}
        category (str): The category of changes being displayed (for title).
    """
    try:
        with open(data_path, "r") as f:
            heatmap_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Heatmap data file not found at {data_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {data_path}", file=sys.stderr)
        sys.exit(1)

    if not heatmap_data:
        print("No data to display for heatmap. Exiting.", file=sys.stderr)
        sys.exit(0)

    # Transform data for Plotly heatmap
    # We need a DataFrame with columns: 'Addon', 'Version Transition', 'Line Changes'
    rows = []
    for addon, transitions in heatmap_data.items():
        for transition, line_changes in transitions.items():
            rows.append(
                {
                    "Addon": addon,
                    "Version Transition": transition,
                    "Line Changes": line_changes,
                }
            )

    df = pd.DataFrame(rows)

    # Sort version transitions for better visualization on the X-axis
    # This creates a sortable key from 'X.Y-A.B' format
    df["Sort Key"] = df["Version Transition"].apply(
        lambda x: tuple(map(int, x.replace(".", "-").split("-")))
    )
    df = df.sort_values(by=["Addon", "Sort Key"])

    # Get unique sorted version transitions for the x-axis order
    sorted_transitions = sorted(
        df["Version Transition"].unique(),
        key=lambda x: tuple(map(int, x.replace(".", "-").split("-"))),
    )

    # Create the heatmap using plotly.express
    fig = px.imshow(
        df.pivot_table(
            index="Addon", columns="Version Transition", values="Line Changes"
        ).reindex(columns=sorted_transitions),
        labels=dict(
            x="Version Transition", y="Addon", color=f"Line Changes ({category})"
        ),
        x=sorted_transitions,  # Ensure correct order of columns
        y=df[
            "Addon"
        ].unique(),  # Ensure correct order of rows (alphabetical by default from pivot_table)
        color_continuous_scale="Viridis",  # Choose a color scale that fits your preference
        title=f"Heatmap of '{category}' Line Changes Across Odoo Versions",
    )

    fig.update_xaxes(
        side="top"
    )  # Place x-axis labels at the top for better readability

    app = Dash(__name__)

    app.layout = html.Div(
        style={
            "fontFamily": "Inter, sans-serif",
            "padding": "20px",
            "maxWidth": "1200px",
            "margin": "auto",
            "backgroundColor": "#f9f9f9",
            "borderRadius": "8px",
            "boxShadow": "0 4px 8px rgba(0,0,0,0.1)",
        },
        children=[
            html.H1(
                f"Odoo Addon Line Change Heatmap",
                style={"textAlign": "center", "color": "#333", "marginBottom": "10px"},
            ),
            html.H2(
                f"Category: '{category}'",
                style={
                    "textAlign": "center",
                    "color": "#555",
                    "fontSize": "1.2em",
                    "marginBottom": "30px",
                },
            ),
            dcc.Graph(
                figure=fig,
                style={"height": "70vh", "width": "100%"},  # Make graph responsive
            ),
        ],
    )

    # Run the Dash app on a specific port
    app.run(debug=True, port=8050)


if __name__ == "__main__":
    # This script expects two command-line arguments:
    # 1. Path to the JSON data file
    # 2. The heatmap category string
    if len(sys.argv) < 3:
        print(
            "Usage: python heatmap_generator.py <data_path> <heatmap_category>",
            file=sys.stderr,
        )
        sys.exit(1)

    data_file_path = sys.argv[1]
    heatmap_category_arg = sys.argv[2]
    run_heatmap_app(data_file_path, heatmap_category_arg)
