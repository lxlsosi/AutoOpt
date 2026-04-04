from __future__ import annotations

import io
import json
import random
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import soundfile as sf
import torch
import torch.nn as nn
from sklearn.metrics import accuracy_score, f1_score, recall_score
from torch.utils.data import DataLoader, Dataset

from task_spec import dataset_policy_map, label_space, load_task_definition, region_mapping


DATASET_REGISTRY = {
    "Local": {
        "relative_path": "Local/processed",
        "layout": "jsonl_file",
        "label_column": "region_label",
        "mapping_name": "",
        "text_columns": ["transcript"],
    },
    "ADI17": {
        "relative_path": "ADI17/data",
        "layout": "hf_split_files",
        "label_column": "dialect",
        "mapping_name": "country_code_to_region",
        "text_columns": [],
    },
    "MGB2_parquet": {
        "relative_path": "MGB2_parquet",
        "layout": "split_subdir",
        "label_column": "dialect",
        "mapping_name": "country_code_to_region",
        "text_columns": [],
    },
    "NADI2025_subtask1_SLID": {
        "relative_path": "NADI2025_subtask1_SLID/data",
        "layout": "hf_split_files",
        "label_column": "country",
        "mapping_name": "country_name_to_region",
        "text_columns": [],
    },
    "MADIS5-spoken-arabic-dialects": {
        "relative_path": "MADIS5-spoken-arabic-dialects/data",
        "layout": "hf_split_files",
        "label_column": "dialect",
        "mapping_name": "english_region_name_to_region",
        "text_columns": [],
    },
}

EVAL_SUITES = {
    "smoke": [
        {"name": "ADI17", "split": "dev", "limit_files": 1, "max_samples": 30},
        {"name": "NADI2025_subtask1_SLID", "split": "validation", "limit_files": 1, "max_samples": 20},
    ],
    "formal_dev": [
        {"name": "ADI17", "split": "dev", "limit_files": 4},
        {"name": "NADI2025_subtask1_SLID", "split": "validation", "limit_files": 4, "max_samples": 4000},
    ],
    "local_gold": [
        {"name": "Local", "file_name": "local_gold_combined.jsonl"},
    ],
}


RECIPES = {
    "smoke": {
        "protocol_id": "acl26_acoustic_only_readiness_smoke_v1",
        "protocol_tier": "readiness",
        "model_track": "acoustic_only_baseline_v1",
        "transcript_mode": "disabled",
        "class_weight_mode": "none",
        "batch_size": 2,
        "epochs": 1,
        "max_steps": 3,
        "num_workers": 0,
        "learning_rate": 1e-5,
        "max_audio_seconds": 5,
        "max_text_length": 64,
        "train_datasets": [
            {"name": "ADI17", "split": "dev", "limit_files": 1, "max_samples": 30},
            {"name": "MGB2_parquet", "split": "dev", "limit_files": 1, "max_samples": 20},
        ],
        "eval_suite": "smoke",
    },
    "acoustic_pilot": {
        "protocol_id": "acl26_acoustic_only_eco_pilot_v1",
        "protocol_tier": "pilot",
        "model_track": "acoustic_only_baseline_v1",
        "transcript_mode": "disabled",
        "class_weight_mode": "inverse_sqrt",
        "train_eval_strategy": "holdout",
        "train_eval_fraction": 0.1,
        "train_eval_min_samples": 96,
        "batch_size": 8,
        "epochs": 2,
        "max_steps": 80,
        "num_workers": 2,
        "pin_memory": True,
        "persistent_workers": True,
        "prefetch_factor": 2,
        "learning_rate": 2e-5,
        "max_audio_seconds": 5,
        "max_text_length": 64,
        "train_datasets": [
            {"name": "ADI17", "split": "train", "limit_files": 4, "max_samples_per_file": 1500, "indexed_loader": True},
            {"name": "MGB2_parquet", "split": "train", "limit_files": 30, "max_samples_per_file": 50, "indexed_loader": True},
        ],
        "eval_suite": "formal_dev",
    },
    "acoustic_v1": {
        "protocol_id": "acl26_acoustic_only_formal_v1",
        "protocol_tier": "baseline",
        "model_track": "acoustic_only_baseline_v1",
        "transcript_mode": "disabled",
        "class_weight_mode": "inverse_sqrt",
        "train_eval_strategy": "holdout",
        "train_eval_fraction": 0.02,
        "train_eval_min_samples": 1024,
        "train_eval_max_samples": 4096,
        "batch_size": 16,
        "epochs": 1,
        "max_steps": 12000,
        "num_workers": 6,
        "pin_memory": True,
        "persistent_workers": True,
        "prefetch_factor": 4,
        "learning_rate": 2e-5,
        "max_audio_seconds": 5,
        "max_text_length": 64,
        "train_datasets": [
            {"name": "ADI17", "split": "train", "indexed_loader": True},
            {
                "name": "MGB2_parquet",
                "split": "train",
                "indexed_loader": True,
                "repeat_factor": 64,
            },
        ],
        "eval_suite": "formal_dev",
    },
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: dict) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def seed_everything(seed: int = 42) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def available_recipe_names() -> list[str]:
    return sorted(RECIPES)


