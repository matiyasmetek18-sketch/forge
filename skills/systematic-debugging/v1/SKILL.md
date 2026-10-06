# Systematic Debugging (v1)

Use this procedure when repairing a failing software behavior.

1. **Reproduce.** Establish the observed failure with the smallest relevant command or example before editing.
2. **Localize.** Trace the failing path and narrow it to the smallest plausible component or interaction. Inspect existing behavior and contracts first.
3. **Hypothesize.** State a root cause that explains the evidence. Keep alternative explanations only while they remain plausible.
4. **Discriminate.** Choose the cheapest useful inspection or test that separates those explanations. Stop exploring once the cause is sufficiently supported.
5. **Fix.** Make the smallest justified source change that repairs the cause, not a patch that merely hides the symptom. Preserve intended external behavior; avoid broad rewrites.
6. **Verify locally.** Re-run the original failure and focused edge cases.
7. **Verify globally.** Run relevant regression tests and check adjacent behavior.
8. **Review.** Inspect the final diff for unrelated edits, overfitting, test tampering, unnecessary complexity, and regressions.

Do not change tests just to make a failure disappear. Let observed behavior and the requested contract, not speculative edits, guide the repair. Confirm the actual requested behavior before declaring success.
