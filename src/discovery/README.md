# Discovery output builder

`src.discovery` turns a validated base `research_graph` plus reviewed discovery
configuration and an auditable novelty-search result into one deterministic
release. It does not infer claims from node labels.

## Python API

```python
from pathlib import Path
from src.discovery import build_discovery_outputs, write_discovery_release

artifacts = build_discovery_outputs(base_graph, config, novelty_search)
manifest = write_discovery_release(
    artifacts,
    output_dir=Path("output/run/F_discovery/release"),
    config=config,
    base_graph_snapshot_id=base_graph["snapshot_id"],
)
```

The config contract is `schemas/discovery_config.schema.json`. All references
to source/knowledge nodes and evidence are real graph IDs. IDs for new streams,
trend snapshots, gaps and hypotheses are explicit, stable IDs in the config.
`run.build_timestamp` is required, so rerunning the same three inputs produces
the same snapshots, hashes, manifest and file bytes.

Optional `inferred_entities` creates design-candidate `variable`, `measure`,
`dataset`, `method`, `model`, `identification_strategy` or `mechanism` nodes.
Each candidate must state its definition and granularity and must carry existing
graph evidence plus a derivation with graph-node inputs. This is the supported
way to keep, for example, a firm-year emission-intensity construct distinct
from a city-level emissions variable.

The preferred novelty input is the real `novelty-search/1.0.1` protocol: the
Gap config references its top-level `search_id`. The builder aggregates query
texts and source names, deduplicates returned works, and defaults to
`partially_covered` when evaluated bibliographic candidates exist or
`uncertain` when none exist. Automatic nearest-work descriptions stay
`unverified` and explicitly bounded to metadata. Optional
`gap.novelty_assessment` can supply reviewed overlap/difference judgments; a
`covered` status is rejected unless every included nearest work is verified.

## CLI

```powershell
python -m src.discovery `
  --base-graph output/run/E_graph/research_graph.json `
  --config output/run/F_discovery/discovery_config.json `
  --novelty-search output/run/F_discovery/novelty_search.json `
  --out output/run/F_discovery/release

python -m src.discovery.validate `
  --release-dir output/run/F_discovery/release `
  --novelty-search output/run/F_discovery/novelty_search.json `
  --small-sample-threshold 10
```

The release contains `final_research_graph.json`,
`research_landscape.json`, one file per GapCard and HypothesisCard, and
`discovery_release_manifest.json`. The validation command checks schemas,
graph semantics, artifact hashes and every graph/evidence/card reference.

## Hard gates

- Base and final graphs must pass `validate_graph`.
- Every Gap has both incoming `INDICATES_GAP` and outgoing
  `SUPPORTED_BY_EVIDENCE`.
- Every Hypothesis has `ADDRESSES_GAP` and `HAS_OUTCOME`; card variables and
  recommended designs must resolve to matching graph relations.
- If the eligible paper count is below `run.small_sample_threshold`, all trend
  `growth_rate` values are `null` and the Landscape carries a small-sample
  warning.
- Assigned papers dated after `run.as_of` are rejected.
- A `novelty-search/1.0.1` input must include exact, broad and adjacent query
  families and at least three distinct sources.
- Every Landscape includes an explicit corpus-limit warning; no output is a
  claim about the global literature.
