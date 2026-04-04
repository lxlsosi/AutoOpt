from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path

from task_spec import load_task_definition


REQUIRED_MODULES = [
    "torch",
    "transformers",
    "pandas",
    "numpy",
    "soundfile",
    "pyarrow",
    "sklearn",
    "timm",
]


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def module_status(name: str) -> dict:
    try:
        module = importlib.import_module(name)
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
        }
    return {
        "ok": True,
        "version": getattr(module, "__version__", "unknown"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--task-definition-path", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--result-json", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    task_definition = load_task_definition(Path(args.task_definition_path).resolve())
    source_root = Path(args.source_root).resolve()
    acl_root = source_root / "ACL"
    data_root = source_root / "Data"

    imports = {name: module_status(name) for name in REQUIRED_MODULES}
    missing = [name for name, status in imports.items() if not status["ok"]]

    torch_info = imports.get("torch", {})
    cuda_available = False
    device_count = 0
    if torch_info.get("ok"):
        import torch

        cuda_available = bool(torch.cuda.is_available())
        device_count = int(torch.cuda.device_count())

    report = {
        "conda_default_env": os.environ.get("CONDA_DEFAULT_ENV", ""),
        "python_executable": os.sys.executable,
        "task_name": task_definition["task_name"],
        "label_space": task_definition["label_space"],
        "source_root_exists": source_root.exists(),
        "acl_root_exists": acl_root.exists(),
        "data_root_exists": data_root.exists(),
        "imports": imports,
        "missing_modules": missing,
        "cuda_available": cuda_available,
        "cuda_device_count": device_count,
    }

    artifact_path = project_root / "artifacts" / "runtime" / "runtime_report.json"
    write_json(artifact_path, report)

    success = (
        report["source_root_exists"]
        and report["acl_root_exists"]
        and report["data_root_exists"]
        and not missing
    )
    if not success:
        raise RuntimeError(
            "Runtime verification failed: "
            + ", ".join(
                [
                    message
                    for message in [
                        "source root missing" if not report["source_root_exists"] else "",
                        "ACL root missing" if not report["acl_root_exists"] else "",
                        "Data root missing" if not report["data_root_exists"] else "",
                        f"missing modules: {missing}" if missing else "",
                    ]
                    if message
                ]
            )
        )

    write_json(
        Path(args.result_json).resolve(),
        {
            "success": True,
            "summary": "Verified that conda AutoOpt can run the ACL26 ADI wrappers.",
            "artifacts": {
                "runtime_report": str(artifact_path.relative_to(project_root)),
            },
            "notes": [
                f"Conda env: {report['conda_default_env']}",
                f"CUDA available: {cuda_available}",
                f"CUDA device count: {device_count}",
            ],
            "budget_cost": 2,
        },
    )


if __name__ == "__main__":
    main()
