"""
DataMFM End-to-End Document Parsing Challenge - EvalAI Evaluation Script
Uses OmniDocBench's real evaluation code for accurate metrics.

Metrics computed:
- Text: Normalized Edit Distance (Levenshtein)
- Table: TEDS (Tree Edit Distance-based Similarity, APTED algorithm)
- Formula: Edit Distance (CDM proxy until xelatex environment available)
- Reading Order: Normalized Edit Distance
- Overall: ((1 - Text_ED) * 100 + Table_TEDS + Formula_CDM_proxy) / 3
"""

import os
import sys
import json
import zipfile
import tempfile
import shutil
import traceback

# Add bundled OmniDocBench code to path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OMNIDOCBENCH_DIR = os.path.join(SCRIPT_DIR, "omnidocbench")
if OMNIDOCBENCH_DIR not in sys.path:
    sys.path.insert(0, OMNIDOCBENCH_DIR)


def extract_submission(zip_path, output_dir):
    """Extract .md files from submission zip."""
    md_files = []
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for name in zf.namelist():
            if name.endswith('.md') and not name.startswith('__MACOSX'):
                # Flatten: extract to output_dir regardless of zip structure
                basename = os.path.basename(name)
                if basename:
                    target = os.path.join(output_dir, basename)
                    with zf.open(name) as src, open(target, 'wb') as dst:
                        dst.write(src.read())
                    md_files.append(basename)
    return md_files


def run_omnidocbench_eval(gt_path, pred_dir):
    """
    Run OmniDocBench end2end evaluation.
    Returns dict with metric scores.
    """
    import yaml
    from registry.registry import EVAL_TASK_REGISTRY, DATASET_REGISTRY, METRIC_REGISTRY
    import dataset
    import task
    import metrics

    # Build config programmatically
    cfg = {
        "end2end_eval": {
            "metrics": {
                "text_block": {
                    "metric": ["Edit_dist"]
                },
                "display_formula": {
                    "metric": ["Edit_dist"]
                },
                "table": {
                    "metric": ["TEDS", "Edit_dist"]
                },
                "reading_order": {
                    "metric": ["Edit_dist"]
                }
            },
            "dataset": {
                "dataset_name": "end2end_dataset",
                "ground_truth": {
                    "data_path": gt_path
                },
                "prediction": {
                    "data_path": pred_dir
                },
                "match_method": "quick_match"
            }
        }
    }

    task_cfg = cfg["end2end_eval"]
    dataset_name = task_cfg["dataset"]["dataset_name"]
    metrics_list = task_cfg["metrics"]
    
    # Create result directory
    os.makedirs("./result", exist_ok=True)
    
    # Initialize dataset
    val_dataset = DATASET_REGISTRY.get(dataset_name)(task_cfg)
    val_task = EVAL_TASK_REGISTRY.get("end2end_eval")
    
    save_name = "evalai_submission_quick_match"
    
    # Run evaluation (this populates ./result/ with JSON files)
    val_task(val_dataset, metrics_list, gt_path, save_name)
    
    # Read results
    result_path = f"./result/{save_name}_metric_result.json"
    if os.path.exists(result_path):
        with open(result_path, 'r') as f:
            return json.load(f)
    
    return None


def compute_scores(eval_result):
    """
    Extract final scores from OmniDocBench eval result.
    Returns EvalAI-compatible score dict.
    """
    # Text Edit Distance
    text_ed = 1.0  # default worst
    if "text_block" in eval_result:
        text_all = eval_result["text_block"].get("all", {})
        ed = text_all.get("Edit_dist", {})
        text_ed = ed.get("ALL_page_avg", ed.get("edit_whole", 1.0))
    
    # Table TEDS (0-1 scale in result, display as 0-100)
    table_teds = 0.0
    if "table" in eval_result:
        table_all = eval_result["table"].get("all", {})
        teds = table_all.get("TEDS", {})
        table_teds = teds.get("all", 0.0) * 100  # Convert to 0-100 scale
    
    # Formula CDM proxy (using Edit Distance as proxy)
    formula_cdm_proxy = 0.0
    if "display_formula" in eval_result:
        formula_all = eval_result["display_formula"].get("all", {})
        fed = formula_all.get("Edit_dist", {})
        formula_ed = fed.get("ALL_page_avg", fed.get("edit_whole", 1.0))
        formula_cdm_proxy = (1.0 - formula_ed) * 100  # Convert ED to CDM-like score
    
    # Reading Order Edit Distance
    reading_ed = 1.0
    if "reading_order" in eval_result:
        ro_all = eval_result["reading_order"].get("all", {})
        red = ro_all.get("Edit_dist", {})
        reading_ed = red.get("ALL_page_avg", red.get("edit_whole", 1.0))
    
    # Overall = ((1 - Text_ED) * 100 + Table_TEDS + Formula_CDM) / 3
    overall = ((1.0 - text_ed) * 100 + table_teds + formula_cdm_proxy) / 3.0
    
    return {
        "Text_ED": round(text_ed, 4),
        "Table_TEDS": round(table_teds, 2),
        "Formula_CDM": round(formula_cdm_proxy, 2),
        "Overall": round(overall, 2),
    }


