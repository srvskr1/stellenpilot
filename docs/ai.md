# The AI

## What the AI does for you

* **Reads your CV.** Drop a PDF or Word file and it becomes a structured profile. A CV with clear headings is sorted in about a second, without any AI; for other layouts the AI only points at line numbers, so even a laptop needs just a minute or two. Every word is copied from your CV, and anything left out is flagged.
* **Scores every job** from 0 to 100 with a one line reason and the honest gaps (for example "asks for dbt, which you are still learning").
* **Understands German job ads.** It finds the German level an ad really needs (A1 to C2, from phrases like "verhandlungssicher" or "gute Deutschkenntnisse"), compares it with yours, and writes an English summary of every German ad.
* **Tailors your CV.** It picks and orders the experience, projects and skills from your profile that matter most for this job, and chooses the best fitting headline. Four layouts: Modern (the default, dates on the right), Classic, Compact, or a German Lebenslauf with dates first. Each job gets one short folder: the PDFs to send on top, the Word files and your gap notes in `edit`.
* **Writes the cover letter** in natural language for that company and role, plus a short report: what the ad asks for, what you cover, and which gaps to be honest about. German letters only if your German is B2 or better.
* **Prepares interviews** with likely questions and questions to ask them, and runs a mock interview where you practise your answers and get feedback from your own CV.
* **Learns your taste.** Mark jobs as a good match or not for you, and the next search leans toward what you liked.
* **Speaks English and German.** Pick the dashboard language in the first setup step or under Settings, Language. Automatic follows your browser. Your CVs and cover letters keep their own language setting.

## Truthful by design

A job assistant that invents experience gets people into trouble. Stellenpilot has a **truth guard**: any generated sentence that mentions a number, a tool or a language level your profile does not back up is rejected and replaced with safe text. Skills in a group called "Learning" (or "Lernen") are never presented as experience. The AI rephrases and selects; it never adds facts.

## Measured, not assumed

`stellenpilot eval` checks how well the scores rank the jobs you labeled (thumbs, interviews, or a sheet you fill in), and compares the stored score, keyword scoring and any AI you name: Spearman correlation, AUC, precision at 10, and how many good jobs pass `min_match`. Use it to pick a model and a threshold on your own data. See [docs/evaluation.md](https://github.com/srvskr1/stellenpilot/blob/main/docs/evaluation.md)

First results on 28 real jobs: AUC 0.73 for the stored score and 0.75 for keywords, and 9 of the top 10 were jobs worth applying to. The built-in AI does not beat keywords yet, and the default `min_match` of 70 skips most good jobs. Full numbers and limits in [docs/results.md](https://github.com/srvskr1/stellenpilot/blob/main/docs/results.md)

## Choose your AI

| | Built-in AI | Ollama, LM Studio, llama.cpp | Claude or OpenAI | No AI |
|---|---|---|---|---|
| Setup | one **Download** button | install the app, pull a model | paste an API key | nothing |
| Cost | free | free | a few cents a day | free |
| Privacy | stays on your computer | stays on your computer | CV and ads go to the provider | stays on your computer |
| Writing | good | depends on the model | best | templates |
| Speed | slower (see below) | depends on your computer | fast | instant |

**Built-in AI** is the default for new users. Pick it in setup or in **Settings, AI model** and press **Download**. Stellenpilot downloads the [llama.cpp](https://github.com/ggml-org/llama.cpp) engine and an open Qwen3.5 model (Apache 2.0) once, into `~/.stellenpilot/ai`. It starts by itself when a search needs it and stops when the search is done.

| model | download | memory | writing |
|---|---|---|---|
| Standard: Qwen3.5 4B (default) | 2.7 GB | about 6 GB free | better |
| Light: Qwen3.5 2B | 1.3 GB | runs with 8 GB in total | simpler, about twice as fast |

**How fast is it?** It runs on your processor, so it is slower than Claude, but free and private:

* Standard on a typical laptop: about 20 to 40 seconds to score one job, and 1 to 2 minutes for a CV with its cover letter. Light is about twice as fast.
* To keep searches short, an AI on your own computer reads the 20 most promising new jobs of each search (picked by keywords); the others keep a keyword score. Change it with `max_ai_jobs` under `[llm]`.
* A daily search with the AI takes about 10 to 20 minutes with Standard, or 5 to 10 with Light, in the background. Without AI it takes a minute or two.
* Measured on our small test server with only 2 processor cores: Standard needed 67 seconds per job and 2 minutes per CV and letter; Light 32 seconds and about 1 minute. Older laptops can be that slow; newer ones and Macs with Apple chips are faster.
* After the download, **Test speed** in Settings measures your own computer.

The laptop figures are estimates from published CPU benchmarks for these model sizes, not measured on every computer.

<details>
<summary><b>Using your own local model or a cloud API</b></summary>

Set `[llm]` in `config.toml`, or choose it in **Settings, AI model**:

| provider | what you need | notes |
|---|---|---|
| `builtin` | press Download once in Settings | Local and free, set up by Stellenpilot. `model = "standard"` or `"light"`. |
| `ollama` | Ollama running, a pulled model | Local and free. |
| `lmstudio` | LM Studio with its server started | Local and free. |
| `llamacpp`, `vllm`, `local` | a running server | Any OpenAI compatible local server. |
| `anthropic` | `ANTHROPIC_API_KEY` in `.env` | Claude through the Anthropic API. |
| `openai` | `OPENAI_API_KEY` in `.env` | OpenAI API. |
| `none` | nothing | Keyword scoring and template letters. |

Which local model for Ollama or LM Studio? Pick an instruction tuned version, because the tool asks for JSON answers.

| your computer | try | download |
|---|---|---|
| 8 GB RAM, no GPU | `ministral-3:3b` or `qwen3.5:2b`. Expect rougher scores and shorter letters. | about 3 GB |
| 16 GB RAM, or a GPU with 8 GB | `qwen3.5:4b` (default pick), or `ministral-3:8b` if many of your ads are in German | 4 to 6 GB |
| GPU with 16 GB or more | `qwen3.5:9b` or `gemma4:12b` | 7 to 9 GB |

Why these (checked on their model cards, October 2026): all are Apache 2.0, run in Ollama, and handle JSON well. Qwen3.5 covers 201 languages; Ministral 3 lists German among its main languages and is built for JSON output; Gemma 4 is Google's newest small family. Qwen3.5 and Gemma 4 can "think" before answering, which makes them slow; Stellenpilot switches that off for Ollama (set `think = true` under `[llm]` to turn it back on).

What we saw in testing with a very small model (Qwen2.5 1.5B on 2 CPU cores): the pipeline worked end to end, the German check and the truth guard did their job, and the cover letter stayed truthful. But the model gave every job the same score and wrote a two sentence letter, and each answer took about a minute. Small models are fine for trying the setup, not for real use.

Full setup for Ollama, LM Studio, llama.cpp, vLLM and Docker, plus speed tips and troubleshooting: [docs/local-llm.md](https://github.com/srvskr1/stellenpilot/blob/main/docs/local-llm.md), and run `stellenpilot doctor` to check that your model server is reachable and the model is installed.

</details>


[Back to the README](https://github.com/srvskr1/stellenpilot#readme)
