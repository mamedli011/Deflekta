# 04. Data Contracts

Canonical machine-readable versions live in `contracts/`. This doc explains them.

## Event (one JSON object per line in `runs/{session_id}.jsonl`)

| Field | Type | Values / notes |
|-------|------|----------------|
| `id` | str | `evt_0001`, increasing per session |
| `timestamp` | str | ISO 8601 UTC |
| `session_id` | str | `run_{n}` |
| `shield_on` | bool | |
| `stage` | str | `input` (page read), `action` (tool call), `agent` (model turn), `final` |
| `tool` | str or null | e.g. `browse_web`, `send_email` |
| `args` | object | tool arguments as the model sent them |
| `verdict` | str | `ALLOWED`, `FLAGGED`, `STRIPPED`, `NEEDS_CONFIRM`, `BLOCKED` |
| `severity` | str | `low`, `medium`, `high`, `critical` |
| `layer` | int or null | 1 visibility gap, 2 judge, 3 action guard, null if no shield decision |
| `rule_triggered` | str or null | e.g. `luhn_card_number`, `hidden_computed_style` |
| `reason` | str | one plain-English sentence, shown in the UI |
| `evidence` | object | `{ "hidden_text": ..., "technique": ..., "selector": ... }` or matched values (masked) |
| `result` | any | tool result or null |

Rules:

- Secrets in `evidence` are masked (`4111 **** **** 1111`), never logged in full, even fake ones,
  so screenshots of the UI never show a full number.

- Additive fields are fine. Renames need team agreement.

## Policy rule (`shield/policy.json`)
```json
{ "rule": "luhn_card_number",
  "tools": ["send_email", "http_request"],
  "check": "luhn_card_number",
  "action": "BLOCK",
  "severity": "critical",
  "reason": "Outgoing message contains a payment card number" }
```
`check` names a function in `shield/action_guard.py`. `action` is `BLOCK` or `CONFIRM`.

## Page manifest (`sandbox/pages/manifest.json`)
Every test page has an entry so the benchmark knows the ground truth:
```json
{ "path": "evil/recipe_external_css.html",
  "label": "evil",
  "technique": "external_css_class",
  "payload_id": "reset_email_forward",
  "wording": "polite_v2",
  "expected_layer1": true }
```
Benign pages: `"label": "benign"`, `"technique": null`, plus `"source"` (which real site it copies).
