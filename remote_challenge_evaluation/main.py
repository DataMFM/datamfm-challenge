import json
import os
import time
import traceback
from pathlib import Path
from urllib.parse import urlparse

import requests

from eval_ai_interface import EvalAI_Interface
from evaluate import evaluate


auth_token = os.environ["AUTH_TOKEN"]
evalai_api_server = os.environ["API_SERVER"]
queue_name = os.environ["QUEUE_NAME"]
challenge_pk = os.environ["CHALLENGE_PK"]
save_dir = Path(os.environ.get("SAVE_DIR", "/root/datamfm-test/downloads"))
poll_interval_sec = int(os.environ.get("POLL_INTERVAL_SEC", "60"))


def download(submission, save_dir):
    save_dir.mkdir(parents=True, exist_ok=True)
    url = submission["input_file"]
    response = requests.get(url, timeout=300)
    response.raise_for_status()
    parsed_name = os.path.basename(urlparse(url).path) or f"submission_{submission.get('id') or submission.get('pk')}.zip"
    submission_file_path = save_dir / parsed_name
    with open(submission_file_path, "wb") as f:
        f.write(response.content)
    return str(submission_file_path)


def update_running(evalai, submission_pk):
    evalai.update_submission_status({
        "submission": submission_pk,
        "submission_status": "RUNNING",
    })


def update_failed(evalai, phase_pk, submission_pk, submission_error, stdout="", metadata=""):
    evalai.update_submission_data({
        "challenge_phase": phase_pk,
        "submission": submission_pk,
        "stdout": stdout[-12000:],
        "stderr": submission_error[-12000:],
        "submission_status": "FAILED",
        "metadata": metadata,
    })


def update_finished(evalai, phase_pk, submission_pk, result, submission_error="", stdout="", metadata=""):
    evalai.update_submission_data({
        "challenge_phase": phase_pk,
        "submission": submission_pk,
        "stdout": stdout[-12000:],
        "stderr": submission_error[-12000:],
        "submission_status": "FINISHED",
        "result": result,
        "metadata": metadata,
    })


def process_message(evalai, message):
    message_body = message.get("body") or {}
    receipt_handle = message.get("receipt_handle")
    if not message_body:
        return

    submission_pk = message_body.get("submission_pk")
    phase_pk = message_body.get("phase_pk")
    if not submission_pk or not phase_pk:
        if receipt_handle:
            evalai.delete_message_from_sqs_queue(receipt_handle)
        return

    submission = evalai.get_submission_by_pk(submission_pk)
    challenge_phase = evalai.get_challenge_phase_by_pk(phase_pk)
    status = submission.get("status")
    if status in {"finished", "failed", "cancelled"}:
        if receipt_handle:
            evalai.delete_message_from_sqs_queue(receipt_handle)
        return

    try:
        if status == "submitted":
            update_running(evalai, submission_pk)
        submission_file_path = download(submission, save_dir)
        submission_metadata = dict(submission)
        submission_metadata.update({
            "submission_pk": submission_pk,
            "phase_pk": phase_pk,
            "challenge_phase": challenge_phase,
        })
        results = evaluate(
            submission_file_path,
            challenge_phase["codename"],
            submission_metadata=submission_metadata,
        )
        if results.get("submission_status") == "FAILED":
            update_failed(
                evalai,
                phase_pk,
                submission_pk,
                results.get("stderr", "Evaluation failed"),
                stdout=results.get("stdout", ""),
                metadata=results.get("submission_metadata", ""),
            )
        else:
            leaderboard_result = results.get("leaderboard_result", results.get("submission_result", results["result"]))
            update_finished(
                evalai,
                phase_pk,
                submission_pk,
                json.dumps(leaderboard_result),
                submission_error=results.get("stderr", ""),
                stdout=results.get("stdout", ""),
                metadata=results.get("submission_metadata", ""),
            )
    except Exception as exc:
        metadata = json.dumps({
            "submission_pk": submission_pk,
            "phase_pk": phase_pk,
            "error": str(exc),
        })
        update_failed(
            evalai,
            phase_pk,
            submission_pk,
            str(exc),
            stdout=traceback.format_exc(),
            metadata=metadata,
        )
    finally:
        if receipt_handle:
            evalai.delete_message_from_sqs_queue(receipt_handle)


if __name__ == "__main__":
    evalai = EvalAI_Interface(auth_token, evalai_api_server, queue_name, challenge_pk)
    while True:
        message = evalai.get_message_from_sqs_queue()
        process_message(evalai, message)
        time.sleep(poll_interval_sec)
