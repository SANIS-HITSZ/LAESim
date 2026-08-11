#!/usr/bin/env python3
"""Export LAESim constellation runtime data to concise Markdown and CSV reports."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from collections import defaultdict


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", default=".runtime/constellation_demo")
    parser.add_argument("--summary", default="")
    parser.add_argument("--jsonl", default="")
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path):
    records = []
    if not os.path.isfile(path):
        return records
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise RuntimeError(f"Invalid JSONL at {path}:{line_number}: {error}") from error
    return records


def write_csv(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def format_number(value, digits=3):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{value:.{digits}f}" if math.isfinite(value) else "N/A"


def export_report(summary, records, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    statistics_rows = []
    for target, values in sorted(summary.get("selection_statistics", {}).items()):
        statistics_rows.append({
            "target": target,
            "selected_satellite": values.get("selected_satellite", ""),
            "handover_count": values.get("handover_count", 0),
            "acquisition_count": values.get("acquisition_count", 0),
            "outage_count": values.get("outage_count", 0),
            "completed_outage_count": values.get("completed_outage_count", 0),
            "total_outage_s": values.get("total_outage_s_including_current", 0.0),
            "max_outage_s": values.get("max_outage_s_including_current", 0.0),
            "mean_revisit_s": values.get("mean_revisit_s", 0.0),
        })

    event_rows = []
    for event in summary.get("selection_events", []):
        event_rows.append({
            "scenario_time": event.get("scenario_time", ""),
            "target": event.get("target", ""),
            "previous_satellite": event.get("previous_satellite", ""),
            "selected_satellite": event.get("selected_satellite", ""),
            "outage": event.get("outage", False),
            "interruption_s": event.get("interruption_s", 0.0),
        })

    isl_values = defaultdict(lambda: {"samples": 0, "up": 0, "range_sum_m": 0.0})
    for record in records:
        for link in record.get("isl_links", []):
            key = (link.get("source", ""), link.get("destination", ""))
            item = isl_values[key]
            item["samples"] += 1
            item["up"] += int(bool(link.get("access", False)))
            range_m = float(link.get("range_m", 0.0))
            if math.isfinite(range_m):
                item["range_sum_m"] += range_m
    isl_rows = []
    for (source, destination), values in sorted(isl_values.items()):
        samples = values["samples"]
        isl_rows.append({
            "source": source,
            "destination": destination,
            "samples": samples,
            "up_samples": values["up"],
            "availability_fraction": values["up"] / samples if samples else 0.0,
            "mean_range_m": values["range_sum_m"] / samples if samples else 0.0,
        })

    statistics_path = os.path.join(output_dir, "target_statistics.csv")
    events_path = os.path.join(output_dir, "selection_events.csv")
    isl_path = os.path.join(output_dir, "isl_statistics.csv")
    markdown_path = os.path.join(output_dir, "space_demo_report.md")
    write_csv(statistics_path, list(statistics_rows[0].keys()) if statistics_rows else [
        "target", "selected_satellite", "handover_count", "acquisition_count", "outage_count",
        "completed_outage_count", "total_outage_s", "max_outage_s", "mean_revisit_s",
    ], statistics_rows)
    write_csv(events_path, list(event_rows[0].keys()) if event_rows else [
        "scenario_time", "target", "previous_satellite", "selected_satellite", "outage", "interruption_s",
    ], event_rows)
    write_csv(isl_path, list(isl_rows[0].keys()) if isl_rows else [
        "source", "destination", "samples", "up_samples", "availability_fraction", "mean_range_m",
    ], isl_rows)

    metadata = summary.get("metadata", {})
    summary_sample_count = int(summary.get("sample_count", 0))
    runtime_sample_count = len(records)
    lines = [
        "# LAESim 天基任务运行报告",
        "",
        f"- 场景开始：`{summary.get('scenario_start', '')}`",
        f"- 场景结束：`{summary.get('scenario_stop', '')}`",
        f"- 统计样本数：`{summary_sample_count}`",
        f"- JSONL 记录数：`{runtime_sample_count}`",
        f"- 传播后端：`{metadata.get('provider', '')}`",
        f"- 卫星：`{', '.join(metadata.get('vehicles', []))}`",
        f"- 目标：`{', '.join(metadata.get('targets', []))}`",
        "",
        "## 目标选择与重访",
        "",
        "| 目标 | 最终选择 | 切换 | 捕获 | 空窗 | 总空窗/s | 最大空窗/s | 平均重访/s |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    if summary_sample_count != runtime_sample_count:
        lines.extend([
            "",
            "> 注意：summary 与 JSONL 样本数不一致，通常表示进程曾被强制结束；正式报告前应重新正常停止任务。",
        ])
    for row in statistics_rows:
        lines.append(
            f"| {row['target']} | {row['selected_satellite'] or 'OUTAGE'} | "
            f"{row['handover_count']} | {row['acquisition_count']} | {row['outage_count']} | "
            f"{format_number(row['total_outage_s'])} | {format_number(row['max_outage_s'])} | "
            f"{format_number(row['mean_revisit_s'])} |"
        )
    if not statistics_rows:
        lines.append("| 无数据 |  | 0 | 0 | 0 | 0 | 0 | 0 |")
    lines.extend([
        "",
        "## 星间链路",
        "",
        "| 源 | 目的 | 样本 | UP 样本 | 可用率 | 平均斜距/km |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ])
    for row in isl_rows:
        lines.append(
            f"| {row['source']} | {row['destination']} | {row['samples']} | {row['up_samples']} | "
            f"{format_number(100.0 * row['availability_fraction'], 2)}% | "
            f"{format_number(row['mean_range_m'] / 1000.0, 3)} |"
        )
    if not isl_rows:
        lines.append("| 无数据 |  | 0 | 0 | 0% | 0 |")
    lines.extend([
        "",
        "## 附件",
        "",
        "- `target_statistics.csv`：目标选星、切换、空窗和重访统计。",
        "- `selection_events.csv`：捕获、切换与进入空窗的事件序列。",
        "- `isl_statistics.csv`：星间链路可用率与平均斜距。",
        "",
    ])
    with open(markdown_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return [markdown_path, statistics_path, events_path, isl_path]


def main():
    args = parse_args()
    runtime_dir = os.path.abspath(os.path.expanduser(args.runtime_dir))
    summary_path = os.path.abspath(args.summary) if args.summary else os.path.join(
        runtime_dir, "space_constellation_summary.json"
    )
    jsonl_path = os.path.abspath(args.jsonl) if args.jsonl else os.path.join(
        runtime_dir, "space_constellation_runtime.jsonl"
    )
    output_dir = os.path.abspath(args.output_dir) if args.output_dir else os.path.join(runtime_dir, "report")
    if not os.path.isfile(summary_path):
        raise SystemExit(f"Summary not found: {summary_path}. Stop the demo gracefully before exporting.")
    paths = export_report(read_json(summary_path), read_jsonl(jsonl_path), output_dir)
    print(json.dumps({"outputs": paths}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
