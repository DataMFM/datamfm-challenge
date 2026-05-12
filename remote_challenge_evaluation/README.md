## How to setup remote challenge evaluation using EvalAI :rocket:
If you are looking for setting up a remote challenge evaluation on EvalAI, then you are at the right place. Follow the instructions given below to get started.

1. Create a challenge on EvalAI using [GitHub](https://github.com/Cloud-CV/EvalAI-Starters#create-challenge-using-github) based challenge creation.

2. Once the challenge is successfully created, please email EvalAI admin on team@cloudcv.org for sending the `challenge_pk` and `queue_name`.

3. After receiving the details from the admin, please add these in the `evaluation_script_starter.py`.

4. Create a new virtual python3 environment for installating the worker requirements.

5. Install the requirements using `pip install -r requirements.txt`.

6. For python3, run the worker using `python -m evaluation_script_starter`
## DataMFM-specific worker setup

For DataMFM, the remote worker is expected to:

1. Run on the host that already has Docker available.
2. Use the patched OmniDocBench runtime image: `omnidocbench-cdm-fixed:v2`.
3. Route submissions by the required EvalAI `Task` submission metadata inside the existing `dev` / `test` phases. `Document Parsing` uses the document parser evaluator, while `Chart Understanding` uses the chart evaluator.
4. Mount the host md2md evaluator checkout, defaulting to `/root/datamfm-test/OmniDocBench-eval-md2md`.
5. Store all submission artifacts under `/root/datamfm-test/submissions/<task>/<submission_pk>/`. This artifact directory includes the original zip, extracted predictions, raw metric results, `scores.json`, and request metadata.
6. Read env vars from `.env.example` or another untracked env file before running.

Important environment variables:

```bash
DOC_EVAL_HOST_DIR=/root/datamfm-test/OmniDocBench-eval-md2md
DOC_GT_MDS_DIR=/root/datamfm-test/OmniDocBench/demo_data/datamfm_20260409/mds
DOC_CDM_WORKERS=4
CHART_GT_ROOT=/root/datamfm-test/chart_gt
DATAMFM_SUBMISSIONS_ROOT=/root/datamfm-test/submissions
```

Chart GT files are expected at:

```text
$CHART_GT_ROOT/
  real/
    chart2csv_gt.jsonl
    chart2summary_gt.jsonl
    hallucination_gt.jsonl
  synthetic/
    chart2csv_gt.jsonl
    chart2summary_gt.jsonl
    hallucination_gt.jsonl
    grounding_gt_hq_v16_final.jsonl
```

The active Chart Understanding evaluator currently scores the chart-to-CSV and chart-to-summary tracks. Its deterministic metrics are aligned with the public ChartNet-Bench evaluator for the leaderboard-facing fields: CSV numeric F1 uses CSV data-cell numeric matching with 1% relative tolerance, CSV structural score uses header column F1 and row-count ratio, summary numeric fact F1 uses summary number matching with 1% relative tolerance, and ROUGE-L uses `rouge_score` with stemming when the package is installed. Hallucination and grounding GT files are stored on the server for future task expansion, but are not routed by the current EvalAI `Chart Understanding` worker path.

Because the existing EvalAI challenge already exists, the worker does not require new EvalAI phases, dataset splits, or leaderboards. The submit page exposes a required `Task` radio field, and the worker records the selected task plus final scores in `submission_metadata.json`. The EvalAI leaderboard remains a document-oriented leaderboard. For chart submissions, the worker saves the real chart scores in the artifact directory and metadata, while returning a document-schema placeholder to EvalAI so chart metrics do not pollute the document leaderboard. Chart ranking can be rendered by an external DataMFM page from the saved chart artifacts or from a periodic export of the worker results.

Example:

```bash
cd remote_challenge_evaluation
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
set -a
source .env
set +a
python main.py
```

## Facing problems in setting up evaluation?

Please feel free to open issues on our [GitHub Repository](https://github.com/Cloud-CV/EvalAI-Starter/issues) or contact us at team@cloudcv.org if you have issues.
