"""
DataMFM End-to-End Document Parsing Challenge - EvalAI Evaluation Script

LIGHTWEIGHT VERSION: Uses only Python standard library to avoid dependency issues
on EvalAI's shared worker (Python 3.7, minimal packages).

Flow: .zip submission → extract .md files → match with GT JSON → score → EvalAI JSON
"""

import os
import sys
import json
import zipfile
import tempfile
import shutil
import traceback
import re
import difflib
from collections import defaultdict


# ============================================================
# Text Edit Distance (using difflib, no external deps)
# ============================================================

def normalized_edit_distance(s1, s2):
    """Normalized edit distance using SequenceMatcher (standard lib)."""
    if not s1 and not s2:
        return 0.0
    if not s1 or not s2:
        return 1.0
    ratio = difflib.SequenceMatcher(None, s1, s2).ratio()
    return 1.0 - ratio


# ============================================================
# TEDS (Tree Edit Distance-based Similarity) - Simplified
# ============================================================

def simple_table_similarity(gt_html, pred_html):
    """
    Simplified table similarity based on cell text comparison.
    Returns 0-1 score (1 = perfect match).
    """
    def extract_cells(html_str):
        """Extract cell texts from HTML table."""
        cells = []
        # Simple regex to extract td/th content
        cell_pattern = re.compile(r'<t[dh][^>]*>(.*?)</t[dh]>', re.DOTALL | re.IGNORECASE)
        for match in cell_pattern.finditer(html_str):
            # Strip nested HTML tags
            text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
            cells.append(text)
        return cells

    gt_cells = extract_cells(gt_html)
    pred_cells = extract_cells(pred_html)

    if not gt_cells and not pred_cells:
        return 1.0
    if not gt_cells or not pred_cells:
        return 0.0

    # Compare cell by cell
    max_len = max(len(gt_cells), len(pred_cells))
    matches = 0
    for i in range(min(len(gt_cells), len(pred_cells))):
        ratio = difflib.SequenceMatcher(None, gt_cells[i], pred_cells[i]).ratio()
        matches += ratio

    return matches / max_len


# ============================================================
# Markdown Parser (extract text, formulas, tables from .md)
# ============================================================

def parse_markdown(content):
    """
    Parse markdown content into text blocks, formulas, and tables.
    Simplified version of OmniDocBench's md_tex_filter.
    """
    elements = {
        'text': [],
        'formula': [],
        'table': []
    }

    # Remove image references
    content = re.sub(r'!\[.*?\]\(.*?\)', '', content)
    # Remove markdown code fences
    content = re.sub(r'```.*?```', '', content, flags=re.DOTALL)

    # Extract HTML tables
    table_pattern = re.compile(r'<table.*?>.*?</table>', re.DOTALL | re.IGNORECASE)
    tables = table_pattern.findall(content)
    for t in tables:
        elements['table'].append(t.strip())
    content = table_pattern.sub(' ', content)

    # Extract display formulas ($$...$$)
    formula_pattern = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
    formulas = formula_pattern.findall(content)
    for f in formulas:
        elements['formula'].append(f.strip())
    content = formula_pattern.sub(' ', content)

    # Extract \[...\] formulas
    formula_pattern2 = re.compile(r'\\\[(.*?)\\\]', re.DOTALL)
    formulas2 = formula_pattern2.findall(content)
    for f in formulas2:
        elements['formula'].append(f.strip())
    content = formula_pattern2.sub(' ', content)

    # Remaining text: split by double newlines into paragraphs
    paragraphs = re.split(r'\n\s*\n', content)
    for p in paragraphs:
        p = p.strip()
        # Remove heading markers
        p = re.sub(r'^#{1,6}\s*', '', p)
        p = re.sub(r'\*\*(.*?)\*\*', r'\1', p)  # Remove bold
        p = p.strip()
        if p and len(p) > 3:  # Skip very short fragments
            elements['text'].append(p)

    return elements


# ============================================================
# Matching: GT elements ↔ Pred elements
# ============================================================

def match_elements(gt_list, pred_list):
    """
    Match GT elements to pred elements by content similarity.
    Returns list of (gt_text, pred_text, similarity) tuples.
    """
    if not gt_list or not pred_list:
        return []

    matches = []
    used_pred = set()

    for gt_text in gt_list:
        best_score = -1
        best_idx = -1
        for j, pred_text in enumerate(pred_list):
            if j in used_pred:
                continue
            score = difflib.SequenceMatcher(None, gt_text, pred_text).ratio()
            if score > best_score:
                best_score = score
                best_idx = j

        if best_idx >= 0 and best_score > 0.1:  # minimum threshold
            matches.append((gt_text, pred_list[best_idx], best_score))
            used_pred.add(best_idx)

    return matches


# ============================================================
# Main evaluation logic
# ============================================================

def extract_submission(zip_path, extract_dir):
    """Extract .zip → flat directory of .md files."""
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(extract_dir)

    # Flatten: move all .md files to root
    md_files = []
    for root, dirs, files in os.walk(extract_dir):
        if '__MACOSX' in root:
            continue
        for f in files:
            if f.endswith('.md') and not f.startswith('.'):
                md_files.append(os.path.join(root, f))

    for md_path in md_files:
        dest = os.path.join(extract_dir, os.path.basename(md_path))
        if md_path != dest:
            shutil.move(md_path, dest)

    # Clean subdirectories
    for item in os.listdir(extract_dir):
        item_path = os.path.join(extract_dir, item)
        if os.path.isdir(item_path):
            shutil.rmtree(item_path)

    return [f for f in os.listdir(extract_dir) if f.endswith('.md')]


