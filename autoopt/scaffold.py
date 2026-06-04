from __future__ import annotations

import json
import re
from pathlib import Path


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "autoopt-project"


def init_linked_project(
    target_dir: str,
    project_name: str,
    external_project_path: str,
    linked_name: str = "source_project",
) -> Path:
    project_dir = Path(target_dir).resolve()
    external_path = Path(external_project_path).resolve()

    if project_dir.exists() and any(project_dir.iterdir()):
        raise RuntimeError(f"Target directory already exists and is not empty: {project_dir}")
    if not external_path.exists():
        raise RuntimeError(f"External project path does not exist: {external_path}")

    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "scripts").mkdir(exist_ok=True)
    (project_dir / "assets").mkdir(exist_ok=True)

    link_path = project_dir / linked_name
    if link_path.exists() or link_path.is_symlink():
        raise RuntimeError(f"Link path already exists: {link_path}")
    link_path.symlink_to(external_path, target_is_directory=external_path.is_dir())

    project_id = _slugify(project_name)
    project_json = {
        "project_id": project_id,
        "name": project_name,
        "walkthrough_path": "walkthrough.md",
        "contract_path": "contract.json",
        "runtime": {
            "state_dir": ".autoopt/jobs",
            "artifacts_dir": "artifacts",
            "default_worker": "rule-based",
            "max_turns_per_run": 6,
            "source_conda_env": "AutoOPT",
            "remote_env_export_strategy": "from-history",
        },
        "execution_topology": {
            "controller_host": "local-controller",
            "default_local_host": "local-controller",
            "default_compute_hosts": ["gpu-worker-02", "gpu-worker-03", "gpu-worker-01"],
            "routing_profiles": {
                "repo_diagnose": ["local-controller"],
                "evaluation": ["local-controller"],
                "gpu_train": ["gpu-worker-02", "gpu-worker-03", "gpu-worker-01"],
            },
            "hosts": {
                "local-controller": {
                    "mode": "local",
                    "ssh_target": "local",
                    "roles": ["controller", "diagnose", "evaluation"],
                    "local_aliases": ["local-controller", "localhost"],
                },
                "gpu-worker-02": {
                    "mode": "dispatch",
                    "roles": ["gpu_train"],
                    "ssh_target": "gpu-worker-02",
                    "project_root": f"/data/AutoOpt/{project_dir.name}",
                    "workspace_root": "/data/AutoOpt",
                    "conda_env_name": "AutoOPT",
                    "bootstrap": {
                        "sync_paths": [
                            "autoopt",
                            project_dir.name,
                            "README.md",
                            "pyproject.toml",
                            "docs",
                            "templates",
                            "walkthrough.md",
                        ]
                    },
                },
                "gpu-worker-03": {
                    "mode": "dispatch",
                    "roles": ["gpu_train"],
                    "ssh_target": "gpu-worker-03",
                    "project_root": f"/data/AutoOpt/{project_dir.name}",
                    "workspace_root": "/data/AutoOpt",
                    "conda_env_name": "AutoOPT",
                    "bootstrap": {
                        "sync_paths": [
                            "autoopt",
                            project_dir.name,
                            "README.md",
                            "pyproject.toml",
                            "docs",
                            "templates",
                            "walkthrough.md",
                        ]
                    },
                },
                "gpu-worker-01": {
                    "mode": "dispatch",
                    "roles": ["gpu_train"],
                    "ssh_target": "gpu-worker-01",
                    "project_root": f"/data/AutoOpt/{project_dir.name}",
                    "workspace_root": "/data/AutoOpt",
                    "conda_env_name": "AutoOPT",
                    "bootstrap": {
                        "sync_paths": [
                            "autoopt",
                            project_dir.name,
                            "README.md",
                            "pyproject.toml",
                            "docs",
                            "templates",
                            "walkthrough.md",
                        ]
                    },
                },
            },
        },
        "tool_registry": {
            "diagnose_linked_project": {
                "adapter": "data",
                "description": "Inspect the linked external project and summarize what AutoOpt needs to adapt.",
                "command": f"python3 scripts/diagnose.py --project-root {{project_root}} --linked-root {{project_root}}/{linked_name} --result-json {{result_json}}",
                "produces_artifacts": ["artifacts/analysis/linked_project_diagnosis.json"],
                "budget_cost": 5,
                "workload_profile": "repo_diagnose",
            }
        },
        "decision_rules": [
            {
                "name": "diagnose linked project first",
                "when": {
                    "missing_artifacts": ["artifacts/analysis/linked_project_diagnosis.json"]
                },
                "phase": "diagnose",
                "tools": ["diagnose_linked_project"],
                "summary": "Inspect the linked external project and build an adaptation summary first.",
                "followup_phase": "handoff",
            },
            {
                "name": "handoff for project adaptation",
                "when": {"always": True},
                "phase": "handoff",
                "tools": [],
                "summary": "This scaffold is ready. Ask Codex to adapt the tool scripts and decision rules to the linked project.",
                "requires_human": True,
            },
        ],
    }

    contract_json = {
        "project_id": project_id,
        "objective": f"Adapt AutoOpt to the linked external project '{project_name}' without mutating its frozen evaluation rules.",
        "goal": "Diagnose the linked project, identify required adapters, and then replace the scaffold tools with project-specific execution logic.",
        "success_metrics": [
            {
                "name": "adaptation_readiness",
                "target": 1.0,
                "mode": "max",
                "description": "Whether the linked project has been fully adapted into an executable AutoOpt workflow.",
            }
        ],
        "frozen_eval_sets": [],
        "constraints": [
            "Do not modify the linked project blindly.",
            "Prefer adapting wrappers and orchestration code before changing model code.",
            "Keep the linked project path stable and accessible.",
        ],
        "data_policy": {
            "allowed_source_classes": ["linked_project_native"],
            "blocked_source_classes": [],
            "require_checksum": False,
            "require_split_leakage_review": False,
        },
        "compute_policy": {
            "allowed_backends": ["local", "tmux-ssh"],
            "allowed_hosts": ["local-controller", "gpu-worker-02", "gpu-worker-03", "gpu-worker-01"],
            "max_gpu_hours": 0,
            "max_total_budget": 0,
        },
        "human_gates": [
            {
                "name": "adaptation_gate",
                "condition": "scaffold_only",
                "action": "handoff",
            }
        ],
    }

    walkthrough = f"""# {project_name} Walkthrough

## Linked Project

- Symlink name: `{linked_name}`
- Linked path: `{external_path}`

## Goal

让 Codex 先分析这个外部工程的结构、训练入口、评测入口、依赖和数据布局，再把当前 scaffold 改造成该工程可运行的 AutoOpt 项目。

## Adaptation Checklist

1. 确认训练入口和评测入口
2. 确认依赖管理方式
3. 确认需要保留的 benchmark / config / checkpoint 路径
4. 确认哪些动作应该留在 local-controller，哪些动作应该发到 ECO 机器
5. 用真实脚本替换 `scripts/diagnose.py` 之外的 scaffold
"""

    diagnose_script = f"""from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--linked-root", required=True)
    parser.add_argument("--result-json", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    linked_root = Path(args.linked_root).resolve()
    result_json = Path(args.result_json).resolve()

    top_entries = sorted(item.name for item in linked_root.iterdir())[:50]
    diagnosis_path = project_root / "artifacts" / "analysis" / "linked_project_diagnosis.json"
    diagnosis_path.parent.mkdir(parents=True, exist_ok=True)
    diagnosis = {{
        "linked_root": str(linked_root),
        "top_entries": top_entries,
        "detected_files": {{
            "pyproject_toml": (linked_root / "pyproject.toml").exists(),
            "requirements_txt": (linked_root / "requirements.txt").exists(),
            "readme_md": (linked_root / "README.md").exists(),
            "train_py": any(path.name == "train.py" for path in linked_root.rglob("train.py")),
            "config_dir": any(path.name in {{"configs", "config"}} for path in linked_root.iterdir()),
        }},
        "summary": "Scaffold diagnosis completed. Next step is to adapt tool scripts to the linked project."
    }}
    diagnosis_path.write_text(json.dumps(diagnosis, indent=2, ensure_ascii=False), encoding="utf-8")
    result_json.parent.mkdir(parents=True, exist_ok=True)
    result_json.write_text(json.dumps({{
        "success": True,
        "summary": "Diagnosed the linked project scaffold and produced an adaptation summary.",
        "artifacts": {{
            "linked_project_diagnosis": str(diagnosis_path.relative_to(project_root))
        }},
        "notes": [
            "This scaffold intentionally stops after diagnosis.",
            "Ask Codex to replace the scaffold with project-specific tools next."
        ],
        "budget_cost": 5
    }}, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
"""

    readme = f"""# {project_name}

这个目录是由 `autoopt project init-linked` 生成的适配骨架。

它通过软链接 `{linked_name}` 指向真实工程：

- `{external_path}`

推荐下一步直接让 Codex 在这个目录里做“项目适配”，把 scaffold 的脚本和规则换成真实训练/评测/数据流程。

初始化完成后你可以先跑：

```bash
autoopt run --project project.json --job-id {project_id}-diagnose --max-turns 2
```
"""

    (project_dir / "project.json").write_text(json.dumps(project_json, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (project_dir / "contract.json").write_text(json.dumps(contract_json, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (project_dir / "walkthrough.md").write_text(walkthrough, encoding="utf-8")
    (project_dir / "README.md").write_text(readme, encoding="utf-8")
    (project_dir / "scripts" / "diagnose.py").write_text(diagnose_script, encoding="utf-8")

    return project_dir
