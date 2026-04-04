from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


LOCAL_COUNTRY_LABEL_TO_REGION = {
    "SY": "Levant",
    "IQ": "Mesopotamian",
    "EG": "Egyptian",
}

ADI5_LABEL_TO_REGION = {
    "GLF": "Gulf",
    "NOR": "NorthAfrica",
    "MSA": "MSA",
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def write_json(path: Path, data: dict) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def normalize_562(rows: list[dict]) -> tuple[list[dict], dict]:
    normalized: list[dict] = []
    unknown_labels: Counter[str] = Counter()
    region_counts: Counter[str] = Counter()

    for index, row in enumerate(rows, start=1):
        raw_label = str(row.get("final_label", "")).strip()
        region_label = LOCAL_COUNTRY_LABEL_TO_REGION.get(raw_label)
        if region_label is None:
            unknown_labels[raw_label] += 1

        normalized_row = {
            "record_id": f"local_562_{index:04d}",
            "subset": "local_562_syiqeg",
            "source_family": "Local",
            "audio_filepath": row.get("audio_filepath", ""),
            "audio_url": row.get("url", ""),
            "audio_url_raw": row.get("url_raw", ""),
            "audio_url_mp4": row.get("url_mp4", ""),
            "transcript": row.get("ctc", ""),
            "duration_sec": row.get("duration"),
            "raw_label": raw_label,
            "raw_label_type": "country_code_2char",
            "region_label": region_label,
            "home_country": row.get("home_country"),
            "home_region": row.get("home_region"),
            "uid": row.get("uid"),
            "vad": row.get("vad"),
            "start_time": row.get("start_time"),
            "end_time": row.get("end_time"),
        }
        normalized.append(normalized_row)
        if region_label:
            region_counts[region_label] += 1

    summary = {
        "record_count": len(normalized),
        "raw_label_distribution": dict(Counter(row["raw_label"] for row in normalized)),
        "region_label_distribution": dict(region_counts),
        "unknown_labels": dict(unknown_labels),
    }
    return normalized, summary


def normalize_adi5_pair(
    wav_rows: list[dict],
    meta_rows: list[dict],
    subset_name: str,
) -> tuple[list[dict], dict]:
    wav_by_audio = {str(row.get("audio_filepath", "")): row for row in wav_rows}
    meta_by_audio = {str(row.get("audio_filepath", "")): row for row in meta_rows}

    wav_keys = set(wav_by_audio)
    meta_keys = set(meta_by_audio)
    shared_keys = [key for key in wav_by_audio if key in meta_by_audio]

    normalized: list[dict] = []
    region_counts: Counter[str] = Counter()
    transcript_mismatches = 0
    url_mismatches = 0
    unknown_labels: Counter[str] = Counter()

    for index, audio_filepath in enumerate(shared_keys, start=1):
        wav_row = wav_by_audio[audio_filepath]
        meta_row = meta_by_audio[audio_filepath]

        wav_text = wav_row.get("ctc", "")
        meta_text = meta_row.get("ctc", "")
        if wav_text != meta_text:
            transcript_mismatches += 1

        wav_url = wav_row.get("url", "")
        meta_url = meta_row.get("url", "")
        if wav_url != meta_url:
            url_mismatches += 1

        raw_label = str(meta_row.get("dialect", "")).strip()
        region_label = ADI5_LABEL_TO_REGION.get(raw_label)
        if region_label is None:
            unknown_labels[raw_label] += 1

        normalized_row = {
            "record_id": f"{subset_name}_{index:04d}",
            "subset": subset_name,
            "source_family": "Local",
            "audio_filepath": audio_filepath,
            "audio_url": wav_url or meta_url,
            "transcript": wav_text or meta_text,
            "duration_sec": meta_row.get("duration"),
            "sampling_rate": meta_row.get("sampling_rate"),
            "raw_label": raw_label,
            "raw_label_type": "adi5_dialect_code",
            "region_label": region_label,
            "gemini3_country": meta_row.get("gemini3_country"),
            "varDial_id": meta_row.get("id"),
            "wavlist_id": wav_row.get("id"),
            "status": meta_row.get("status"),
        }
        normalized.append(normalized_row)
        if region_label:
            region_counts[region_label] += 1

    summary = {
        "record_count": len(normalized),
        "wavlist_count": len(wav_rows),
        "metadata_count": len(meta_rows),
        "shared_audio_filepath_count": len(shared_keys),
        "only_in_wavlist": len(wav_keys - meta_keys),
        "only_in_metadata": len(meta_keys - wav_keys),
        "transcript_mismatches": transcript_mismatches,
        "url_mismatches": url_mismatches,
        "raw_label_distribution": dict(Counter(row["raw_label"] for row in normalized)),
        "region_label_distribution": dict(region_counts),
        "unknown_labels": dict(unknown_labels),
    }
    return normalized, summary


def check_audio_paths(rows: list[dict]) -> dict:
    exists = 0
    missing = 0
    checked = 0
    for row in rows:
        audio_filepath = str(row.get("audio_filepath", "")).strip()
        if not audio_filepath:
            continue
        checked += 1
        if Path(audio_filepath).exists():
            exists += 1
        else:
            missing += 1
    return {
        "checked": checked,
        "exists": exists,
        "missing": missing,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--audio-mirror-root", default="")
    parser.add_argument("--check-audio-paths", action="store_true")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    manifest_path = Path(args.manifest_path).resolve()
    audio_mirror_root = Path(args.audio_mirror_root).resolve() if args.audio_mirror_root else None
    ensure_dir(output_dir)

    local_562_rows = load_jsonl(input_dir / "test_600_SYIQEG.txt_1kh3hw08")
    wavlist_375_rows = load_jsonl(input_dir / "testwavlist_GMN_20260319.txt_1kh3hw08")
    meta_375_rows = load_jsonl(input_dir / "varDial2017_GLF_NOR_MSA_merged_test.jsonl_1kh3hw08")
    wavlist_300_rows = load_jsonl(input_dir / "testwavlist_GMN_20260324_100.txt_1kh3hw08")
    meta_300_rows = load_jsonl(input_dir / "varDial2017_dev_wav_GLF_NOR_MSA_gemini3_100.jsonl_1kh3hw08")

    normalized_562, summary_562 = normalize_562(local_562_rows)
    normalized_375, summary_375 = normalize_adi5_pair(
        wavlist_375_rows,
        meta_375_rows,
        "local_gmn_20260319",
    )
    normalized_300, summary_300 = normalize_adi5_pair(
        wavlist_300_rows,
        meta_300_rows,
        "local_gmn_20260324_100",
    )

    if audio_mirror_root:
        for rows in [normalized_562, normalized_375, normalized_300]:
            for row in rows:
                source_audio_filepath = str(row.get("audio_filepath", "")).strip()
                if not source_audio_filepath:
                    continue
                row["source_audio_filepath"] = source_audio_filepath
                row["audio_filepath"] = str(audio_mirror_root / source_audio_filepath.lstrip("/"))

    combined = normalized_562 + normalized_375 + normalized_300
    combined_summary = {
        "record_count": len(combined),
        "region_label_distribution": dict(Counter(row["region_label"] for row in combined)),
        "raw_label_distribution": dict(Counter(row["raw_label"] for row in combined)),
    }
    if args.check_audio_paths:
        combined_summary["audio_path_check"] = check_audio_paths(combined)
    if audio_mirror_root:
        combined_summary["audio_mirror_root"] = str(audio_mirror_root)

    processed_dir = output_dir / "processed"
    write_jsonl(processed_dir / "local_562_syiqeg.jsonl", normalized_562)
    write_jsonl(processed_dir / "local_gmn_20260319.jsonl", normalized_375)
    write_jsonl(processed_dir / "local_gmn_20260324_100.jsonl", normalized_300)
    write_jsonl(processed_dir / "local_gold_combined.jsonl", combined)

    manifest = {
        "source_files": {
            "test_600_SYIQEG.txt_1kh3hw08": {
                "record_count": len(local_562_rows),
                "bytes": (input_dir / "test_600_SYIQEG.txt_1kh3hw08").stat().st_size,
            },
            "testwavlist_GMN_20260319.txt_1kh3hw08": {
                "record_count": len(wavlist_375_rows),
                "bytes": (input_dir / "testwavlist_GMN_20260319.txt_1kh3hw08").stat().st_size,
            },
            "varDial2017_GLF_NOR_MSA_merged_test.jsonl_1kh3hw08": {
                "record_count": len(meta_375_rows),
                "bytes": (input_dir / "varDial2017_GLF_NOR_MSA_merged_test.jsonl_1kh3hw08").stat().st_size,
            },
            "testwavlist_GMN_20260324_100.txt_1kh3hw08": {
                "record_count": len(wavlist_300_rows),
                "bytes": (input_dir / "testwavlist_GMN_20260324_100.txt_1kh3hw08").stat().st_size,
            },
            "varDial2017_dev_wav_GLF_NOR_MSA_gemini3_100.jsonl_1kh3hw08": {
                "record_count": len(meta_300_rows),
                "bytes": (input_dir / "varDial2017_dev_wav_GLF_NOR_MSA_gemini3_100.jsonl_1kh3hw08").stat().st_size,
            },
        },
        "processed_subsets": {
            "local_562_syiqeg": summary_562,
            "local_gmn_20260319": summary_375,
            "local_gmn_20260324_100": summary_300,
            "local_gold_combined": combined_summary,
        },
        "output_files": {
            "local_562_syiqeg": "processed/local_562_syiqeg.jsonl",
            "local_gmn_20260319": "processed/local_gmn_20260319.jsonl",
            "local_gmn_20260324_100": "processed/local_gmn_20260324_100.jsonl",
            "local_gold_combined": "processed/local_gold_combined.jsonl",
        },
    }
    write_json(manifest_path, manifest)


if __name__ == "__main__":
    main()