def resolve_recipe(name: str) -> dict:
    if name not in RECIPES:
        raise KeyError(f"Unknown recipe: {name}")
    return deepcopy(RECIPES[name])


def resolve_runtime_recipe(recipe_name: str, task_definition_path: Path) -> dict:
    recipe = resolve_recipe(recipe_name)
    task_definition = load_task_definition(task_definition_path)
    protocol = task_definition.get("modeling_protocol", {})
    track_name = recipe.get("model_track") or protocol.get("official_baseline_track")
    tracks = protocol.get("tracks", {})
    if track_name not in tracks:
        raise KeyError(f"Unknown model track '{track_name}' for recipe '{recipe_name}'")
    model_track = deepcopy(tracks[track_name])
    recipe["name"] = recipe_name
    recipe["model_track_name"] = track_name
    recipe["model_track"] = model_track
    recipe["text_enabled"] = bool(model_track.get("requires_text", False)) and recipe.get("transcript_mode") != "disabled"
    return recipe


def _dataset_files(data_root: Path, dataset_name: str, split: str) -> list[Path]:
    spec = DATASET_REGISTRY[dataset_name]
    if spec["layout"] == "jsonl_file":
        base = data_root / spec["relative_path"]
        return [base / split]
    if spec["layout"] == "split_subdir":
        base = data_root / spec["relative_path"] / split
        return sorted(base.glob(f"{split}-*.parquet"))
    base = data_root / spec["relative_path"]
    files = sorted(base.glob(f"{split}-*.parquet"))
    if files:
        return files
    return sorted(base.glob(f"{split}.parquet"))


def _extract_text(frame: pd.DataFrame, text_columns: list[str]) -> pd.Series:
    if not text_columns:
        return pd.Series([""] * len(frame), index=frame.index, dtype="object")

    text = pd.Series([""] * len(frame), index=frame.index, dtype="object")
    for column in text_columns:
        if column not in frame.columns:
            continue
        values = frame[column].fillna("").astype(str)
        mask = text.eq("") & values.ne("")
        text.loc[mask] = values.loc[mask]
    return text


def _map_labels_to_regions(frame: pd.DataFrame, dataset_name: str, task_definition: dict) -> pd.DataFrame:
    spec = DATASET_REGISTRY[dataset_name]
    label_column = spec["label_column"]
    if label_column not in frame.columns:
        raise RuntimeError(f"Dataset {dataset_name} missing label column '{label_column}'")

    frame = frame.copy()
    mapping_name = spec.get("mapping_name", "")
    if mapping_name:
        mapping = region_mapping(task_definition, mapping_name)
        frame["raw_label"] = frame[label_column].astype(str)
        frame["region_label"] = frame["raw_label"].map(mapping)
    else:
        if "raw_label" in frame.columns:
            frame["raw_label"] = frame["raw_label"].astype(str)
        else:
            frame["raw_label"] = frame[label_column].astype(str)
        frame["region_label"] = frame[label_column].astype(str)
    frame = frame[frame["region_label"].notna()].reset_index(drop=True)
    return frame


