# DataMFM Challenge Submission Format Examples

This folder provides small, format-only examples for the two DataMFM Challenge tracks:

- Document Parsing
- Chart Understanding

These examples are intended to help participants verify file structure, required fields, and data alignment before creating a full EvalAI submission.

Important: the files here are intentionally partial examples. They are not valid full EvalAI submissions. A real EvalAI submission must include every required document or chart prediction for the selected task and split.

## 1. Document Parsing

Select `Task = Document Parsing` on EvalAI.

Submit a `.zip` archive with Markdown files at the archive root. Do not wrap files inside an extra top-level folder.

Expected structure:

```text
submission.zip
├── 00da2f04-2fd9-4ed2-a6e3-0839d06da691.md
├── 09933144-8982-4100-b18c-fa6dfacba7c7.md
├── 0c4c6baa-d003-4b3b-aeb7-f81b6334ab99.md
└── ...
```

Rules:

- File extension: `.md`
- One Markdown file per document.
- Each filename must exactly match the ground-truth document filename.
- The archive should be flat; nested paths are ignored/flattened by the worker and can create filename conflicts.
- The current dev/test worker expects the complete set of document-level Markdown files for the split.
- Preserve text, tables, formulas, and reading order in Markdown.

A partial ground-truth-style snippet is provided at:

```text
document_parsing/ground_truth_sample_partial/00da2f04-2fd9-4ed2-a6e3-0839d06da691.md
```

A matching prediction-format example is provided at:

```text
document_parsing/prediction_example/00da2f04-2fd9-4ed2-a6e3-0839d06da691.md
```

## 2. Chart Understanding

Select `Task = Chart Understanding` on EvalAI.

Submit a `.zip` archive containing JSONL prediction files for both `real` and `synthetic` splits:

```text
submission.zip
├── real/
│   ├── chart2csv_predictions.jsonl
│   └── chart2summary_predictions.jsonl
└── synthetic/
    ├── chart2csv_predictions.jsonl
    └── chart2summary_predictions.jsonl
```

Rules:

- Use newline-delimited JSON (`.jsonl`): exactly one JSON object per line.
- Do not submit a single JSON array.
- Every row must include an image identifier. Recommended field: `imagename`.
- For chart-to-CSV, use `predicted_csv`.
- For chart-to-summary, use `predicted_summary`.
- The worker also accepts `image_name`, `filename`, or `id` for identifiers, and `prediction`/`output` as compatibility aliases, but the explicit fields above are recommended.
- A full submission must include predictions for all expected images in both real and synthetic splits.

Example chart-to-CSV prediction row:

```json
{"imagename": "20150131_inc871_7.png", "predicted_csv": "Date,Aluminium,Zinc,Copper,Nickel,Iron ore\n2011-01,100,100,100,100,100"}
```

Example chart-to-summary prediction row:

```json
{"imagename": "20150131_inc871_7.png", "predicted_summary": "This image is a line chart depicting metal prices over time..."}
```

Partial ground-truth examples are provided in:

```text
chart_understanding/ground_truth_sample_partial/
```

Matching prediction-format examples are provided in:

```text
chart_understanding/prediction_example/
```

## 3. EvalAI Result Columns

EvalAI displays both task groups in the result table:

```text
Doc_Text_ED
Doc_Table_TEDS
Doc_Formula_CDM
Doc_Reading_Order
Doc_Overall
Chart_CSV_Numeric_F1
Chart_CSV_Structural_Score
Chart_Summary_ROUGE_L
Chart_Summary_Numeric_Fact_F1
Chart_Overall
Overall
```

For each submission, only the selected task's columns are meaningful. The other task's columns are placeholders. The shared `Overall` column is the selected task's overall score.
