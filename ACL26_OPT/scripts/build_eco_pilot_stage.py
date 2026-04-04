from __future__ import annotations

import argparse
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def sample_to_parquet(source_path: Path, target_path: Path, max_rows: int) -> int:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_file = pq.ParquetFile(source_path)
    batches = []
    remaining = max_rows
    for batch in parquet_file.iter_batches(batch_size=min(max_rows, 512)):
        if batch.num_rows > remaining:
            batch = batch.slice(0, remaining)
        batches.append(batch)
        remaining -= batch.num_rows
        if remaining <= 0:
            break
    table = pa.Table.from_batches(batches)
    pq.write_table(table, target_path, compression="snappy")
    return int(table.num_rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--stage-root", required=True)
    parser.add_argument("--adi17-train-shards", type=int, default=4)
    parser.add_argument("--adi17-train-samples-per-file", type=int, default=1500)
    parser.add_argument("--mgb2-train-files", type=int, default=30)
    parser.add_argument("--mgb2-train-samples-per-file", type=int, default=50)
    args = parser.parse_args()

    source_root = Path(args.source_root).resolve()
    stage_root = Path(args.stage_root).resolve()

    acl_src = source_root / "ACL"
    acl_dst = stage_root / "ACL"
    acl_dst.mkdir(parents=True, exist_ok=True)

    adi17_train_files = sorted((source_root / "Data" / "ADI17" / "data").glob("train-*.parquet"))[: args.adi17_train_shards]
    mgb2_train_files = sorted((source_root / "Data" / "MGB2_parquet" / "train").glob("train-*.parquet"))[: args.mgb2_train_files]

    for source_path in adi17_train_files:
        target_path = stage_root / "Data" / "ADI17" / "data" / source_path.name
        sample_to_parquet(source_path, target_path, args.adi17_train_samples_per_file)

    for source_path in mgb2_train_files:
        target_path = stage_root / "Data" / "MGB2_parquet" / "train" / source_path.name
        sample_to_parquet(source_path, target_path, args.mgb2_train_samples_per_file)

    print(f"stage_root={stage_root}")
    print(f"adi17_train_files={len(adi17_train_files)}")
    print(f"mgb2_train_files={len(mgb2_train_files)}")


if __name__ == "__main__":
    main()
