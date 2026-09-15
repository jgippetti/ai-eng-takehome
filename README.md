# Hecks Takehome Assignment

## Summary

Imagine this: you are an AI engineer at a purely fictitious company named "Hecks",
and you have been put in charge of improving the company's "natural language
question answering" product. This product is a compound AI system built on top
of a large language model with access to some tools.

Your users have provided you with a database (hecks.duckdb, see the zip file),
and your agent should use it to answer their questions!

Additionally, they have provided you with a collection of markdown files that capture
some important business rules for their company.

For the sake of simplicity, your agent will ultimately answer user questions with a SQL
query - this query is submitted via the "submit_answer" tool.

In order to compare you against some other vendors providing similar services, the
customer has given you a pair of evaluation datasets (evaluation/data/evals_easy.json
and evaluation/data/evals_hard.json, respectively).

These datasets are a collection of pairs of the form:

- natural language question
- query whose result defines the expected dataframe

For example, a simple evaluation pair might be:

```bash
prompt: "How many users are there at our company?"
query: "SELECT COUNT(*) FROM our_company.users"
```

The easy set does not require information from the rules files, _but the hard set does_.

To determine how well your agent performs, the queries in the eval will be
executed, and the resulting dataframes will be compared against the dataframe that your
agent's SQL queries returned.

This comparison is "loose" - in your agent's output dataframe,

- column order is ignored (if your agent returns a different order of columns,
  it's still correct)
- column names are ignored (if your agent returns a different name for a column
  with the right values, it's still correct)
- extra columns on the returned dataframe are not penalized (if your agent
  returns extra columns, it's still correct)

Your goal is to build tools and structures for an agent that can reproduce the
appropriate answers to as many of the given HARD questions as possible!

Be careful not to overfit, though! They have a held-out test set that will be
used to evaluate your agent's performance.

## Rules

- You're strongly encouraged to take no more than four hours here. More than
  six hours is out-of-scope.
- You have seven days to complete the take-home; please find time to work on it
  that's compatible with your schedule.
- Feel free to fragment the time over several days if that's preferable for you.
- Please present your work in a format that communicates what you've done
  clearly. We'd love to see two components:
  - Some sort of prose writeup (PDF, document, etc) including communication
    around choices / tradeoffs you made during the course of the exercise, and
    your ultimate conclusions and guidance.
  - A forked version of this repo w/ your code changes.
- Once complete, please email a link to your fork of this repository to your recruiter.

## Getting Started

The duckdb database file is included in this repository via Git LFS as `hecks.duckdb.zip`.
After cloning the repository, you'll need to unzip it:

```bash
unzip hecks.duckdb.zip
```

This will extract `hecks.duckdb` (~635 MB) to the root directory of the repository.

Additionally, you'll need an OpenRouter API Key.
Your recruiter will provision you with a key to use for the week.

Install the dependencies with uv:

```bash
uv sync
```

Once you have the duckdb file and the OpenRouter API Key, you can run the following command to start the agent:

```bash
uv run interactive --api-key YOUR_API_KEY
```

This will start the agent in a REPL-like environment.
You can enter natural language questions, and the agent will respond.
You can exit the REPL-like environment by typing "quit".
You can start a new conversation by typing "reset".

The agent discovers business guidance in two steps: `search_guides` searches guide names,
Markdown headings, and body text, returning only short matching excerpts. Then `read_guide`
loads the complete selected guide. This keeps irrelevant documentation out of the context
while allowing applicable rules to inform schema exploration and the final SQL. The agent uses
the `output-shape` workflow by default, which also preserves useful identity and component
columns when they do not change the requested result grain. The earlier `original`, `baseline`,
`human-workflow`, and `iterative-rules` prompts remain available for comparison; only
`iterative-rules` adds the experimental `record_rules` tool.

## Evaluation

To evaluate your agent, you can run the following command:

```bash
uv run evaluate --api-key YOUR_API_KEY --concurrency 16
```

This will run the agent against the evaluation dataset and report the results.

For quicker iteration, run the first N cases or select specific one-based case numbers:

```bash
uv run evaluate --api-key YOUR_API_KEY --split easy --limit 20
uv run evaluate --api-key YOUR_API_KEY --split easy --cases 5,15,16,19
```

Select a retained prompt experiment with `--prompt` (the default is `output-shape`):

```bash
uv run evaluate --api-key YOUR_API_KEY --split hard --prompt human-workflow
uv run evaluate --api-key YOUR_API_KEY --split hard --cases 15 --prompt iterative-rules
```

The agent only accepts a final answer after that exact SQL has succeeded through `run_query`.
This prevents an untested edit from introducing a syntax error at submission time.

Each run also writes two small files in its run directory:

- `run_config.json` records the prompt, selected cases, concurrency, tools, model, provider,
  reasoning effort, temperature, token and iteration limits, timeout, and context compression.
- `run_summary.json` records pass, mismatch, other-failure, failure-type, pass-rate, and token
  totals for the overall run and each split.

To turn every JSON trace in a run into readable Markdown timelines, provide its split run
directory:

```bash
uv run summarize-eval-logs logs/run_20260911_192231/evals_hard
```

This creates a `summaries` folder containing an index and one report per case. To inspect only
one case, provide its one-based case number:

```bash
uv run summarize-eval-logs logs/run_20260911_192231/evals_hard --case 13
```

The report is written beside the trace as `case_13_summary.md`.

## Goal

Your goal is to get as many of the HARD questions correct as possible by improving the
agent and the codebase. Change whatever helps, but do not alter the evaluation script to
inflate your score.

That might mean tweaking parameters, adding tools, prompt engineering, context
manipulation, or—less realistically, given the timebox—training custom models.

We are looking for a system that is _generally capable_: it should tolerate _arbitrary_
warehouses and _arbitrary_ guidance, not only this database and these markdown files.
Overfitting here misses the point. Do not edit the bundled guide files; in a real setup
you do not control that content, and the agent should handle unfamiliar or shifting rules
without rewriting the customer's guidance.

Likewise, avoid a hand-maintained schema map that is tailored only to this warehouse.
Prefer approaches that discover or infer structure from the database and the docs so the
same patterns still apply when the schema or documentation changes.

Please let us know what you tried, and how far you got!
The implementation we've got here is intentionally pretty bare-bones.
You're free to use any resources you like, including AI assistants, to help you complete the assignment.

## Submission

Once you have completed the assignment, please email a link to your repository to your
recruiter.