def evaluate_page(gt_page, pred_content):
    """Evaluate a single page: GT JSON page vs predicted .md content."""
    # Extract GT elements by category
    gt_texts = []
    gt_formulas = []
    gt_tables = []

    sorted_dets = sorted(gt_page.get('layout_dets', []),
                         key=lambda x: x.get('order', 0) or 0)

    for det in sorted_dets:
        cat = det.get('category_type', '')
        if cat in ['text_block', 'title', 'reference', 'code_txt']:
            text = det.get('text', '').strip()
            if text:
                gt_texts.append(text)
        elif cat == 'equation_isolated':
            latex = det.get('latex', '').strip()
            if latex:
                # Clean $$ wrappers
                latex = re.sub(r'^\$\$\s*', '', latex)
                latex = re.sub(r'\s*\$\$$', '', latex)
                gt_formulas.append(latex)
        elif cat == 'table':
            html = det.get('html', '').strip()
            if html:
                gt_tables.append(html)

    # Parse prediction .md
    pred = parse_markdown(pred_content)

    # Score text
    text_scores = []
    text_matches = match_elements(gt_texts, pred['text'])
    for gt, pr, _ in text_matches:
        ed = normalized_edit_distance(gt, pr)
        text_scores.append(ed)

    # Add penalty for unmatched GT texts
    unmatched_gt_text = len(gt_texts) - len(text_matches)
    for _ in range(unmatched_gt_text):
        text_scores.append(1.0)  # worst score for missing

    # Score formulas
    formula_scores = []
    formula_matches = match_elements(gt_formulas, pred['formula'])
    for gt, pr, _ in formula_matches:
        ed = normalized_edit_distance(gt, pr)
        formula_scores.append(ed)

    unmatched_gt_formula = len(gt_formulas) - len(formula_matches)
    for _ in range(unmatched_gt_formula):
        formula_scores.append(1.0)

    # Score tables
    table_scores = []
    table_matches = match_elements(gt_tables, pred['table'])
    for gt, pr, _ in table_matches:
        teds = simple_table_similarity(gt, pr)
        table_scores.append(teds)

    unmatched_gt_table = len(gt_tables) - len(table_matches)
    for _ in range(unmatched_gt_table):
        table_scores.append(0.0)

    return {
        'text_eds': text_scores,
        'formula_eds': formula_scores,
        'table_teds': table_scores,
    }


def run_evaluation(gt_path, pred_dir):
    """Run full evaluation across all pages."""
    with open(gt_path, 'r') as f:
        gt_data = json.load(f)

    all_text_eds = []
    all_formula_eds = []
    all_table_teds = []
    pages_evaluated = 0

    for gt_page in gt_data:
        img_name = gt_page['page_info']['image_path']
        base_name = os.path.splitext(img_name)[0]

        # Find matching .md prediction
        pred_path = os.path.join(pred_dir, base_name + '.md')
        if not os.path.exists(pred_path):
            # Try alternative naming
            pred_path = os.path.join(pred_dir, base_name.replace('.pdf', '') + '.md')
            if not os.path.exists(pred_path):
                print("WARNING: No prediction for {}".format(img_name))
                continue

        with open(pred_path, 'r', encoding='utf-8') as f:
            pred_content = f.read()

        page_result = evaluate_page(gt_page, pred_content)
        all_text_eds.extend(page_result['text_eds'])
        all_formula_eds.extend(page_result['formula_eds'])
        all_table_teds.extend(page_result['table_teds'])
        pages_evaluated += 1

    print("Evaluated {} pages".format(pages_evaluated))

    # Compute averages
    text_ed = sum(all_text_eds) / max(len(all_text_eds), 1)
    formula_ed = sum(all_formula_eds) / max(len(all_formula_eds), 1)
    table_teds = sum(all_table_teds) / max(len(all_table_teds), 1) * 100

    # Formula CDM approximated by (1 - ED) * 100
    formula_cdm = (1.0 - formula_ed) * 100

    # Overall = ((1 - Text_ED) * 100 + Table_TEDS + Formula_CDM) / 3
    text_score = (1.0 - text_ed) * 100
    overall = (text_score + table_teds + formula_cdm) / 3.0

    return {
        "Text_ED": round(text_ed, 4),
        "Table_TEDS": round(table_teds, 2),
        "Formula_CDM": round(formula_cdm, 2),
        "Overall": round(overall, 2)
    }


# ============================================================
# EvalAI entry point
# ============================================================

def evaluate(test_annotation_file, user_submission_file, phase_codename, **kwargs):
    """
    EvalAI evaluation entry point.
    """
    print("Starting DataMFM Evaluation for phase: {}".format(phase_codename))
    print("GT file: {}".format(test_annotation_file))
    print("Submission file: {}".format(user_submission_file))

    output = {}
    tmp_dir = None

    try:
        tmp_dir = tempfile.mkdtemp(prefix="datamfm_eval_")
        pred_dir = os.path.join(tmp_dir, "predictions")
        os.makedirs(pred_dir, exist_ok=True)

        # Extract submission
        if not zipfile.is_zipfile(user_submission_file):
            raise ValueError("Submission must be a .zip file containing .md files")

        md_files = extract_submission(user_submission_file, pred_dir)
        print("Extracted {} .md files from submission".format(len(md_files)))

        if len(md_files) == 0:
            raise ValueError("No .md files found in the submitted .zip")

        if not os.path.exists(test_annotation_file):
            raise ValueError("Ground truth file not found: {}".format(test_annotation_file))

        # Run evaluation
        scores = run_evaluation(test_annotation_file, pred_dir)
        print("Scores: {}".format(json.dumps(scores, indent=2)))

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
            "phase": phase_codename
        })

        print("Evaluation completed successfully for {} phase".format(phase_codename))

    except Exception as e:
        print("Evaluation failed: {}".format(str(e)))
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
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return output
