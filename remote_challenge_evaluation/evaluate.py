import csv
import io
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SUBMISSIONS_ROOT = Path(os.environ.get("DATAMFM_SUBMISSIONS_ROOT", "/root/datamfm-test/submissions"))

DOCKER_IMAGE = os.environ.get("EVAL_DOCKER_IMAGE", "omnidocbench-cdm-fixed:v2")
DOC_EVAL_HOST_DIR = os.environ.get(
    "DOC_EVAL_HOST_DIR", "/root/datamfm-test/OmniDocBench-eval-md2md"
)
DOC_GT_MDS_DIR = os.environ.get(
    "DOC_GT_MDS_DIR", "/root/datamfm-test/OmniDocBench/demo_data/datamfm_20260409/mds"
)
DOC_EXPECTED_MD_COUNT = int(os.environ.get("DOC_EXPECTED_MD_COUNT", "89"))
DOC_CDM_WORKERS = int(os.environ.get("DOC_CDM_WORKERS", "4"))

CHART_GT_ROOT = Path(os.environ.get("CHART_GT_ROOT", "/root/datamfm-test/chart_gt"))
CHART_NUMERIC_REL_TOL = float(os.environ.get("CHART_NUMERIC_REL_TOL", "0.01"))
CHART_NUMERIC_ABS_TOL = float(os.environ.get("CHART_NUMERIC_ABS_TOL", "1e-4"))

PHASE_KINDS = {
    "dev": "dev",
    "test": "test",
    "doc_dev": "dev",
    "doc_test": "test",
    "chart_dev": "dev",
    "chart_test": "test",
}

EXPLICIT_PHASE_TASKS = {
    "doc_dev": "doc",
    "doc_test": "doc",
    "chart_dev": "chart",
    "chart_test": "chart",
}

TASK_ALIASES = {
    "doc": "doc",
    "document": "doc",
    "document_parsing": "doc",
    "document parsing": "doc",
    "documents": "doc",
    "chart": "chart",
    "chart_understanding": "chart",
    "chart understanding": "chart",
    "charts": "chart",
}


def _submission_id(kwargs):
    metadata = kwargs.get("submission_metadata") or {}
    for key in ("submission_pk", "pk", "id"):
        value = metadata.get(key)
        if value is not None:
            return str(value)
    return f"local_{int(time.time())}"


def _normalize_task(value):
    if value is None:
        return None
    normalized = str(value).strip().lower().replace("-", "_")
    return TASK_ALIASES.get(normalized)


def _metadata_values(metadata, wanted_keys):
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            return

    if isinstance(metadata, dict):
        lower_to_key = {str(key).lower(): key for key in metadata}
        for wanted in wanted_keys:
            key = lower_to_key.get(wanted)
            if key is not None:
                yield metadata[key]
        for nested_key in ("submission_metadata", "metadata", "meta"):
            if nested_key in metadata:
                yield from _metadata_values(metadata[nested_key], wanted_keys)
        return

    if isinstance(metadata, list):
        for item in metadata:
            if isinstance(item, dict):
                name = item.get("name") or item.get("key") or item.get("field_name")
                if name and str(name).lower() in wanted_keys:
                    for value_key in ("value", "values", "answer", "data"):
                        if value_key in item:
                            yield item[value_key]
                yield from _metadata_values(item, wanted_keys)


def _task_from_metadata(metadata):
    wanted_keys = {"task", "submission_task"}
    for value in _metadata_values(metadata, wanted_keys):
        if isinstance(value, list):
            for item in value:
                task = _normalize_task(item)
                if task:
                    return task
        else:
            task = _normalize_task(value)
            if task:
                return task
    return None


def _task_for_phase(phase_codename, submission_metadata=None):
    if phase_codename not in PHASE_KINDS:
        supported = sorted(set(PHASE_KINDS) | {"dev", "test"})
        raise ValueError(f"Unsupported phase_codename={phase_codename!r}. Expected one of {supported}")

    phase_kind = PHASE_KINDS[phase_codename]
    task = EXPLICIT_PHASE_TASKS.get(phase_codename)
    if task is None:
        task = _task_from_metadata(submission_metadata or {})
    if task is None:
        task = os.environ.get("DATAMFM_DEFAULT_TASK", "doc")
    task = _normalize_task(task)
    if task not in {"doc", "chart"}:
        raise ValueError(
            "Unsupported or missing Task metadata. Please choose either "
            "'Document Parsing' or 'Chart Understanding'."
        )
    return task, phase_kind


