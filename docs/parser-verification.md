# Parser verification

`rosetta verify` checks a draft parser against a labeled JSON Lines fixture. Every
case has a `raw` string and an explicit `expected_template_id`; use `null` for a
record that the parser must reject. `required_fields` lists parser field names
that must be mapped for that case.

```json
{"raw":"Sep 29 08:15:00 fw01 %ASA-4-106023: Deny tcp src 10.0.0.5/443 dst 203.0.113.4/443","expected_template_id":"asa_deny","required_fields":["action","src_ip"]}
{"raw":"not an ASA event","expected_template_id":null,"required_fields":[]}
```

Run verification and activation from the repository root:

```powershell
rosetta verify draft_parsers\asa_candidate.yaml fixtures\asa.jsonl
rosetta activate draft_parsers\asa_candidate.yaml
```

The verifier emits JSON and escaped HTML reports. A candidate advances from
`draft` to `verified` only when all labeled positive cases are covered, negative
cases remain unmatched, required fields are present, patterns compile with RE2,
and captured raw strings round-trip unchanged. The state machine refuses to
activate a parser unless its referenced report is successful and names the same
parser version. Failed candidates remain `draft`.

Verification fixtures and reports may contain sensitive log data. Store them
locally and grant access only to authorized reviewers. The generated reports do
not copy raw fixture contents.
