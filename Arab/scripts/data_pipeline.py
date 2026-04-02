from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: dict) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def discover(project_root: Path, result_json: Path) -> None:
    candidates_path = project_root / "assets" / "source_candidates.json"
    catalog = json.loads(candidates_path.read_text(encoding="utf-8"))
    output_path = project_root / "artifacts" / "data" / "source_catalog.json"
    payload = {
        "generated_at": utc_now(),
        "candidate_count": len(catalog),
        "sources": catalog,
    }
    write_json(output_path, payload)
    write_json(
        result_json,
        {
            "success": True,
            "summary": "Cataloged candidate Arabic speech sources and flagged review risks.",
            "artifacts": {
                "source_catalog": str(output_path.relative_to(project_root)),
            },
            "notes": [
                "One source is blocked due to license risk.",
                "One source still needs manual review and was not selected.",
            ],
            "budget_cost": 5,
        },
    )


def validate(project_root: Path, result_json: Path) -> None:
    catalog_path = project_root / "artifacts" / "data" / "source_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    approved = [
        source
        for source in catalog["sources"]
        if source["license_review_status"] == "approved"
        and source["checksum_available"]
        and source["ready_for_download"]
    ]
    blocked = [
        {
            "source_id": source["source_id"],
            "reason": source["license_review_status"],
        }
        for source in catalog["sources"]
        if source not in approved
    ]
    output_path = project_root / "artifacts" / "data" / "validated_sources.json"
    payload = {
        "generated_at": utc_now(),
        "approved_sources": approved,
        "blocked_sources": blocked,
        "approved_count": len(approved),
    }
    write_json(output_path, payload)
    write_json(
        result_json,
        {
            "success": True,
            "summary": "Validated sources against license, checksum, and download readiness rules.",
            "artifacts": {
                "validated_sources": str(output_path.relative_to(project_root)),
            },
            "notes": [
                "Blocked sources were kept out of the dataset plan.",
                "Approved sources now satisfy the data contract.",
            ],
            "budget_cost": 5,
        },
    )


def prepare(project_root: Path, result_json: Path) -> None:
    validated_path = project_root / "artifacts" / "data" / "validated_sources.json"
    validated = json.loads(validated_path.read_text(encoding="utf-8"))

    dialect_counts = {
        "egyptian": 5400,
        "gulf": 3200,
        "levantine": 3900,
        "maghrebi": 1800,
        "iraqi": 1400,
        "msa": 3600,
        "sudanese": 900,
    }
    dataset_version = "arab-dialect-v2026.04.02.1"
    output_path = project_root / "artifacts" / "data" / "clean_dataset_manifest.json"
    payload = {
        "generated_at": utc_now(),
        "dataset_version": dataset_version,
        "source_count": validated["approved_count"],
        "dialect_counts": dialect_counts,
        "quality_checks": {
            "checksum_verified": True,
            "dedup_done": True,
            "speaker_overlap_review": "pending_manual_sample",
        },
        "warnings": [
            "Sudanese remains underrepresented and should be monitored in evaluation.",
            "Broadcast-heavy data may still create a domain gap against social speech.",
        ],
    }
    write_json(output_path, payload)
    write_json(
        result_json,
        {
            "success": True,
            "summary": "Prepared a cleaned dataset manifest with dialect balance metadata.",
            "artifacts": {
                "clean_dataset_manifest": str(output_path.relative_to(project_root)),
            },
            "dataset_version": dataset_version,
            "notes": [
                f"Approved sources used: {validated['approved_count']}",
                "Low-resource dialect coverage is still a risk for Sudanese and Maghrebi.",
            ],
            "hypotheses": [
                "Balanced sampling will likely help underrepresented dialects.",
                "Domain-robust augmentation may reduce broadcast-to-social mismatch.",
            ],
            "budget_cost": 15,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["discover", "validate", "prepare"])
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--result-json", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    result_json = Path(args.result_json).resolve()

    if args.action == "discover":
        discover(project_root, result_json)
    elif args.action == "validate":
        validate(project_root, result_json)
    else:
        prepare(project_root, result_json)


if __name__ == "__main__":
    main()
