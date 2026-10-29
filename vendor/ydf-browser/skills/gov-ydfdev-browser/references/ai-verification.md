# AI Business Verification

Use this workflow only after an AI changes a YonDiF business repository. The business system is the system under test; ydf-browser is the E2E verifier. A green DSL run is a tool fact, not a verified business change.

## Required inputs

Obtain these explicitly before running:

- frozen release ZIP SHA-256 and pre-install runtime/skill fingerprints;
- default-installed skill root and PATH-resolved ydf-browser executable;
- DSL path and a new private run directory outside the business repository;
- a separate idempotent cleanup DSL declared by the frozen manifest;
- forwarding rules;
- a readiness JSON file;
- the temporary business identifier used by both UI assertions and API evidence.

Do not infer a service type from a forwarding prefix, URL, scheme, host, or port. Each forwarding target needs a separate readiness item with `target`, `mode`, `url`, `timeout_seconds`, and `tls_verify`. See `readiness.example.json`.

不得从转发路径、目标地址或端口推断服务类型。

`http_reachable` accepts any HTTP status after TCP/TLS/HTTP interaction succeeds. `semantic_probe` additionally requires `expected_status`, `json_path`, and `equals`. TLS verification may be disabled only by explicit `tls_verify: false`.

## Contract preflight

Install runtime and skill from the same frozen release ZIP, then run the installed runtime preflight:

```bash
command -v ydf-browser
ydf-browser doctor --skip-config
```

Require contract major version `1` and every advertised capability used by this workflow. If doctor fails or capabilities are missing, stop with `blocked/contract_incompatible`; do not start the browser.

The bundled helper performs doctor and readiness before launching the run:

```bash
SKILL_ROOT="$HOME/.agents/skills/gov-ydfdev-browser"
python3 "$SKILL_ROOT/scripts/ai_verification.py" run \
  --dsl "$DSL_FILE" \
  --run-dir "$PRIVATE_ROOT/runs/red-1" \
  --readiness-file "$PRIVATE_ROOT/readiness.json" \
  --verification-manifest "$PRIVATE_ROOT/verification-manifest.json" \
  --cleanup-dsl "$PRIVATE_ROOT/cleanup.yaml" \
  --var business_id="$BUSINESS_ID" \
  --step-timeout-seconds 120 \
  --case-timeout-seconds 900 \
  --run-timeout-seconds 1800 \
  --forward-strip-prefix '/business-fe/**=https://127.0.0.1:3006' \
  --forward-strip-prefix '/business-be/**=http://127.0.0.1:62871'
```

The helper resolves `ydf-browser` from `PATH` once and uses that same executable for preflight, the main run, and cleanup. Before opening a browser it compares the PATH executable, the default-installed `agents_skill` canonical copy, and the running helper against the frozen manifest. Invoke the helper only from the default-installed skill; neither the source checkout nor the unpacked release directory is an execution entry.

Its run command is equivalent to this installed invocation:

```bash
ydf-browser run \
  --dsl "$DSL_FILE" --headless --ai-observe \
  --report-file "$PRIVATE_RUN_DIR/report.json"
```

The helper creates a new `0700` directory. The tool writes `report.json`, `events.jsonl`, and `artifacts/` there. Never reuse a prior run directory.

After every main outcome, including assertion failure or external termination, the helper runs the separate cleanup DSL under `cleanup/attempt-1`; it retries once in `cleanup/attempt-2` when needed. Omitting `--cleanup-dsl`, a manifest path mismatch, or two failed cleanup attempts makes the run ineligible for `verified`. Use `--var` for the run-specific identifier rather than rewriting the frozen main or cleanup DSL.

## External watchdog

The helper waits until `run_timeout_seconds + 30`. It then requests process termination, waits five seconds, and only then kills the process. When this happens, use only already-flushed `events.jsonl` and artifacts and report `terminated/external_termination`. Do not invent a tool-internal timeout report.

## Evidence selection

Read the business assertion receipt first. Only inspect request IDs listed in its `candidate_request_ids`; ydf-browser deliberately does not rank them.

For each selected request verify all of the following:

