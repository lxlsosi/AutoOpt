from __future__ import annotations

import json
import os
import posixpath
import shlex
import subprocess
import uuid
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
        remote_bootstrap_root = posixpath.join(remote_workspace_root, ".autoopt", "bootstrap")
        remote_env_yaml = posixpath.join(remote_bootstrap_root, "environment.portable.yml")

        self._ssh_mkdir(host.ssh_target, remote_workspace_root)
        self._ssh_mkdir(host.ssh_target, remote_project_root)
        self._ssh_mkdir(host.ssh_target, remote_bootstrap_root)

        for relative_path in self._sync_paths(host):
            self._sync_relative_path_to_remote(host.ssh_target, relative_path, remote_workspace_root)

        self._sync_file_to_remote(host.ssh_target, local_env_yaml, remote_env_yaml)

        self._ensure_remote_conda_env(
            ssh_target=host.ssh_target,
            host=host,
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

    def submit_background_tool(
        self,
        bootstrap: RemoteBootstrapResult,
        tool: ToolSpec,
        remote_command: str,
        local_result_json_path: str,
        remote_result_json_path: str,
        state_path: str | None = None,
        remote_state_path: str | None = None,
    ) -> dict[str, str]:
        if state_path and remote_state_path:
            self._sync_file_to_remote(bootstrap.ssh_target, Path(state_path), remote_state_path)

        job_uid = uuid.uuid4().hex[:10]
        job_name = f"{tool.name}-{job_uid}"
        remote_job_root = posixpath.join(bootstrap.remote_project_root, ".autoopt", "remote_jobs", job_name)
        local_job_root = Path(self.spec.project_root) / ".autoopt" / "remote_jobs" / job_name
        local_job_root.mkdir(parents=True, exist_ok=True)

        remote_script_path = posixpath.join(remote_job_root, "run.sh")
        remote_stdout_log = posixpath.join(remote_job_root, "stdout.log")
        remote_stderr_log = posixpath.join(remote_job_root, "stderr.log")
        remote_launcher_log = posixpath.join(remote_job_root, "launcher.log")
        remote_status_path = posixpath.join(remote_job_root, "status.txt")
        remote_exit_code_path = posixpath.join(remote_job_root, "exit_code.txt")
        remote_pid_path = posixpath.join(remote_job_root, "pid.txt")
        remote_tmux_session = f"autoopt_{tool.name}_{job_uid}"

        self._ssh_mkdir(bootstrap.ssh_target, remote_job_root)

        wrapped = self._wrap_remote_command(
            conda_env_name=bootstrap.conda_env_name,
            remote_workspace_root=bootstrap.remote_workspace_root,
            remote_command=remote_command,
        )
        script_contents = f"""#!/usr/bin/env bash
set -euo pipefail
mkdir -p {shlex.quote(remote_job_root)}
echo running > {shlex.quote(remote_status_path)}
set +e
(
{wrapped}
) > {shlex.quote(remote_stdout_log)} 2> {shlex.quote(remote_stderr_log)}
RC=$?
set -e
echo "$RC" > {shlex.quote(remote_exit_code_path)}
if [ "$RC" -eq 0 ]; then
  echo completed > {shlex.quote(remote_status_path)}
else
  echo failed > {shlex.quote(remote_status_path)}
fi
exit "$RC"
"""
        local_script_path = local_job_root / "run.sh"
        local_script_path.write_text(script_contents, encoding="utf-8")
        self._sync_file_to_remote(bootstrap.ssh_target, local_script_path, remote_script_path)

        submit_command = f"""
set -euo pipefail
mkdir -p {shlex.quote(remote_job_root)}
chmod +x {shlex.quote(remote_script_path)}
if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is required on {bootstrap.host_name} for background training jobs" >&2
  exit 23
fi
tmux has-session -t {shlex.quote(remote_tmux_session)} 2>/dev/null && tmux kill-session -t {shlex.quote(remote_tmux_session)} || true
tmux new-session -d -s {shlex.quote(remote_tmux_session)} "bash {shlex.quote(remote_script_path)} > {shlex.quote(remote_launcher_log)} 2>&1"
sleep 1
tmux list-panes -t {shlex.quote(remote_tmux_session)} -F '#{{pane_pid}}' | head -n 1 > {shlex.quote(remote_pid_path)}
printf 'PID=%s\\n' "$(cat {shlex.quote(remote_pid_path)})"
printf 'TMUX_SESSION=%s\\n' {shlex.quote(remote_tmux_session)}
"""
        submitted = self._run_ssh(bootstrap.ssh_target, submit_command)
        if submitted.returncode != 0:
            raise RuntimeError(f"Failed to submit remote job for '{tool.name}': {submitted.stderr.strip()}")

        remote_pid = ""
        for line in submitted.stdout.splitlines():
            if line.startswith("PID="):
                remote_pid = line.split("=", 1)[1].strip()
        pending_job = {
            "job_name": job_name,
            "tool_name": tool.name,
            "host_name": bootstrap.host_name,
            "ssh_target": bootstrap.ssh_target,
            "remote_workspace_root": bootstrap.remote_workspace_root,
            "remote_project_root": bootstrap.remote_project_root,
            "conda_env_name": bootstrap.conda_env_name,
            "remote_job_root": remote_job_root,
            "remote_script_path": remote_script_path,
            "remote_stdout_log": remote_stdout_log,
            "remote_stderr_log": remote_stderr_log,
            "remote_launcher_log": remote_launcher_log,
            "remote_status_path": remote_status_path,
            "remote_exit_code_path": remote_exit_code_path,
            "remote_pid_path": remote_pid_path,
            "remote_tmux_session": remote_tmux_session,
            "remote_result_json_path": remote_result_json_path,
            "local_result_json_path": local_result_json_path,
            "local_job_root": str(local_job_root),
            "pid": remote_pid,
        }
        self.sync_job_logs(pending_job)
        return pending_job

    def poll_background_job(self, pending_job: dict[str, str]) -> dict[str, str]:
        ssh_target = pending_job["ssh_target"]
        remote_status_path = pending_job["remote_status_path"]
        remote_pid_path = pending_job["remote_pid_path"]
        remote_exit_code_path = pending_job["remote_exit_code_path"]
        remote_result_json_path = pending_job["remote_result_json_path"]

        poll_command = f"""
STATUS=unknown
PID=""
EXIT_CODE=""
if [ -f {shlex.quote(remote_status_path)} ]; then STATUS="$(cat {shlex.quote(remote_status_path)})"; fi
if [ -f {shlex.quote(remote_pid_path)} ]; then PID="$(cat {shlex.quote(remote_pid_path)})"; fi
if [ -f {shlex.quote(remote_exit_code_path)} ]; then EXIT_CODE="$(cat {shlex.quote(remote_exit_code_path)})"; fi
if [ "$STATUS" = "running" ] && [ -n "$PID" ] && ! kill -0 "$PID" 2>/dev/null; then
  if [ -n "$EXIT_CODE" ]; then
    if [ "$EXIT_CODE" = "0" ]; then
      STATUS=completed
    else
      STATUS=failed
    fi
  elif [ -f {shlex.quote(remote_result_json_path)} ]; then
    STATUS=completed
  else
    STATUS=failed
  fi
fi
printf 'STATUS=%s\\n' "$STATUS"
printf 'PID=%s\\n' "$PID"
printf 'EXIT_CODE=%s\\n' "$EXIT_CODE"
"""
        completed = self._run_ssh(ssh_target, poll_command)
        if completed.returncode != 0:
            raise RuntimeError(f"Failed to poll remote job '{pending_job['job_name']}': {completed.stderr.strip()}")

        parsed: dict[str, str] = {}
        for line in completed.stdout.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            parsed[key.lower()] = value

        self.sync_job_logs(pending_job)
        return parsed

    def collect_job_outputs(self, pending_job: dict[str, str], tool: ToolSpec) -> dict:
        ssh_target = pending_job["ssh_target"]
        local_result_path = Path(pending_job["local_result_json_path"])
        remote_result_json_path = pending_job["remote_result_json_path"]

        if self._remote_path_exists(ssh_target, remote_result_json_path):
            self._sync_file_from_remote(ssh_target, remote_result_json_path, local_result_path)

        result_data = {}
        if local_result_path.exists():
            result_data = json.loads(local_result_path.read_text(encoding="utf-8"))

        artifact_paths = set(tool.produces_artifacts)
        artifact_paths.update(result_data.get("artifacts", {}).values())
        for relative_path in sorted(path for path in artifact_paths if path):
            self._sync_relative_path_from_remote(
                ssh_target,
                pending_job["remote_project_root"],
                relative_path,
                Path(self.spec.project_root),
                optional=True,
            )

        return result_data

    def sync_job_logs(self, pending_job: dict[str, str]) -> dict[str, str]:
        ssh_target = pending_job["ssh_target"]
        local_job_root = Path(pending_job["local_job_root"])
        local_job_root.mkdir(parents=True, exist_ok=True)
        synced: dict[str, str] = {}
        prefix = pending_job["job_name"]

        for key, filename in [
            ("launcher_log", "launcher.log"),
            ("stdout_log", "stdout.log"),
            ("stderr_log", "stderr.log"),
            ("status_file", "status.txt"),
            ("exit_code_file", "exit_code.txt"),
        ]:
            remote_path = pending_job.get(f"remote_{filename.replace('.', '_')}")
            if remote_path is None:
                remote_path = pending_job.get(
                    {
                        "launcher.log": "remote_launcher_log",
                        "stdout.log": "remote_stdout_log",
                        "stderr.log": "remote_stderr_log",
                        "status.txt": "remote_status_path",
                        "exit_code.txt": "remote_exit_code_path",
                    }[filename]
                )
            local_path = local_job_root / filename
            if self._remote_path_exists(ssh_target, remote_path):
                self._sync_file_from_remote(ssh_target, remote_path, local_path)
                synced[f"{prefix}_{key}"] = str(local_path.relative_to(Path(self.spec.project_root)))
        return synced

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
            or self.spec.runtime.get("source_conda_env")
            or os.environ.get("CONDA_DEFAULT_ENV")
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
        explicit_spec = self.spec.runtime.get("remote_env_spec_path")
        if explicit_spec:
            spec_path = Path(explicit_spec)
            if not spec_path.is_absolute():
                spec_path = Path(self.spec.project_root) / spec_path
            if not spec_path.exists():
                raise RuntimeError(f"Configured remote_env_spec_path does not exist: {spec_path}")
            export_path = self.bootstrap_dir / spec_path.name
            export_path.write_text(spec_path.read_text(encoding="utf-8"), encoding="utf-8")
            return export_path

        source_env = (
            os.environ.get("AUTOOPT_SOURCE_CONDA_ENV")
            or self.spec.runtime.get("source_conda_env")
            or os.environ.get("CONDA_DEFAULT_ENV")
        )
        if not source_env:
            raise RuntimeError(
                "No source conda environment detected. Set AUTOOPT_SOURCE_CONDA_ENV or runtime.source_conda_env."
            )

        strategy = (
            os.environ.get("AUTOOPT_REMOTE_ENV_EXPORT_STRATEGY")
            or self.spec.runtime.get("remote_env_export_strategy")
            or "from-history"
        )
        command = ["conda", "env", "export", "-n", source_env]
        if strategy == "from-history":
            command.append("--from-history")
        else:
            command.append("--no-builds")

        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"Failed to export conda env '{source_env}': {completed.stderr.strip()}")

        lines = []
        for line in completed.stdout.splitlines():
            if line.startswith("prefix:"):
                continue
            lines.append(line)

        export_path = self.bootstrap_dir / "environment.portable.yml"
        export_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return export_path

    def _ensure_remote_conda_env(
        self,
        ssh_target: str,
        host: ExecutionHost,
        conda_env_name: str,
        remote_env_yaml: str,
        remote_workspace_root: str,
    ) -> None:
        post_create = host.metadata.get("post_create_commands", [])
        post_create_script = "\n".join(post_create)
        install_conda_if_missing = host.metadata.get(
            "install_conda_if_missing",
            self.spec.runtime.get("install_conda_if_missing", False),
        )
        installer_url = host.metadata.get(
            "conda_installer_url",
            self.spec.runtime.get(
                "remote_conda_installer_url",
                "https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh",
            ),
        )
        conda_root = host.metadata.get("conda_root", "$HOME/miniconda3")
        command = f"""
set -euo pipefail
find_conda() {{
  if command -v conda >/dev/null 2>&1; then command -v conda; return 0; fi
  for candidate in "$HOME/miniconda3/bin/conda" "$HOME/miniforge3/bin/conda" "$HOME/anaconda3/bin/conda"; do
    if [ -x "$candidate" ]; then echo "$candidate"; return 0; fi
  done
  return 17
}}
install_conda_if_missing={str(bool(install_conda_if_missing)).lower()}
install_conda() {{
  installer_url={shlex.quote(str(installer_url))}
  conda_root={shlex.quote(str(conda_root))}
  installer_path="$(mktemp /tmp/autoopt-miniconda-XXXXXX.sh)"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$installer_url" -o "$installer_path"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$installer_path" "$installer_url"
  else
    echo "Neither curl nor wget is available to install miniconda" >&2
    return 19
  fi
  bash "$installer_path" -b -p "$conda_root"
  rm -f "$installer_path"
}}
CONDA_BIN="$(find_conda || true)"
if [ -z "$CONDA_BIN" ]; then
  if [ "$install_conda_if_missing" != "true" ]; then
    echo "conda not found on remote host and auto-install is disabled" >&2
    exit 17
  fi
  install_conda
  CONDA_BIN="$(find_conda)"
fi
if ! "$CONDA_BIN" env list | awk '{{print $1}}' | grep -Fxq {shlex.quote(conda_env_name)}; then
  "$CONDA_BIN" env create -n {shlex.quote(conda_env_name)} -f {shlex.quote(remote_env_yaml)}
else
  "$CONDA_BIN" env update -n {shlex.quote(conda_env_name)} -f {shlex.quote(remote_env_yaml)} --prune
fi
if [ -f {shlex.quote(posixpath.join(remote_workspace_root, "pyproject.toml"))} ]; then
  "$CONDA_BIN" run -n {shlex.quote(conda_env_name)} python -m pip install -e {shlex.quote(remote_workspace_root)}
fi
{post_create_script}
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
        follow_links = local_path.is_symlink()
        if parent_dir:
            self._ssh_mkdir(ssh_target, parent_dir)
        if local_path.is_dir():
            self._ssh_mkdir(ssh_target, remote_path)
            self._run_rsync(local_path, f"{ssh_target}:{remote_path}/", is_dir=True, direction="to", follow_links=follow_links)
        else:
            self._run_rsync(local_path, f"{ssh_target}:{remote_path}", is_dir=False, direction="to", follow_links=follow_links)

    def _sync_relative_path_from_remote(
        self,
        ssh_target: str,
        remote_project_root: str,
        relative_path: str,
        local_project_root: Path,
        optional: bool = False,
    ) -> None:
        local_path = local_project_root / relative_path
        local_path.parent.mkdir(parents=True, exist_ok=True)
        remote_path = posixpath.join(remote_project_root, relative_path)
        if optional and not self._remote_path_exists(ssh_target, remote_path):
            return
        self._run_rsync(f"{ssh_target}:{remote_path}", local_path.parent, is_dir=False, direction="from")

    def _sync_file_to_remote(self, ssh_target: str, local_path: Path, remote_path: str) -> None:
        self._ssh_mkdir(ssh_target, posixpath.dirname(remote_path))
        self._run_rsync(local_path, f"{ssh_target}:{remote_path}", is_dir=False, direction="to")

    def _sync_file_from_remote(self, ssh_target: str, remote_path: str, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self._run_rsync(f"{ssh_target}:{remote_path}", local_path.parent, is_dir=False, direction="from")

    def _remote_path_exists(self, ssh_target: str, remote_path: str) -> bool:
        completed = self._run_ssh(ssh_target, f"test -e {shlex.quote(remote_path)}")
        return completed.returncode == 0

    def _run_rsync(self, source, target, is_dir: bool, direction: str, follow_links: bool = False) -> None:
        command = [
            "rsync",
            "-az",
            "-e",
            "ssh " + " ".join(SSH_OPTIONS),
        ]
        if follow_links:
            command.append("-L")
        if is_dir and direction == "to":
            command.extend([str(source) + "/", str(target)])
        else:
            command.extend([str(source), str(target)])

        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"rsync failed: {completed.stderr.strip() or completed.stdout.strip()}")

    def _run_ssh(self, ssh_target: str, remote_command: str) -> subprocess.CompletedProcess[str]:
        command = ["ssh", *SSH_OPTIONS, ssh_target, f"bash -lc {shlex.quote(remote_command)}"]
        return subprocess.run(command, capture_output=True, text=True, check=False)
