# 🔐 Securing Quantum Channel — BB84 QKD Simulation

> **BB84 Quantum Key Distribution** with QBER-based eavesdropper detection and Quantum Temporal Authentication (QTA) on a 3-node network: Alice ──── Eve? ──── Bob

---

## 📋 Table of Contents

- [Overview](#overview)
- [Key Concepts](#key-concepts)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Usage](#usage)
- [Simulation Results](#simulation-results)
- [How It Works](#how-it-works)
- [Configuration](#configuration)
- [Output](#output)
- [Research Component](#research-component)

---

## Overview

This project simulates a **3-node Quantum Key Distribution (QKD) network** implementing the **BB84 protocol** from scratch. It models:

- ✅ Alice preparing and transmitting qubits over a quantum channel
- ✅ An optional **Eve (Man-in-the-Middle)** performing an intercept-resend attack at a configurable rate
- ✅ Bob measuring qubits and performing basis sifting with Alice
- ✅ **QBER (Quantum Bit Error Rate)** calculation to detect eavesdropping
- ✅ **QTA (Quantum Temporal Authentication)** detecting Eve via nanosecond-scale timing anomalies
- ✅ Automatic session abort when thresholds are exceeded
- ✅ A full sweep across interception rates to find the critical abort threshold

No external quantum simulation framework is required — the simulation is built entirely with Python's `numpy`, `random`, and `matplotlib`, faithfully modelling the physics and statistics of BB84.

---

## Key Concepts

### BB84 Protocol
BB84 (Bennett & Brassard, 1984) is the first quantum cryptographic protocol. It encodes bits in two non-orthogonal bases:

| Basis | Bit 0 | Bit 1 |
|-------|-------|-------|
| Rectilinear `+` | `\|0⟩` (0°) | `\|1⟩` (90°) |
| Diagonal `×` | `\|+⟩` (45°) | `\|-⟩` (135°) |

Security is guaranteed by the **No-Cloning Theorem** — Eve cannot copy a qubit without measuring it, and measuring in the wrong basis introduces errors.

### QBER (Quantum Bit Error Rate)
```
QBER = mismatched bits in sample / total sample size
```
When Eve intercepts a fraction `p` of qubits, she introduces:
```
QBER = 0.25 × p
```
**Abort threshold: QBER ≥ 11%** → session is discarded. This maps to Eve intercepting ≥ 44% of qubits.

### QTA (Quantum Temporal Authentication)
Eve's intercept-resend attack is not instantaneous. Measuring and re-preparing a qubit adds **1–3 ns** of latency. QTA verifies that photon arrival times match the expected propagation delay within a ±2 ns window. Anomalies flag a potential MitM attack independently of QBER.

---

## Project Structure

```
.
├── bb84_qkd_simulation.py      # Main simulation script
├── bb84_research_report.docx   # Full research report (BB84 + QBER + QTA)
├── bb84_qkd_security_report.png # Generated analysis figure
└── README.md
```

---

## Installation

**Requirements:** Python 3.9+

Install dependencies:
```bash
pip install numpy matplotlib scipy
```

No quantum framework installation needed — the simulation models BB84 physics directly.

---

## Usage

### Run the full simulation
```bash
python bb84_qkd_simulation.py
```

This will:
1. Run **Session 1** — No Eve (baseline secure session)
2. Run **Session 2** — Eve intercepts 100% of qubits
3. Run **Session 3** — Eve at exactly the theoretical threshold (44%)
4. Sweep interception rates from 0% → 100% and report QBER at each step
5. Generate a multi-panel security analysis figure (`bb84_qkd_security_report.png`)

### Expected output (truncated)
```
======================================================================
  BB84 QKD Simulation — Securing Quantum Channel
  3-Node Network: Alice ──── (Eve?) ──── Bob
======================================================================

[SESSION 1]  No eavesdropper present
  Raw qubits          : 2000
  After sifting       : 970
  QBER                : 0.0000  (0.00%)
  QTA violations      : 0
  Session verdict     : ✓ SECURE

[SESSION 2]  Eve intercepts 100% of qubits
  QBER                : 0.2481  (24.81%)
  QTA violations      : 960
  Session verdict     : ✗ ABORTED
  Abort reason        : QBER=0.248 ≥ threshold=0.11; QTA: 960 timing violations

[SWEEP]  ...
  ▶  Critical interception rate for abort: ~44%
     (Theoretical prediction: 44.0%)
```

---

## Simulation Results

| Session | Eve Interception | QBER | QTA Violations | Verdict |
|---------|-----------------|------|----------------|---------|
| No Eve | 0% | ~0.00% | 0 | ✅ SECURE |
| Partial Eve | 30% | ~7.5% | Low | ✅ SECURE |
| Threshold Eve | 44% | ~11% | Moderate | ❌ ABORTED |
| Full Eve | 100% | ~25% | ~960 | ❌ ABORTED |

### Critical Threshold
The simulation empirically confirms the theoretical prediction:

```
QBER_abort = 11%   →   Eve intercept rate = 11% / 25% = 44%
```

Eve must intercept **fewer than 44%** of qubits to stay statistically invisible. Above this rate, Alice and Bob will abort.

---

## How It Works

### Architecture

```
Alice                      Eve (optional)              Bob
──────                     ──────────────              ────
Prepares N qubits   ──►   Intercept-Resend?   ──►    Measures in
in random bases            (wrong basis 50%)           random bases
                           adds 1-3 ns delay
        │                                                  │
        └──────────── Public classical channel ────────────┘
                      (basis comparison, QBER sample)
```

### Classes

| Class | Role |
|-------|------|
| `Alice` | Generates random bits, encodes in random basis, timestamps photons |
| `Eve` | Intercepts qubits at a configurable rate, measures in random basis, re-prepares |
| `Bob` | Measures incoming qubits, records arrival timestamps |
| `BB84Session` | Orchestrates the full protocol: prepare → intercept → measure → sift → QBER → QTA → verdict |
| `QuantumTemporalAuthenticator` | Compares measured arrival times against expected propagation delay; flags anomalies |

### Session Flow
```
1. Alice prepares N qubits (random bits × random bases)
2. Eve optionally intercepts (intercept-resend attack)
3. Bob measures in random bases, records timestamps
4. Basis sifting → ~50% of bits kept (matching bases only)
5. QBER estimated on 25% random sample of sifted key
6. QTA verifies arrival times against expected ± 2 ns window
7. Verdict: SECURE if QBER < 11% AND QTA violations < 2%
```

---

## Configuration

All simulation parameters are defined as constants at the top of `bb84_qkd_simulation.py`:

```python
QBER_ABORT_THRESHOLD = 0.11   # 11% — standard BB84 abort threshold
SPEED_OF_LIGHT_FIBER = 2.0e8  # m/s in optical fiber (~2/3 c)
CHANNEL_LENGTH_KM    = 10.0   # Alice→Bob fiber distance
TIMING_JITTER_NS     = 0.5    # detector timing jitter (nanoseconds)
QTA_WINDOW_NS        = 2.0    # ±ns tolerance for arrival-time verification
NUM_QUBITS           = 2000   # qubits transmitted per session
SAMPLE_SIZE_FRACTION = 0.25   # fraction used for QBER estimation
```

To experiment:
- Increase `NUM_QUBITS` for more statistically stable results
- Adjust `QTA_WINDOW_NS` to tighten or loosen timing detection
- Change `QBER_ABORT_THRESHOLD` to simulate different security policies
- Modify `CHANNEL_LENGTH_KM` to simulate longer fiber links

---

## Output

The simulation generates `bb84_qkd_security_report.png` with 6 panels:

| Panel | Description |
|-------|-------------|
| ① QBER vs Interception Rate | Shows QBER rising linearly with Eve's activity; abort threshold marked |
| ② Session Comparison | Bar chart comparing QBER for no-Eve vs full-Eve sessions |
| ③ Key Agreement (No Eve) | Heatmap of Alice/Bob bit agreement — near 100% match |
| ④ Key Agreement (Eve Active) | Heatmap showing ~25% mismatch from Eve's interference |
| ⑤ QTA Timing Distribution | Histogram of photon arrival times; Eve's delayed photons clearly separated |
| ⑥ Protocol Flow | Visual diagram of all BB84 phases from qubit prep to key/abort |

---

## Research Component

A full research report (`bb84_research_report.docx`) covers:

- **Part 1 — BB84 Protocol:** Encoding scheme, no-cloning theorem, all 6 protocol phases
- **Part 2 — QBER:** Mathematical derivation of the 25% error rate, abort threshold decision table, real-world noise sources
- **Part 3 — QTA:** Physics of Eve's timing delay, the 6-step verification protocol, limitations
- **Part 4 — Combined Security:** Why both mechanisms are needed together, information-theoretic security guarantees

---

## References

- Bennett, C.H. & Brassard, G. (1984). *Quantum cryptography: Public key distribution and coin tossing.*
- Mayers, D. (2001). *Unconditional security in quantum cryptography.* JACM.
- Wootters, W.K. & Zurek, W.H. (1982). *A single quantum cannot be cloned.* Nature.
- Gisin, N. et al. (2002). *Quantum cryptography.* Reviews of Modern Physics.
- Lo, H.K. & Chau, H.F. (1999). *Unconditional security of quantum key distribution over arbitrarily long distances.* Science.

---

## License

MIT License — free to use, modify, and distribute with attribution.