def _load_table(table_path: Path) -> pd.DataFrame:
    if table_path.suffix == ".parquet":
        return pd.read_parquet(table_path)
    if table_path.suffix == ".jsonl":
        rows: list[dict] = []
        with table_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        return pd.DataFrame(rows)
    raise RuntimeError(f"Unsupported dataset file type: {table_path}")


def _text_values_from_table(table, text_columns: list[str], row_count: int) -> list[str]:
    if not text_columns:
        return [""] * row_count

    frame = table.to_pandas()
    return _extract_text(frame, text_columns).astype(str).tolist()


def _build_indexed_metadata_frame(
    table_path: Path,
    dataset_name: str,
    task_definition: dict,
) -> pd.DataFrame:
    spec = DATASET_REGISTRY[dataset_name]
    label_column = spec["label_column"]
    text_columns = spec.get("text_columns", [])
    parquet_file = pq.ParquetFile(table_path)

    records: list[dict] = []
    mapping_name = spec.get("mapping_name", "")
    mapping = region_mapping(task_definition, mapping_name) if mapping_name else {}
    requested_columns = [label_column, *[column for column in text_columns if column != label_column]]

    for row_group_index in range(parquet_file.num_row_groups):
        row_group_table = parquet_file.read_row_group(row_group_index, columns=requested_columns)
        label_values = [str(value) for value in row_group_table.column(label_column).to_pylist()]
        text_values = _text_values_from_table(row_group_table, text_columns, len(label_values))

        for row_index_in_group, raw_label in enumerate(label_values):
            region_label = mapping.get(raw_label) if mapping else raw_label
            if region_label is None:
                continue
            records.append(
                {
                    "storage_mode": "parquet_indexed",
                    "parquet_path": str(table_path),
                    "row_group_index": int(row_group_index),
                    "row_index_in_group": int(row_index_in_group),
                    "text": text_values[row_index_in_group] if row_index_in_group < len(text_values) else "",
                    "source_dataset": dataset_name,
                    "raw_label": raw_label,
                    "region_label": str(region_label),
                }
            )

    if not records:
        return pd.DataFrame(
            columns=[
                "storage_mode",
                "parquet_path",
                "row_group_index",
                "row_index_in_group",
                "text",
                "source_dataset",
                "raw_label",
                "region_label",
            ]
        )

    frame = pd.DataFrame.from_records(records)
    for column in ["storage_mode", "parquet_path", "source_dataset", "raw_label", "region_label"]:
        frame[column] = frame[column].astype("category")
    return frame


