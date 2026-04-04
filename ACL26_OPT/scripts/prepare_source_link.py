from __future__ import annotations

import argparse
import json
from pathlib import Path


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--original-source-root", required=True)
    parser.add_argument("--link-name", default="ACL26_ADI_source")
    parser.add_argument("--shared-source-root", default="/data/AutoOpt/ACL26_ADI_source")
    parser.add_argument("--result-json", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    workspace_root = project_root.parent
    original_source_root = Path(args.original_source_root)
    link_path = workspace_root / args.link_name
    shared_source_root = Path(args.shared_source_root)

    if not original_source_root.exists():
        raise FileNotFoundError(f"Source project does not exist: {original_source_root}")

    if link_path.exists() or link_path.is_symlink():
        if link_path.is_symlink() and link_path.resolve() == original_source_root.resolve():
            created = False
        else:
            if link_path.is_dir() and not link_path.is_symlink():
                raise RuntimeError(f"Cannot replace existing directory at {link_path}")
            link_path.unlink()
            link_path.symlink_to(original_source_root, target_is_directory=True)
            created = True
    else:
        link_path.symlink_to(original_source_root, target_is_directory=True)
        created = True

    report = {
        "workspace_root": str(workspace_root),
        "original_source_root": str(original_source_root),
        "link_path": str(link_path),
        "link_resolves_to": str(link_path.resolve()),
        "created": created,
        "shared_source_root": str(shared_source_root),
        "shared_source_present": shared_source_root.exists(),
        "shared_source_ready_for_eco": (shared_source_root / "ACL").exists() and (shared_source_root / "Data").exists(),
    }

    artifact_path = project_root / "artifacts" / "runtime" / "source_link.json"
    write_json(artifact_path, report)
    write_json(
        Path(args.result_json).resolve(),
        {
            "success": True,
            "summary": "Prepared ACL26_ADI source link for the ADI-only AutoOpt layer.",
            "artifacts": {
                "source_link": str(artifact_path.relative_to(project_root)),
            },
            "notes": [
                f"Workspace source link: {link_path}",
                f"Shared ECO source present: {report['shared_source_present']}",
                "ECO training still requires one-time data staging if the shared source root is missing.",
            ],
            "budget_cost": 1,
        },
    )


if __name__ == "__main__":
    main()
