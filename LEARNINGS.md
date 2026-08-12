# Learnings

*Fill this in after you've actually run the chain against a few real
inputs — including a deliberately vague or scope-creeping one to watch
Stage 3 catch something. This file is the part of the repo that reads
as "I shipped this" instead of "I followed a tutorial," so it's worth
being specific and honest rather than generic.*

Prompts to answer once you've run it:

- What did Stage 3 actually flag, if anything? Paste a real example.
- Did the JSON parsing in `_parse_json_block` ever break on a model
  response you didn't expect? What did you change?
- Where did Stage 1's extraction lose information that mattered —
  did any constraint from the raw input silently disappear?
- What would you change about the system prompts after seeing 5-10
  real runs?
- If you extended this (multi-input batching, a web UI, a different
  model per stage), what forced that change?