def _load_dataset_plan(
    data_root: Path,
    dataset_plan: list[dict],
    summary_name: str,
    task_definition_path: Path,
    usage_purpose: str,
) -> tuple[pd.DataFrame, dict]:
    task_definition = load_task_definition(task_definition_path)
    policy_map = dataset_policy_map(task_definition)
    frames: list[pd.DataFrame] = []
    summary: dict[str, dict] = {}

    for dataset_cfg in dataset_plan:
        dataset_name = dataset_cfg["name"]
        policy_item = policy_map.get(dataset_name)
        if policy_item is None:
            raise RuntimeError(f"Dataset {dataset_name} is not declared in task_definition dataset_policy")
        if usage_purpose == "train":
            if policy_item["policy_bucket"] != "whitelist":
                raise RuntimeError(
                    f"Dataset {dataset_name} is not eligible for training because it is in the {policy_item['policy_bucket']} bucket"
                )
            role = str(policy_item.get("role", ""))
            if "evaluation" in role:
                raise RuntimeError(
                    f"Dataset {dataset_name} is reserved for evaluation only and cannot be used in training"
                )
        elif usage_purpose == "eval" and policy_item["policy_bucket"] == "blocked":
            raise RuntimeError(f"Dataset {dataset_name} is blocked and cannot be used for evaluation")

        file_key = dataset_cfg.get("file_name") or dataset_cfg.get("split", "")
        files = _dataset_files(data_root, dataset_name, file_key)
        limited_files = files[: dataset_cfg.get("limit_files", len(files))]
        if not limited_files:
            summary[dataset_name] = {
                "split": file_key,
                "file_count": 0,
                "sample_count": 0,
                "usable": False,
            }
            continue

        dataset_frames: list[pd.DataFrame] = []
        for parquet_path in limited_files:
            if dataset_cfg.get("indexed_loader", False):
                frame = _build_indexed_metadata_frame(parquet_path, dataset_name, task_definition)
            else:
                frame = _load_table(parquet_path)
                frame = _map_labels_to_regions(frame, dataset_name, task_definition)
                frame["source_dataset"] = dataset_name
                frame["text"] = _extract_text(frame, DATASET_REGISTRY[dataset_name].get("text_columns", []))
            max_samples_per_file = dataset_cfg.get("max_samples_per_file")
            if max_samples_per_file and len(frame) > max_samples_per_file:
                frame = frame.sample(n=max_samples_per_file, random_state=42).reset_index(drop=True)
            keep_columns = [
                "storage_mode",
                "parquet_path",
                "row_group_index",
                "row_index_in_group",
                "audio",
                "audio_filepath",
                "text",
                "source_dataset",
                "raw_label",
                "region_label",
            ]
            dataset_frames.append(frame[[column for column in keep_columns if column in frame.columns]])

        combined = pd.concat(dataset_frames, ignore_index=True)
        max_samples = dataset_cfg.get("max_samples")
        if max_samples and len(combined) > max_samples:
            combined = combined.sample(n=max_samples, random_state=42).reset_index(drop=True)

        repeat_factor = max(int(dataset_cfg.get("repeat_factor", 1)), 1)
        if repeat_factor > 1 and not combined.empty:
            combined = pd.concat([combined] * repeat_factor, ignore_index=True)

        frames.append(combined)
        summary[dataset_name] = {
            "split": file_key,
            "file_count": len(limited_files),
            "sample_count": int(len(combined)),
            "repeat_factor": repeat_factor,
            "non_empty_text_samples": int(combined["text"].fillna("").astype(str).str.strip().ne("").sum()),
            "raw_labels": sorted(combined["raw_label"].astype(str).unique().tolist()),
            "region_labels": sorted(combined["region_label"].astype(str).unique().tolist()),
            "usable": True,
            "policy_bucket": policy_item["policy_bucket"],
            "policy_role": policy_item.get("role", ""),
        }

    if not frames:
        raise RuntimeError(f"No usable datasets found for dataset plan '{summary_name}'")

    return pd.concat(frames, ignore_index=True), summary


def load_split_dataframe(
    data_root: Path,
    recipe_name: str,
    stage: str,
    task_definition_path: Path,
) -> tuple[pd.DataFrame, dict]:
    recipe = resolve_runtime_recipe(recipe_name, task_definition_path)
    if stage == "train":
        dataset_plan = recipe["train_datasets"]
        usage_purpose = "train"
    else:
        dataset_plan = EVAL_SUITES[recipe.get("eval_suite", "smoke")]
        usage_purpose = "eval"
    return _load_dataset_plan(data_root, dataset_plan, f"{recipe_name}:{stage}", task_definition_path, usage_purpose)


def load_eval_suite_dataframe(
    data_root: Path,
    eval_suite_name: str,
    task_definition_path: Path,
) -> tuple[pd.DataFrame, dict]:
    if eval_suite_name not in EVAL_SUITES:
        raise KeyError(f"Unknown eval suite: {eval_suite_name}")
    return _load_dataset_plan(data_root, EVAL_SUITES[eval_suite_name], eval_suite_name, task_definition_path, "eval")


def build_label_names(task_definition_path: Path) -> list[str]:
    return label_space(load_task_definition(task_definition_path))


def build_hierarchy_map(label_names: list[str]) -> dict[int, int]:
    coarse_map = {
        "NorthAfrica": "West",
        "Egyptian": "Center",
        "MSA": "Center",
        "Levant": "East",
        "Mesopotamian": "East",
        "Gulf": "East",
    }
    coarse_names = sorted({coarse_map.get(label, "Other") for label in label_names})
    coarse_to_idx = {name: idx for idx, name in enumerate(coarse_names)}
    return {
        idx: coarse_to_idx[coarse_map.get(label, "Other")]
        for idx, label in enumerate(label_names)
    }


