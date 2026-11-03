"""Standalone trajectory HTML with sample/barcode selection and offline Plotly assets."""

from __future__ import annotations

import html
from pathlib import Path

from barcode_groups import trajectory_legend, trajectory_style


TRAJECTORY_CONTROLS = r"""
const graph = document.getElementById('{plot_id}');
const sampleNames = graph.layout.meta.sample_names;
const barcodeNames = graph.layout.meta.barcode_names;
const groupNames = graph.layout.meta.group_names;
const barcodeGroups = graph.layout.meta.barcode_group_indices;
const coloredIndices = [];
const originalY = [];
const originalBaseY = [];
graph.layout.meta.colored_trace_indices.forEach(index => {
    coloredIndices.push(index);
    originalY.push(Array.from(graph.data[index].y));
    originalBaseY.push(Array.from(graph.data[index - 1].y));
});
let sampleBoxes = [];
let barcodeBoxes = [];
let groupBoxes = [];
function updateSelection() {
    const samplesEnabled = sampleBoxes.map(box => box.checked);
    const values = [];
    const visible = [];
    const indices = [];
    originalY.forEach((row, barcode) => {
        const group = barcodeGroups[barcode];
        const enabled = group === null || groupBoxes[group].checked;
        values.push(originalBaseY[barcode], row.map((value, sample) =>
            barcodeBoxes[barcode].checked && samplesEnabled[sample] ? value : null));
        visible.push(enabled, enabled);
        indices.push(coloredIndices[barcode] - 1, coloredIndices[barcode]);
    });
    return Plotly.restyle(graph, {y: values, visible: visible}, indices);
}
function addControls(title, kind, names, explanation) {
    const panel = document.createElement('section');
    panel.className = 'selection-controls ' + kind + '-controls';
    panel.setAttribute('aria-label', 'Trajectory ' + kind + ' selection');
    const heading = document.createElement('h2');
    heading.textContent = title;
    panel.appendChild(heading);
    const note = document.createElement('p');
    note.textContent = explanation;
    panel.appendChild(note);
    const boxes = [];
    const labels = [];
    const status = document.createElement('span');
    status.className = 'selection-status';
    status.setAttribute('aria-live', 'polite');
    function refreshStatus() {
        status.textContent = boxes.filter(box => box.checked).length + ' of ' + names.length + ' selected';
    }
    ['Select all', kind === 'group' ? 'Hide all' : 'Gray out all'].forEach((text, index) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = text;
        button.addEventListener('click', () => {
            boxes.forEach(box => { box.checked = index === 0; });
            refreshStatus();
            updateSelection();
        });
        panel.appendChild(button);
    });
    panel.appendChild(status);
    if (kind === 'barcode') {
        const search = document.createElement('input');
        search.type = 'search';
        search.placeholder = 'Search barcodes';
        search.setAttribute('aria-label', 'Search barcodes');
        search.addEventListener('input', () => {
            const query = search.value.trim().toLowerCase();
            labels.forEach((label, index) => {
                label.hidden = !names[index].toLowerCase().includes(query);
            });
        });
        panel.appendChild(search);
    }
    const list = document.createElement('div');
    list.className = kind + '-list';
    names.forEach((name, index) => {
        const label = document.createElement('label');
        const box = document.createElement('input');
        box.type = 'checkbox';
        box.checked = true;
        box.addEventListener('change', () => { refreshStatus(); updateSelection(); });
        label.appendChild(box);
        if (kind === 'barcode' || kind === 'group') {
            const swatch = document.createElement('span');
            swatch.className = 'barcode-color';
            const style = kind === 'group' ? graph.layout.meta.group_styles[index] :
                [graph.data[coloredIndices[index]].line.color, graph.data[coloredIndices[index]].opacity];
            swatch.style.backgroundColor = style[0];
            swatch.style.opacity = style[1];
            label.appendChild(swatch);
        }
        label.appendChild(document.createTextNode(name));
        list.appendChild(label);
        labels.push(label);
        boxes.push(box);
    });
    panel.appendChild(list);
    refreshStatus();
    graph.parentNode.insertBefore(panel, graph);
    return boxes;
}
sampleBoxes = addControls('Samples', 'sample', sampleNames,
    'Uncheck samples to gray out their points and connecting segments. Counts and frequencies stay unchanged. All plotted barcodes must be real in the first sample; later real flags do not restrict plots.');
if (groupNames.length) {
    groupBoxes = addControls('Groups', 'group', groupNames,
        'Uncheck a group to hide all its trajectories, including gray backgrounds. Rechecking it preserves your barcode and sample selections. Counts and frequencies stay unchanged.');
}
barcodeBoxes = addControls('Barcodes', 'barcode', barcodeNames,
    'Uncheck barcodes to gray out their entire trajectories. Barcode and sample selections work together. Search filters this list without changing selections; the buttons apply to all barcodes.');
"""


