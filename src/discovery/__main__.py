"""Command-line entry point for deterministic discovery release construction."""

from __future__ import annotations

import argparse
from pathlib import Path

from .builder import build_discovery_outputs, load_json, write_discovery_release


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build ResearchLandscape, GapCards, HypothesisCards and an augmented graph"
    )
    parser.add_argument("--base-graph", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--novelty-search", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    base_graph = load_json(args.base_graph)
    config = load_json(args.config)
    novelty = load_json(args.novelty_search)
    artifacts = build_discovery_outputs(base_graph, config, novelty)
    manifest = write_discovery_release(
        artifacts,
        output_dir=args.out,
        config=config,
        base_graph_snapshot_id=base_graph["snapshot_id"],
    )
    print(
        "OK: wrote discovery release "
        f"{manifest['release_id']} with graph {artifacts.graph['snapshot_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
