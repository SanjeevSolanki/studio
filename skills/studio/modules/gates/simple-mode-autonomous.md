# Autonomous Mode Branch

```pdsl
UNIT SimpleModeAutonomous
PURPOSE: The default interaction mode — run autonomously, resolving an eligible gate from the approved plan instead of asking, while every validator, prerequisite, hard gate, and closing audit still runs exactly as in any other mode.
WHEN:
  - REQUIRE SIMPLE_MODE == normal
DO:
  - REQUIRE SIMPLE_MODE == normal
RULES:
  - ALWAYS announce the active autonomous mode, and that the user may say "change mode" to switch, before the first autonomous resolution in the session; NEVER announce it after, or in the same breath as, reporting a resolution
  - ALWAYS resolve an eligible gate — one whose declared TYPE is `confirmation` or `decision` — by taking the one valid original option the approved plan's `[[gate_decisions]]` answers for that gate's declared KEY by exact match, and report briefly which option was taken and that it came from the plan
  - NEVER resolve a gate whose declared TYPE is `blocking` or undeclared, or one the plan does not answer for its declared key: a blocking gate is passable only by a fresh explicit user authorisation, and an unanswered or undeclared gate is asked, never guessed
  - ALWAYS keep every underlying rule, prerequisite, menu, wait, hard stop, validation gate, review-fix approval gate, plan approval, GitCommitModeGate, SubAgentDispatch, and terminal shape active — autonomy changes who answers an eligible question, never what gets checked
  - NEVER add assistant-mode explanations or narration while SIMPLE_MODE == normal
```
