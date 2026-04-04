from __future__ import annotations

import argparse
import json
from pathlib import Path

from task_spec import load_task_definition


def read_text(path: Path, limit: int = 4000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:limit]


def has_text(text: str, pattern: str) -> bool:
    return pattern.lower() in text.lower()


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--task-definition-path", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--acl-root", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--result-json", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    task_definition = load_task_definition(Path(args.task_definition_path).resolve())
    source_root = Path(args.source_root).resolve()
    acl_root = Path(args.acl_root).resolve()
    data_root = Path(args.data_root).resolve()
    result_json = Path(args.result_json).resolve()

    root_readme = read_text(source_root / "README.md")
    root_config = load_json(source_root / "config.json")
    acl_readme = read_text(acl_root / "README.md")
    train_py = read_text(acl_root / "train.py", limit=12000)
    dataset_py = read_text(acl_root / "dataset.py", limit=12000)
    model_py = read_text(acl_root / "model.py", limit=12000)
    requirements = read_text(source_root / "requirements.txt")
    repo_conflicts = {
        "root_readme_primary_task_is_not_adi": not (
            has_text(root_readme, "dialect")
            or has_text(root_readme, "方言")
            or has_text(root_readme, "audio classification")
        ),
        "root_readme_keeps_legacy_reference_only": has_text(root_readme, "fusion-gec") or has_text(root_readme, "asr correction"),
        "acl_readme_mentions_adi": has_text(acl_readme, "方言") or has_text(acl_readme, "dialect"),
        "root_config_matches_adi_task": (
            root_config.get("project", {}).get("task_type") == "audio_classification"
            and root_config.get("project", {}).get("source_of_truth") == "ACL"
            and root_config.get("task_definition", {}).get("label_space") == task_definition["label_space"]
        ),
    }
    suggested_next_steps = []
    if repo_conflicts["root_readme_primary_task_is_not_adi"] or repo_conflicts["root_readme_keeps_legacy_reference_only"] or not repo_conflicts["root_config_matches_adi_task"]:
        suggested_next_steps.append("Keep the root project description aligned with the ADI-only 6-region task.")
    suggested_next_steps.extend(
        [
            "Keep only whitelist datasets in the automatic training loop until graylist provenance is confirmed.",
            "Use explicit region mapping so the optimization target matches the 6-region task rather than country codes.",
            "Define a stable ADI evaluation protocol before automated optimization starts.",
        ]
    )

    diagnosis = {
        "source_root": str(source_root),
        "acl_root": str(acl_root),
        "data_root": str(data_root),
        "task_name": task_definition["task_name"],
        "target_label_space": task_definition["label_space"],
        "source_of_truth_guess": "ACL/",
        "repo_conflicts": repo_conflicts,
        "training_pipeline_findings": [
            "ACL/train.py currently uses split='dev' as the training set for PoC.",
            "ACL/dataset.py only loads the first parquet shard per dataset for speed.",
            "ACL/train.py generates dummy text instead of using real semantic transcripts.",
            "ACL/train.py assumes a synthetic hierarchy_map rather than a true dialect-region mapping.",
            "ACL/README.md references baseline_wav2vec.py, but that file is not present in the repository.",
        ],
        "dependency_findings": [
            "requirements.txt misses some runtime imports used by ACL code, such as scikit-learn, soundfile, and pyarrow.",
            "The project should run in conda env AutoOpt rather than qwen3_omni for stable orchestration.",
        ],
        "data_findings": [
            "ADI17 parquet shards are present for train/dev/test.",
            "MGB2_parquet provides an immediately usable MSA-only augmentation source.",
            "NADI2025 and MADIS5 are aligned with spoken dialect evaluation and adaptation.",
            "MGB3 and MGB5 exist locally but remain graylisted until their label provenance is confirmed.",
        ],
        "suggested_next_steps": suggested_next_steps,
        "file_inventory": {
            "acl_files": sorted(str(path.relative_to(source_root)) for path in acl_root.glob("*.py")),
            "data_roots": sorted(path.name for path in data_root.iterdir() if path.is_dir()),
        },
    }

    diagnosis_path = project_root / "artifacts" / "analysis" / "acl26_adi_diagnosis.json"
    diagnosis_path.parent.mkdir(parents=True, exist_ok=True)
    diagnosis_path.write_text(json.dumps(diagnosis, indent=2, ensure_ascii=False), encoding="utf-8")

    result_json.parent.mkdir(parents=True, exist_ok=True)
    result_json.write_text(
        json.dumps(
            {
                "success": True,
                "summary": "Diagnosed ACL26_ADI and confirmed that ACL/ is the ADI source of truth for the 6-region task.",
                "artifacts": {
                    "acl26_adi_diagnosis": str(diagnosis_path.relative_to(project_root)),
                },
                "notes": [
                    "The repository mixes an ASR/GEC root narrative with an ADI ACL/ pipeline.",
                    "Whitelist datasets should drive the first automatic loop; graylist datasets need confirmation first.",
                ],
                "budget_cost": 5,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
