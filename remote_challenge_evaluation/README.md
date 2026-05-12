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
3. Route submissions by EvalAI phase codename: `doc_dev` / `doc_test` use the document parser evaluator, while `chart_dev` / `chart_test` use the chart evaluator.
4. Mount the host md2md evaluator checkout, defaulting to `/root/datamfm-test/OmniDocBench-eval-md2md`.
5. Store all submission artifacts under `/root/datamfm-test/submissions/<task>/<submission_pk>/`.
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
  synthetic/
    chart2csv_gt.jsonl
    chart2summary_gt.jsonl
```

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
