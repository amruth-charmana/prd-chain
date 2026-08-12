# Dashboard PDF Export

## Background
Sales reps currently have no way to leave a polished artifact with
prospects after a demo call. The only workaround today is a raw
screenshot, which doesn't reflect the product's quality bar.

## Goals
- Let a user export their dashboard's summary view as a clean, shareable PDF
- Ship by end of quarter

## Non-Goals
- Exporting every individual chart (explicitly ruled out — generation time)
- Any new auth/permissions work (explicitly ruled out — export is scoped to the user's own data)

## User Stories
**As a** sales rep, **I want** to export my dashboard summary as a PDF, **so that** I can leave a professional artifact with a prospect after a call.

## Acceptance Criteria
- Export button is available from the summary view
- Output is a PDF, not an image dump of the screen
- Only the summary view is included, not the full chart set
- Export completes without requiring any new authentication step

## Success Metrics
- % of demo calls that end with an export generated
- Time-to-generate stays under a threshold that doesn't disrupt a live call

## Open Risks
- "Look decent" is not a defined visual bar — needs a design pass before engineering estimates a size
- "End of quarter" was stated as a soft deadline, not a hard one — worth confirming with sales before it gets treated as a commitment

---

## Groundedness Review (Stage 3, independent pass)

```json
{
  "groundedness_score": 100,
  "ungrounded_criteria": [],
  "missing_from_intent": [],
  "verdict": "PASS"
}
```

*This file is a hand-written illustration of the expected shape of the
output, not a captured live run — the model's actual wording will vary
each time you run it. Before publishing this repo, replace this file
with a real run: `python -m src.prd_chain --input
examples/sample_input.txt --output out.md`. That's also the more
convincing artifact — an actual timestamped run beats a static mockup
for anyone evaluating whether this really works.*
