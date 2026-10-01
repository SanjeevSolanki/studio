# Simple Mode Gate

```pdsl
UNIT SimpleModeGate
PURPOSE: Run autonomously by default, announcing the active mode rather than asking, then apply any mode-specific session setup. The user may switch with "change mode".
STATE:
  SET SIMPLE_MODE: unset | simple | normal | guided | debug (default normal, scope session)
  SET SIMPLE_MODE_BRAVE_NEW_WORLD_DECISION: unset | enable | skip (default unset, scope session)
  SET ASSISTANT_MODE_NAME: string | unset (default unset, scope session)
WHEN:
  REQUIRE a non-exempt cf workflow is loading
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/simple-mode-simple.md WHEN SIMPLE_MODE == simple
  CONTINUE SimpleModeSimpleEntry WHEN SIMPLE_MODE == simple
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/simple-mode-debug.md WHEN SIMPLE_MODE == debug
  CONTINUE SimpleModeDebug WHEN SIMPLE_MODE == debug
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/simple-mode-autonomous.md WHEN SIMPLE_MODE == normal
  CONTINUE SimpleModeAutonomous WHEN SIMPLE_MODE == normal
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/simple-mode-guided.md WHEN SIMPLE_MODE == guided
  CONTINUE SimpleModeGuided WHEN SIMPLE_MODE == guided
RULES:
  ALWAYS run before workflow-specific routing, discovery, planning, validation, authoring, review, or writes in non-exempt workflows
  ALWAYS default to the autonomous mode without asking; announce it, and that "change mode" switches, before the first autonomous resolution
  ALWAYS remember the selected interaction mode for the whole session
  ALWAYS remember the Brave New World opt-in or skip decision for the whole session after the user answers it
  NEVER run for `cf-debug-prompts` or `cf-help`
MENU SimpleModeChoice
TITLE: Choose interaction mode for this session — reply with a number. You can change mode any time by saying "change mode".
TYPE: confirmation
KEY: interaction_mode
OPTIONS:
  1 assistant — explains each step, why it is happening, and which path is recommended -> SET SIMPLE_MODE = simple; LOAD {cf-studio-path}/.core/skills/studio/modules/gates/simple-mode-simple.md; CONTINUE SimpleModeSimpleEntry
  2 normal — run autonomously: resolve routine decisions from the approved plan and ask only where it must (suggested) -> SET SIMPLE_MODE = normal; LOAD {cf-studio-path}/.core/skills/studio/modules/gates/simple-mode-autonomous.md; CONTINUE SimpleModeAutonomous
  3 debug — debugger overlay in run mode, for workflow development only -> SET SIMPLE_MODE = debug; LOAD {cf-studio-path}/.core/skills/studio/modules/gates/simple-mode-debug.md; CONTINUE SimpleModeDebug
  4 guided — today's step-by-step behavior; every menu, gate, and stop is shown -> SET SIMPLE_MODE = guided; LOAD {cf-studio-path}/.core/skills/studio/modules/gates/simple-mode-guided.md; CONTINUE SimpleModeGuided
  INVALID -> EMIT_MENU SimpleModeChoice
```

```pdsl
UNIT SimpleModeChangeTrigger
PURPOSE: Recognize the one declared mode-change trigger and re-open mode selection without resetting any other session state.
WHEN:
  REQUIRE SIMPLE_MODE != unset
  REQUIRE the user's message, after trimming leading/trailing whitespace and folding ASCII case, equals exactly the phrase "change mode" with no other leading, trailing, or embedded characters (not a paraphrase, synonym, punctuation-padded variant, or superset phrase)
DO:
  EMIT_MENU SimpleModeChoice
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS treat "change mode" as the sole mode-change trigger; NEVER treat semantically similar phrases, synonyms, or partial matches as satisfying it.
```
