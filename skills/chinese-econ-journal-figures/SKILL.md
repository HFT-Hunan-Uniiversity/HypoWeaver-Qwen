---
name: chinese-econ-journal-figures
description: Generate or revise reproducible, grayscale figures for Chinese economics and finance papers, especially event-study plots, robustness coefficient plots, trend charts, and theoretical mechanism diagrams styled after journals such as Economic Research Journal, Journal of Financial Research, and China Industrial Economics. Use when a Chinese empirical paper, competition report, or research system needs publication-ready figures, figure captions, provenance labels, or visual QA.
---

# Chinese Economics Journal Figures

Create restrained, evidence-linked figures that remain legible in black-and-white printing and can be regenerated from a small JSON specification.

## Required inputs

Before rendering, establish:

- the claim or relationship the figure is meant to communicate;
- the figure kind: `mechanism`, `event_study`, or `coefficient`;
- the values and labels to plot;
- the provenance status: `conceptual`, `observed`, `estimated`, `simulated`, or `demo`;
- the output directory and figure identifier.

Never present simulated or preloaded values as observed empirical results. Use `conceptual` for theory diagrams that contain no estimates. For `demo` and `simulated` inputs, keep a visible provenance label in the figure and a complete qualification in the caption.

## Workflow

1. Read [references/venue-style.md](references/venue-style.md) before choosing layout or captions.
2. Choose the smallest chart that answers the research question:
   - `mechanism` for theory, channels, moderators, and outcomes;
   - `event_study` for dynamic treatment effects and pre-trend diagnostics;
   - `coefficient` for robustness or subgroup estimates with confidence intervals.
3. Prepare a UTF-8 JSON specification. Use the examples in this skill or the schema implied by `scripts/render_econ_figure.py`.
4. Validate scientific semantics before rendering:
   - event-study periods must be sorted; estimates and interval arrays must have equal lengths; `lower <= estimate <= upper`; the omitted reference period must be identified;
   - coefficient rows must have names, estimates, and valid intervals;
   - mechanism nodes need unique IDs and every edge endpoint must exist.
5. Render with:

   `python scripts/render_econ_figure.py --spec <spec.json> --output-dir <directory>`

6. Inspect the PNG at original resolution. Confirm that Chinese glyphs, minus signs, confidence intervals, legends, and the zero line are readable.
7. Place the figure number, title, source, interpretation, and data-status note outside the plot in the manuscript. Do not rely on a decorative in-chart title.

## House style

- Use a white background, black text, black/gray strokes, and no gradients or ornamental panels.
- Use line style, marker shape, and fill in addition to tone; never encode meaning with color alone.
- Prefer 95% confidence intervals for empirical coefficients unless the manuscript states another level.
- Use a dashed horizontal zero line for effect estimates and a thin vertical line for the policy time where relevant.
- Use concise axis labels and direct units. Avoid dense gridlines, legends inside the data region, and excessive decimal precision.
- In multi-panel figures, label panels `(a)`, `(b)`, and so on, then give one shared caption.
- Keep figure notes complete enough to stand alone: sample, estimator, fixed effects, standard errors, confidence level, omitted period, and provenance status.
- Export SVG for the web or vector editing, PDF for manuscripts, and a 300-dpi PNG for previews and Word.

## Output contract

The renderer writes `<id>.svg`, `<id>.pdf`, `<id>.png`, and `<id>.metadata.json`. The metadata records a SHA-256 digest of the input specification, provenance status, generation time, and output filenames. Treat the JSON specification as the source of truth; do not edit exported graphics by hand.