def build_class_weights(frame: pd.DataFrame, label_names: list[str], mode: str) -> torch.Tensor | None:
    if mode in {"", "none", None}:
        return None

    counts = frame["region_label"].astype(str).value_counts().to_dict()
    weights: list[float] = []
    for label in label_names:
        count = max(int(counts.get(label, 0)), 1)
        if mode == "inverse":
            weight = 1.0 / float(count)
        elif mode == "inverse_sqrt":
            weight = 1.0 / float(np.sqrt(count))
        else:
            raise KeyError(f"Unsupported class weight mode: {mode}")
        weights.append(weight)

    weights_tensor = torch.tensor(weights, dtype=torch.float32)
    weights_tensor = weights_tensor / weights_tensor.mean()
    return weights_tensor


def _cap_eval_frame(frame: pd.DataFrame, max_eval_samples: int, seed: int) -> pd.DataFrame:
    if max_eval_samples <= 0 or len(frame) <= max_eval_samples:
        return frame

    sampled_parts: list[pd.DataFrame] = []
    grouped = list(frame.groupby("region_label", sort=False))
    remaining_budget = max_eval_samples
    remaining_groups = len(grouped)
    total_rows = len(frame)

    for label, group in grouped:
        del label
        remaining_groups -= 1
        group = group.sample(frac=1.0, random_state=seed)
        proportional_target = int(round(len(group) / total_rows * max_eval_samples))
        target = max(1, proportional_target)
        if remaining_groups == 0:
            target = min(len(group), remaining_budget)
        else:
            target = min(len(group), max(1, remaining_budget - remaining_groups), target)
        sampled_parts.append(group.iloc[:target].copy())
        remaining_budget -= target

    capped = pd.concat(sampled_parts, axis=0)
    if len(capped) > max_eval_samples:
        capped = capped.sample(n=max_eval_samples, random_state=seed)
    return capped