def evaluate(test_annotation_file, user_submission_file, phase_codename, **kwargs):
    """
    EvalAI evaluation entry point.
    
    Args:
        test_annotation_file: Path to GT JSON (OmniDocBench format)
        user_submission_file: Path to submitted .zip file
        phase_codename: "dev" or "test"
    
    Returns:
        dict with EvalAI result format
    """
    print(f"Starting DataMFM Evaluation (OmniDocBench metrics) for phase: {phase_codename}")
    print(f"GT file: {test_annotation_file}")
    print(f"Submission file: {user_submission_file}")
    
    output = {}
    tmp_dir = None
    original_cwd = os.getcwd()
    
    try:
        tmp_dir = tempfile.mkdtemp(prefix="datamfm_eval_")
        pred_dir = os.path.join(tmp_dir, "predictions")
        os.makedirs(pred_dir, exist_ok=True)
        
        # Create result dir in tmp
        result_dir = os.path.join(tmp_dir, "result")
        os.makedirs(result_dir, exist_ok=True)
        
        # Extract submission
        if not zipfile.is_zipfile(user_submission_file):
            raise ValueError("Submission must be a .zip file containing .md files")
        
        md_files = extract_submission(user_submission_file, pred_dir)
        print(f"Extracted {len(md_files)} .md files from submission")
        
        if len(md_files) == 0:
            raise ValueError("No .md files found in the submitted .zip")
        
        if not os.path.exists(test_annotation_file):
            raise ValueError(f"Ground truth file not found: {test_annotation_file}")
        
        # Change to tmp_dir so result files go there
        os.chdir(tmp_dir)
        
        # Run OmniDocBench evaluation
        eval_result = run_omnidocbench_eval(test_annotation_file, pred_dir)
        
        if eval_result is None:
            raise RuntimeError("Evaluation produced no results")
        
        # Compute final scores
        scores = compute_scores(eval_result)
        print(f"Scores: {json.dumps(scores, indent=2)}")
        
        # Format for EvalAI
        split_name = "dev_split" if phase_codename == "dev" else "test_split"
        
        if phase_codename == "dev":
            output["result"] = [
                {split_name: scores}
            ]
        elif phase_codename == "test":
            output["result"] = [
                {"dev_split": scores},
                {"test_split": scores}
            ]
        else:
            output["result"] = [
                {split_name: scores}
            ]
        
        output["submission_result"] = scores
        output["submission_metadata"] = json.dumps({
            "num_predictions": len(md_files),
            "phase": phase_codename,
            "eval_engine": "OmniDocBench_v1.5",
            "cdm_note": "Formula_CDM uses Edit Distance proxy (CDM requires xelatex)"
        })
        
        print(f"Evaluation completed successfully for {phase_codename} phase")
    
    except Exception as e:
        print(f"Evaluation failed: {str(e)}")
        print(traceback.format_exc())
        
        error_scores = {
            "Text_ED": 1.0,
            "Table_TEDS": 0.0,
            "Formula_CDM": 0.0,
            "Overall": 0.0
        }
        split_name = "dev_split" if phase_codename == "dev" else "test_split"
        output["result"] = [{split_name: error_scores}]
        output["submission_result"] = error_scores
        output["submission_metadata"] = json.dumps({"error": str(e)})
    
    finally:
        os.chdir(original_cwd)
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
    
    return output
