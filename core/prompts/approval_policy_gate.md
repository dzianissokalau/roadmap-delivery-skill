# Approval Policy Gate Prompt Fragment

Read `approval_policy.json` and use shared named decisions: `allowed`, `ask`,
`forbidden`. Honor already-scoped human authority; invalid policy grants none.
Missing policy uses conservative defaults. Default completion/stall status-only
pause and explicit false opt-outs resolve through the shared context resolver,
separately from broad runner edit permission. Never-auto operations remain forbidden.
