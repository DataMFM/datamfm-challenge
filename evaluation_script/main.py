"""
DataMFM End-to-End Document Parsing Challenge
EvalAI Evaluation Script

This script receives:
  - test_annotation_file: path to GT JSON (OmniDocBench format)
  - user_submission_file: path to submitted .zip (containing .md files)
  - phase_codename: "dev" or "test"

It runs OmniDocBench end-to-end evaluation and returns scores in EvalAI format.
"""

import os
import sys
import json
import zipfile
import tempfile
import shutil
import traceback

# Add evaluation_script to sys.path so internal imports work
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# Import OmniDocBench eval components
from registry.registry import DATASET_REGISTRY, METRIC_REGISTRY, EVAL_TASK_REGISTRY

# Force registration of all modules
import dataset.end2end_dataset
import dataset.recog_dataset
import metrics.cal_metric
import task.end2end_run_eval


def extract_submission(zip_path, extract_dir):
    """
    Extract .zip submission to a flat directory of .md files.
    Handles nested directories by flattening.
    """
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(extract_dir)

    # Flatten: find all .md files and move to extract_dir root
    md_files = []
    for root, dirs, files in os.walk(extract_dir):
        # Skip __MACOSX
        if '__MACOSX' in root:
            continue
        for f in files:
            if f.endswith('.md') and not f.startswith('.'):
                md_files.append(os.path.join(root, f))

    # Move all .md files to root of extract_dir
    for md_path in md_files:
        dest = os.path.join(extract_dir, os.path.basename(md_path))
        if md_path != dest:
            shutil.move(md_path, dest)

    # Clean up subdirectories
    for item in os.listdir(extract_dir):
        item_path = os.path.join(extract_dir, item)
        if os.path.isdir(item_path):
            shutil.rmtree(item_path)

    final_md_files = [f for f in os.listdir(extract_dir) if f.endswith('.md')]
    return final_md_files


def run_evaluation(gt_path, pred_dir):
    """
    Run OmniDocBench end-to-end evaluation.
    Returns dict with per-dimension scores.
    """
    # Build config matching OmniDocBench end2end format
    cfg_task = {
        'dataset': {
            'dataset_name': 'end2end_dataset',
            'ground_truth': {
                'data_path': gt_path
            },
            'prediction': {
                'data_path': pred_dir
            },
            'match_method': 'quick_match'
        },
        'metrics': {
            'text_block': {
                'metric': ['Edit_dist']
            },
            'display_formula': {
                'metric': ['Edit_dist']  # CDM requires LaTeX rendering; use Edit_dist as fallback
            },
            'table': {
                'metric': ['TEDS', 'Edit_dist']
            }
        }
    }

    # Initialize dataset (does matching)
    dataset_cls = DATASET_REGISTRY.get('end2end_dataset')
    dataset = dataset_cls(cfg_task)

    # Run metrics for each element type
    results = {}
    metrics_cfg = cfg_task['metrics']

    for element_type in metrics_cfg:
        samples = dataset.samples.get(element_type)
        if samples is None:
            continue

        # Check if samples have any data
        sample_list = samples.samples if hasattr(samples, 'samples') else samples
        if not sample_list:
            print(f"Warning: no matched samples for {element_type}, skipping")
            continue

        element_results = {}
        for metric_name in metrics_cfg[element_type]['metric']:
            metric_cls = METRIC_REGISTRY.get(metric_name)
            if metric_cls is None:
                print(f"Warning: metric {metric_name} not found, skipping")
                continue
            try:
                samples_out, result_s = metric_cls(samples).evaluate([], f"evalai_{element_type}")
                if result_s:
                    element_results.update(result_s)
                # Update samples for next metric
                if samples_out is not None:
                    samples = samples_out
            except Exception as e:
                print(f"Warning: metric {metric_name} failed for {element_type}: {e}")

        results[element_type] = element_results

    return results


