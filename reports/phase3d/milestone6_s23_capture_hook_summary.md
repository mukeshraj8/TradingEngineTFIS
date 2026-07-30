# Phase 3D Milestone 6 S23 Capture Hook Summary

## Verdict

PHASE3D_M6_ACCEPT

## Capture Insertion Point

The capture seam sits in `src/tfis/adapters/legacy_policies/s23_vertical_slice.py` immediately after the S23 vertical path returns from `OfflineStrategyDecisionOrchestrator.evaluate`. This is the smallest safe boundary because all S23-specific stage payloads, the final `TFISDecision`, and the final `TFISDecisionEvidencePacket` are available there, while the generic orchestrator and business engines remain strategy-neutral and filesystem-neutral.

## Decision Authority

Capture observes only. No observer means no capture work, no filesystem access, no serialization, and no output difference. When an observer is supplied, packet construction and sink failures are caught as capture diagnostics and do not alter the returned decision, evidence packet, downstream permission, stage order, or deterministic hash.

## Default Configuration

DISABLED. No paper, live, backtest, broker, runtime, or strategy profile was enabled or modified.

## Fields Captured

- identity, strategy family/definition/version/instance, resolved configuration hash, trading date, session identity
- Monthly Status, resolved branch, source timestamps, underlying references
- full option-chain snapshot supplied to selection, expiry/strike/premium/OI fields, selected contract and quote
- selected-contract historical references, ORPT observation, RC observation, Base Entry, Gap/Missed-Entry, Effective Entry
- Target and MSL compatibility inputs/results
- final `TFISDecision` and `TFISDecisionEvidencePacket`
- provenance, synthetic supplements, missing real-world fields, redaction metadata, and capture locations for missing fields

## Redaction

Sensitive key fragments such as token, access_token, refresh_token, authorization, cookie, password, api_key, and secret are rejected or serialized only as `REDACTED`. Broker credentials, raw authorization headers, and unrestricted broker account identifiers are not captured.

## Fixture Capture Results

- Bull Call: `TRADE`, selected `NIFTY_20260806_22250_CALL`, disabled hash `4e327a977aeaad6841891b2a044155ca8a1f644c1b11a261e255252506deaa1c`, enabled hash `4e327a977aeaad6841891b2a044155ca8a1f644c1b11a261e255252506deaa1c`, packet bytes `48190`.
- Bear Call: `TRADE`, selected `NIFTY_20260806_22150_CALL`, disabled hash `3a8dbc6b507ac7603f2c0a4b289f3ecf9855f17206b3d96744b3291af8f20d41`, enabled hash `3a8dbc6b507ac7603f2c0a4b289f3ecf9855f17206b3d96744b3291af8f20d41`, packet bytes `50810`.

Both fixture packets are classified as `LEGACY_FIXTURE_WITH_SYNTHETIC_SUPPLEMENT`. Fixture serialization is not counted as real market capture.

## Disabled-Mode Equivalence

Disabled and enabled fixture runs preserve the same decisions, evidence packets, and deterministic hashes. Capture output path, sink diagnostics, and write timing do not enter the business hash.

## Failure Isolation

Tests cover unavailable output directory, serialization/invalid packet failure, write permission failure, duplicate capture identity, and observer exception. In every case, the decision result remains unchanged and no partial packet is presented as complete.

## Performance

- Bull disabled duration seconds: `0.03448650000063935`.
- Bull enabled duration seconds: `0.05471419999958016`.
- Bear disabled duration seconds: `0.028783000001567416`.
- Bear enabled duration seconds: `0.05118570000195177`.

These are local fixture timings only; capture is disabled by default and has zero disabled-mode filesystem overhead.

## Runtime Impact

NONE. No runtime shadow, paper authority, live authority, broker behavior, lifecycle behavior, execution routing, order placement, or position state changed.

## Real Market Packets Obtained

0

## Steps Required For First Real Packet

Run one explicitly approved non-authoritative shadow/debug session with capture enabled for an S23 Bull Call or Bear Call case, writing to a controlled offline/debug directory. That session must provide the missing real-world evidence fields: real trading date, captured option-chain snapshot, selected-contract quote, ORPT option observation, RC option observation, and legacy/runtime decision packet.
