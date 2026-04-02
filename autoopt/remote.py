from __future__ import annotations

import json
import os
import posixpath
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from autoopt.models import ExecutionHost, ProjectSpec, ToolSpec


SSH_OPTIONS = [
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=10",
    "-o",
    "ClearAllForwardings=yes",
]


@dataclass
class RemoteBootstrapResult:
    host_name: str
    ssh_target: str
    remote_workspace_root: str
    remote_project_root: str
    conda_env_name: str
    env_yaml_remote: str


class SSHRemoteManager:
    def __init__(self, spec: ProjectSpec) -> None:
        self.spec = spec
        self.workspace_root = self._detect_workspace_root(Path(spec.project_root))
        self.bootstrap_dir = Path(spec.project_root) / ".autoopt" / "remote_bootstrap"
        self.bootstrap_dir.mkdir(parents=True, exist_ok=True)

    def bootstrap_host(self, host_name: str) -> RemoteBootstrapResult:
        host = self._require_host(host_name)
        if not host.ssh_target:
            raise RuntimeError(f"Host '{host_name}' does not define an ssh_target")

        remote_workspace_root = self._remote_workspace_root(host)
        remote_project_root = host.project_root or posixpath.join(remote_workspace_root, Path(self.spec.project_root).name)
        conda_env_name = self._target_conda_env_name(host)
        local_env_yaml = self._export_conda_environment()
        local_env_explicit = self._export_conda_explicit()
        remote_bootstrap_root = posixpath.join(remote_workspace_root, ".autoopt", "bootstrap")
        remote_env_yaml = posixpath.join(remote_bootstrap_root, "environment.lock.yml")
        remote_env_explicit = posixpath.join(remote_bootstrap_root, "environment.explicit.txt")

        self._ssh_mkdir(host.ssh_target, remote_workspace_root)
        self._ssh_mkdir(host.ssh_target, remote_project_root)
        self._ssh_mkdir(host.ssh_target, remote_bootstrap_root)

        for relative_path in self._sync_paths(host):
            self._sync_relative_path_to_remote(host.ssh_target, relative_path, remote_workspace_root)

        self._sync_file_to_remote(host.ssh_target, local_env_yaml, remote_env_yaml)
        self._sync_file_to_remote(host.ssh_target, local_env_explicit, remote_env_explicit)

        self._ensure_remote_conda_env(
            ssh_target=host.ssh_target,
            conda_env_name=conda_env_name,
            remote_env_yaml=remote_env_yaml,
            remote_workspace_root=remote_workspace_root,
        )

        return RemoteBootstrapResult(
            host_name=host.name,
            ssh_target=host.ssh_target,
            remote_workspace_root=remote_workspace_root,
            remote_project_root=remote_project_root,
            conda_env_name=conda_env_name,
            env_yaml_remote=remote_env_yaml,
        )

    def dispatch_tool(
        self,
        bootstrap: RemoteBootstrapResult,
        tool: ToolSpec,
        remote_command: str,
        local_result_json_path: str,
        remote_result_json_path: str,
        state_path: str | None = None,
        remote_state_path: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if state_path and remote_state_path:
            self._sync_file_to_remote(bootstrap.ssh_target, Path(state_path), remote_state_path)

        command = self._wrap_remote_command(
            conda_env_name=bootstrap.conda_env_name,
            remote_workspace_root=bootstrap.remote_workspace_root,
            remote_command=remote_command,
        )
        completed = self._run_ssh(bootstrap.ssh_target, command)

        local_result_path = Path(local_result_json_path)
        local_result_path.parent.mkdir(parents=True, exist_ok=True)
        self._sync_file_from_remote(bootstrap.ssh_target, remote_result_json_path, local_result_path)

        if local_result_path.exists():
            result_data = json.loads(local_result_path.read_text(encoding="utf-8"))
            artifact_paths = set(tool.produces_artifacts)
            artifact_paths.update(result_data.get("artifacts", {}).values())
            for relative_path in sorted(path for path in artifact_paths if path):
                self._sync_relative_path_from_remote(
                    bootstrap.ssh_target,
                    bootstrap.remote_project_root,
                    relative_path,
                    Path(self.spec.project_root),
                )

        return completed

    def _detect_workspace_root(self, project_root: Path) -> Path:
        candidates = [project_root, *project_root.parents]
        for candidate in candidates:
            if (candidate / "pyproject.toml").exists() and (candidate / "autoopt").exists():
                return candidate
        return project_root

    def _require_host(self, host_name: str) -> ExecutionHost:
        host = self.spec.execution_topology.hosts.get(host_name)
        if host is None:
            raise RuntimeError(f"Unknown execution host '{host_name}'")
        return host

    def _remote_workspace_root(self, host: ExecutionHost) -> str:
        return str(host.metadata.get("workspace_root") or host.project_root or "~/AutoOpt")

    def _target_conda_env_name(self, host: ExecutionHost) -> str:
        return str(
            host.metadata.get("conda_env_name")
            or self.spec.runtime.get("remote_conda_env")
            or os.environ.get("AUTOOPT_REMOTE_CONDA_ENV")
            or os.environ.get("AUTOOPT_SOURCE_CONDA_ENV")
            or os.environ.get("CONDA_DEFAULT_ENV")
            or self.spec.runtime.get("source_conda_env")
            or "AutoOPT"
        )

    def _sync_paths(self, host: ExecutionHost) -> list[str]:
        bootstrap = host.metadata.get("bootstrap", {})
        configured = bootstrap.get("sync_paths")
        if configured:
            return configured

        defaults = []
        for relative_path in ["autoopt", Path(self.spec.project_root).name, "README.md", "pyproject.toml", "docs", "templates"]:
            if (self.workspace_root / relative_path).exists():
                defaults.append(str(relative_path))
        return defaults

    def _export_conda_environment(self) -> Path:
        source_env = (
            os.environ.get("AUTOOPT_SOURCE_CONDA_ENV")
            or os.environ.get("CONDA_DEFAULT_ENV")
            or self.spec.runtime.get("source_conda_env")
        )
        if not source_env:
            raise RuntimeError(
                "No source conda environment detected. Activate the AutoOPT conda env or set AUTOOPT_SOURCE_CONDA_ENV."
            )

        completed = subprocess.run(
            ["conda", "env", "export", "-n", source_env, "--no-builds"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Failed to export conda env '{source_env}': {completed.stderr.strip()}")

        lines = []
        for line in completed.stdout.splitlines():
            if line.startswith("prefix:"):
                continue
            lines.append(line)

        export_path = self.bootstrap_dir / "environment.lock.yml"
        export_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return export_path

    def _export_conda_explicit(self) -> Path:
        source_env = (
            os.environ.get("AUTOOPT_SOURCE_CONDA_ENV")
            or os.environ.get("CONDA_DEFAULT_ENV")
            or self.spec.runtime.get("source_conda_env")
        )
        if not source_env:
            raise RuntimeError(
                "No source conda environment detected. Activate the AutoOPT conda env or set AUTOOPT_SOURCE_CONDA_ENV."
            )

        completed = subprocess.run(
            ["conda", "list", "-n", source_env, "--explicit"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Failed to export explicit package list for '{source_env}': {completed.stderr.strip()}")

        export_path = self.bootstrap_dir / "environment.explicit.txt"
        export_path.write_text(completed.stdout, encoding="utf-8")
        return export_path

    def _ensure_remote_conda_env(
        self,
        ssh_target: str,
        conda_env_name: str,
        remote_env_yaml: str,
        remote_workspace_root: str,
    ) -> None:
        command = f"""
set -euo pipefail
find_conda() {{
  if command -v conda >/dev/null 2>&1; then command -v conda; return 0; fi
  for candidate in "$HOME/miniconda3/bin/conda" "$HOME/miniforge3/bin/conda" "$HOME/anaconda3/bin/conda"; do
    if [ -x "$candidate" ]; then echo "$candidate"; return 0; fi
  done
  return 17
}}
CONDA_BIN="$(find_conda)"
if ! "$CONDA_BIN" env list | awk '{{print $1}}' | grep -Fxq {shlex.quote(conda_env_name)}; then
  "$CONDA_BIN" env create -n {shlex.quote(conda_env_name)} -f {shlex.quote(remote_env_yaml)}
else
  "$CONDA_BIN" env update -n {shlex.quote(conda_env_name)} -f {shlex.quote(remote_env_yaml)} --prune
fi
if [ -f {shlex.quote(posixpath.join(remote_workspace_root, "pyproject.toml"))} ]; then
  "$CONDA_BIN" run -n {shlex.quote(conda_env_name)} python -m pip install -e {shlex.quote(remote_workspace_root)}
fi
"""
        completed = self._run_ssh(ssh_target, command)
        if completed.returncode != 0:
            raise RuntimeError(f"Failed to ensure remote conda env '{conda_env_name}': {completed.stderr.strip()}")

    def _wrap_remote_command(
        self,
        conda_env_name: str,
        remote_workspace_root: str,
        remote_command: str,
    ) -> str:
        return f"""
set -euo pipefail
find_conda() {{
  if command -v conda >/dev/null 2>&1; then command -v conda; return 0; fi
  for candidate in "$HOME/miniconda3/bin/conda" "$HOME/miniforge3/bin/conda" "$HOME/anaconda3/bin/conda"; do
    if [ -x "$candidate" ]; then echo "$candidate"; return 0; fi
  done
  return 17
}}
CONDA_BIN="$(find_conda)"
cd {shlex.quote(remote_workspace_root)}
"$CONDA_BIN" run -n {shlex.quote(conda_env_name)} bash -lc {shlex.quote(remote_command)}
"""

    def _ssh_mkdir(self, ssh_target: str, remote_dir: str) -> None:
        completed = self._run_ssh(ssh_target, f"mkdir -p {shlex.quote(remote_dir)}")
        if completed.returncode != 0:
            raise RuntimeError(f"Failed to create remote directory '{remote_dir}': {completed.stderr.strip()}")

    def _sync_relative_path_to_remote(self, ssh_target: str, relative_path: str, remote_workspace_root: str) -> None:
        local_path = self.workspace_root / relative_path
        if not local_path.exists():
            return
        remote_path = posixpath.join(remote_workspace_root, relative_path)
        parent_dir = posixpath.dirname(remote_path)
        if parent_dir:
            self._ssh_mkdir(ssh_target, parent_dir)
        if local_path.is_dir():
            self._ssh_mkdir(ssh_target, remote_path)
            self._run_rsync(local_path, f"{ssh_target}:{remote_path}/", is_dir=True, direction="to")
        else:
            self._run_rsync(local_path, f"{ssh_target}:{remote_path}", is_dir=False, direction="to")

    def _sync_relative_path_from_remote(
        self,
        ssh_target: str,
        remote_project_root: str,
        relative_path: str,
        local_project_root: Path,
    ) -> None:
        local_path = local_project_root / relative_path
        local_path.parent.mkdir(parents=True, exist_ok=True)
        remote_path = posixpath.join(remote_project_root, relative_path)
        self._run_rsync(f"{ssh_target}:{remote_path}", local_path.parent, is_dir=False, direction="from")

    def _sync_file_to_remote(self, ssh_target: str, local_path: Path, remote_path: str) -> None:
        self._ssh_mkdir(ssh_target, posixpath.dirname(remote_path))
        self._run_rsync(local_path, f"{ssh_target}:{remote_path}", is_dir=False, direction="to")

    def _sync_file_from_remote(self, ssh_target: str, remote_path: str, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self._run_rsync(f"{ssh_target}:{remote_path}", local_path.parent, is_dir=False, direction="from")

    def _run_rsync(self, source, target, is_dir: bool, direction: str) -> None:
        command = [
            "rsync",
            "-az",
            "-e",
            "ssh " + " ".join(SSH_OPTIONS),
        ]
        if is_dir and direction == "to":
            command.extend([str(source) + "/", str(target)])
        else:
            command.extend([str(source), str(target)])

        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        self._raise_if_hostkey_issue(completed.stderr)
        if completed.returncode != 0:
            raise RuntimeError(f"rsync failed: {completed.stderr.strip() or completed.stdout.strip()}")

    def _run_ssh(self, ssh_target: str, remote_command: str) -> subprocess.CompletedProcess[str]:
        command = ["ssh", *SSH_OPTIONS, ssh_target, "bash", "-lc", remote_command]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        self._raise_if_hostkey_issue(completed.stderr)
        return completed

    def _raise_if_hostkey_issue(self, stderr: str) -> None:
        if "REMOTE HOST IDENTIFICATION HAS CHANGED" in stderr:
            raise RuntimeError(
                "SSH host key mismatch detected. Please fix the known_hosts entry before AutoOpt dispatches to this host."
            )