def _safe_json_dump(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _extract_flat(zip_path, output_dir, suffixes):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            if member.startswith("__MACOSX") or member.endswith("/"):
                continue
            if not any(member.endswith(suffix) for suffix in suffixes):
                continue
            basename = os.path.basename(member)
            if not basename:
                continue
            target = output_dir / basename
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted.append(basename)
    return extracted


def _extract_tree(zip_path, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            if member.startswith("__MACOSX") or member.endswith("/"):
                continue
            parts = [p for p in Path(member).parts if p not in ("", ".", "..")]
            if not parts:
                continue
            target = output_dir.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted.append(str(Path(*parts)))
    return extracted


def _write_doc_config(work_dir):
    config = f"""end2end_eval:
  metrics:
    text_block:
      metric:
        - Edit_dist
    display_formula:
      metric:
        - CDM
    table:
      metric:
        - TEDS
        - Edit_dist
    reading_order:
      metric:
        - Edit_dist
  dataset:
    dataset_name: md2md_dataset
    ground_truth:
      data_path: /workspace_gt/mds
      page_info: /workspace_gt/mds
    prediction:
      data_path: /workspace_run/pred_mds
    match_method: quick_match
"""
    config_path = Path(work_dir) / "doc_md2md_eval.yaml"
    config_path.write_text(config, encoding="utf-8")
    return config_path


def _validate_doc_submission(pred_dir):
    gt_names = {p.name for p in Path(DOC_GT_MDS_DIR).glob("*.md")}
    pred_names = {p.name for p in Path(pred_dir).glob("*.md")}
    missing = sorted(gt_names - pred_names)
    extra = sorted(pred_names - gt_names)
    if len(pred_names) != DOC_EXPECTED_MD_COUNT or missing or extra:
        raise ValueError(
            "Document submission filename mismatch. "
            f"expected_count={DOC_EXPECTED_MD_COUNT}, got_count={len(pred_names)}, "
            f"missing={missing[:10]}, extra={extra[:10]}"
        )


def _run_doc_eval(artifact_dir):
    artifact_dir = Path(artifact_dir)
    if not Path(DOC_EVAL_HOST_DIR).is_dir():
        raise RuntimeError(f"DOC_EVAL_HOST_DIR does not exist: {DOC_EVAL_HOST_DIR}")
    if not Path(DOC_GT_MDS_DIR).is_dir():
        raise RuntimeError(f"DOC_GT_MDS_DIR does not exist: {DOC_GT_MDS_DIR}")

    _write_doc_config(artifact_dir)
    (artifact_dir / "result").mkdir(parents=True, exist_ok=True)
    cmd = [
        "docker", "run", "--rm", "--entrypoint", "bash",
        "-e", f"OMNIDOCBENCH_CDM_WORKERS={DOC_CDM_WORKERS}",
        "-v", f"{DOC_EVAL_HOST_DIR}:/workspace_eval:ro",
        "-v", f"{Path(DOC_GT_MDS_DIR).parent}:/workspace_gt:ro",
        "-v", f"{artifact_dir}:/workspace_run",
        "-w", "/workspace_run",
        DOCKER_IMAGE,
        "-lc",
        "PYTHONUNBUFFERED=1 python /workspace_eval/pdf_validation.py --config /workspace_run/doc_md2md_eval.yaml",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    (artifact_dir / "stdout.log").write_text(proc.stdout, encoding="utf-8")
    (artifact_dir / "stderr.log").write_text(proc.stderr, encoding="utf-8")
    _safe_json_dump(artifact_dir / "docker_command.json", {"cmd": cmd, "returncode": proc.returncode})
    if proc.returncode != 0:
        raise RuntimeError(
            "Document Docker evaluation failed\n"
            f"stdout_tail={proc.stdout[-4000:]}\n"
            f"stderr_tail={proc.stderr[-4000:]}"
        )

    result_dir = artifact_dir / "result"
    candidates = sorted(result_dir.glob("*_metric_result.json"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise RuntimeError("Document evaluation finished without *_metric_result.json")
    metric_path = candidates[-1]
    metric_result = json.loads(metric_path.read_text(encoding="utf-8"))
    return metric_result, metric_path


def _score_doc(metric_result):
    text_ed = metric_result.get("text_block", {}).get("all", {}).get("Edit_dist", {}).get("ALL_page_avg", 1.0)
    table_teds = metric_result.get("table", {}).get("all", {}).get("TEDS", {}).get("all", 0.0) * 100
    formula_cdm = metric_result.get("display_formula", {}).get("all", {}).get("CDM", {}).get("all", 0.0) * 100
    reading_ed = metric_result.get("reading_order", {}).get("all", {}).get("Edit_dist", {}).get("ALL_page_avg", 1.0)
    reading_order = (1.0 - reading_ed) * 100
    overall = ((1.0 - text_ed) * 100 + table_teds + formula_cdm + reading_order) / 4.0
    return {
        "Text_ED": round(float(text_ed), 4),
        "Table_TEDS": round(float(table_teds), 2),
        "Formula_CDM": round(float(formula_cdm), 2),
        "Reading_Order": round(float(reading_order), 2),
        "Overall": round(float(overall), 2),
    }


def _read_jsonl(path):
    if Path(path).suffix == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError(f"Expected JSON array at {path}")
        return data

    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
    return rows


def _key(row):
    for field in ("imagename", "image_name", "filename", "id"):
        if field in row:
            return str(row[field])
    raise ValueError(f"Chart row missing image key: {row}")


def _first(row, fields, default=""):
    for field in fields:
        if field in row and row[field] is not None:
            return str(row[field])
    return default


def _numbers(text):
    values = []
    pattern = r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?"
    for raw in re.findall(pattern, str(text)):
        try:
            value = float(raw.replace(",", "").rstrip("%"))
        except ValueError:
            continue
        if math.isfinite(value):
            values.append(value)
    return sorted(set(values))


def _numbers_match(a, b):
    if a == b == 0:
        return True
    return abs(a - b) / max(abs(a), abs(b)) <= CHART_NUMERIC_REL_TOL


def _numeric_fact_f1(gt_text, pred_text):
    gt = _numbers(gt_text)
    pred = _numbers(pred_text)
    if not gt and not pred:
        return 1.0
    if not gt or not pred:
        return 0.0
    tp_pred = sum(1 for p in pred if any(_numbers_match(p, g) for g in gt))
    tp_gt = sum(1 for g in gt if any(_numbers_match(p, g) for p in pred))
    precision = tp_pred / len(pred)
    recall = tp_gt / len(gt)
    return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)


def _parse_csv_safe(text):
    text = str(text).strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text).strip()
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error:
        return [], []
    nonempty = [row for row in rows if any(cell.strip() for cell in row)]
    if not nonempty:
        return [], []
    return nonempty[0], nonempty[1:]


def _cell_to_float(cell):
    try:
        value = float(str(cell).strip().replace(",", "").rstrip("%"))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _csv_numbers(text):
    _, rows = _parse_csv_safe(text)
    values = set()
    for row in rows:
        for cell in row:
            value = _cell_to_float(cell)
            if value is not None:
                values.add(value)
    return sorted(values)


def _csv_numeric_f1(gt_csv, pred_csv):
    gt = _csv_numbers(gt_csv)
    pred = _csv_numbers(pred_csv)
    if not gt and not pred:
        return 1.0
    if not gt or not pred:
        return 0.0
    tp_pred = sum(1 for p in pred if any(_numbers_match(p, g) for g in gt))
    tp_gt = sum(1 for g in gt if any(_numbers_match(p, g) for p in pred))
    precision = tp_pred / len(pred)
    recall = tp_gt / len(gt)
    return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)


def _csv_structural_score(gt_csv, pred_csv):
    gt_header, gt_rows = _parse_csv_safe(gt_csv)
    pred_header, pred_rows = _parse_csv_safe(pred_csv)
    gt_cols = {cell.strip().lower() for cell in gt_header if cell.strip()}
    pred_cols = {cell.strip().lower() for cell in pred_header if cell.strip()}
    if gt_cols or pred_cols:
        true_positive = len(gt_cols & pred_cols)
        precision = true_positive / len(pred_cols) if pred_cols else 0.0
        recall = true_positive / len(gt_cols) if gt_cols else 0.0
        col_f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    else:
        col_f1 = 1.0
    if not gt_rows and not pred_rows:
        row_ratio = 1.0
    else:
        row_ratio = min(len(gt_rows), len(pred_rows)) / max(len(gt_rows), len(pred_rows)) if max(len(gt_rows), len(pred_rows)) else 0.0
    return (col_f1 + row_ratio) / 2.0


def _tokens(text):
    return re.findall(r"[a-z0-9]+", str(text).lower())


def _rouge_l_f1(reference, prediction):
    try:
        from rouge_score import rouge_scorer

        scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
        return scorer.score(str(reference), str(prediction))["rougeL"].fmeasure
    except Exception:
        pass

    ref = _tokens(reference)
    pred = _tokens(prediction)
    if not ref and not pred:
        return 1.0
    if not ref or not pred:
        return 0.0
    prev = [0] * (len(pred) + 1)
    for rt in ref:
        cur = [0]
        for j, pt in enumerate(pred, 1):
            cur.append(prev[j - 1] + 1 if rt == pt else max(prev[j], cur[-1]))
        prev = cur
    lcs = prev[-1]
    precision = lcs / len(pred)
    recall = lcs / len(ref)
    return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)


def _chart_gt_file(split, task):
    candidates = [
        CHART_GT_ROOT / split / f"{task}_gt.jsonl",
        CHART_GT_ROOT / split / f"{task}.jsonl",
        CHART_GT_ROOT / f"{split}_{task}_gt.jsonl",
        CHART_GT_ROOT / f"{split}_{task}.jsonl",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise RuntimeError(
        f"Missing chart GT for split={split}, task={task}. Tried: {[str(p) for p in candidates]}"
    )


def _chart_pred_file(pred_root, split, task):
    candidates = [
        Path(pred_root) / split / f"{task}_predictions.jsonl",
        Path(pred_root) / split / f"{task}.jsonl",
        Path(pred_root) / f"{split}_{task}_predictions.jsonl",
        Path(pred_root) / f"{split}_{task}.jsonl",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise ValueError(
        f"Missing chart prediction for split={split}, task={task}. Tried: {[str(p) for p in candidates]}"
    )


def _evaluate_chart_task(gt_path, pred_path, task):
    gt_rows = {_key(row): row for row in _read_jsonl(gt_path)}
    pred_rows = {_key(row): row for row in _read_jsonl(pred_path)}
    missing = sorted(set(gt_rows) - set(pred_rows))
    extra = sorted(set(pred_rows) - set(gt_rows))
    per_sample = []
    if missing:
        raise ValueError(f"Missing {len(missing)} predictions for {task}: {missing[:10]}")
    for key in sorted(gt_rows):
        gt = gt_rows[key]
        pred = pred_rows[key]
        if task == "chart2csv":
            gt_csv = _first(gt, ["ground_truth_csv", "csv", "target_csv", "reference_csv"])
            pred_csv = _first(pred, ["predicted_csv", "prediction", "output", "csv"])
            per_sample.append({
                "imagename": key,
                "numeric_f1": _csv_numeric_f1(gt_csv, pred_csv),
                "structural_score": _csv_structural_score(gt_csv, pred_csv),
            })
        else:
            gt_summary = _first(gt, ["ground_truth_summary", "summary", "target_summary", "reference_summary"])
            pred_summary = _first(pred, ["predicted_summary", "prediction", "output", "summary"])
            per_sample.append({
                "imagename": key,
                "rouge_l": _rouge_l_f1(gt_summary, pred_summary),
                "numeric_fact_f1": _numeric_fact_f1(gt_summary, pred_summary),
            })
    return per_sample, extra


def _mean(rows, field):
    vals = [row[field] for row in rows if field in row and not math.isnan(row[field])]
    return sum(vals) / len(vals) if vals else 0.0


def _run_chart_eval(artifact_dir):
    pred_root = Path(artifact_dir) / "predictions"
    all_csv = []
    all_summary = []
    extras = {}
    for split in ("real", "synthetic"):
        csv_rows, csv_extra = _evaluate_chart_task(
            _chart_gt_file(split, "chart2csv"), _chart_pred_file(pred_root, split, "chart2csv"), "chart2csv"
        )
        summary_rows, summary_extra = _evaluate_chart_task(
            _chart_gt_file(split, "chart2summary"), _chart_pred_file(pred_root, split, "chart2summary"), "chart2summary"
        )
        for row in csv_rows:
            row["split"] = split
        for row in summary_rows:
            row["split"] = split
        all_csv.extend(csv_rows)
        all_summary.extend(summary_rows)
        extras[split] = {"chart2csv": csv_extra[:20], "chart2summary": summary_extra[:20]}

    scores = {
        "CSV_Numeric_F1": round(_mean(all_csv, "numeric_f1") * 100, 2),
        "CSV_Structural_Score": round(_mean(all_csv, "structural_score") * 100, 2),
        "Summary_ROUGE_L": round(_mean(all_summary, "rouge_l") * 100, 2),
        "Summary_Numeric_Fact_F1": round(_mean(all_summary, "numeric_fact_f1") * 100, 2),
    }
    scores["Overall"] = round(sum(scores.values()) / 4.0, 2)
    metric_result = {"scores": scores, "extra_predictions": extras}
    _safe_json_dump(Path(artifact_dir) / "result" / "chart_metric_result.json", metric_result)
    _safe_json_dump(Path(artifact_dir) / "result" / "chart_per_sample.json", {"csv": all_csv, "summary": all_summary})
    return metric_result, Path(artifact_dir) / "result" / "chart_metric_result.json"


def _result_for_phase(phase_kind, scores):
    split_name = "dev_split" if phase_kind == "dev" else "test_split"
    return [{
        "split": split_name,
        "show_to_participant": True,
        "accuracies": scores,
    }]


def _evalai_leaderboard_scores(task, scores):
    if task == "doc":
        return {
            "Doc_Text_ED": scores.get("Text_ED", 1.0),
            "Doc_Table_TEDS": scores.get("Table_TEDS", 0.0),
            "Doc_Formula_CDM": scores.get("Formula_CDM", 0.0),
            "Doc_Overall": scores.get("Overall", 0.0),
            "Chart_CSV_Numeric_F1": 0.0,
            "Chart_CSV_Structural_Score": 0.0,
            "Chart_Summary_ROUGE_L": 0.0,
            "Chart_Summary_Numeric_Fact_F1": 0.0,
            "Chart_Overall": 0.0,
            "Overall": scores.get("Overall", 0.0),
        }
    return {
        "Doc_Text_ED": 1.0,
        "Doc_Table_TEDS": 0.0,
        "Doc_Formula_CDM": 0.0,
        "Doc_Overall": 0.0,
        "Chart_CSV_Numeric_F1": scores.get("CSV_Numeric_F1", 0.0),
        "Chart_CSV_Structural_Score": scores.get("CSV_Structural_Score", 0.0),
        "Chart_Summary_ROUGE_L": scores.get("Summary_ROUGE_L", 0.0),
        "Chart_Summary_Numeric_Fact_F1": scores.get("Summary_Numeric_Fact_F1", 0.0),
        "Chart_Overall": scores.get("Overall", 0.0),
        "Overall": scores.get("Overall", 0.0),
    }


def _format_success_stdout(metadata, scores):
    lines = [
        "DataMFM evaluation completed successfully.",
        f"Task: {metadata['task']}",
        f"Phase: {metadata['phase']}",
        f"Submission ID: {metadata['submission_id']}",
        f"Evaluation engine: {metadata['eval_engine']}",
        f"Extracted files: {metadata['num_extracted_files']}",
        f"Artifact directory: {metadata['artifact_dir']}",
        f"Metric result: {metadata['metric_result_path']}",
        "Scores:",
    ]
    for key, value in scores.items():
        lines.append(f"  {key}: {value}")
    lines.append("Raw evaluator stdout/stderr are saved in the artifact directory.")
    return "\n".join(lines)


def evaluate(user_submission_file, phase_codename, test_annotation_file=None, **kwargs):
    submission_metadata = kwargs.get("submission_metadata", {})
    task, phase_kind = _task_for_phase(phase_codename, submission_metadata)
    submission_id = _submission_id(kwargs)
    artifact_dir = SUBMISSIONS_ROOT / task / submission_id
    if artifact_dir.exists():
        shutil.rmtree(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(user_submission_file, artifact_dir / "submission.zip")
    _safe_json_dump(artifact_dir / "request_metadata.json", {
        "task": task,
        "phase_codename": phase_codename,
        "phase_kind": phase_kind,
        "submission_id": submission_id,
        "submission_metadata": submission_metadata,
    })

    try:
        if not zipfile.is_zipfile(user_submission_file):
            raise ValueError("Submission must be a .zip file")

        if task == "doc":
            pred_dir = artifact_dir / "pred_mds"
            extracted = _extract_flat(user_submission_file, pred_dir, [".md"])
            if not extracted:
                raise ValueError("Document submission must contain .md files")
            _validate_doc_submission(pred_dir)
            metric_result, metric_path = _run_doc_eval(artifact_dir)
            scores = _score_doc(metric_result)
            eval_engine = "doc_md2md_cdm"
        else:
            pred_dir = artifact_dir / "predictions"
            extracted = _extract_tree(user_submission_file, pred_dir)
            if not extracted:
                raise ValueError("Chart submission zip is empty")
            metric_result, metric_path = _run_chart_eval(artifact_dir)
            scores = metric_result["scores"]
            eval_engine = "chart_jsonl_deterministic"

        metadata = {
            "task": task,
            "phase": phase_codename,
            "phase_kind": phase_kind,
            "submission_id": submission_id,
            "artifact_dir": str(artifact_dir),
            "metric_result_path": str(metric_path),
            "num_extracted_files": len(extracted),
            "eval_engine": eval_engine,
            "scores": scores,
        }
        _safe_json_dump(artifact_dir / "scores.json", scores)
        _safe_json_dump(artifact_dir / "submission_metadata.json", metadata)
        leaderboard_scores = _evalai_leaderboard_scores(task, scores)
        return {
            "submission_status": "FINISHED",
            "result": _result_for_phase(phase_kind, leaderboard_scores),
            "submission_result": scores,
            "submission_metadata": json.dumps(metadata),
            "stdout": _format_success_stdout(metadata, scores),
            "stderr": "",
        }
    except Exception as exc:
        if task == "doc":
            error_scores = {"Text_ED": 1.0, "Table_TEDS": 0.0, "Formula_CDM": 0.0, "Reading_Order": 0.0, "Overall": 0.0}
        else:
            error_scores = {"CSV_Numeric_F1": 0.0, "CSV_Structural_Score": 0.0, "Summary_ROUGE_L": 0.0, "Summary_Numeric_Fact_F1": 0.0, "Overall": 0.0}
        metadata = {
            "task": task,
            "phase": phase_codename,
            "phase_kind": phase_kind,
            "submission_id": submission_id,
            "artifact_dir": str(artifact_dir),
            "error": str(exc),
            "scores": error_scores,
        }
        _safe_json_dump(artifact_dir / "error.json", metadata)
        leaderboard_scores = _evalai_leaderboard_scores(task, error_scores)
        return {
            "submission_status": "FAILED",
            "result": _result_for_phase(phase_kind, leaderboard_scores),
            "submission_result": error_scores,
            "submission_metadata": json.dumps(metadata),
            "stdout": "",
            "stderr": str(exc),
        }
