# Open Questions

## S23 Premium Formula Semantics

The manually encoded S23 rule currently keeps the premium formulas exactly as explicit arithmetic:

- `ideal_premium_formula: "PRV_3DLL + 1.20%"`
- `minimum_premium_formula: "PRV_3DLL + 0.90%"`

Open question:
- Should these premium formulas remain percentage adjustments on the referenced value, or were they intended to behave like a multiplication-based premium model in the original TFIS source?

For now the runtime behavior matches the literal configured formulas so the test path remains deterministic and explicit.
