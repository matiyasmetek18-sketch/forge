# Systematic Debugging (v2)

Use the minimum debugging procedure justified by uncertainty. These are decision
points, not a checklist of commands.

1. **Reproduce.** Use the cheapest reliable command or direct example. One
   focused confirmation is enough when the mismatch is already exposed.
2. **Localize.** Trace only until the responsible component and contract are
   clear.
3. **Hypothesize.** Explain the evidence with a root cause. Keep alternatives
   only while they remain plausible.
4. **Discriminate.** Inspect or test again only if the result can change the
   diagnosis or fix. Stop when the cause is sufficiently supported.
5. **Fix.** Make the smallest justified source change that repairs the cause and
   preserves intended behavior. Avoid broad rewrites and never alter tests to
   excuse broken behavior.
6. **Verify locally.** Re-run the original failure or narrowest authoritative
   test. Add an edge check only for a plausible uncovered regression.
7. **Verify broadly.** Run the relevant broader suite once when scope or shared
   behavior creates regression risk. Do not repeat unchanged tests or stack
   redundant test, compile, and lint commands without new information.
8. **Review.** Inspect the final diff for unrelated edits, overfitting, test
   tampering, unnecessary complexity, and regressions.

Combine compatible checks. Skip repeated listing, status, history, cleanup, and
procedural narration when they add no confidence. Report the supported cause,
change, and verification concisely.
