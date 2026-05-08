# Prompt Fidelity Matrix

## Target classification
- Outline Agent: direct Appendix F restoration target
- Literature Review Agent: direct Appendix F restoration target
- Section Writing Agent: direct Appendix F restoration target
- Content Refinement Agent: direct Appendix F restoration target
- Plotting Agent: bounded substitute target; paper delegates core generation to PaperBanana and only publishes the caption-generation addendum in Appendix F
- Discovery worker prompt: split-stage port artifact; no direct single Appendix F prompt exists in the paper because the paper describes search-grounded concurrent discovery procedurally rather than as a standalone prompt block

## Porting note
This repo preserves paper-stage semantics where Appendix F publishes direct prompts, but still appends runtime-level anti-leakage guidance required for secure GPT/Codex execution.
