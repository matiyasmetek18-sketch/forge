# Pilot Readiness Audit

Verdict: **READY for a six-slot smoke and development pilot**, not final evidence.
Counts: **10 READY, 0 REPAIR, 0 REJECT** after two local prompt repairs.

| Task ID | Family | Leakage | Grader | Difficulty | Distinctness | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| `parse_limit` | Input/validation | Contract only | Types, syntax, bounds | Easy; ceiling risk | Lexical gate | READY |
| `parse_tags` | Input/validation | Contract only | Normalization, empties, duplicates | Easy; ceiling risk | Tokenization | READY |
| `cart_snapshot` | State/mutation | Root-cause hint removed | Input/output ownership, add | Easy-medium | Aliasing | READY |
| `event_dispatch` | State/mutation | Contract only | Add/remove during emit, order | Moderate | Iteration mutation | READY |
| `booking_overlap` | Algorithm/logic | Contract only | Enclosing, partial, adjacent, invalid | Moderate | Interval predicate | READY |
| `weighted_route` | Algorithm/logic | Contract only | Weighted detour, relaxation, cycle | Challenging relative to set | Search ordering | READY |
| `pagination_cursor` | Integration/boundary | API contract only | Empty middle/final, cursor calls | Easy-medium | Pagination termination | READY |
| `timestamp_offset` | Integration/boundary | Time contract only | Positive/negative offsets, naive | Easy-medium | Time-zone conversion | READY |
| `retry_scope` | Error/edge | Exact catch hint removed | Permanent, recovery, exhaustion | Easy; ceiling risk | Retry exception policy | READY |
| `config_fallback` | Error/edge | Contract only | Primary, absent, malformed, bounds | Easy; ceiling risk | Fallback exception policy; overlaps `retry_scope` | READY |

All graders assert behavior rather than a reference diff, protect `tests/`, fail
on the buggy base, and pass on the reference. Validation also checks protected
files and reference hiding. The graders are visible in the task checkout: they
reveal example expected outputs, though no reference patch or implementation is
present. Easy tasks and the two broad-exception cases may show ceiling effects
or correlated outcomes; pilot results should be inspected for those effects,
not promoted to final evidence.

Baseline and skill use the same base tree, task statement, grader, Codex model,
reasoning effort, environment, timeouts, and trial plan; only the final prompt
adds the fixed skill in the skill condition. The skill has no case-specific
filenames, examples, or repair steps. The snapshot has one fresh commit and no
reference history. **Known limit:** an agent that knows the external Forge
checkout path can read source fixtures and references there; the current
sandbox does not prevent that. No stronger isolation is claimed.

Smoke selection, before observing any agent performance: `parse_tags`
(straightforward input validation), `event_dispatch` (moderate state mutation),
and `weighted_route` (comparatively challenging algorithm reasoning).
