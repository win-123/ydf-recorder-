---
name: gov-ydfdev-browser
description: Generate, review, repair, and execute ydf-browser YAML DSL suites for YonDiF template-driven pages in AI-assisted government YDF development workflows. Use when Codex or Claude Code needs to translate a business workflow into ydf-browser DSL, create or update examples/*.yaml, validate DSL, run generated DSL through the installed ydf-browser CLI, diagnose execution failures, configure local request forwarding, or choose semantic steps such as tree.select, query.search, toolbar.click, table_row_action.click, editable_table.fill_row, attachment.upload, import.upload, workflow_result.assert/details/confirm, and table assertions.
---

# gov-ydfdev-browser

Use this skill to produce DSL that drives the installed `ydf-browser` CLI. The DSL describes YonDiF single-bill page semantics; it is not a Playwright selector script and should not contain raw DOM selectors, coordinates, keyboard shortcuts, or generic click/type recipes.

## Ground Rules

- Use the installed `ydf-browser` from `PATH` for DSL authoring, tester regression, and AI business development verification.
- For AI business development verification, follow `references/ai-verification.md`; run this skill's installed helper, which performs contract preflight and invokes the same PATH executable for every observed run.
- Run `ydf-browser doctor` before ordinary first execution. AI verification must run the installed runtime's `doctor --skip-config` contract preflight.
- If `ydf-browser` is not found, ask the user to run the release package runtime installer.
- For ordinary development, read the project `README.md` and `AGENTS.md` when the source repository is available. A frozen AI verification pilot must use only the installed skill, release docs, and installed CLI; do not read or invoke the ydf-browser source checkout.
- Do not depend on other `gov-*` skills or external government-domain toolkits. This skill must work from the bundled references, examples, installed CLI, and test output alone.
- Prefer the modern `suite + cases + steps` shape. Use legacy top-level `steps:` only for tiny throwaway probes or when an existing file already uses it.
- Write component-level semantic steps: `tree.select`, `query.search`, `toolbar.click`, `table_row_action.click`, `form.fill`, and the other operations documented in `references/dsl-reference.md`.
- Include a verification step for every meaningful business effect. For mutating workflows, include cleanup or query-based assertions so reruns remain understandable.
- When a batch workflow shows a result layer, use `workflow_result.assert` followed by `workflow_result.details`/`workflow_result.confirm`; use `notification.assert` for the separate all-success notification path.
- Use `{{random.suffix}}`, `{{random.id_card}}`, `{{random.mobile}}`, or `{{random.bank_card}}` when creating data that must be unique across runs.

## Workflow

1. Identify the requested business effect and its read-back assertion. Obtain tenant, user alias, organization, and fiscal year from the selected environment; example values are not current environment facts. Discover page labels and candidates with the CLI rather than asking the user to enumerate controls. When the user permits arbitrary ordinary test data, choose observed candidates yourself, including structural leaves for leaf-only references, and verify actual acceptance and read-back. Use the opt-in observation and terminal exploration parameters described in Page discovery to obtain leaf candidates; keep exploration out of the final test DSL. If choices change business prerequisites (such as real versus virtual funding, or manual entry versus importing a preceding document), present the observed choices and ask the user before filling dependent fields. Page defaults do not resolve missing business intent; continue read-only discovery while awaiting the answer.
2. Load the smallest needed references:
   - `references/dsl-reference.md` for YAML schema and all supported components.
   - `references/verified-patterns.md` for known stable real-page patterns and examples.
   - `references/execution-guide.md` before running, validating, or troubleshooting DSL.
   - [Page discovery](references/page-discovery.md) before authoring against an unfamiliar page, after a dynamic page change, when choosing business branches or detail editor modes, or when fields, reference values, validation messages, or post-save list states are unknown.
   - `references/ai-verification.md` only when validating a business-code change or Bug fix. Generating a save use case alone is ordinary DSL authoring, even when `--ai-observe` supplies discovery evidence.
3. Run the shortest exploratory DSL that reaches the next unknown page, then read its report's current manifest and binding. Extend the flow only when its next targets have evidence. Reuse examples for DSL shape, replacing their business labels and data with observed facts. Keep new durable suites in `examples/`; use `tmp/` for discovery probes.
4. Generate YAML with stable case metadata: `suite.code`, `suite.name`, `cases[].code`, `cases[].name`, `user`, `default_org`, and `steps`.
5. Validate the DSL parser before a real browser run when practical:

```bash
ydf-browser validate --dsl examples/your_suite.yaml
```

6. Execute generated DSL through the project CLI, headless by default:

```bash
ydf-browser run --dsl examples/your_suite.yaml --headless
```

7. If execution fails, follow [Page discovery](references/page-discovery.md): read the first failed step and its evidence before changing one hypothesis. Use `--ai-observe` when the ordinary report lacks current candidates or validation details. Distinguish a corrected DSL from an environment/data blocker or tool gap; two identical failures require new evidence, not another guessed value.

For AI business development verification, CLI success is only the tool outcome. Report `verified` only when the business assertion has complete relevant API evidence and the selected request actually hit the intended local forward target. If either response evidence or forward-hit evidence is missing, report `not_verified/evidence_unavailable` even when the DSL is green. Do not label the result `business_bug` or infer a root cause from tool evidence.

## Output Standard

When delivering DSL work, report the DSL file path, the command used to validate or run it, whether the run passed, and the key evidence from the JSON result such as `success`, failed step, `data.downloaded_files`, `data.import_results`, or captured notifications.