def save_interactive_trajectory_plot(barcodes, freqs, outpath: Path, title: str, cfg: dict):
    import plotly.graph_objects as go
    import plotly.io as pio
    from plotly.colors import qualitative

    samples = list(freqs.columns)
    pseudo = float(cfg["pseudocount_for_log_plots"])
    fig = go.Figure()
    for i, barcode in enumerate(barcodes):
        style = trajectory_style(barcode, cfg)
        color = style[1] if style else qualitative.Plotly[i % len(qualitative.Plotly)]
        opacity = style[2] if style else 1.0
        unlisted = style is not None and opacity == 0.5
        frequencies = freqs.loc[barcode].astype(float).tolist()
        values = [value + pseudo for value in frequencies]
        group_text = f" | {style[0]}" if style else ""
        hover = [html.escape(f"{barcode} | {sample}{group_text}") for sample in samples]
        # Unlisted trajectories are already gray: keep a single 50%-opaque base.
        # An empty overlay lets selection controls preserve this appearance without
        # stacking two translucent traces and making the line more opaque.
        for overlay in (False, True):
            trace_color = color if overlay or unlisted else "#b8b8b8"
            fig.add_trace(go.Scattergl(
                x=list(range(len(samples))),
                y=[None] * len(samples) if unlisted and overlay else values,
                mode="lines+markers", opacity=opacity,
                line={"color": trace_color, "width": 1},
                marker={"color": trace_color, "size": 5},
                name=html.escape(barcode), text=hover, customdata=frequencies,
                hovertemplate="%{text}<br>Frequency: %{customdata:.6g}<extra></extra>",
                showlegend=False, connectgaps=False,
            ))
    legend = trajectory_legend(barcodes, cfg)
    group_names = [style[0] for style in legend]
    group_indices = {group: index for index, group in enumerate(group_names)}
    for group, color, opacity in legend:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="lines+markers", name=html.escape(group),
            line={"color": color, "width": 2}, marker={"color": color, "size": 5},
            opacity=opacity, showlegend=True, hoverinfo="skip",
        ))
    fig.update_layout(
        title=html.escape(title), template="plotly_white", height=650,
        xaxis={"tickmode": "array", "tickvals": list(range(len(samples))),
               "ticktext": [html.escape(sample) for sample in samples], "tickangle": -90},
        yaxis={"title": "Barcode frequency", "type": "log" if cfg.get("log_scale_y_axis", True) else "linear"},
        legend={"title": {"text": "Barcode group"}, "itemclick": False, "itemdoubleclick": False},
        meta={"sample_names": samples, "barcode_names": list(barcodes), "real_barcode_sample": "first",
              "colored_trace_indices": list(range(1, 2 * len(barcodes), 2))},
        uirevision="trajectory-selection",
    )
    fig.layout.meta.update({
        "group_names": group_names,
        "group_styles": [[color, opacity] for _, color, opacity in legend],
        "barcode_group_indices": [group_indices[style[0]] if (style := trajectory_style(barcode, cfg)) else None
                                  for barcode in barcodes],
    })
    # Embed the JavaScript bundle: these files can be opened with no server/network.
    fragment = pio.to_html(
        fig, full_html=False, include_plotlyjs=True,
        div_id="barcode-trajectories", post_script=TRAJECTORY_CONTROLS,
        config={"responsive": True, "displaylogo": False},
    )
    document = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Barcode trajectories</title><style>
body { font: 15px system-ui, sans-serif; margin: 24px; color: #222; }
.selection-controls { padding: 16px; margin-bottom: 12px; background: #f5f5f5; border-radius: 8px; }
.selection-controls h2 { margin: 0; }
.selection-controls button { margin: 0 8px 12px 0; padding: 6px 12px; }
.selection-status { color: #555; }
.barcode-controls input[type="search"] { display: block; margin-bottom: 12px; padding: 6px; }
.sample-list, .group-list { display: flex; flex-wrap: wrap; gap: 12px; }
.selection-controls label { display: inline-flex; align-items: center; gap: 4px; }
.selection-controls label[hidden] { display: none; }
.barcode-list { display: flex; flex-wrap: wrap; gap: 12px; max-height: 220px; overflow-y: auto; }
.barcode-list label { font-family: monospace; overflow-wrap: anywhere; }
.barcode-color { display: inline-block; width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
</style></head><body>""" + fragment + "</body></html>"
    outpath.write_text(document, encoding="utf-8")
