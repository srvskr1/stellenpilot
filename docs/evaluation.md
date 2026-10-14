# Is the scoring any good? `stellenpilot eval`

Every tailored CV Stellenpilot writes depends on one number: the match score. If the model gives
every job 70, or ranks a Senior SAP role above a Werkstudent Python role, the rest of the pipeline
does careful work on the wrong jobs. `stellenpilot eval` measures that, on your own jobs.

## 1. Get labels

A label says whether a job is a good match for you. There are two ways to get them.

**From the dashboard (no extra work).** A thumbs up, or a job that reached an interview or an offer,
counts as good. A thumbs down counts as bad. Rejections are left out by default, because a rejection
says more about the competition than about fit; add `--include-rejected` to count them as bad.

**By hand (better).** Thumbs are biased toward jobs you already looked at, which are the high scores.
For an honest test, label a sample that covers the whole score range:

```bash
stellenpilot eval --make-sheet        # writes eval/labels.csv with 100 jobs
```

The sheet takes jobs evenly from every score band and leaves the scores out, so the old score does
not pull your judgement. Open it in Excel or LibreOffice and fill the `label` column with 1 (I would
apply) or 0 (I would not), or a grade from 0 to 3 if you want more detail. Empty rows are ignored, so
you can label in several sittings. 50 labels give a first look; about 100 let you compare models.

## 2. Run it

```bash
stellenpilot eval --labels eval/labels.csv
stellenpilot eval --labels eval/labels.csv --provider builtin:light --provider ollama:qwen3.5:4b
stellenpilot eval --labels eval/labels.csv --provider anthropic --limit 60   # caps the API cost
```

It always includes the score that was saved at search time (`stored`, free) and keyword scoring
(`keyword`, free), then the AI from `config.toml`, then every `--provider` you add. Use `--no-llm`
to skip the configured AI. A model on your own computer takes as long per job as in a normal search.

The model never sees your thumbs during eval. In a normal search they are part of the prompt, but
here they are the answers, so showing them would be cheating.

## 3. Read the table

```
scorer                        spearman    AUC   P@10  recall precision  spread  fail  s/job
stored                            0.41   0.74    70%     83%       52%    11.2     0    0.0
keyword                           0.22   0.63    50%     95%       38%     9.8     0    0.0
builtin:light                     0.35   0.71    60%     64%       58%    14.0     2   31.5
```

(Example numbers, not a measurement.)

| column | question it answers | good sign |
|---|---|---|
| spearman | Do higher scores go with better labels? From -1 to 1. | above 0.3 |
| AUC | Pick one good and one bad job at random: how often does the good one score higher? 0.5 is a coin flip. | above 0.7 |
| P@10 | Of the 10 highest scored jobs, how many are good? | well above the base rate |
| recall | Of the good jobs, how many reach `tailor.min_match` and get a CV? | high, or you miss jobs |
| precision | Of the jobs that reach `min_match`, how many are good? | high, or you write CVs for nothing |
| spread | How much the scores vary. Near 0 means the model gives everything the same score. | above 8 |
| fail | Jobs where the AI broke and keyword scoring stood in. | 0 |
| s/job | Seconds per job. | |

Recall and precision move against each other as you change `min_match`. If recall is low, lower
`min_match`; if precision is low, raise it. `scores.csv` lists every job with every scorer's score,
so you can try thresholds in a spreadsheet.

When the AUC interval is wide (the report says so), the difference between two models may be luck.
Label more jobs before you switch.

Each run saves `report.json` and `scores.csv` in `eval/<date and time>/`, so you can compare runs
after you change the model, the prompt or your profile.
