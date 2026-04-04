from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
from pathlib import Path


RECIPE_DATA_REQUIREMENTS = {
    "acoustic_pilot": {
        "adi17_train_files": 4,
        "mgb2_train_files": 0,
    },
    "acoustic_v1": {
        "adi17_train_files": 40,
        "mgb2_train_files": 45,
    },
}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def run_text(command: list[str]) -> tuple[int, str]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return completed.returncode, (completed.stdout or completed.stderr).strip()


def find_conda() -> str:
    candidates = [
        shutil.which("conda") or "",
        str(Path.home() / "miniforge3" / "bin" / "conda"),
        str(Path.home() / "miniconda3" / "bin" / "conda"),
        "/root/miniforge3/bin/conda",
        "/root/miniconda3/bin/conda",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return ""


def find_rclone() -> str:
    candidate = shutil.which("rclone") or ""
    if candidate and Path(candidate).exists():
        return candidate
    return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--recipe", default="acoustic_pilot")
    parser.add_argument("--rclone-remote", default="volctos")
    parser.add_argument("--tos-bucket", default="momo-test-a100-02")
    parser.add_argument("--require-tos-access", action="store_true")
    parser.add_argument("--result-json", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    source_root = Path(args.source_root).resolve()
    data_root = Path(args.data_root).resolve()
    result_json = Path(args.result_json).resolve()
    recipe_name = args.recipe
    recipe_requirements = RECIPE_DATA_REQUIREMENTS.get(recipe_name, RECIPE_DATA_REQUIREMENTS["acoustic_pilot"])

    tmux_ok = shutil.which("tmux") is not None
    tmux_version = ""
    if tmux_ok:
        _code, tmux_version = run_text(["tmux", "-V"])

    gpu_code, gpu_text = run_text(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"]
    )
    gpu_lines = [line.strip() for line in gpu_text.splitlines() if line.strip()]
    conda_bin = find_conda()
    conda_env_present = False
    runtime_import_ok = False
    runtime_import_text = ""
    if conda_bin:
        env_code, env_text = run_text([conda_bin, "env", "list"])
        conda_env_present = env_code == 0 and any(
            line.split() and line.split()[0] == "AutoOpt"
            for line in env_text.splitlines()
            if line.strip() and not line.lstrip().startswith(("#", "*", "+"))
        )
        if conda_env_present:
            runtime_code, runtime_import_text = run_text(
                [
                    conda_bin,
                    "run",
                    "-n",
                    "AutoOpt",
                    "python",
                    "-c",
                    "import torch,transformers,pandas,pyarrow,soundfile,sklearn,numpy,safetensors; print('runtime_ok')",
                ]
            )
            runtime_import_ok = runtime_code == 0 and "runtime_ok" in runtime_import_text

    rclone_bin = find_rclone()
    rclone_remote_present = False
    tos_access_ok = False
    tos_access_text = ""
    if rclone_bin:
        remotes_code, remotes_text = run_text([rclone_bin, "listremotes"])
        if remotes_code == 0:
            rclone_remote_present = f"{args.rclone_remote}:" in {
                line.strip() for line in remotes_text.splitlines() if line.strip()
            }
        if rclone_remote_present and args.tos_bucket:
            tos_code, tos_access_text = run_text([rclone_bin, "lsd", f"{args.rclone_remote}:{args.tos_bucket}"])
            tos_access_ok = tos_code == 0

    data_checks = {
        "acl_root_exists": (source_root / "ACL").exists(),
        "adi17_train_files": len(sorted((data_root / "ADI17" / "data").glob("train-*.parquet"))),
        "mgb2_train_files": len(sorted((data_root / "MGB2_parquet" / "train").glob("train-*.parquet"))),
    }
    data_ready = (
        data_checks["adi17_train_files"] >= recipe_requirements["adi17_train_files"]
        and data_checks["mgb2_train_files"] >= recipe_requirements["mgb2_train_files"]
    )
    success = (
        data_checks["acl_root_exists"]
        and tmux_ok
        and gpu_code == 0
        and len(gpu_lines) >= 1
        and data_ready
        and conda_env_present
        and runtime_import_ok
        and ((not args.require_tos_access) or tos_access_ok)
    )

    artifact_path = project_root / "artifacts" / "runtime" / f"eco_ready_{recipe_name}.json"
    report = {
        "hostname": socket.gethostname(),
        "recipe": recipe_name,
        "source_root": str(source_root),
        "data_root": str(data_root),
        "tmux_ok": tmux_ok,
        "tmux_version": tmux_version,
        "conda_bin": conda_bin,
        "conda_env_present": conda_env_present,
        "gpu_query_ok": gpu_code == 0,
        "gpu_inventory": gpu_lines,
        "runtime_import_ok": runtime_import_ok,
        "runtime_import_text": runtime_import_text,
        "rclone_bin": rclone_bin,
        "rclone_remote": args.rclone_remote,
        "rclone_remote_present": rclone_remote_present,
        "tos_bucket": args.tos_bucket,
        "tos_access_ok": tos_access_ok,
        "tos_access_text": tos_access_text,
        "data_checks": data_checks,
        "recipe_requirements": recipe_requirements,
        "data_ready": data_ready,
        "ready": success,
    }
    write_json(artifact_path, report)
    write_json(
        result_json,
        {
            "success": success,
            "summary": (
                f"Verified ECO readiness for recipe '{recipe_name}' on the remote training host."
                if success
                else f"ECO readiness check failed for recipe '{recipe_name}'."
            ),
            "artifacts": {
                f"eco_ready_{recipe_name}": str(artifact_path.relative_to(project_root)),
            },
            "notes": [
                f"Host: {report['hostname']}",
                f"recipe={recipe_name}",
                f"tmux_ok={tmux_ok}",
                f"conda_env_present={conda_env_present}",
                f"runtime_import_ok={runtime_import_ok}",
                f"gpu_count={len(gpu_lines)}",
                f"ADI17_train_files={data_checks['adi17_train_files']}",
                f"MGB2_train_files={data_checks['mgb2_train_files']}",
                f"rclone_remote_present={rclone_remote_present}",
                f"tos_access_ok={tos_access_ok}",
            ],
            "budget_cost": 2,
        },
    )


if __name__ == "__main__":
    main()
