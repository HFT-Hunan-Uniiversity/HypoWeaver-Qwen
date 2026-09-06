from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


def _request_bytes(url: str, *, timeout: int = 90, attempts: int = 4) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/xml, application/json",
                "User-Agent": "GreenFin-Scientist-OA-Pilot/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:  # network retry boundary
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    assert last_error is not None
    raise last_error


def _request_json(url: str) -> dict[str, Any]:
    value = json.loads(_request_bytes(url))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object from {url}")
    return value


def _text(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    value = " ".join("".join(element.itertext()).split())
    return value or None


def _metadata_for(pmcid: str) -> dict[str, Any]:
    # Europe PMC's public query parser resolves the canonical PMCID as a
    # free identifier token; PMC_ID/EXT_ID fields do not match these records.
    query = urllib.parse.quote(pmcid)
    url = f"{BASE_URL}/search?query={query}&resultType=core&format=json&pageSize=2"
    payload = _request_json(url)
    results = ((payload.get("resultList") or {}).get("result") or [])
    if len(results) != 1:
        raise ValueError(f"expected exactly one Europe PMC record for {pmcid}")
    result = results[0]
    if not isinstance(result, dict):
        raise ValueError(f"invalid Europe PMC metadata for {pmcid}")
    return result


def _license(root: ET.Element) -> tuple[str | None, str | None, str, str]:
    license_element = root.find(".//permissions/license")
    license_text = _text(license_element)
    license_url = None if license_element is None else license_element.get(XLINK_HREF)
    if license_url is None and license_element is not None:
        license_link = license_element.find(".//ext-link")
        if license_link is not None:
            license_url = license_link.get(XLINK_HREF)
    if license_url is None and license_text:
        match = re.search(
            r"https?://creativecommons\.org/licenses/[a-z-]+/[0-9.]+/?",
            license_text,
            flags=re.IGNORECASE,
        )
        if match:
            license_url = match.group(0).replace("http://", "https://")
    normalized = f"{license_url or ''} {license_text or ''}".lower()
    if "duration of the world health organization" in normalized:
        return license_text, license_url, "restricted", "time_limited_permission_expired"
    if "creativecommons.org/licenses/" in normalized or "creative commons" in normalized:
        return license_text, license_url, "open", "reusable_with_license"
    return license_text, license_url, "restricted", "rights_unknown"


def collect(pmcids: list[str], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_pmcid in pmcids:
        pmcid = raw_pmcid.upper()
        if not re.fullmatch(r"PMC[0-9]+", pmcid):
            raise ValueError(f"invalid PMCID: {raw_pmcid}")
        if pmcid in seen:
            raise ValueError(f"duplicate PMCID: {pmcid}")
        seen.add(pmcid)

        metadata = _metadata_for(pmcid)
        if str(metadata.get("isRetracted", "N")).upper() == "Y":
            raise ValueError(f"refusing retracted article {pmcid}")
        xml_url = f"{BASE_URL}/{pmcid}/fullTextXML"
        xml_bytes = _request_bytes(xml_url)
        root = ET.fromstring(xml_bytes)
        title = _text(root.find(".//article-meta/title-group/article-title"))
        if not title:
            raise ValueError(f"full text {pmcid} has no article title")
        if title.casefold().startswith(("retraction", "retracted")):
            raise ValueError(f"refusing retraction record {pmcid}: {title}")

        doi = _text(root.find(".//article-id[@pub-id-type='doi']"))
        pmid = _text(root.find(".//article-id[@pub-id-type='pmid']"))
        journal = _text(root.find(".//journal-title-group/journal-title"))
        year = _text(root.find(".//pub-date[@pub-type='epub']/year")) or _text(
            root.find(".//pub-date[@pub-type='ppub']/year")
        ) or str(metadata.get("pubYear") or "")
        authors: list[str] = []
        for contrib in root.findall(".//contrib-group/contrib[@contrib-type='author']"):
            surname = _text(contrib.find("./name/surname"))
            given = _text(contrib.find("./name/given-names"))
            collective = _text(contrib.find("./collab"))
            name = " ".join(value for value in (given, surname) if value) or collective
            if name:
                authors.append(name)

        license_text, license_url, access_level, rights_status = _license(root)
        filename = f"{pmcid}.xml"
        (output_dir / filename).write_bytes(xml_bytes)
        items.append(
            {
                "pmcid": pmcid,
                "pmid": pmid,
                "doi": doi,
                "title": title,
                "authors": authors,
                "journal": journal,
                "year": int(year) if year and year.isdigit() else None,
                "source_url": f"https://europepmc.org/articles/{pmcid}",
                "content_url": xml_url,
                "raw_file": filename,
                "raw_sha256": hashlib.sha256(xml_bytes).hexdigest(),
                "bytes": len(xml_bytes),
                "license": license_url,
                "license_text": license_text,
                "access_level": access_level,
                "rights_status": rights_status,
                "is_open_access": metadata.get("isOpenAccess"),
                "is_retracted": metadata.get("isRetracted"),
                "status": "verified_fulltext_xml",
            }
        )

    manifest = {
        "schema_version": "open-fulltext-collection/1.0.0",
        "source": "Europe PMC",
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "record_count": len(items),
        "items": sorted(items, key=lambda item: item["pmcid"]),
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    (output_dir / "manifest.json").write_bytes(manifest_bytes)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download and integrity-check selected Europe PMC JATS full texts."
    )
    parser.add_argument("--pmcid", action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = collect(args.pmcid, args.output_dir)
    except Exception as exc:  # pragma: no cover - CLI failure boundary
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "record_count": manifest["record_count"],
                "open": sum(
                    item["access_level"] == "open" for item in manifest["items"]
                ),
                "restricted": sum(
                    item["access_level"] != "open" for item in manifest["items"]
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
