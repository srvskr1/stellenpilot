# Results: how well does the match score rank real jobs?

First measurement with `stellenpilot eval` on my own job search, 15 October 2026.
How the tool works and what each column means is in [evaluation.md](evaluation.md).

## Setup

- **Jobs:** 28 real job ads found on 14 October 2026 by one search (Werkstudent Data and Junior Data Engineer, 50 km
  around Essen, plus remote), from the Bundesagentur für Arbeit, Adzuna, TheirStack and company career pages.
- **Labels:** I labelled every job by hand with 1 (I would apply) or 0 (I would not), on a sheet that
  hides the score. 16 are good, 12 are not, so the base rate is 57%.
- **stored:** the score saved at search time. For 19 jobs that is the built-in AI (Qwen3.5 4B,
  "Standard"); for 9 the saved score came from keyword scoring.
- **keyword:** keyword overlap between the ad and my profile, no AI.
- `min_match` is 70: jobs at or above it get a tailored CV.

## The numbers

```
scorer     spearman    AUC   P@10  recall precision  spread  fail
stored         0.40   0.73    90%     31%      100%    16.1     0
keyword        0.44   0.75    80%     38%       86%    15.2     0
```

AUC 95% interval: stored 0.55 to 0.89, keyword 0.54 to 0.91.

What the threshold does (from `scores.csv`):

| min_match | stored: recall | stored: precision | keyword: recall | keyword: precision |
|---|---|---|---|---|
| 40 | 88% | 67% | 100% | 64% |
| 50 | 56% | 90% | 75% | 71% |
| 60 | 44% | 88% | 62% | 71% |
| 70 | 31% | 100% | 38% | 86% |

## What I take from it

1. **Both scorers rank better than chance, and the top is good.** AUC is around 0.75, and 9 of the 10
   highest stored scores are jobs I would apply to (base rate 57%).
2. **The AI does not beat keywords yet.** The intervals overlap almost completely, so on 28 jobs the
   two are a tie. The AI is much slower than keywords, so it has to win clearly on a bigger sample
   to be worth it.
3. **`min_match = 70` is too strict.** It writes a CV only for jobs that are really good (100% precision)
   but skips 11 of 16 jobs I wanted. At 50 the stored score keeps 90% precision and reaches 56% recall.
   For my search, 50 is the better setting. The default stays 70 until more people have measured it.
4. **The AI's reasons need work.** 18 of its 19 explanations open with a sentence about remote work even
   when that does not matter for the decision. The prompt should ask for the deciding skill first.

## Limits

28 jobs from one person and one search is a first look, not a verdict. The labels are my own judgement,
the stored scores mix AI and keyword, and every job is in data roles in Germany. The next run will have
about 100 jobs labelled over a wider search and compare the Light and Standard models side by side.

To reproduce on your own jobs: `stellenpilot eval --make-sheet`, label the sheet, then
`stellenpilot eval --labels eval/labels.csv`.