1. it has a terminal `request_completed` record;
2. the required request or response body artifact is present and complete;
3. the same new temporary business identifier appears in the relevant API semantic body and UI assertion receipt;
4. `forwarding.matched` and `forwarding.success` are both true for that request;
5. the actual URL is the intended local target.

Use the helper to shortlist candidates, then inspect the referenced redacted semantic bodies and source code yourself:

```bash
python "$SKILL_ROOT/scripts/ai_verification.py" inspect \
  --run-dir "$PRIVATE_RUN_DIR" \
  --business-id "$BUSINESS_ID"
```

`not_present` means that direction had no body. Other unavailable reasons, missing terminal records, identifier disagreement, or no actual local forward hit make the business change `not_verified/evidence_unavailable`, even if the DSL passed. Never label tool output `business_bug`, `bad_data`, or a root cause.

## Red and green gates

- Before editing business code, run the real DSL and obtain a qualified red result.
- A qualified run must execute the complete precondition query, business mutation, and postcondition assertion through the helper in one run directory. Record their three distinct, ordered, completed request IDs in `flow_request_ids`; diagnostic browser or API calls cannot supply a missing phase. Precondition and mutation bodies must carry the run's unique identifier. A passing postcondition must carry it too; a failing red postcondition may omit it only when the selected request is cited by the authentic failing assertion receipt, because a negative query response naturally excludes the missing row.
- Create and freeze `verification-manifest.json` before the first run. Its inputs must include the main DSL, cleanup DSL, and readiness paths; fingerprints must include `release_package_sha256`, installed `ydf_browser`, the canonical `agents_skill`, and `helper_sha256`. Every helper `run` verifies those paths and current fingerprints before opening a browser and records the manifest SHA-256; a missing or later-created manifest invalidates the pilot. The main DSL may be refined before a qualified red result without changing its manifest path.
- Before that qualified red result, do not write any file in the business repository. Temporary logging, probes, instrumentation, or changes intended to be reverted still invalidate the pilot; if saved evidence is insufficient, stop as blocked.
- After a qualified red result, freeze that DSL content. Every helper run records its actual SHA-256 in `external-result.json`; copy it to the run's `dsl_sha256` field in the final result. Run the same content with two fresh identifiers in two new evidence directories; the red and both green identifiers must all differ.
- Both green runs require matching API/UI identifiers and actual local forward hits.
- Let the helper clean all temporary data through the frozen cleanup DSL. It retries once idempotently; remaining data means `not_verified/cleanup_failed`.
- Recheck the release package, installed ydf-browser, canonical skill copy, and helper fingerprints. Any change makes the pilot `invalid`.

## Machine-readable files

Keep `verification-manifest.json` immutable after the pilot starts. It records inputs, the business-repository baseline, the release ZIP SHA-256, and installed runtime/skill/helper fingerprints; use `verification-manifest.schema.json` and its example.

Write the final `verification-result.json` atomically. It records each run directory, tool outcome, report, assertion receipt, selected request ID, API/UI identifier, local-forward hit, temporary data, cleanup, and fingerprint comparison. Use `verification-result.schema.json`, the single example, and `verification-result.examples.json` for verified, cleanup-failed, and invalid cases:

```bash
python "$SKILL_ROOT/scripts/ai_verification.py" write-result \
  --input "$PRIVATE_ROOT/verification-result.pending.json" \
  --output "$PRIVATE_ROOT/verification-result.json"
```

Only one qualified red run and exactly two qualified green runs permit `status: verified`. The writer verifies one shared DSL SHA-256, three fresh API/UI identifiers, all three same-run flow requests and local-forward facts, successful cleanup, and unchanged fingerprints. Human-readable diagnosis belongs in `evaluator-final.md`.

## Verdict table

| Observed facts | Tool outcome | Verification status |
|---|---|---|
| Assertion passed, relevant API body complete, API/UI identifier agrees, intended local target hit | `passed` | eligible for `verified` after all gates |
| Assertion passed, relevant body unavailable or over capacity | `passed` | `not_verified/evidence_unavailable` |
| Assertion passed, no selected request hit the intended local target | `passed` | `not_verified/evidence_unavailable` |
| Assertion did not produce a comparable result | `blocked` | `not_verified` |

Read `ai-verification-examples.json` for machine-readable negative examples. First phase intentionally has no general `api.assert` DSL.
