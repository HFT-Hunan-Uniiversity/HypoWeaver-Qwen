"""Repair invalid sections without discarding previously validated content."""

from .models import SectionsDraft
from .rendering import NARRATIVE, issues


async def generate_sections(llm, payload, project_id):
    accepted, failures = {}, {}
    for attempt in range(2):
        output = await llm.generate("write_proposal_sections", payload, SectionsDraft, project_id)
        failures = {}
        for key in NARRATIVE:
            if key in accepted:
                continue
            matches = [s for s in output.sections if s.key == key]
            problems = []
            if len(matches) != 1:
                problems.append({"section": key, "snippet": "", "rule": "章节缺失或重复"})
            else:
                section = matches[0]
                for paragraph in section.markdown.split("\n\n"):
                    problems.extend(
                        {"section": key, "snippet": paragraph, "rule": rule}
                        for rule in issues(
                            paragraph, payload["numbers"], payload["max_strength"], payload.get("metadata")
                        )
                    )
                if not problems:
                    accepted[key] = section
            if problems:
                failures[key] = problems
        if not failures:
            break
        payload = {
            **payload,
            "previous": output.model_dump(),
            "rewrite_reasons": [p for group in failures.values() for p in group],
            "accepted_sections": list(accepted),
            "repair_sections": list(failures),
        }
    return accepted, [p for group in failures.values() for p in group]


async def generate_interpretations(llm, claims, numbers, project_id, metadata=None):
    from .models import Interpretation

    accepted, failures = {}, {}
    payload = {"claims": claims, "numbers": numbers}
    for attempt in range(2):
        output = await llm.generate("interpret_results", payload, Interpretation, project_id)
        failures = {}
        for claim in claims:
            key = claim["claim_id"]
            if key in accepted:
                continue
            matches = [p for p in output.paragraphs if p.claim_id == key]
            reasons = (
                ["结论标识缺失或重复"]
                if len(matches) != 1
                else issues(matches[0].text, numbers, claim["chosen_strength"], metadata)
            )
            if reasons:
                failures[key] = [
                    {
                        "section": "results",
                        "claim_id": key,
                        "snippet": matches[0].text if matches else "",
                        "rule": reason,
                    }
                    for reason in reasons
                ]
            else:
                accepted[key] = matches[0].text
        if not failures:
            break
        payload = {
            **payload,
            "previous": output.model_dump(),
            "rewrite_reasons": [p for group in failures.values() for p in group],
        }
    return accepted, [p for group in failures.values() for p in group]


def failure_summary(errors):
    """The API exposes one compact record per section, including older stored diagnostics."""
    grouped = {}
    for error in errors or []:
        section = error["section"]
        snippet = " ".join(error.get("snippet", "").split())
        if len(snippet) > 200:
            snippet = snippet[:200] + "…"
        reason = error.get("reason") or error.get("rule", "叙述校验未通过")
        if snippet:
            reason += "：" + snippet
        reasons = grouped.setdefault(section, [])
        if reason not in reasons:
            reasons.append(reason)
    return [{"section": section, "reason": "；".join(reasons)} for section, reasons in grouped.items()]
