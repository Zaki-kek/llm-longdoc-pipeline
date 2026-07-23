# Deployment runbook

`llm-longdoc-pipeline` is a batch library plus CLI. It has no server: you run
it as a one-shot job that turns a brief into a document. This runbook covers
running it locally and in a container, the provider environment schema, where
state lives, and what is out of scope.

## Run locally

```bash
pip install -e ".[docx,yaml]"
python -m pipeline examples/report_from_brief/brief.yaml --out jobs/report
# -> jobs/report/output.md (+ output.docx unless --no-docx)
```

With no provider configured the deterministic mock backend runs, so a fresh
checkout works offline with no key.

## Run in a container

```bash
docker build -t llm-longdoc .
docker run --rm -v "$PWD/jobs:/app/jobs" \
  -e LLM_PROVIDERS=openai_compat \
  -e OPENAI_COMPAT_BASE_URL=https://api.your-gateway.example/v1 \
  -e OPENAI_COMPAT_MODEL=your-model \
  -e OPENAI_COMPAT_API_KEY="$OPENAI_COMPAT_API_KEY" \
  llm-longdoc examples/report_from_brief/brief.yaml --out /app/jobs/report
```

Keys are passed at run time via `-e`; none are baked into the image. See also
[`docker-compose.example.yml`](../docker-compose.example.yml) and
[`.env.example`](../.env.example).

## Programmatic entry (`run()` facade)

The same engine is callable in-process through the typed facade
(see [`pipeline/api.py`](../pipeline/api.py)):

```python
from pipeline import run, RunConfig

result = run(
    {"topic": "Quarterly outlook", "sections": ["Overview", "Analysis"]},
    "jobs/report",
    config=RunConfig(make_docx=True, use_cache=True),
)
print(result.sections, result.metrics)
```

## Provider environment schema

`LLM_PROVIDERS` is a comma-separated list, highest priority first. Each name
maps to three per-provider variables (name upper-cased):

| Variable | Meaning |
|----------|---------|
| `LLM_PROVIDERS` | Ordered provider list, e.g. `primary,backup` |
| `<NAME>_MODEL` | Model id for that provider |
| `<NAME>_BASE_URL` | OpenAI-compatible base URL |
| `<NAME>_API_KEY` | API key (read from env, never committed) |
| `ALLOW_PRIVATE_LLM_URL` | Set to `1` to permit a private/loopback gateway |

The provider order maps directly onto `FallbackClient`: the first provider is
tried first and a failure degrades to the next, so `LLM_PROVIDERS=primary,backup`
uses `backup` only when `primary` fails. Unset (or `mock`) yields the mock.

## State, checkpoints and auto-resume

All run state lives under the job/output directory (`--out`), including
`state.json`. Every accepted section is checkpointed atomically, so auto-resume
is simply re-running the same command with the same `--out`: sections already
recorded are skipped and only the remainder is generated. Mount that directory
(for example `./jobs:/app/jobs`) so checkpoints survive a container restart.
The checkpoint design is described in
[`docs/decisions/0001-file-checkpoint-store.md`](decisions/0001-file-checkpoint-store.md).

## Out of scope

- No model training and no fine-tuning.
- No model serving / inference endpoint - this drives external providers, it
  does not host a model.
- Single-host checkpoint store only; there is no distributed or multi-node
  state coordination.