def compute_scores(results):
    """
    Compute final scores from OmniDocBench results.

    Result structure from OmniDocBench metrics:
      Edit_dist: {"Edit_dist": {"ALL_page_avg": float, "edit_whole": float, "edit_sample_avg": float}}
      TEDS: {"TEDS": {"all": float}, "TEDS_structure_only": {"all": float}}

    Returns:
        dict with Text_ED, Table_TEDS, Formula_CDM, Overall
    """
    # Extract Text Edit Distance
    # Use ALL_page_avg (average ED per page, then average across pages)
    text_ed = 0.0
    if 'text_block' in results and results['text_block']:
        ed_results = results['text_block'].get('Edit_dist', {})
        text_ed = ed_results.get('ALL_page_avg', ed_results.get('edit_sample_avg', 0.0))

    # Extract Table TEDS (0-1 scale from OmniDocBench, convert to 0-100)
    table_teds = 0.0
    if 'table' in results and results['table']:
        teds_results = results['table'].get('TEDS', {})
        table_teds = teds_results.get('all', 0.0)
        # TEDS is 0-1 in OmniDocBench, convert to 0-100
        if table_teds <= 1.0:
            table_teds *= 100

    # Extract Formula score (Edit Distance for now, CDM when available)
    # Convert ED to CDM-like score: (1 - ED) * 100
    formula_score = 0.0
    if 'display_formula' in results and results['display_formula']:
        formula_results = results['display_formula'].get('Edit_dist', {})
        formula_ed = formula_results.get('ALL_page_avg', formula_results.get('edit_sample_avg', 0.0))
        formula_score = (1.0 - formula_ed) * 100

    # Compute Overall: ((1 - Text_ED) * 100 + Table_TEDS + Formula_CDM) / 3
    text_score = (1.0 - text_ed) * 100
    overall = (text_score + table_teds + formula_score) / 3.0

    return {
        "Text_ED": round(text_ed, 4),
        "Table_TEDS": round(table_teds, 2),
        "Formula_CDM": round(formula_score, 2),
        "Overall": round(overall, 2)
    }


def evaluate(test_annotation_file, user_submission_file, phase_codename, **kwargs):
    """
    EvalAI evaluation entry point.

    Args:
        test_annotation_file: Path to GT JSON on the server
        user_submission_file: Path to submitted .zip file
        phase_codename: "dev" or "test"

    Returns:
        dict in EvalAI format
    """
    print(f"Starting DataMFM Evaluation for phase: {phase_codename}")
    print(f"GT file: {test_annotation_file}")
    print(f"Submission file: {user_submission_file}")

    output = {}
    tmp_dir = None

    try:
        # Create temp directory for extraction
        tmp_dir = tempfile.mkdtemp(prefix="datamfm_eval_")
        pred_dir = os.path.join(tmp_dir, "predictions")
        os.makedirs(pred_dir, exist_ok=True)

        # Extract submission .zip
        if not zipfile.is_zipfile(user_submission_file):
            raise ValueError("Submission must be a .zip file containing .md files")

        md_files = extract_submission(user_submission_file, pred_dir)
        print(f"Extracted {len(md_files)} .md files from submission")

        if len(md_files) == 0:
            raise ValueError("No .md files found in the submitted .zip")

        # Verify GT file exists
        if not os.path.exists(test_annotation_file):
            raise ValueError(f"Ground truth file not found: {test_annotation_file}")

        # Ensure result directory exists (OmniDocBench metrics write intermediate files)
        os.makedirs('./result', exist_ok=True)

        # Run evaluation
        results = run_evaluation(test_annotation_file, pred_dir)
        scores = compute_scores(results)

        print(f"Scores: {json.dumps(scores, indent=2)}")

        # Format for EvalAI
        split_name = "dev_split" if phase_codename == "dev" else "test_split"

        if phase_codename == "dev":
            output["result"] = [
                {
                    split_name: scores
                }
            ]
        elif phase_codename == "test":
            output["result"] = [
                {
                    "dev_split": scores  # Show on dev leaderboard too
                },
                {
                    "test_split": scores
                }
            ]
        else:
            output["result"] = [
                {
                    split_name: scores
                }
            ]

        output["submission_result"] = scores
        output["submission_metadata"] = {
            "num_predictions": len(md_files),
            "phase": phase_codename
        }

        print(f"Evaluation completed successfully for {phase_codename} phase")

    except Exception as e:
        print(f"Evaluation failed: {str(e)}")
        print(traceback.format_exc())

        # Return zero scores on error so EvalAI can still process
        error_scores = {
            "Text_ED": 1.0,
            "Table_TEDS": 0.0,
            "Formula_CDM": 0.0,
            "Overall": 0.0
        }
        split_name = "dev_split" if phase_codename == "dev" else "test_split"
        output["result"] = [{split_name: error_scores}]
        output["submission_result"] = error_scores
        output["submission_metadata"] = {"error": str(e)}

    finally:
        # Cleanup temp directory
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return output
