"""
prd-chain — a three-stage LLM prompt chain that turns a raw idea
into a scored, production-ready PRD.

Stage 1  EXTRACT   raw text  ->  structured intent (JSON)
Stage 2  EXPAND     intent    ->  full PRD (markdown)
Stage 3  SCORE      intent + PRD  ->  groundedness score (JSON)

The core pattern this repo demonstrates: Stage 3 never sees Stage 2's
reasoning or prompt — only the raw intent and the final PRD text. That
separation is what catches hallucinated acceptance criteria that a
single "write me a PRD and check your work" call would miss, because
a model grading its own reasoning tends to agree with itself.

Usage:
    python -m src.prd_chain --input examples/sample_input.txt --output out.md

Requires:
    ANTHROPIC_API_KEY set in the environment (see .env.example)
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass

import anthropic
from anthropic import APIConnectionError, APIStatusError, RateLimitError

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

# Claude Sonnet 5 (claude-sonnet-5) runs adaptive thinking on by default and
# cannot be disabled; manual extended-thinking config and non-default
# temperature/top_p/top_k all return a 400 error on this model. We
# deliberately never set those params below — this isn't an omission.
# (Verified against Anthropic's release notes, Aug 2026.)
EXTRACT_MAX_TOKENS = 1024
EXPAND_MAX_TOKENS = 8000
SCORE_MAX_TOKENS = 2000

RETRYABLE_ERRORS = (RateLimitError, APIConnectionError)


@dataclass
class ChainResult:
    intent: dict
    prd_markdown: str
    score: dict


def _client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env, "
            "add your key, and `export $(cat .env | xargs)` before running."
        )
    return anthropic.Anthropic(api_key=api_key)


def _call(client: anthropic.Anthropic, system: str, user: str, model: str,
          max_tokens: int, max_retries: int = 3) -> str:
    """Call the API with exponential backoff on rate limits, connection
    errors, and 5xx responses. Does not retry on 4xx (bad request) —
    that's a bug in our prompt, not a transient failure."""
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return "".join(block.text for block in resp.content if block.type == "text")
        except RETRYABLE_ERRORS as e:
            last_err = e
        except APIStatusError as e:
            if e.status_code < 500:
                raise
            last_err = e
        if attempt < max_retries - 1:
            wait = 2 ** attempt
            print(f"[retry] {type(last_err).__name__}, waiting {wait}s "
                  f"(attempt {attempt + 1}/{max_retries})", file=sys.stderr)
            time.sleep(wait)
    raise last_err


def _parse_json_block(text: str) -> dict:
    """Strip markdown code fences if present, then fall back to extracting
    the outermost {...} span in case the model added stray prose despite
    instructions not to."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(cleaned[start:end + 1])
        raise


def _call_json(client: anthropic.Anthropic, system: str, user: str, model: str,
                max_tokens: int, max_attempts: int = 2) -> dict:
    """Call the API expecting JSON back. If the response doesn't parse,
    retry once with a stricter instruction appended rather than failing
    the whole chain on a formatting slip."""
    for attempt in range(max_attempts):
        raw = _call(client, system, user, model, max_tokens=max_tokens)
        try:
            return _parse_json_block(raw)
        except json.JSONDecodeError as e:
            if attempt == max_attempts - 1:
                raise ValueError(
                    f"Model did not return valid JSON after {max_attempts} "
                    f"attempts. Last response:\n{raw}"
                ) from e
            print(f"[retry] response wasn't valid JSON, retrying with a "
                  f"stricter instruction", file=sys.stderr)
            system = system + ("\n\nIMPORTANT: your previous response was not "
                                "valid JSON. Return ONLY raw JSON — no prose, "
                                "no markdown fences, no explanation.")


# ---------------------------------------------------------------------------
# Stage 1 — EXTRACT
# ---------------------------------------------------------------------------

EXTRACT_SYSTEM = """You extract structured product intent from raw, messy \
input (a Slack message, a rambling feature request, meeting notes). \
Return ONLY valid JSON, no prose, no markdown fences, matching this shape:

{
  "problem": "the actual problem being solved, in one sentence",
  "target_users": ["who this is for"],
  "primary_goal": "the single most important outcome",
  "constraints": ["explicit constraints mentioned: time, tech, budget, compliance"],
  "explicit_non_goals": ["anything the input explicitly rules out or says is NOT in scope"],
  "open_questions": ["ambiguities in the input you had to guess at"]
}

