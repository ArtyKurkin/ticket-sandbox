# №20.1b-7b: provenance and limits

`native/` contains the five original files from the user-supplied archive
`trusted_checker_kernel_evidence_20261020.zip`, copied byte for byte. No native
JSON was reserialized, reconstructed, filtered or normalized. `provenance.json`
records archive/file SHA-256 and byte lengths. Each of the three JSON files was
also checked to be an exact unchanged line in `raw_terminal_capture.md` (plus
its final newline). These checks establish preservation of the supplied data,
not independent host attestation.

Original commands recorded in the terminal capture:

- `nft -j -a list ruleset` → `nft_ruleset_final.json`;
- `bridge -j link show` → `bridge_links_final.json`;
- `ip -j -d link show tc-br0` → `bridge_tc_br0_final.json`.

The ip dump includes **only the bridge**, not all host interfaces or namespace
peers. The bridge-port dump is a different schema: `master` is the name
`tc-br0`, and peer links appear as `link: "if6"` / `"if8"`. Neither dump is a
complete topology observation. The raw terminal log also records host routes,
four namespaces and a listener; these are human-readable diagnostic snapshots,
not all-table/RPDB or per-probe JSON evidence.

Both nft tables (`tc_ct_lab`, `tc_strict_lab`) are laboratory policies with base
policy accept, not the canonical counter recipe. Counters are final cumulative
values. The three `tc_ct_lab` rules are nonterminal observers. The strict table
has two ARP accept rules without counters, three TCP counter/accept rules and
two counter/drop rules. Native handles repeat across scopes/kinds. Do not treat
labels or handles alone as canonical identity or ownership.

`observations.json` is our summary schema, initially transcribed from the user's
task. The five strict-table pairs were subsequently matched to the native dump
without changing their values. It is not native nft JSON. Its availability flag
now records receipt of the native files. There is still no JSON before/after
from one controlled attempt, no fixed-frame capture, and no canonical recipe run.

`test_kernel_compatibility.py` uses the existing **synthetic** `CounterLab` for
contract boundary tests. Numeric tests deliberately place observed pairs in
synthetic counters without asserting a lab-rule/canonical-rule mapping.
`test_kernel_native_formats.py` separately reads the original native fixtures,
checks observed formats/values and exercises existing pure JSON decoding and
mandatory contract refusals. No test executes commands from the terminal log.

For a future separately approved experiment, collect the full canonical nft
round trip, host/peer links and addresses, bridge state, all IPv4/IPv6 route
tables/RPDB, attachments/offloads/FD inventory, fixed packet events and fresh
context-bound before/after JSON for every probe. Never infer missing snapshots
from cumulative values or regenerate them from human-readable output.
