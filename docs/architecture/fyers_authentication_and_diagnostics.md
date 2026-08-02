# FYERS Authentication And Diagnostics

## Scope

This document records the reusable FYERS authentication and diagnostic boundary
used for read-only TFIS data acquisition.

Authentication is a broker-platform capability. Strategies must not read
credentials, token files, PINs, TOTP secrets, auth codes, cookies, or session
secrets.

## Canonical Auth Flow

The canonical operator command is:

```powershell
.\.venv\Scripts\python.exe scripts\fyers_token_refresh.py --prepare
```

That command reuses `src/tfis/brokers/fyers_token.py`.

Canonical token source:

- file: `data/token_store.json`
- schema: JSON object containing `access_token` and optional `refreshed_at`
- protection: ignored by Git through `data/token_store.json` and `data/`
- validation: FYERS `get_profile` read-only request

No second active FYERS token contract is approved.

## Session Boundary

`src/tfis/broker/authentication/` defines broker-neutral authentication
objects:

- `BrokerCredentialReference`
- `BrokerAuthenticationRequest`
- `BrokerSessionIdentity`
- `BrokerAuthenticationResult`
- `BrokerAuthenticationFailure`
- `ValidatedBrokerSession`
- `BrokerSessionStatus`

`src/tfis/broker/authentication/fyers.py` adapts the canonical FYERS token
flow and returns a validated session handle. The raw token remains in process
memory only and is not exposed in reports, fixtures, hashes, or domain
evidence.

## Diagnostic Boundary

The command is:

```powershell
.\.venv\Scripts\python.exe scripts\run_broker_diagnostics.py --broker fyers --account s22-reliance-read-only --check-reference-data --check-historical-data --check-quote --check-option-chain
```

The diagnostic separates:

- configuration health
- credential-source health
- authentication/session health
- reference-data health
- historical-data health
- quote health
- option-chain health
- account-read status
- order-write authority

For this milestone, order writes are always `NOT_AUTHORIZED`.

## Authority Rule

Authentication success is not trading authority.

Future submission eligibility would require all of the following, in a
separate approved milestone:

```text
authenticated broker session
+ explicit authority mode
+ reconciliation readiness
+ risk readiness
+ operator enablement
```

No broker order, external paper order, live order, or real position mutation is
added by this boundary.

## S22 RELIANCE Capture Sequence

The approved read-only sequence is:

```text
canonical FYERS token prepare
-> FyersAuthenticationAdapter
-> ValidatedBrokerSession
-> FyersReadOnlyAdapter
-> RELIANCE symbol master/history/option-chain capture
-> sanitized offline fixture
-> S22 implementation gate
```

The sanitized fixture is stored at:

```text
tests/fixtures/s22_reliance/s22_reliance_fyers_snapshot_2026-08-02_sanitized.json
```

This fixture contains market/reference candidates only. It does not contain an
S22 selected contract, execution intent, client order, position cycle, trade
fact, or P&L fact.
