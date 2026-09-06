"""Build the reviewed discovery configuration for the six-paper pilot.

The configuration is generated from stable graph node IDs and inherits evidence
IDs from the source graph.  It deliberately labels proposed variables, data,
methods, identification and models as inferred design candidates rather than as
observations extracted from any paper.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


AS_OF = "2026-08-09T18:30:00+08:00"
NOVELTY_ID = "novelty:4de85d5658e5c1dad9018271"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def build_config(graph: dict[str, Any], novelty: dict[str, Any]) -> dict[str, Any]:
    node_by_id = {node["id"]: node for node in graph["nodes"]}

    def require(node_id: str, node_type: str | None = None) -> str:
        node = node_by_id.get(node_id)
        if node is None:
            raise ValueError(f"source graph is missing required node {node_id}")
        if node_type is not None and node.get("type") != node_type:
            raise ValueError(
                f"required node {node_id} has type {node.get('type')}, expected {node_type}"
            )
        return node_id

    def evidence(*node_ids: str) -> list[str]:
        values: list[str] = []
        for node_id in node_ids:
            require(node_id)
            for evidence_id in node_by_id[node_id].get("evidence_ids", []):
                if evidence_id not in values:
                    values.append(evidence_id)
        if not values:
            raise ValueError(f"nodes have no evidence: {node_ids}")
        return values

    if novelty.get("schema_version") != "novelty-search/1.0.1":
        raise ValueError("the formal build requires novelty-search/1.0.1")
    if novelty.get("search_id") != NOVELTY_ID:
        raise ValueError(
            f"unexpected novelty search id {novelty.get('search_id')}; expected {NOVELTY_ID}"
        )

    paper = {
        "digital": require("paper:0bd565cac43dabd7f104", "paper"),
        "regional_pollution": require("paper:6c2b7f26d1d65870d5cc", "paper"),
        "greenwashing": require("paper:737eb3a66c0d2f040ff2", "paper"),
        "carbon_efficiency": require("paper:7de68d3c5cc5cbc612f6", "paper"),
        "investment": require("paper:b5b07eddd3a8af3b1a12", "paper"),
        "fintech": require("paper:f2ded7345d6e1eab920c", "paper"),
    }

    finding = {
        "carbon_efficiency": require("finding:07693c9c88cc0219a9ae", "finding"),
        "regional_mechanisms": require("finding:079105718f2bbbe163f6", "finding"),
        "threshold": require("finding:0ff8a96b5f1dc66f9c4e", "finding"),
        "digital_human_capital": require("finding:1783e2252eed25b0ff58", "finding"),
        "greenwashing_subgroups": require("finding:17cfc4b46d0b092a195d", "finding"),
        "fintech_investment": require("finding:5225aa8022947de2ccbd", "finding"),
        "fintech_so2": require("finding:6b9d34537940ec95409c", "finding"),
        "investment_mechanism_proxy": require("finding:7f5ce05e5b742e2a94f7", "finding"),
        "innovation_mediation": require("finding:829cd3fe935a3a64a106", "finding"),
        "regional_so2": require("finding:9339e5515469448234f0", "finding"),
        "monitoring": require("finding:966c561f5882221d0241", "finding"),
        "policy_pollution": require("finding:9fe28507ee78bfe4c7b5", "finding"),
        "investment_efficiency": require("finding:be90e1cb4f9949ca9272", "finding"),
        "digital_carbon": require("finding:c07446524415193bc420", "finding"),
        "greenwashing": require("finding:d6439e0d037564f743fb", "finding"),
        "investment_scale": require("finding:f0900238ce57a4421988", "finding"),
        "digital_innovation": require("finding:f73802233441c0258041", "finding"),
    }

    limitation = {
        "greenwashing_scope": require("limitation:01189e1c1ea7d5b83dab", "limitation"),
        "digital_omitted": require("limitation:212d2464e7228d33a28e", "limitation"),
        "fintech_endogeneity": require("limitation:4b1df2654cac0a52df50", "limitation"),
        "digital_comparison": require("limitation:9c4dca3861105dd5113b", "limitation"),
        "province_aggregation": require("limitation:a01636fb291230478b07", "limitation"),
        "disclosure_selection": require("limitation:b7762bcd39ebcf094a62", "limitation"),
    }

    variable = {
        "policy": require("variable:7bb6a3ded79cc368c137", "variable"),
        "rd": require("variable:264d504e913014a7486d", "variable"),
        "patents": require("variable:3481e1b357df45b7a4a6", "variable"),
        "investment_efficiency": require("variable:6e901cfa40048f423a4d", "variable"),
        "greenwashing": require("variable:9716536f62c81fe13e7c", "variable"),
        "fintech": require("variable:6c4b748b14ae4105be27", "variable"),
        "city_co2": require("variable:2b575994aa4e7cffb619", "variable"),
        "carbon_efficiency": require("variable:a91fceeaef207ed27d2f", "variable"),
        "so2_intensity": require("variable:70d8b5cc2718aa09c94c", "variable"),
        "degf": require("variable:ba7c4c265d14430ae307", "variable"),
        "ctfp": require("variable:f18e1f25e1e2dd3d9972", "variable"),
        "green_finance_index": require("variable:f0cca5e02a4bef033525", "variable"),
        "green_innovation": require("variable:abf8b923fd79faf5fbf9", "variable"),
        "policy_adoption": require("variable:efa1eaaeaa80666c16a7", "variable"),
    }

    inferred = {
        "firm_emissions": "variable:firm_emission_intensity",
        "digital_capacity": "variable:prepolicy_regional_digital_fintech_capacity",
        "linked_panel": "dataset:candidate_linked_firm_environment_panel",
        "method": "method:staggered_did_event_study_ddd",
        "identification": "identification_strategy:staggered_did_prepolicy_digital_ddd",
        "model": "model:dual_outcome_staggered_did_ddd",
    }

    dataset = {
        "policy": require("dataset:1771fc3c5a5642c8b73d", "dataset"),
        "csmar": require("dataset:802021914aed4b33bd77", "dataset"),
        "wind": require("dataset:9b58e68145a79ca0e199", "dataset"),
        "hesg": require("dataset:480c9ccfbb3aa55da2de", "dataset"),
        "besg": require("dataset:8b44bff02ef242fec7fa", "dataset"),
        "disclosures": require("dataset:fa4bd5bdef8cd401e91f", "dataset"),
        "digital": require("dataset:d76b86630b7740576809", "dataset"),
    }

    method = {
        "staggered_did": require("method:9037c3268abe9a476486", "method"),
        "multi_did": require("method:5a507199c6f6b303a401", "method"),
        "subgroup": require("method:8f858f12d1649529f2c6", "method"),
        "fixed_effects": require("method:5c58282a291ebdd9a4a6", "method"),
        "mediation": require("method:b0d7d9906518894f0902", "method"),
        "threshold": require("method:e5d245fe973c41444d04", "method"),
        "sdid": require("method:863e7b41039ed64c0f38", "method"),
        "lasso_scm": require("method:3e2ef6e96f577bdbb860", "method"),
        "dml": require("method:045063b24340b8ea84e3", "method"),
    }

    identification = {
        "gfripz": require("identification_strategy:71df48cacbc4927a2414", "identification_strategy"),
        "staggered": require("identification_strategy:e0166329ab986501355b", "identification_strategy"),
        "dml": require("identification_strategy:bf89c2eb19a71b812e51", "identification_strategy"),
        "scm": require("identification_strategy:f89656df735bbcb0dc80", "identification_strategy"),
        "sdid": require("identification_strategy:fd4318a6c0c227b7af6d", "identification_strategy"),
    }

    model = {
        "investment_did": require("model:13a481645a654f531271", "model"),
        "greenwashing_did": require("model:cdbdae6857ac917076f1", "model"),
        "mechanism_proxy": require("model:b2903ac593365f8ff768", "model"),
        "monitoring": require("model:f88f1c6623073bf32fc5", "model"),
        "regional_fe": require("model:09fce5d38fa6fe89dfb5", "model"),
        "threshold": require("model:5866bd353d28cc359884", "model"),
        "mediation": require("model:f0393911e6213304568f", "model"),
        "sdid": require("model:863e7b41039ed64c0f38", "model"),
        "scm": require("model:923f00a4701059a3a199", "model"),
        "dml": require("model:045063b24340b8ea84e3", "model"),
        "fintech_fe": require("model:97f7b97237051078a478", "model"),
    }

    topic = {
        "investment_efficiency": require("topic:e245fc811d8aa7006c8e", "topic"),
        "greenwashing": require("topic:77f473afb50fd71424c6", "topic"),
        "regional_emissions": require("topic:204650108c53e564fe3a", "topic"),
        "carbon_efficiency": require("topic:a91fceeaef207ed27d2f", "topic"),
        "threshold": require("topic:4fcebb078831c5c794c7", "topic"),
        "fintech": require("topic:6c4b748b14ae4105be27", "topic"),
        "green_policy": require("topic:6b9d24c6ef255a31cf24", "topic"),
        "digital_green": require("topic:b16b327396caeebca102", "topic"),
        "carbon_cobenefits": require("topic:e0fcb61532a082337388", "topic"),
    }

    mechanism = {
        "investment_reallocation": require("mechanism:5ea6e0043a6755a16fe5", "mechanism"),
        "financing": require("mechanism:4a4708bd7c1d26bec5d4", "mechanism"),
        "monitoring": require("mechanism:c5dda13611bca1aedf7c", "mechanism"),
        "reputation": require("mechanism:ae4320bd59d16ddc82e9", "mechanism"),
        "industrial": require("mechanism:4f045c16e4893218fdf4", "mechanism"),
        "regional_innovation": require("mechanism:537490cb4b5e71949b47", "mechanism"),
        "regional_green_tech": require("mechanism:abf8b923fd79faf5fbf9", "mechanism"),
        "fintech": require("mechanism:9518cb71824690dc545a", "mechanism"),
        "digital_innovation": require("mechanism:3f006f83130df7345c45", "mechanism"),
        "human_capital": require("mechanism:9126e1c344599968c306", "mechanism"),
    }

    trend = {
        "corporate": "trend_snapshot:corporate_investment_disclosure",
        "regional": "trend_snapshot:regional_emissions_efficiency",
        "digital": "trend_snapshot:digital_green_real_outcomes",
    }
    stream = {
        "corporate": "research_stream:corporate_investment_disclosure",
        "regional": "research_stream:regional_emissions_efficiency",
        "digital": "research_stream:digital_green_real_outcomes",
    }
    gap_id = "research_gap:firm_level_policy_innovation_efficiency_integrity_emissions"
    hypothesis_id = "hypothesis:policy_innovation_efficiency_integrity_emissions"

    inferred_entities = [
        {
            "id": inferred["firm_emissions"],
            "type": "variable",
            "label": "Firm emission intensity",
            "description": (
                "Proposed firm-year real-emissions outcome, deliberately kept distinct from "
                "the city- and province-level emissions observed in the pilot corpus."
            ),
            "confidence": 0.55,
            "evidence_ids": evidence(
                finding["digital_carbon"], finding["fintech_so2"], limitation["province_aggregation"]
            ),
            "derivation": {
                "method": "granularity_preserving_construct_refinement",
                "method_version": "0.1.0",
                "input_refs": [
                    variable["city_co2"],
                    variable["so2_intensity"],
                    limitation["province_aggregation"],
                ],
                "input_edge_refs": [],
                "parameters": {
                    "do_not_merge_across_granularity": True,
                    "observed_in_corpus": False,
                },
                "prompt_hash": None,
            },
            "properties": {
                "definition": (
                    "Firm greenhouse-gas emissions divided by a preregistered scale denominator "
                    "such as revenue, assets or physical output."
                ),
                "granularity": "firm-year",
                "candidate_denominators": ["revenue", "total assets", "physical output"],
                "observed_in_source_corpus": False,
            },
        },
        {
            "id": inferred["digital_capacity"],
            "type": "variable",
            "label": "Pre-policy regional digital and fintech capacity",
            "description": (
                "Proposed pre-treatment regional moderator, separated from policy-period digital-green "
                "treatment and from contemporaneous fintech outcomes."
            ),
            "confidence": 0.58,
            "evidence_ids": evidence(
                variable["fintech"], finding["fintech_investment"], limitation["digital_omitted"]
            ),
            "derivation": {
                "method": "temporal_construct_refinement",
                "method_version": "0.1.0",
                "input_refs": [
                    variable["fintech"],
                    topic["digital_green"],
                    limitation["digital_omitted"],
                ],
                "input_edge_refs": [],
                "parameters": {
                    "pre_treatment_only": True,
                    "observed_in_corpus": False,
                },
                "prompt_hash": None,
            },
            "properties": {
                "definition": (
                    "Regional digital-finance or fintech capacity measured strictly before each "
                    "region's green-finance pilot treatment date."
                ),
                "granularity": "region by pre-treatment year or fixed pre-period baseline",
                "candidate_measure": "lagged or pre-period PKU-DFIC / validated fintech index",
                "observed_in_source_corpus": False,
            },
        },
        {
            "id": inferred["linked_panel"],
            "type": "dataset",
            "label": "Candidate linked firm environmental panel",
            "description": (
                "A proposed join of policy timing, firm accounts, environmental investment, ESG "
                "disclosure, patents, real emissions and pre-policy regional digital capacity."
            ),
            "confidence": 0.48,
            "evidence_ids": evidence(
                dataset["policy"],
                dataset["csmar"],
                dataset["wind"],
                dataset["hesg"],
                dataset["disclosures"],
                dataset["digital"],
            ),
            "derivation": {
                "method": "candidate_data_linkage_design",
                "method_version": "0.1.0",
                "input_refs": [
                    dataset["policy"],
                    dataset["csmar"],
                    dataset["wind"],
                    dataset["hesg"],
                    dataset["besg"],
                    dataset["disclosures"],
                    dataset["digital"],
                ],
                "input_edge_refs": [],
                "parameters": {
                    "materialized": False,
                    "rights_and_join_keys_require_review": True,
                },
                "prompt_hash": None,
            },
            "properties": {
                "definition": "Unmaterialized candidate firm-year analysis table assembled from the listed sources.",
                "granularity": "firm-year linked to region-year",
                "availability": "conditional",
                "observed_in_source_corpus": False,
            },
        },
        {
            "id": inferred["method"],
            "type": "method",
            "label": "Staggered DID event study with pre-policy digital DDD",
            "description": (
                "Proposed estimation workflow combining staggered-treatment event studies with a "
                "pre-treatment digital-capacity interaction and joint outcome reporting."
            ),
            "confidence": 0.57,
            "evidence_ids": evidence(
                method["staggered_did"], method["dml"], method["lasso_scm"]
            ),
            "derivation": {
                "method": "method_synthesis",
                "method_version": "0.1.0",
                "input_refs": [
                    method["staggered_did"], method["dml"], method["lasso_scm"]
                ],
                "input_edge_refs": [],
                "parameters": {
                    "executed": False,
                    "requires_pretrend_and_spillover_diagnostics": True,
                },
                "prompt_hash": None,
            },
            "properties": {
                "definition": (
                    "A preregistered staggered DID/event-study analysis with a policy-by-baseline-"
                    "digital-capacity interaction, interpreted as a DDD contrast."
                ),
                "granularity": "firm-year estimates with region-level treatment and moderator",
                "executed_in_pilot": False,
            },
        },
        {
            "id": inferred["identification"],
            "type": "identification_strategy",
            "label": "GFRIPZ staggered adoption by pre-policy digital capacity",
            "description": (
                "Proposed identification strategy using staggered GFRIPZ timing and predetermined "
                "digital capacity; validity remains conditional on pre-trends, no anticipation and spillover tests."
            ),
            "confidence": 0.52,
            "evidence_ids": evidence(
                identification["gfripz"], identification["staggered"], variable["fintech"]
            ),
            "derivation": {
                "method": "identification_strategy_synthesis",
                "method_version": "0.1.0",
                "input_refs": [
                    identification["gfripz"],
                    identification["staggered"],
                    inferred["digital_capacity"],
                ],
                "input_edge_refs": [],
                "parameters": {
                    "identified": False,
                    "moderator_must_predate_treatment": True,
                },
                "prompt_hash": None,
            },
            "properties": {
                "definition": (
                    "Staggered policy adoption contrast augmented by a predetermined regional digital "
                    "capacity interaction; not yet empirically validated."
                ),
                "granularity": "firm-year outcome, region-year treatment",
                "executed_in_pilot": False,
            },
        },
        {
            "id": inferred["model"],
            "type": "model",
            "label": "Dual-outcome staggered DID and DDD model",
            "description": (
                "Proposed model estimating disclosure-integrity and real-emissions outcomes in parallel, "
                "with an innovation/EPIE mechanism sequence and pre-policy digital moderation."
            ),
            "confidence": 0.5,
            "evidence_ids": evidence(
                finding["investment_efficiency"],
                finding["greenwashing"],
                finding["digital_carbon"],
                finding["investment_mechanism_proxy"],
            ),
            "derivation": {
                "method": "falsifiable_model_synthesis",
                "method_version": "0.1.0",
                "input_refs": [
                    inferred["method"],
                    inferred["identification"],
                    variable["policy"],
                    variable["investment_efficiency"],
                    variable["greenwashing"],
                    inferred["firm_emissions"],
                    inferred["digital_capacity"],
                ],
                "input_edge_refs": [],
                "parameters": {
                    "estimated": False,
                    "sequential_mediation_is_conjectural": True,
                },
                "prompt_hash": None,
            },
            "properties": {
                "definition": (
                    "Joint reporting framework for staggered DID/DDD coefficients on greenwashing and "
                    "firm emission intensity, plus separately audited mechanism regressions."
                ),
                "granularity": "firm-year",
                "estimated_in_pilot": False,
            },
        },
    ]

    corporate_evidence = evidence(
        finding["investment_efficiency"],
        finding["investment_mechanism_proxy"],
        finding["greenwashing"],
        finding["monitoring"],
    )
    regional_evidence = evidence(
        finding["regional_so2"],
        finding["regional_mechanisms"],
        finding["carbon_efficiency"],
        finding["threshold"],
    )
    digital_evidence = evidence(
        finding["policy_pollution"],
        finding["fintech_investment"],
        finding["digital_carbon"],
        finding["digital_innovation"],
    )

    supporting_findings = [
        finding["investment_mechanism_proxy"],
        finding["investment_efficiency"],
        finding["greenwashing"],
        finding["monitoring"],
        finding["fintech_investment"],
        finding["fintech_so2"],
        finding["digital_carbon"],
        finding["digital_innovation"],
    ]
    supporting_evidence = evidence(*supporting_findings)
    challenge_findings = [finding["greenwashing"], finding["digital_carbon"]]
    counterevidence = evidence(*challenge_findings)

    signal_bridge = {
        "signal_type": "cross_stream_bridge",
        "metric_name": "separately_observed_component_streams",
        "metric_value": 3,
        "threshold": 2,
        "explanation": (
            "The six-paper graph separately contains corporate investment/disclosure outcomes, "
            "regional emissions outcomes, and digital/fintech mechanisms, but no single paper-owned "
            "path joins all components at firm-year granularity."
        ),
        "graph_refs": [
            trend["corporate"],
            trend["regional"],
            trend["digital"],
            finding["investment_efficiency"],
            finding["greenwashing"],
            finding["digital_carbon"],
        ],
        "evidence_ids": evidence(
            finding["investment_efficiency"],
            finding["greenwashing"],
            finding["digital_carbon"],
        ),
    }
    signal_granularity = {
        "signal_type": "population_coverage",
        "metric_name": "firm_emissions_outcome_present",
        "metric_value": 0,
        "threshold": 1,
        "explanation": (
            "Real emissions evidence in the selected corpus is city/province-level, while the "
            "greenwashing and investment-efficiency evidence is firm-level; the graph therefore "
            "does not substitute a city outcome for the proposed firm outcome."
        ),
        "graph_refs": [
            limitation["province_aggregation"],
            limitation["disclosure_selection"],
            inferred["firm_emissions"],
        ],
        "evidence_ids": evidence(
            limitation["province_aggregation"], limitation["disclosure_selection"]
        ),
    }
    signal_mechanism = {
        "signal_type": "untested_mechanism",
        "metric_name": "joint_sequential_mediation_test_count",
        "metric_value": 0,
        "threshold": 1,
        "explanation": (
            "The corporate-investment paper reports R&D/patent mechanism-proxy regressions rather "
            "than a formal indirect-effect test, and the greenwashing paper tests different channels."
        ),
        "graph_refs": [
            finding["investment_mechanism_proxy"],
            limitation["greenwashing_scope"],
            mechanism["investment_reallocation"],
        ],
        "evidence_ids": evidence(
            finding["investment_mechanism_proxy"], limitation["greenwashing_scope"]
        ),
    }

    config: dict[str, Any] = {
        "schema_version": "0.1.0",
        "inferred_entities": inferred_entities,
        "run": {
            "as_of": AS_OF,
            "build_timestamp": AS_OF,
            "pipeline_run_id": "run:discovery:green_finance_deep6_hardened:20260809",
            "corpus_limit_statement": (
                "Trend, gap and hypothesis claims are limited to six eligibility-approved full-text "
                "papers, the frozen 1,062-record metadata snapshot, and the eight-query/four-source novelty search "
                "as of 2026-08-09. They are not global literature prevalence or priority claims."
            ),
            "small_sample_threshold": 10,
            "generator": "green-finance-discovery-builder/0.1.0",
            "code_version": "0.2.0",
        },
        "landscape": {
            "window": {
                "current_from": "2023-01-01",
                "current_to": "2026-08-09",
                "baseline_from": "2021-01-01",
                "baseline_to": "2022-12-31",
            },
            "methodology": {
                "eligibility_rule": (
                    "Only non-retracted, non-stub papers in the eligibility-approved six-paper "
                    "full-text release are assigned; membership was reviewed by paper node ID."
                ),
                "clustering": {
                    "features": ["graph_entities", "policy_link"],
                    "algorithm": "reviewed-membership",
                    "version": "0.1.0",
                    "parameters": {
                        "automatic_clustering": False,
                        "overlap_allowed": False,
                        "stream_count": 3,
                    },
                },
                "trend_scoring": {
                    "formula_version": "bounded-weighted-components/0.1.0",
                    "component_weights": {
                        "recent_paper_share": 0.3,
                        "growth_rate": 0.0,
                        "policy_alignment": 0.35,
                        "method_diversity": 0.35,
                    },
                },
                "llm_labeling": {
                    "model": "human-reviewed-graph-synthesis",
                    "prompt_hash": "2e8f750b267625595797609e3a6061179f03b3276784086043e54455bf250561",
                    "temperature": 0,
                },
            },
            "cluster_stability": 0.55,
            "warnings": [
                "Six papers are sufficient for a contract pilot, not for field-wide growth estimation.",
                "Growth rates are suppressed because each stream has only two papers.",
                "The 1,062-record metadata topic counts are descriptive retrieval signals and are not used as causal or prevalence estimates.",
                "Nearest works were reviewed at the strongest legally accessible layer (publisher full text or official abstract); restricted abstracts are not treated as full text.",
            ],
            "fields": [
                {
                    "field_id": "field:corporate_environmental_integrity",
                    "graph_node_id": require("research_field:628d4fe1dffbbd25d665", "research_field"),
                    "label": "Corporate environmental investment and disclosure integrity",
                    "member_paper_ids": [paper["investment"], paper["greenwashing"]],
                    "top_topic_ids": [topic["investment_efficiency"], topic["greenwashing"]],
                    "top_model_ids": [
                        model["investment_did"], model["greenwashing_did"], model["mechanism_proxy"]
                    ],
                    "evidence_ids": corporate_evidence,
                },
                {
                    "field_id": "field:regional_environmental_efficiency",
                    "graph_node_id": require("research_field:f9fc6b9ac6cb9e325200", "research_field"),
                    "label": "Regional pollution and carbon efficiency",
                    "member_paper_ids": [paper["regional_pollution"], paper["carbon_efficiency"]],
                    "top_topic_ids": [
                        topic["regional_emissions"], topic["carbon_efficiency"], topic["threshold"]
                    ],
                    "top_model_ids": [model["regional_fe"], model["threshold"], model["mediation"]],
                    "evidence_ids": regional_evidence,
                },
                {
                    "field_id": "field:digital_green_real_outcomes",
                    "graph_node_id": require("research_field:57706e5b785279332ba6", "research_field"),
                    "label": "Digital-green integration and real environmental outcomes",
                    "member_paper_ids": [paper["fintech"], paper["digital"]],
                    "top_topic_ids": [
                        topic["fintech"], topic["digital_green"], topic["carbon_cobenefits"]
                    ],
                    "top_model_ids": [model["fintech_fe"], model["sdid"], model["scm"], model["dml"]],
                    "evidence_ids": digital_evidence,
                },
            ],
            "streams": [
                {
                    "stream_id": stream["corporate"],
                    "trend_id": trend["corporate"],
                    "label": "Corporate investment efficiency and disclosure integrity",
                    "description": (
                        "In this six-paper sample, the 2024 corporate studies move from investment "
                        "scale toward investment efficiency and ESG greenwashing outcomes."
                    ),
                    "label_confidence": 0.84,
                    "confidence": 0.7,
                    "field_ids": ["field:corporate_environmental_integrity"],
                    "member_paper_ids": [paper["investment"], paper["greenwashing"]],
                    "core_paper_ids": [paper["investment"], paper["greenwashing"]],
                    "top_topic_ids": [topic["investment_efficiency"], topic["greenwashing"]],
                    "top_theory_ids": [],
                    "top_mechanism_ids": [
                        mechanism["investment_reallocation"],
                        mechanism["financing"],
                        mechanism["monitoring"],
                        mechanism["reputation"],
                    ],
                    "top_variable_ids": [
                        variable["policy"],
                        variable["investment_efficiency"],
                        variable["greenwashing"],
                        variable["rd"],
                        variable["patents"],
                    ],
                    "top_method_ids": [method["staggered_did"], method["multi_did"], method["subgroup"]],
                    "top_model_ids": [
                        model["investment_did"],
                        model["greenwashing_did"],
                        model["mechanism_proxy"],
                        model["monitoring"],
                    ],
                    "evidence_ids": corporate_evidence,
                },
                {
                    "stream_id": stream["regional"],
                    "trend_id": trend["regional"],
                    "label": "Regional pollution and carbon-efficiency pathways",
                    "description": (
                        "The two 2023 papers in the selected sample emphasize regional emissions, "
                        "carbon efficiency, industrial upgrading, innovation mediation and GDP thresholds."
                    ),
                    "label_confidence": 0.86,
                    "confidence": 0.72,
                    "field_ids": ["field:regional_environmental_efficiency"],
                    "member_paper_ids": [paper["regional_pollution"], paper["carbon_efficiency"]],
                    "core_paper_ids": [paper["regional_pollution"], paper["carbon_efficiency"]],
                    "top_topic_ids": [
                        topic["regional_emissions"], topic["carbon_efficiency"], topic["threshold"]
                    ],
                    "top_theory_ids": [],
                    "top_mechanism_ids": [
                        mechanism["industrial"], mechanism["regional_green_tech"], mechanism["regional_innovation"]
                    ],
                    "top_variable_ids": [
                        variable["green_finance_index"],
                        variable["so2_intensity"],
                        variable["carbon_efficiency"],
                        variable["green_innovation"],
                    ],
                    "top_method_ids": [method["fixed_effects"], method["mediation"], method["threshold"]],
                    "top_model_ids": [model["regional_fe"], model["threshold"], model["mediation"]],
                    "evidence_ids": regional_evidence,
                },
                {
                    "stream_id": stream["digital"],
                    "trend_id": trend["digital"],
                    "label": "Digital-green integration and real environmental outcomes",
                    "description": (
                        "The 2021 and 2025 papers in the selected sample connect fintech or digital-green "
                        "policy combinations to environmental investment, pollution, CO2 and carbon productivity."
                    ),
                    "label_confidence": 0.82,
                    "confidence": 0.68,
                    "field_ids": ["field:digital_green_real_outcomes"],
                    "member_paper_ids": [paper["fintech"], paper["digital"]],
                    "core_paper_ids": [paper["fintech"], paper["digital"]],
                    "top_topic_ids": [
                        topic["fintech"], topic["green_policy"], topic["digital_green"], topic["carbon_cobenefits"]
                    ],
                    "top_theory_ids": [],
                    "top_mechanism_ids": [
                        mechanism["fintech"], mechanism["digital_innovation"], mechanism["human_capital"]
                    ],
                    "top_variable_ids": [
                        variable["fintech"],
                        variable["policy_adoption"],
                        variable["degf"],
                        variable["city_co2"],
                        variable["ctfp"],
                    ],
                    "top_method_ids": [method["sdid"], method["lasso_scm"], method["dml"]],
                    "top_model_ids": [model["fintech_fe"], model["sdid"], model["scm"], model["dml"]],
                    "evidence_ids": digital_evidence,
                },
            ],
            "controversies": [],
            "frontier_signals": [
                {
                    "signal_id": "frontier:firm_level_real_and_reported_outcomes_bridge",
                    "signal_type": "cross_stream_bridge",
                    "statement": (
                        "The bounded graph exposes a testable bridge from policy and innovation-driven "
                        "investment efficiency to both reported integrity and real emissions, but the bridge "
                        "itself is an inferred design target rather than an extracted result."
                    ),
                    "score": 62,
                    "graph_node_ids": [
                        stream["corporate"], stream["digital"], finding["investment_efficiency"],
                        finding["greenwashing"], finding["digital_carbon"]
                    ],
                    "evidence_ids": evidence(
                        finding["investment_efficiency"], finding["greenwashing"], finding["digital_carbon"]
                    ),
                }
            ],
        },
        "gaps": [
            {
                "gap_id": gap_id,
                "gap_type": "cross_stream",
                "title": "Digital-capacity sign switch between substantive transition and opportunistic compliance",
                "statement": (
                    "Within the six eligible full-text papers, the eight-query/four-source search and the "
                    "reviewed citation-chasing set, close studies now cover most adjacent components. However, "
                    "no reviewed study tests whether digital/fintech capacity fixed before GFRIPZ treatment "
                    "separates a substantive firm-year pathway (innovation, higher EPIE, lower greenwashing and "
                    "lower direct carbon intensity) from an opportunistic pathway (greenwashing or environmental "
                    "overinvestment without commensurate real decarbonization)."
                ),
                "current_state": (
                    "The source graph contains separate positive links from GFRIPZ to R&D/patent proxies and "
                    "EPIE, lower greenwashing, and regional carbon outcomes. External nearest works report "
                    "conflicting signs for GFRIPZ-to-greenwashing, a digitalization buffer, firm pollution/carbon "
                    "effects, and an almost-complete pollution-versus-misallocation pathway."
                ),
                "missing_piece": (
                    "A single eligibility-checked firm-year test that fixes digital/fintech capacity before "
                    "treatment, measures direct firm carbon intensity, distinguishes efficient environmental "
                    "investment from overinvestment/misallocation, and estimates the competing substantive and "
                    "opportunistic response paths under the same policy exposure."
                ),
                "why_important": (
                    "The sign-switch design explains why credible studies can report both less and more "
                    "greenwashing after the same policy class, while separating real decarbonization from "
                    "disclosure or investment responses that only appear green."
                ),
                "signals": [signal_bridge, signal_granularity, signal_mechanism],
                "supporting_graph_refs": [
                    trend["corporate"], trend["regional"], trend["digital"],
                    *supporting_findings,
                    limitation["greenwashing_scope"], limitation["province_aggregation"],
                    inferred["firm_emissions"], inferred["digital_capacity"],
                ],
                "supporting_evidence_ids": supporting_evidence,
                "counterevidence_ids": counterevidence,
                "novelty_search_id": NOVELTY_ID,
                "novelty_assessment": {
                    "coverage_status": "partially_covered",
                    "remaining_difference": (
                        "The closest work (10.1016/j.eneco.2026.109333) already joins PZGFRI, corporate pollution, "
                        "greenwashing, environmental overinvestment, resource-allocation losses, digitalization and "
                        "green-innovation capacity. The remaining difference is narrower: a predetermined rather than "
                        "contemporaneous digital moderator, EPIE versus overinvestment measured in one framework, direct "
                        "firm carbon intensity, and a preregistered sign-switch test across real and reported outcomes."
                    ),
                    "max_nearest_works": 5,
                    "nearest_works": [
                        {
                            "paper_id": "10.1016/j.eneco.2026.109333",
                            "title": "Cleaner but less efficient? Green finance, resource misallocation, and supply chain spillovers in China",
                            "year": 2026,
                            "overlap": "Official publisher abstract covers PZGFRI, firm pollution, greenwashing, environmental overinvestment, resource-allocation efficiency, digitalization and green-innovation capacity.",
                            "difference": "It does not establish a pre-treatment digital moderator, the source-study EPIE construct, or direct firm carbon intensity under the proposed dual-outcome sign-switch test.",
                            "verification_status": "verified",
                        },
                        {
                            "paper_id": "10.1016/j.irfa.2025.104037",
                            "title": "How does green finance reform affect corporate ESG greenwashing behavior?",
                            "year": 2025,
                            "overlap": "Official publisher abstract reports that GFRIPZ increases greenwashing and that regional digitization mitigates the adverse effect.",
                            "difference": "It does not report a predetermined digital measure, EPIE, green innovation or direct firm carbon outcomes in the accessible record.",
                            "verification_status": "verified",
                        },
                        {
                            "paper_id": "10.1016/j.jenvman.2025.126110",
                            "title": "The impact of green finance reform and innovation pilot zones on corporate pollution and carbon reduction: From the perspective of dual objective constraints",
                            "year": 2025,
                            "overlap": "Official abstract covers GFRIPZ, corporate pollution/carbon reduction, environmental investment and green-technological innovation.",
                            "difference": "It does not jointly measure ESG greenwashing, EPIE and a predetermined digital-capacity moderator.",
                            "verification_status": "verified",
                        },
                        {
                            "paper_id": "10.1007/s10668-025-07142-y",
                            "title": "Can green finance reform curb corporate ESG greenwashing?",
                            "year": 2025,
                            "overlap": "Official abstract reports a negative green-finance-reform effect on ESG greenwashing and monitoring/information mechanisms.",
                            "difference": "Accessible material does not confirm GFRIPZ treatment, predetermined digital capacity, EPIE, innovation or direct emissions.",
                            "verification_status": "verified",
                        },
                        {
                            "paper_id": "10.1080/20430795.2026.2644286",
                            "title": "When green claims mislead: the effect of greenwashing on corporate investment efficiency",
                            "year": 2026,
                            "overlap": "Official abstract establishes the reverse adjacent link from greenwashing to lower general investment efficiency.",
                            "difference": "General investment efficiency is not EPIE, and the study has no GFRIPZ, digital moderator, innovation or direct emissions outcome.",
                            "verification_status": "verified",
                        },
                    ],
                },
                "data_feasibility": {
                    "status": "conditional",
                    "required_variable_ids": [
                        variable["policy"], variable["rd"], variable["patents"],
                        variable["investment_efficiency"], variable["greenwashing"],
                        inferred["firm_emissions"], inferred["digital_capacity"],
                    ],
                    "candidate_data_source_ids": [
                        inferred["linked_panel"], dataset["policy"], dataset["csmar"],
                        dataset["wind"], dataset["hesg"], dataset["besg"],
                        dataset["disclosures"], dataset["digital"],
                    ],
                    "blocking_gaps": [
                        "Firm-level verified emissions coverage and stable denominators are not established.",
                        "Commercial-source licenses, join keys and historical coverage require owner approval.",
                        "The ESG-disclosure sample may exclude non-disclosing firms and induce selection bias.",
                        "Policy spillovers and treatment contamination across neighboring regions require diagnostics.",
                    ],
                    "assessment_as_of": AS_OF,
                },
                "candidate_research_questions": [
                    "Does pre-policy digital/fintech capacity reverse the sign of GFRIPZ effects on ESG greenwashing?",
                    "Does a high-capacity regime raise innovation and EPIE while a low-capacity regime produces environmental overinvestment or resource misallocation?",
                    "Do disclosure-integrity changes align with direct firm carbon-intensity changes within each regime?",
                ],
                "scores": {
                    "novelty": 2.3,
                    "importance": 4.7,
                    "evidence_strength": 3.7,
                    "data_feasibility": 2.4,
                    "method_feasibility": 3.5,
                    "policy_value": 4.7,
                    "overall": 3.6,
                },
                "status": "accepted",
                "derivation": {
                    "workflow_version": "0.1.0",
                    "detector": "corpus_bounded_cross_stream_gap_detector",
                    "model": "human-reviewed-graph-synthesis",
                    "prompt_hash": "7dfd52a6a662becc0e12ea885bb23f141fa9e8ed093455086364b778fa51537e",
                    "input_refs": [
                        trend["corporate"], trend["regional"], trend["digital"],
                        *supporting_findings,
                        limitation["greenwashing_scope"], limitation["province_aggregation"],
                        limitation["digital_omitted"], inferred["firm_emissions"],
                        inferred["digital_capacity"], inferred["linked_panel"],
                    ],
                },
                "review": {
                    "review_status": "accepted",
                    "reviewer": "group1-literature-review",
                    "reviewed_at": AS_OF,
                    "comments": [
                        "Gap status is bounded to the declared corpus and novelty protocol.",
                        "Five formal nearest works and additional edge works were reviewed at publisher-full-text or official-abstract level; access limits are retained per work.",
                        "The gap was narrowed after finding an almost-complete 2026 PZGFRI misallocation study; no global first-study claim is permitted.",
                    ],
                },
                "confidence": 0.72,
                "graph_links": {
                    "indicator_node_ids": [
                        trend["corporate"], trend["regional"], trend["digital"],
                        limitation["greenwashing_scope"], limitation["province_aggregation"],
                    ],
                    "support_node_ids": supporting_findings,
                    "challenge_node_ids": challenge_findings,
                    "concern_node_ids": [
                        stream["corporate"], stream["regional"], stream["digital"],
                        variable["investment_efficiency"], variable["greenwashing"],
                        inferred["firm_emissions"], inferred["digital_capacity"],
                        mechanism["investment_reallocation"], inferred["method"],
                        inferred["identification"],
                    ],
                    "enabled_by_node_ids": [
                        inferred["linked_panel"], dataset["policy"], dataset["csmar"],
                        dataset["wind"], dataset["hesg"], dataset["disclosures"], dataset["digital"],
                    ],
                },
            }
        ],
        "hypotheses": [
            {
                "hypothesis_id": hypothesis_id,
                "gap_card_ids": [gap_id],
                "title": "Pre-policy digital capacity separates substantive transition from opportunistic compliance",
                "hypothesis_statement": (
                    "GFRIPZ has a conditional sign switch. Where regional digital/fintech capacity was high "
                    "before treatment, policy exposure is expected to raise green innovation and EPIE and reduce "
                    "both ESG greenwashing and direct firm carbon intensity. Where baseline capacity was low, "
                    "greenwashing is expected to be non-decreasing and any environmental investment or pollution "
                    "improvement need not translate into efficient, disclosure-consistent decarbonization."
                ),
                "falsifiable_form": (
                    "With digital capacity fixed before treatment, the policy-by-capacity interaction must be "
                    "positive for innovation/EPIE and negative for greenwashing and direct firm carbon intensity. "
                    "High-capacity firms must show aligned real-and-reported improvement, while low-capacity firms "
                    "must show a weaker, null or opposite greenwashing response. Common signs across capacity levels, "
                    "no innovation/EPIE separation, no real-carbon alignment, or failed pre-trends falsifies the sign-switch hypothesis."
                ),
                "rationale": (
                    "The source graph supplies separate, paper-owned evidence for policy-related innovation "
                    "proxies and EPIE, lower greenwashing, fintech/digital mechanisms, and lower city/province "
                    "emissions. The external nearest-work review additionally finds conflicting policy-to-greenwashing "
                    "signs and an almost-complete pollution-versus-misallocation pathway. Competing implementation "
                    "regimes are therefore the hypothesis; external review findings remain a separately audited citation layer, not graph-extracted facts."
                ),
                "mechanism_chain": [
                    {
                        "order": 1,
                        "source_node_id": variable["policy"],
                        "relation": "is_associated_with_candidate_innovation_channel",
                        "target_node_id": mechanism["investment_reallocation"],
                        "statement": (
                            "The corporate-investment study reports higher R&D and patent counts after GFRI "
                            "exposure and interprets them as channel proxies; it does not estimate a formal indirect effect."
                        ),
                        "evidence_ids": evidence(finding["investment_mechanism_proxy"]),
                    },
                    {
                        "order": 2,
                        "source_node_id": mechanism["investment_reallocation"],
                        "relation": "is_hypothesized_to_raise",
                        "target_node_id": variable["investment_efficiency"],
                        "statement": (
                            "R&D/patent proxies and higher EPIE are reported in the same study, but their "
                            "sequential mediation is a proposed test rather than a demonstrated link."
                        ),
                        "evidence_ids": evidence(
                            finding["investment_mechanism_proxy"], finding["investment_efficiency"]
                        ),
                    },
                    {
                        "order": 3,
                        "source_node_id": variable["investment_efficiency"],
                        "relation": "is_hypothesized_to_reduce",
                        "target_node_id": variable["greenwashing"],
                        "statement": (
                            "In the proposed substantive regime, higher EPIE should reduce greenwashing; the link "
                            "bridges separate source papers and must be estimated rather than assumed."
                        ),
                        "evidence_ids": evidence(
                            finding["investment_efficiency"], finding["greenwashing"]
                        ),
                    },
                    {
                        "order": 4,
                        "source_node_id": variable["investment_efficiency"],
                        "relation": "is_hypothesized_to_reduce",
                        "target_node_id": inferred["firm_emissions"],
                        "statement": (
                            "In the proposed substantive regime, higher EPIE should reduce direct firm carbon "
                            "intensity; current graph evidence is city/province-level, so this remains an untested granularity bridge."
                        ),
                        "evidence_ids": evidence(
                            finding["investment_efficiency"], finding["digital_carbon"], finding["policy_pollution"]
                        ),
                    },
                    {
                        "order": 5,
                        "source_node_id": inferred["digital_capacity"],
                        "relation": "is_hypothesized_to_strengthen",
                        "target_node_id": mechanism["investment_reallocation"],
                        "statement": (
                            "Predetermined digital/fintech capacity is proposed to separate substantive from "
                            "opportunistic response regimes; the interaction is not observed in the six-paper source corpus."
                        ),
                        "evidence_ids": evidence(
                            finding["fintech_investment"], finding["digital_innovation"]
                        ),
                    },
                ],
                "variables": {
                    "independent": [
                        {
                            "graph_node_id": variable["policy"],
                            "name": "GFRIPZ exposure",
                            "definition": "Firm exposure induced by the region's Green Finance Reform and Innovation Pilot Zone designation and timing.",
                            "role": "independent",
                            "expected_direction": "not_applicable",
                            "measurement_candidates": [
                                {
                                    "measure_node_id": require("measure:f3e5ac0aa7cec25a63b3", "measure"),
                                    "data_source_id": dataset["policy"],
                                    "availability": "open",
                                    "evidence_ids": evidence(require("measure:f3e5ac0aa7cec25a63b3", "measure")),
                                }
                            ],
                        }
                    ],
                    "dependent": [
                        {
                            "graph_node_id": variable["greenwashing"],
                            "name": "ESG greenwashing gap",
                            "definition": "Difference between substantive ESG performance and disclosed ESG performance under a preregistered construction.",
                            "role": "dependent",
                            "expected_direction": "heterogeneous",
                            "measurement_candidates": [
                                {
                                    "measure_node_id": require("measure:9716536f62c81fe13e7c", "measure"),
                                    "data_source_id": dataset["hesg"],
                                    "availability": "commercial",
                                    "evidence_ids": evidence(require("measure:9716536f62c81fe13e7c", "measure")),
                                }
                            ],
                        },
                        {
                            "graph_node_id": inferred["firm_emissions"],
                            "name": "Firm emission intensity",
                            "definition": "Firm-year greenhouse-gas emissions divided by a preregistered scale denominator.",
                            "role": "dependent",
                            "expected_direction": "heterogeneous",
                            "measurement_candidates": [],
                        },
                    ],
                    "mediators": [
                        {
                            "graph_node_id": variable["rd"],
                            "name": "R&D expenditure",
                            "definition": "Firm R&D expenditure under the source study's accounting construction.",
                            "role": "mediator",
                            "expected_direction": "positive",
                            "measurement_candidates": [
                                {
                                    "measure_node_id": require("measure:51bb1356282e213bfc7e", "measure"),
                                    "data_source_id": dataset["csmar"],
                                    "availability": "commercial",
                                    "evidence_ids": evidence(require("measure:51bb1356282e213bfc7e", "measure")),
                                }
                            ],
                        },
                        {
                            "graph_node_id": variable["patents"],
                            "name": "Granted patent count",
                            "definition": "Firm patent grants, with green-patent classification preferred for the confirmatory specification.",
                            "role": "mediator",
                            "expected_direction": "positive",
                            "measurement_candidates": [
                                {
                                    "measure_node_id": require("measure:ff5c78d2f5cafeeebe71", "measure"),
                                    "data_source_id": dataset["wind"],
                                    "availability": "commercial",
                                    "evidence_ids": evidence(require("measure:ff5c78d2f5cafeeebe71", "measure")),
                                }
                            ],
                        },
                        {
                            "graph_node_id": variable["investment_efficiency"],
                            "name": "Environmental-investment efficiency (EPIE)",
                            "definition": "Efficiency of corporate environmental investment as operationalized in the source study.",
                            "role": "mediator",
                            "expected_direction": "positive",
                            "measurement_candidates": [
                                {
                                    "measure_node_id": require("measure:6e901cfa40048f423a4d", "measure"),
                                    "data_source_id": dataset["csmar"],
                                    "availability": "commercial",
                                    "evidence_ids": evidence(require("measure:6e901cfa40048f423a4d", "measure")),
                                }
                            ],
                        },
                    ],
                    "moderators": [
                        {
                            "graph_node_id": inferred["digital_capacity"],
                            "name": "Pre-policy regional digital/fintech capacity",
                            "definition": "Regional digital-finance or fintech capacity fixed before treatment timing.",
                            "role": "moderator",
                            "expected_direction": "heterogeneous",
                            "measurement_candidates": [],
                        }
                    ],
                    "controls": [],
                },
                "boundary_conditions": [
                    "Chinese listed firms linked to GFRIPZ regions over a window with credible pre-treatment observations.",
                    "Digital/fintech capacity must be fixed before treatment rather than measured contemporaneously.",
                    "Regime separation must be defined by the pre-treatment moderator, not by conditioning on post-treatment EPIE.",
                    "Firm emissions and greenwashing measures must have stable definitions across treatment cohorts.",
                    "Results must be reported both for disclosing firms and under an explicit selection/missingness analysis.",
                ],
                "predictions": [
                    {
                        "prediction_id": "prediction:capacity_separates_innovation_epie",
                        "statement": "GFRIPZ raises R&D/green patents and EPIE more strongly at higher pre-policy digital/fintech capacity.",
                        "observable_pattern": "After flat leads, policy-by-baseline-capacity interactions are positive for innovation and EPIE.",
                        "would_falsify": "The interactions are precise zero/negative, disappear under common-support checks, or rely on post-treatment capacity.",
                    },
                    {
                        "prediction_id": "prediction:greenwashing_sign_switch",
                        "statement": "The GFRIPZ effect on greenwashing is negative at high baseline capacity but non-negative at low baseline capacity.",
                        "observable_pattern": "Marginal policy effects cross zero over the preregistered support of baseline digital/fintech capacity.",
                        "would_falsify": "The policy effect has the same precise sign across the support or the crossing point is specification-dependent.",
                    },
                    {
                        "prediction_id": "prediction:real_reported_alignment",
                        "statement": "High-capacity firms show aligned reductions in greenwashing and direct carbon intensity; low-capacity firms do not.",
                        "observable_pattern": "The same cohort and moderator specification yields two negative high-capacity outcome effects and weaker/null low-capacity real-carbon effects.",
                        "would_falsify": "Greenwashing falls without direct carbon improvement in the high-capacity regime, or low-capacity firms show equally strong alignment.",
                    },
                    {
                        "prediction_id": "prediction:competing_pathways",
                        "statement": "Innovation/EPIE dominates in the high-capacity regime, whereas overinvestment/misallocation or disclosure opportunism dominates in the low-capacity regime.",
                        "observable_pattern": "Preregistered mechanism contrasts are correctly signed and temporally ordered, with sensitivity bounds rather than mediator-conditioned causal claims.",
                        "would_falsify": "Mechanism contrasts do not differ by baseline capacity, temporal ordering fails, or the result exists only in the disclosing-firm subsample.",
                    },
                ],
                "evidence_balance": {
                    "supporting_finding_ids": supporting_findings,
                    "challenging_finding_ids": [],
                    "policy_document_ids": [require("policy_document:9ef2cecad8a35cfc6820", "policy_document")],
                    "unresolved_conflicts": [
                        "No source paper estimates the full sequential mediation chain.",
                        "Real emissions are observed at city/province rather than firm granularity in this pilot.",
                        "The greenwashing sample excludes firms without collectable environmental disclosure.",
                        "Digital-green policy identification may retain omitted-factor bias and policy spillovers.",
                        "Reviewed external studies report both lower and higher greenwashing after green-finance reform; the sign conflict is the target phenomenon, not noise to be averaged away.",
                        "The closest 2026 study links pollution reduction to environmental overinvestment, greenwashing and resource misallocation, challenging a uniformly beneficial EPIE pathway.",
                    ],
                },
                "novelty_check_ref": NOVELTY_ID,
                "feasibility": {
                    "data_status": "conditional",
                    "method_status": "conditional",
                    "citation_status": "partially_verified",
                    "blocking_items": [
                        "Acquire and license a linked firm-emissions panel with defensible denominators.",
                        "Confirm firm-to-pilot-region and policy-timing crosswalks.",
                        "Obtain restricted full texts for abstract-only nearest works before any global priority or fine-grained construct-equivalence claim.",
                        "Pre-register cohort, pre-trend, spillover, missingness and mediation sensitivity rules.",
                    ],
                    "assessed_at": AS_OF,
                },
                "recommended_design": {
                    "candidate_dataset_ids": [
                        inferred["linked_panel"], dataset["policy"], dataset["csmar"],
                        dataset["wind"], dataset["hesg"], dataset["besg"],
                        dataset["disclosures"], dataset["digital"],
                    ],
                    "candidate_method_ids": [inferred["method"]],
                    "candidate_model_ids": [inferred["model"]],
                    "candidate_identification_strategy_ids": [inferred["identification"]],
                    "unit_of_analysis": "firm-year linked to region-year policy treatment",
                    "baseline_specification": (
                        "Cohort-robust staggered DID/event study with firm and year effects, a pre-policy "
                        "digital-capacity DDD interaction, jointly reported greenwashing and firm-emission "
                        "outcomes, and separately audited R&D/patent/EPIE mechanism models."
                    ),
                    "major_threats": [
                        "Differential pre-trends and anticipation",
                        "Treatment spillovers and region contamination",
                        "Post-treatment measurement of the moderator",
                        "Disclosure selection and non-random missing emissions",
                        "Measurement error in ESG greenwashing and emissions denominators",
                        "Sequential-mediation identification assumptions",
                    ],
                },
                "scores": {
                    "novelty": 2.4,
                    "theory": 4.1,
                    "evidence": 3.5,
                    "data": 2.3,
                    "method": 3.4,
                    "policy_value": 4.7,
                    "overall": 3.6,
                },
                "handoff": {
                    "required_inputs": [
                        "Firm-year policy exposure crosswalk",
                        "R&D and green-patent panel",
                        "Environmental-investment scale and EPIE measures",
                        "ESG performance and disclosure-derived greenwashing measure",
                        "Verified firm emissions and scale denominator",
                        "Pre-policy regional digital/fintech-capacity measure",
                    ],
                    "blocking_questions": [
                        "Which firm-emissions source has adequate historical and cohort coverage?",
                        "Can non-disclosing firms be retained through alternative outcome construction or explicit selection weighting?",
                        "Which moderator baseline window avoids anticipation while preserving common support?",
                        "Are neighboring-region spillovers material enough to require exposure mapping?",
                    ],
                    "validation_acceptance_criteria": [
                        "All treatment cohorts pass preregistered pre-trend or equivalence diagnostics.",
                        "The digital moderator is measured strictly before treatment and has common support.",
                        "The policy effect on greenwashing is reported as a marginal-effect curve or preregistered contrast capable of detecting a sign switch.",
                        "Both disclosure and real-emissions outcomes are reported with missingness sensitivity.",
                        "Firm-emissions results survive alternative preregistered denominators.",
                        "Efficient environmental investment is distinguished from overinvestment and general resource-allocation efficiency.",
                        "Mechanism claims remain labeled associative unless sequential-mediation assumptions are defended.",
                        "No global first-study claim is made; restricted nearest works are upgraded only after lawful full-text review.",
                    ],
                    "evidence_bundle_refs": [
                        gap_id, NOVELTY_ID, *supporting_evidence, *counterevidence
                    ],
                    "reproduction_seed": 20260809,
                },
                "status": "approved_for_output",
                "review": {
                    "green_finance_review": "Group1 construct review completed; policy effects are represented as competing implementation regimes rather than a uniform benefit.",
                    "data_review": "Not selected in Group1; candidate availability remains conditional for Group2 feasibility work.",
                    "method_review": "Not selected in Group1; only falsification and identification constraints are handed to Group2.",
                    "citation_review": "Six source papers plus five formal nearest works and additional edge works were reviewed at explicit full-text/abstract access levels.",
                    "final_decision": "accept",
                },
                "confidence": 0.68,
                "graph_links": {
                    "predictor_node_ids": [variable["policy"]],
                    "outcome_node_ids": [variable["greenwashing"], inferred["firm_emissions"]],
                    "mediator_node_ids": [
                        variable["rd"], variable["patents"], variable["investment_efficiency"]
                    ],
                    "moderator_node_ids": [inferred["digital_capacity"]],
                    "mechanism_node_ids": [mechanism["investment_reallocation"]],
                    "support_node_ids": supporting_findings,
                    "challenge_node_ids": [],
                    "enabled_by_node_ids": [
                        inferred["linked_panel"], dataset["policy"], dataset["csmar"],
                        dataset["wind"], dataset["hesg"], dataset["besg"],
                        dataset["disclosures"], dataset["digital"],
                    ],
                    "recommended_method_ids": [inferred["method"]],
                    "recommended_model_ids": [inferred["model"]],
                    "recommended_identification_strategy_ids": [inferred["identification"]],
                    "recommended_dataset_ids": [
                        inferred["linked_panel"], dataset["policy"], dataset["csmar"],
                        dataset["wind"], dataset["hesg"], dataset["besg"],
                        dataset["disclosures"], dataset["digital"],
                    ],
                },
            }
        ],
    }
    return config


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the reviewed discovery config for the eligible six-paper pilot"
    )
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--novelty", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    config = build_config(_load(args.graph), _load(args.novelty))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"WROTE {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