If the input doesn't state something, use an empty list or a short \
"not specified" string — never invent detail that isn't in the input. \
This JSON is the ONLY source of truth Stage 2 will use."""


def extract_intent(client: anthropic.Anthropic, raw_input: str, model: str) -> dict:
    return _call_json(client, EXTRACT_SYSTEM, raw_input, model, max_tokens=EXTRACT_MAX_TOKENS)


# ---------------------------------------------------------------------------
# Stage 2 — EXPAND
# ---------------------------------------------------------------------------

EXPAND_SYSTEM = """You are a senior PM writing a production PRD. You will \
be given a structured intent JSON object — that JSON is your ONLY source \
of ground truth. Do not introduce features, users, or requirements that \
aren't traceable to it.

Write a complete PRD in markdown with these sections:
# <Title>
## Background
## Goals
## Non-Goals
## User Stories
(As a <user>, I want <goal>, so that <outcome> — one per story)
## Acceptance Criteria
(Grouped under each user story. Each criterion must be testable.)
## Success Metrics
## Open Risks
(Pull directly from open_questions in the intent, plus any you notice)

Every acceptance criterion must be traceable back to the intent JSON. \
If you're tempted to add a criterion the intent doesn't support, put it \
in Open Risks as a question instead — don't invent it as a requirement."""


def generate_prd(client: anthropic.Anthropic, intent: dict, model: str) -> str:
    user = f"Intent:\n{json.dumps(intent, indent=2)}\n\nWrite the PRD."
    return _call(client, EXPAND_SYSTEM, user, model, max_tokens=EXPAND_MAX_TOKENS)


# ---------------------------------------------------------------------------
# Stage 3 — SCORE (blind — never sees Stage 2's prompt or reasoning)
# ---------------------------------------------------------------------------

SCORE_SYSTEM = """You are an independent reviewer. You were NOT involved in \
writing this PRD and have no access to the reasoning behind it — you only \
have the original intent and the final PRD text below. Your job is to catch \
hallucinated requirements: acceptance criteria or user stories that sound \
plausible but aren't actually grounded in the stated intent.

Return ONLY valid JSON:
{
  "groundedness_score": <0-100, what % of acceptance criteria trace back to intent>,
  "ungrounded_criteria": ["quote any acceptance criterion not supported by intent"],
  "missing_from_intent": ["anything in intent.constraints or primary_goal that the PRD dropped"],
  "verdict": "PASS if groundedness_score >= 85 and ungrounded_criteria is empty, else REVIEW"
}"""


def score_prd(client: anthropic.Anthropic, intent: dict, prd_markdown: str, model: str) -> dict:
    user = (
        f"Original intent:\n{json.dumps(intent, indent=2)}\n\n"
        f"PRD to review:\n{prd_markdown}"
    )
    return _call_json(client, SCORE_SYSTEM, user, model, max_tokens=SCORE_MAX_TOKENS)


# ---------------------------------------------------------------------------
# Chain
# ---------------------------------------------------------------------------

def run_chain(raw_input: str, model: str = DEFAULT_MODEL, skip_score: bool = False) -> ChainResult:
    client = _client()
    intent = extract_intent(client, raw_input, model)
    prd = generate_prd(client, intent, model)
    score = {} if skip_score else score_prd(client, intent, prd, model)
    return ChainResult(intent=intent, prd_markdown=prd, score=score)


def main():
    parser = argparse.ArgumentParser(description="Three-stage PRD generation chain.")
    parser.add_argument("--input", required=True, help="Path to a text file with the raw idea/request")
    parser.add_argument("--output", required=True, help="Path to write the final PRD markdown")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--skip-score", action="store_true", help="Skip Stage 3 (faster, no groundedness check)")
    args = parser.parse_args()

    with open(args.input, "r") as f:
        raw_input = f.read()

    result = run_chain(raw_input, model=args.model, skip_score=args.skip_score)

    with open(args.output, "w") as f:
        f.write(result.prd_markdown)
        if result.score:
            f.write("\n\n---\n\n## Groundedness Review (Stage 3, independent pass)\n\n")
            f.write(f"```json\n{json.dumps(result.score, indent=2)}\n```\n")

    print(f"Intent extracted: {json.dumps(result.intent, indent=2)}", file=sys.stderr)
    if result.score:
        verdict = result.score.get("verdict", "UNKNOWN")
        print(f"\nGroundedness verdict: {verdict}", file=sys.stderr)
        if verdict != "PASS":
            print(f"Flagged: {result.score.get('ungrounded_criteria')}", file=sys.stderr)
    print(f"\nPRD written to {args.output}")


if __name__ == "__main__":
    main()
