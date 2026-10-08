# Final Benchmark Independence Audit

The final set was designed from general debugging families, not from pilot
outcomes or agent failures. No final task reuses a pilot repository, statement,
solution, or bug mechanism. The three smoke-only tasks are excluded from final
evidence.

| Task | Family | Bug mechanism | Material distinction from pilot | Grading signal | Ambiguity risk | Leakage / hint risk |
| --- | --- | --- | --- | --- | --- | --- |
| `relative_key` | input/validation | path-segment policy is checked incompletely before normalization | Not scalar numeric validation or comma-list parsing | traversal, empty-segment, absolute, and backslash cases | Low: accepted grammar is explicit | Low: statement gives policy, not validation structure |
| `typed_payload` | input/validation | mapping schema accepts wrong exact types and unknown keys | Structured typed mapping, unlike pilot text parsers | defaults plus exact-type and unknown-key cases | Low | Low |
| `money_amount` | input/validation | floating conversion accepts noncanonical forms and loses fixed-point semantics | Fixed-point lexical/representation boundary, not limit or tag parsing | exact cents, canonical syntax, bounds | Low | Low |
| `batch_atomicity` | state/mutation | failed multi-step update leaves partial state | Transactional commit/rollback, not aliasing or callback-list mutation | state equality after late failures | Low | Low |
| `nested_override` | state/mutation | nested context restoration shares one previous-value slot | Dynamic-scope nesting and exception restoration, not collection mutation | inner/outer restoration and propagation | Low | Low |
| `lru_refresh` | state/mutation | successful access/update fails to change recency | Ordered cache state machine, not snapshot ownership or event membership | deterministic eviction after get/update | Low | Low |
| `quota_apportion` | algorithm/logic | independent rounding violates conserved integer total | Proportional integer allocation, not interval predicates or graph search | exact total and deterministic remainder ties | Low | Low: allocation rule is the public contract |
| `wildcard_match` | algorithm/logic | local wildcard handling fails globally interacting matches | String-language matching, not routing or overlap logic | positive/negative multi-wildcard cases | Medium: several valid algorithms exist, same contract | Low |
| `stable_topk` | algorithm/logic | secondary sort reverses stable input order on ties | Stable selection, not graph or interval reasoning | exact ranked identities and immutability | Low | Low |
| `etag_revalidation` | integration/API boundary | status-specific response semantics are conflated | HTTP cache revalidation, not pagination termination or timezone conversion | 200 refresh, 304 reuse, invalid status | Low | Low |
| `partial_writer` | integration/API boundary | adapter assumes one write consumes all bytes | Partial-I/O protocol boundary, unlike pilot API page/time adapters | byte-for-byte sink state and zero progress | Low | Low |
| `stream_decode` | integration/API boundary | decoding each transport chunk independently breaks code points | Incremental byte/text boundary, not cursor or time normalization | split multibyte, malformed, incomplete input | Low | Low |
| `cleanup_precedence` | error/edge | cleanup failure masks the primary action failure | Competing exception precedence, not retry classification or fallback scope | exact raised exception and close state | Medium: precedence is explicitly stated | Low |
| `memoized_failure` | error/edge | preinserted placeholder survives failed computation | Failure-safe cache publication, not retries or config fallback | absence after failure, retry, cached `None` | Low | Low |
| `explicit_timeout` | error/edge | truthiness conflates explicit zero with omission | Sentinel/zero semantics, not missing-file fallback or exception scope | zero/default/type/range cases | Low | Low |

Audit result: **PASS**. No task is a copy, rename, parameter variation, or
pilot-failure derivative. `wildcard_match` and `cleanup_precedence` have modest
interpretive breadth, but their observable contracts are explicit and their
graders accept any implementation satisfying those contracts.