def split_train_eval_holdout(
    frame: pd.DataFrame,
    holdout_fraction: float,
    min_eval_samples: int,
    max_eval_samples: int | None = None,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if frame.empty:
        raise RuntimeError("Cannot create a holdout split from an empty training frame")
    if not 0.0 < holdout_fraction < 1.0:
        raise ValueError(f"holdout_fraction must be in (0, 1), got {holdout_fraction}")

    train_parts: list[pd.DataFrame] = []
    eval_parts: list[pd.DataFrame] = []

    for _label, group in frame.groupby("region_label", sort=False):
        group = group.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        if len(group) <= 1:
            train_parts.append(group)
            continue
        eval_count = max(1, int(round(len(group) * holdout_fraction)))
        eval_count = min(eval_count, len(group) - 1)
        eval_parts.append(group.iloc[:eval_count].copy())
        train_parts.append(group.iloc[eval_count:].copy())

    train_frame = pd.concat(train_parts, ignore_index=True) if train_parts else frame.copy()
    eval_frame = pd.concat(eval_parts, ignore_index=True) if eval_parts else frame.iloc[:0].copy()

    if len(eval_frame) < min_eval_samples and len(train_frame) > 1:
        top_up = min(min_eval_samples - len(eval_frame), len(train_frame) - 1)
        if top_up > 0:
            extra_eval = train_frame.sample(n=top_up, random_state=seed)
            eval_frame = pd.concat([eval_frame, extra_eval], ignore_index=True)
            train_frame = train_frame.drop(extra_eval.index).reset_index(drop=True)

    if max_eval_samples is not None and len(eval_frame) > max_eval_samples:
        capped_eval = _cap_eval_frame(eval_frame, max_eval_samples=max_eval_samples, seed=seed)
        returned_train = eval_frame.drop(index=capped_eval.index)
        train_frame = pd.concat([train_frame, returned_train], ignore_index=True)
        eval_frame = capped_eval

    if eval_frame.empty:
        raise RuntimeError("Holdout split produced no evaluation samples")

    return train_frame.reset_index(drop=True), eval_frame.reset_index(drop=True)


class RuntimeMSAFilter(nn.Module):
    def __init__(self, hidden_size: int) -> None:
        super().__init__()
        self.attention = nn.Sequential(
            nn.Linear(hidden_size, 64),
            nn.Tanh(),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        scores = self.attention(x)
        return x * scores, scores


class AcousticOnlyHiCoDi(nn.Module):
    def __init__(
        self,
        num_classes: int,
        acoustic_model: str = "microsoft/wavlm-base-plus",
        use_msa_filter: bool = True,
        classifier_hidden_dim: int = 512,
        projection_dim: int = 128,
    ) -> None:
        super().__init__()
        patch_transformers_safe_loading()
        from transformers import WavLMModel

        self.use_msa_filter = use_msa_filter
        self.acoustic_encoder = WavLMModel.from_pretrained(acoustic_model)
        self.acoustic_dim = self.acoustic_encoder.config.hidden_size
        self.acoustic_encoder.feature_extractor._freeze_parameters()

        if self.use_msa_filter:
            self.msa_filter = RuntimeMSAFilter(self.acoustic_dim)

        self.acoustic_head = nn.Sequential(
            nn.Linear(self.acoustic_dim, classifier_hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
        )
        self.projector = nn.Sequential(
            nn.Linear(classifier_hidden_dim, classifier_hidden_dim),
            nn.ReLU(),
            nn.Linear(classifier_hidden_dim, projection_dim),
        )
        self.classifier = nn.Linear(classifier_hidden_dim, num_classes)

    def forward(
        self,
        audio_values: torch.Tensor,
        text_input_ids: torch.Tensor | None = None,
        text_mask: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        del text_input_ids, text_mask

        acoustic_outputs = self.acoustic_encoder(audio_values)
        acoustic_hidden = acoustic_outputs.last_hidden_state

        if self.use_msa_filter:
            acoustic_hidden, _ = self.msa_filter(acoustic_hidden)

        acoustic_pooled = torch.mean(acoustic_hidden, dim=1)
        hidden = self.acoustic_head(acoustic_pooled)
        proj_output = self.projector(hidden)
        logits = self.classifier(hidden)
        return logits, proj_output


class Acl26UnifiedDataset(Dataset):
    def __init__(self, frame: pd.DataFrame, label_names: list[str], max_audio_seconds: int) -> None:
        self.frame = frame.reset_index(drop=True)
        self.label_to_index = {name: idx for idx, name in enumerate(label_names)}
        self.max_audio_len = 16000 * max_audio_seconds
        self._parquet_cache: dict[str, pq.ParquetFile] = {}
        self._row_group_audio_cache: dict[tuple[str, int], object] = {}
        self._row_group_cache_order: list[tuple[str, int]] = []
        self._max_row_group_cache_entries = 8

    def __len__(self) -> int:
        return len(self.frame)

    def _indexed_audio_dict(self, row: pd.Series) -> dict | None:
        parquet_path = str(row["parquet_path"])
        row_group_index = int(row["row_group_index"])
        row_index_in_group = int(row["row_index_in_group"])

        parquet_file = self._parquet_cache.get(parquet_path)
        if parquet_file is None:
            parquet_file = pq.ParquetFile(parquet_path, memory_map=True)
            self._parquet_cache[parquet_path] = parquet_file

        cache_key = (parquet_path, row_group_index)
        if cache_key not in self._row_group_audio_cache:
            row_group_table = parquet_file.read_row_group(row_group_index, columns=["audio"])
            self._row_group_audio_cache[cache_key] = row_group_table.column("audio")
            self._row_group_cache_order.append(cache_key)
            if len(self._row_group_cache_order) > self._max_row_group_cache_entries:
                expired = self._row_group_cache_order.pop(0)
                self._row_group_audio_cache.pop(expired, None)

        row_group_audio = self._row_group_audio_cache.get(cache_key)
        if row_group_audio is None:
            return None
        return row_group_audio[row_index_in_group].as_py()

    def __getitem__(self, index: int) -> dict:
        row = self.frame.iloc[index]
        try:
            if row.get("storage_mode", "") == "parquet_indexed":
                audio_dict = self._indexed_audio_dict(row) or {}
                audio_bytes = audio_dict.get("bytes")
                if audio_bytes is not None:
                    waveform, sample_rate = sf.read(io.BytesIO(audio_bytes))
                else:
                    audio_path = audio_dict.get("path")
                    waveform, sample_rate = sf.read(str(audio_path))
            elif "audio" in row and isinstance(row["audio"], dict):
                audio_dict = row["audio"]
                audio_bytes = audio_dict.get("bytes")
                if audio_bytes is not None:
                    waveform, sample_rate = sf.read(io.BytesIO(audio_bytes))
                else:
                    audio_path = audio_dict.get("path")
                    waveform, sample_rate = sf.read(str(audio_path))
            else:
                audio_path = str(row.get("audio_filepath", ""))
                waveform, sample_rate = sf.read(audio_path)
            if waveform.ndim > 1:
                waveform = waveform.mean(axis=1)
            if sample_rate != 16000 and len(waveform) > 0:
                duration_seconds = len(waveform) / float(sample_rate)
                target_length = max(int(duration_seconds * 16000), 1)
                source_positions = np.linspace(0, len(waveform) - 1, num=len(waveform))
                target_positions = np.linspace(0, len(waveform) - 1, num=target_length)
                waveform = np.interp(target_positions, source_positions, waveform)
        except Exception:
            waveform = np.zeros(self.max_audio_len, dtype=np.float32)

        if len(waveform) > self.max_audio_len:
            waveform = waveform[: self.max_audio_len]
        else:
            waveform = np.pad(waveform, (0, self.max_audio_len - len(waveform)), mode="constant")

        return {
            "waveform": torch.tensor(waveform, dtype=torch.float32),
            "label": self.label_to_index[str(row["region_label"])],
            "text": str(row.get("text", "")),
            "raw_label": str(row.get("raw_label", "")),
            "region_label": str(row["region_label"]),
            "source_dataset": str(row.get("source_dataset", "")),
        }


def build_collate_fn(tokenizer, max_text_length: int, text_enabled: bool):
    def collate(batch: list[dict]) -> dict:
        waveforms = torch.stack([item["waveform"] for item in batch], dim=0)
        labels = torch.tensor([item["label"] for item in batch], dtype=torch.long)
        payload = {
            "waveforms": waveforms,
            "labels": labels,
            "raw_labels": [item["raw_label"] for item in batch],
            "region_labels": [item["region_label"] for item in batch],
            "source_datasets": [item["source_dataset"] for item in batch],
        }
        if text_enabled:
            if tokenizer is None:
                raise RuntimeError("Tokenizer is required when text_enabled=True")
            texts = [item["text"] for item in batch]
            tokenized = tokenizer(
                texts,
                padding=True,
                truncation=True,
                max_length=max_text_length,
                return_tensors="pt",
            )
            payload["texts"] = texts
            payload["text_input_ids"] = tokenized["input_ids"]
            payload["text_mask"] = tokenized["attention_mask"]
        return payload

    return collate


def create_dataloader(
    frame: pd.DataFrame,
    label_names: list[str],
    tokenizer,
    recipe_config: dict,
    shuffle: bool,
) -> DataLoader:
    dataset = Acl26UnifiedDataset(
        frame=frame,
        label_names=label_names,
        max_audio_seconds=recipe_config["max_audio_seconds"],
    )
    loader_kwargs = {
        "batch_size": recipe_config["batch_size"],
        "shuffle": shuffle,
        "num_workers": recipe_config["num_workers"],
        "collate_fn": build_collate_fn(tokenizer, recipe_config["max_text_length"], recipe_config["text_enabled"]),
    }
    if recipe_config.get("pin_memory"):
        loader_kwargs["pin_memory"] = True
    if recipe_config["num_workers"] > 0 and recipe_config.get("persistent_workers"):
        loader_kwargs["persistent_workers"] = True
    if recipe_config["num_workers"] > 0 and recipe_config.get("prefetch_factor"):
        loader_kwargs["prefetch_factor"] = recipe_config["prefetch_factor"]
    return DataLoader(
        dataset,
        **loader_kwargs,
    )


def patch_transformers_safe_loading() -> None:
    import transformers

    if getattr(transformers.WavLMModel, "_autoopt_safe_patch", False):
        return

    original_from_pretrained = transformers.WavLMModel.from_pretrained.__func__

    @classmethod
    def patched_from_pretrained(cls, pretrained_model_name_or_path, *args, **kwargs):
        if pretrained_model_name_or_path == "microsoft/wavlm-base-plus":
            kwargs.setdefault("use_safetensors", True)
            kwargs.setdefault("revision", "refs/pr/1")
        return original_from_pretrained(cls, pretrained_model_name_or_path, *args, **kwargs)

    transformers.WavLMModel.from_pretrained = patched_from_pretrained
    transformers.WavLMModel._autoopt_safe_patch = True


def _ensure_acl_on_path(acl_root: Path) -> None:
    acl_root_str = str(acl_root)
    if acl_root_str not in sys.path:
        sys.path.insert(0, acl_root_str)


def import_acl_loss(acl_root: Path):
    patch_transformers_safe_loading()
    _ensure_acl_on_path(acl_root)
    from loss import HierarchicalSupConLoss

    return HierarchicalSupConLoss


def import_acl_dual_modules(acl_root: Path):
    patch_transformers_safe_loading()
    _ensure_acl_on_path(acl_root)
    from model import AutoTokenizer, HiCoDiDual

    return HiCoDiDual, AutoTokenizer


def build_model_bundle(
    recipe_config: dict,
    task_definition_path: Path,
    num_classes: int,
    acl_root: Path,
):
    del task_definition_path
    model_track = recipe_config["model_track"]
    architecture = model_track["architecture"]
    if architecture == "acoustic_only_hicodi":
        model = AcousticOnlyHiCoDi(
            num_classes=num_classes,
            acoustic_model=model_track.get("acoustic_encoder", "microsoft/wavlm-base-plus"),
            use_msa_filter=bool(model_track.get("use_msa_filter", True)),
            classifier_hidden_dim=int(model_track.get("classifier_hidden_dim", 512)),
            projection_dim=int(model_track.get("projection_dim", 128)),
        )
        tokenizer = None
        return model, tokenizer

    if architecture == "hicodi_dual":
        HiCoDiDual, AutoTokenizer = import_acl_dual_modules(acl_root)
        model = HiCoDiDual(
            num_classes=num_classes,
            acoustic_model=model_track.get("acoustic_encoder", "microsoft/wavlm-base-plus"),
            semantic_model=model_track.get("semantic_encoder", "aubmindlab/bert-base-arabertv02"),
            use_msa_filter=bool(model_track.get("use_msa_filter", True)),
        )
        tokenizer = AutoTokenizer.from_pretrained(model_track.get("semantic_encoder", "aubmindlab/bert-base-arabertv02"))
        return model, tokenizer

    raise KeyError(f"Unsupported model architecture: {architecture}")


def forward_batch(model, batch: dict, device: torch.device) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    waveforms = batch["waveforms"].to(device)
    labels = batch["labels"].to(device)
    text_ids = batch.get("text_input_ids")
    text_mask = batch.get("text_mask")
    if text_ids is not None and text_mask is not None:
        logits, proj_features = model(waveforms, text_ids.to(device), text_mask.to(device))
    else:
        logits, proj_features = model(waveforms)
    return logits, proj_features, labels


def evaluate_model(model, dataloader, device, criterion_ce) -> dict:
    model.eval()
    losses: list[float] = []
    all_labels: list[int] = []
    all_preds: list[int] = []
    with torch.no_grad():
        for batch in dataloader:
            logits, _proj_features, labels = forward_batch(model, batch, device)
            loss = criterion_ce(logits, labels)
            losses.append(float(loss.item()))
            preds = torch.argmax(logits, dim=1)
            all_labels.extend(labels.cpu().tolist())
            all_preds.extend(preds.cpu().tolist())

    accuracy = float(accuracy_score(all_labels, all_preds))
    macro_f1 = float(f1_score(all_labels, all_preds, average="macro", zero_division=0))
    per_class_recall = recall_score(all_labels, all_preds, average=None, zero_division=0)
    rare_dialect_recall = float(np.mean(per_class_recall)) if len(per_class_recall) else 0.0
    return {
        "loss": float(np.mean(losses)) if losses else 0.0,
        "dev_accuracy": accuracy,
        "macro_f1": macro_f1,
        "rare_dialect_recall": rare_dialect_recall,
        "sample_count": len(all_labels),
    }
