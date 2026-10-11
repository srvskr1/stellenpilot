# Use a local AI model

With a local model, scoring, CV planning, cover letters and interview prep run on your own computer. Nothing is sent to an AI company and there is no API cost. The truth guard checks local output exactly like cloud output, so a weaker model can make your documents plainer, but not less honest.

## Option 1: Ollama (easiest)

1. Install Ollama from https://ollama.com (Windows, macOS, Linux).
2. Download a model, for example:
   ```bash
   ollama pull qwen2.5:7b
   ```
3. In `config.toml`:
   ```toml
   [llm]
   provider = "ollama"
   model = "qwen2.5:7b"
   ```
4. Check: `stellenpilot doctor` should say `model qwen2.5:7b ready`.

The Ollama provider uses Ollama's own API, which lets the tool set the context window (`num_ctx`, default 8192 tokens). Ollama's default window is smaller, which would silently cut long job ads.

## Option 2: LM Studio

1. Install LM Studio from https://lmstudio.ai and download a model in the app.
2. Open the **Developer** tab and start the server (default port 1234).
3. In `config.toml`:
   ```toml
   [llm]
   provider = "lmstudio"
   model = "the model id shown in LM Studio"
   ```

## Option 3: llama.cpp, vLLM or anything OpenAI compatible

```toml
[llm]
provider = "llamacpp"   # or "vllm", or "local" with base_url set
model = "your-model-name"
# base_url = "http://localhost:8080/v1"
```

Example with the llama.cpp Python server:

```bash
pip install "llama-cpp-python[server]"
python -m llama_cpp.server --model qwen2.5-7b-instruct-q4_k_m.gguf --n_ctx 8192 --port 8080
```

## Which model?

Pick a model trained to follow instructions ("instruct" or "chat" versions). The tool asks for JSON answers, and instruction tuned models handle that much better.

| your computer | try |
|---|---|
| 8 GB RAM, no GPU | a 3B model, e.g. `qwen2.5:3b`. Expect rough scores and short letters. |
| 16 GB RAM, or a GPU with 8 GB | a 7B or 8B model, e.g. `qwen2.5:7b` or `llama3.1:8b` |
| GPU with 16 GB or more | 14B or larger, e.g. `qwen2.5:14b` |

These are starting points, not benchmarks. Look at a few scores and letters and switch models if you are not happy.

What we saw while testing with Qwen2.5 1.5B (the smallest sensible model) on 2 CPU cores: the whole pipeline worked end to end, the fluent German check and the truth guard did their job, and the cover letter stayed truthful. But the model gave every job the same score and wrote a two sentence letter. Use models that small only to try the setup.

## Speed

In our test, a 1.5B model on 2 CPU cores needed about a minute per answer; a run with 4 jobs and 1 tailored CV took about 10 minutes. A 7B model without a GPU is several times slower; with a GPU it is fast. Each tailored job needs several answers (plan, letter, sometimes a retry). Tips:

* Run `stellenpilot run --no-tailor` for a quick scored list, and tailor fewer jobs (`tailor.max_per_run`).
* Schedule the daily run for a time you are not using the computer.
* If answers time out, raise `timeout` in `[llm]`.
* If the model forgets things in long ads, raise `num_ctx` (Ollama) or lower `max_input_chars`.

## Docker

Inside a container, `localhost` is the container itself. Point the tool at your computer instead: uncomment the `environment` and `extra_hosts` lines in `docker-compose.yml`, which set `JOBHUNT_LLM_BASE_URL` to `http://host.docker.internal:11434` (Ollama) or `http://host.docker.internal:1234/v1` (LM Studio).

On Linux, Ollama listens on 127.0.0.1 only by default. To reach it from Docker, start it with `OLLAMA_HOST=0.0.0.0` (only do this on a trusted network or behind a firewall).

## Troubleshooting

| message | fix |
|---|---|
| `NOT reachable` in doctor | Start the server (open the Ollama app, or start LM Studio's server). Check the port. |
| `model ... not found` | `ollama pull <model>`, or copy the exact model id your server lists. |
| `LLM did not return JSON` in the run notes | Use a bigger or instruction tuned model. The run falls back to keyword scoring or template letters for that job and keeps going. |
| very slow | smaller model, fewer jobs per run, or `--no-tailor` |
