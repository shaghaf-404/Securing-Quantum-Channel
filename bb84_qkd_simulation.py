"""
╔══════════════════════════════════════════════════════════════════════╗
║          BB84 Quantum Key Distribution — 3-Node Network              ║
║         Alice ──── (Eve?) ──── Bob  with QBER & QTA Analysis         ║
╚══════════════════════════════════════════════════════════════════════╝

Simulates the BB84 protocol with:
  • Optional Eve (Man-in-the-Middle) with configurable interception rate
  • Quantum Bit Error Rate (QBER) calculation & abort threshold
  • Quantum Temporal Authentication (QTA) at nanosecond resolution
  • Full sifting, error estimation, and session verdict
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import time
import random
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict

# ─── Constants ────────────────────────────────────────────────────────────────
QBER_ABORT_THRESHOLD = 0.11   # 11% — standard BB84 abort threshold
SPEED_OF_LIGHT_FIBER = 2.0e8  # m/s in optical fiber (~2/3 c)
CHANNEL_LENGTH_KM    = 10.0   # Alice→Bob fiber distance
TIMING_JITTER_NS     = 0.5    # detector timing jitter (nanoseconds)
QTA_WINDOW_NS        = 2.0    # ±ns tolerance for arrival-time verification
NUM_QUBITS           = 2000   # qubits transmitted per session
SAMPLE_SIZE_FRACTION = 0.25   # fraction used for QBER estimation

# ─── Qubit & Basis definitions ─────────────────────────────────────────────
# Rectilinear basis (+): |0⟩=0°, |1⟩=90°
# Diagonal basis  (×): |+⟩=45°, |−⟩=135°
BASES = ['+', '×']

# ─── Timing ───────────────────────────────────────────────────────────────────
def expected_arrival_ns(distance_km: float) -> float:
    """Expected photon arrival time in nanoseconds."""
    return (distance_km * 1000) / SPEED_OF_LIGHT_FIBER * 1e9

def measure_arrival_time_ns(distance_km: float, add_extra_delay: bool = False) -> float:
    """
    Returns measured *propagation time* in nanoseconds (not absolute timestamp).
    Eve's intercept-resend adds ~1–3 ns extra latency detectable by QTA.
    """
    base_time   = expected_arrival_ns(distance_km)
    jitter      = np.random.normal(0, TIMING_JITTER_NS)
    extra_delay = np.random.uniform(1.0, 3.0) if add_extra_delay else 0.0
    return base_time + jitter + extra_delay


# ─── BB84 Core ────────────────────────────────────────────────────────────────
@dataclass
class Qubit:
    bit:        int          # Alice's intended bit (0 or 1)
    basis:      str          # Basis used for encoding ('+' or '×')
    send_time:  float = 0.0  # transmission timestamp (ns)

@dataclass
class Measurement:
    bit:          int
    basis:        str
    arrival_time: float = 0.0
    intercepted:  bool  = False

@dataclass
class SessionResult:
    raw_key_length:     int
    sifted_key_length:  int
    qber:               float
    session_secure:     bool
    abort_reason:       str
    qta_violations:     int
    qta_triggered:      bool
    eve_present:        bool
    eve_intercept_rate: float
    alice_sifted_key:   list
    bob_sifted_key:     list
    timing_anomalies:   list


# ─── Alice ────────────────────────────────────────────────────────────────────
class Alice:
    def __init__(self, n_qubits: int):
        self.n    = n_qubits
        self.bits  = np.random.randint(0, 2, n_qubits).tolist()
        self.bases = [random.choice(BASES) for _ in range(n_qubits)]
        self.send_times = []

    def prepare_qubits(self) -> list[Qubit]:
        qubits = []
        t = 0.0
        for i in range(self.n):
            t += np.random.exponential(1.0)   # Poisson photon source
            q = Qubit(bit=self.bits[i], basis=self.bases[i], send_time=t)
            self.send_times.append(t)
            qubits.append(q)
        return qubits


# ─── Eve (Intercept-Resend Attack) ───────────────────────────────────────────
class Eve:
    """
    Eve performs an intercept-resend attack.
    She randomly picks a measurement basis for each intercepted qubit.
    When her basis mismatches Alice's, she introduces a 25% error rate
    (the core vulnerability BB84 detects).
    """
    def __init__(self, intercept_rate: float = 1.0):
        self.intercept_rate   = intercept_rate
        self.intercepted_bits = []
        self.intercept_indices = []

    def intercept(self, qubits: list[Qubit]) -> list[Qubit]:
        modified = []
        for i, q in enumerate(qubits):
            if random.random() < self.intercept_rate:
                # Eve measures in a random basis
                eve_basis = random.choice(BASES)
                if eve_basis == q.basis:
                    # Correct basis → correct bit, no error introduced
                    resent_bit = q.bit
                else:
                    # Wrong basis → random collapse (50% error)
                    resent_bit = random.randint(0, 1)

                self.intercepted_bits.append(resent_bit)
                self.intercept_indices.append(i)

                # Eve re-prepares and re-sends with extra time delay
                new_q = Qubit(
                    bit=resent_bit,
                    basis=eve_basis,
                    send_time=q.send_time
                )
                modified.append(new_q)
            else:
                self.intercepted_bits.append(None)
                modified.append(q)
        return modified


# ─── Bob ──────────────────────────────────────────────────────────────────────
class Bob:
    def __init__(self, n_qubits: int):
        self.n     = n_qubits
        self.bases = [random.choice(BASES) for _ in range(n_qubits)]

    def measure(self, qubits: list[Qubit], channel_km: float,
                eve_active: bool, eve_indices: set) -> list[Measurement]:
        measurements = []
        for i, q in enumerate(qubits):
            via_eve   = eve_active and (i in eve_indices)
            arrival_t = measure_arrival_time_ns(channel_km, add_extra_delay=via_eve)

            if self.bases[i] == q.basis:
                # Basis match → correct bit
                measured_bit = q.bit
            else:
                # Basis mismatch → random result (fundamental QM)
                measured_bit = random.randint(0, 1)

            measurements.append(Measurement(
                bit=measured_bit,
                basis=self.bases[i],
                arrival_time=arrival_t,
                intercepted=via_eve
            ))
        return measurements


# ─── QTA — Quantum Temporal Authentication ───────────────────────────────────
class QuantumTemporalAuthenticator:
    """
    Verifies photon arrival times at nanosecond resolution.
    Eve's intercept-resend attack adds measurable latency
    (measurement + re-preparation + retransmission ≈ 1–3 ns extra).

    Alice and Bob compare arrival-time statistics over an authenticated
    classical channel; anomalies flag a possible MitM.
    """
    def __init__(self, channel_km: float, window_ns: float = QTA_WINDOW_NS):
        self.expected_ns = expected_arrival_ns(channel_km)
        self.window_ns   = window_ns
        self.violations  = []

    def verify(self, measurements: list[Measurement],
               alice_send_times: list[float]) -> tuple[int, list]:
        violation_count = 0
        anomalies       = []
        for i, (m, t_send) in enumerate(zip(measurements, alice_send_times)):
            # arrival_time is absolute: t_send + propagation + jitter [+ eve_delay]
            measured_delta = m.arrival_time  # already absolute propagation time
            deviation      = abs(measured_delta - self.expected_ns)
            if deviation > self.window_ns:
                violation_count += 1
                anomalies.append({
                    'index':     i,
                    'expected':  self.expected_ns,
                    'measured':  measured_delta,
                    'deviation': deviation
                })
        return violation_count, anomalies


# ─── BB84 Protocol Orchestrator ──────────────────────────────────────────────
class BB84Session:
    def __init__(self, n_qubits: int = NUM_QUBITS,
                 eve_present: bool = False,
                 eve_intercept_rate: float = 1.0,
                 channel_km: float = CHANNEL_LENGTH_KM):
        self.n_qubits           = n_qubits
        self.eve_present        = eve_present
        self.eve_intercept_rate = eve_intercept_rate
        self.channel_km         = channel_km

    def run(self) -> SessionResult:
        # 1 ─ Alice prepares qubits
        alice = Alice(self.n_qubits)
        qubits = alice.prepare_qubits()

        # 2 ─ (Optional) Eve intercepts
        eve_indices = set()
        if self.eve_present:
            eve = Eve(self.eve_intercept_rate)
            qubits = eve.intercept(qubits)
            eve_indices = set(eve.intercept_indices)

        # 3 ─ Bob measures
        bob = Bob(self.n_qubits)
        measurements = bob.measure(
            qubits, self.channel_km,
            self.eve_present, eve_indices
        )

        # 4 ─ Sifting: keep only matching-basis qubits
        alice_sifted, bob_sifted, sifted_idx = [], [], []
        for i, (a_basis, m) in enumerate(zip(alice.bases, measurements)):
            if a_basis == m.basis:
                alice_sifted.append(alice.bits[i])
                bob_sifted.append(m.bit)
                sifted_idx.append(i)

        # 5 ─ QTA timing verification
        qta = QuantumTemporalAuthenticator(self.channel_km)
        qta_violations, timing_anomalies = qta.verify(
            measurements, alice.send_times
        )
        qta_triggered = qta_violations > (self.n_qubits * 0.02)  # >2% anomaly

        # 6 ─ QBER estimation on random sample
        n_sifted = len(alice_sifted)
        sample_n = max(10, int(n_sifted * SAMPLE_SIZE_FRACTION))
        sample_idx = random.sample(range(n_sifted), min(sample_n, n_sifted))

        errors = sum(
            1 for i in sample_idx
            if alice_sifted[i] != bob_sifted[i]
        )
        qber = errors / len(sample_idx) if sample_idx else 0.0

        # 7 ─ Remove sample bits from key material
        remaining = [i for i in range(n_sifted) if i not in set(sample_idx)]
        final_alice = [alice_sifted[i] for i in remaining]
        final_bob   = [bob_sifted[i]   for i in remaining]

        # 8 ─ Session verdict
        abort_reason  = ""
        session_secure = True
        if qber >= QBER_ABORT_THRESHOLD:
            session_secure = False
            abort_reason   = f"QBER={qber:.3f} ≥ threshold={QBER_ABORT_THRESHOLD}"
        if qta_triggered:
            session_secure = False
            abort_reason  += ("; " if abort_reason else "") + \
                             f"QTA: {qta_violations} timing violations detected"

        return SessionResult(
            raw_key_length     = self.n_qubits,
            sifted_key_length  = n_sifted,
            qber               = qber,
            session_secure     = session_secure,
            abort_reason       = abort_reason,
            qta_violations     = qta_violations,
            qta_triggered      = qta_triggered,
            eve_present        = self.eve_present,
            eve_intercept_rate = self.eve_intercept_rate if self.eve_present else 0.0,
            alice_sifted_key   = final_alice,
            bob_sifted_key     = final_bob,
            timing_anomalies   = timing_anomalies
        )


# ─── Sweep: QBER vs Eve's interception rate ──────────────────────────────────
def sweep_interception_rates(rates: list[float], trials: int = 10) -> dict:
    results = defaultdict(list)
    for rate in rates:
        for _ in range(trials):
            session = BB84Session(
                n_qubits=NUM_QUBITS,
                eve_present=(rate > 0),
                eve_intercept_rate=rate
            )
            r = session.run()
            results[rate].append(r.qber)
    return {r: (np.mean(v), np.std(v)) for r, v in results.items()}


# ─── Plotting ─────────────────────────────────────────────────────────────────
def generate_report_figure(sweep_data: dict,
                            no_eve_result: SessionResult,
                            eve_result: SessionResult) -> str:

    # colour palette
    C_ALICE  = "#4FC3F7"
    C_BOB    = "#81C784"
    C_EVE    = "#EF5350"
    C_SAFE   = "#26C6DA"
    C_WARN   = "#FFA726"
    C_ABORT  = "#EF5350"
    C_BG     = "#0D1117"
    C_PANEL  = "#161B22"
    C_TEXT   = "#E6EDF3"
    C_MUTED  = "#8B949E"
    C_GRID   = "#21262D"
    C_THRESH = "#FF6B35"

    fig = plt.figure(figsize=(20, 14), facecolor=C_BG)
    gs  = GridSpec(3, 3, figure=fig,
                   hspace=0.55, wspace=0.38,
                   top=0.90, bottom=0.06, left=0.06, right=0.97)

    def styled_ax(ax, title=""):
        ax.set_facecolor(C_PANEL)
        for spine in ax.spines.values():
            spine.set_edgecolor(C_GRID)
        ax.tick_params(colors=C_MUTED, labelsize=8)
        ax.xaxis.label.set_color(C_MUTED)
        ax.yaxis.label.set_color(C_MUTED)
        if title:
            ax.set_title(title, color=C_TEXT, fontsize=10, fontweight='bold', pad=8)
        ax.grid(True, color=C_GRID, linewidth=0.5, alpha=0.7)

    # ── Title ──────────────────────────────────────────────────────────────
    fig.text(0.5, 0.955, "BB84 Quantum Key Distribution — Security Analysis",
             ha='center', va='center', color=C_TEXT,
             fontsize=16, fontweight='bold')
    fig.text(0.5, 0.928,
             "3-Node Network (Alice ──── Eve? ──── Bob)  •  QBER Threshold Detection  •  Quantum Temporal Authentication",
             ha='center', va='center', color=C_MUTED, fontsize=9)

    # ── 1. QBER vs Eve interception rate ───────────────────────────────────
    ax1 = fig.add_subplot(gs[0, :2])
    styled_ax(ax1, "① QBER vs Eve Interception Rate")

    rates  = sorted(sweep_data.keys())
    means  = [sweep_data[r][0] for r in rates]
    stds   = [sweep_data[r][1] for r in rates]

    ax1.fill_between(rates,
                     [m - s for m, s in zip(means, stds)],
                     [m + s for m, s in zip(means, stds)],
                     color=C_EVE, alpha=0.15)
    ax1.plot(rates, means, color=C_EVE, linewidth=2.5,
             marker='o', markersize=5, label="Mean QBER")

    # Threshold line
    ax1.axhline(y=QBER_ABORT_THRESHOLD, color=C_THRESH,
                linestyle='--', linewidth=2.0, label=f"Abort threshold ({QBER_ABORT_THRESHOLD:.0%})")
    ax1.fill_between([0, 1], QBER_ABORT_THRESHOLD, 0.35,
                     color=C_ABORT, alpha=0.08)

    # Safe zone
    ax1.axhspan(0, QBER_ABORT_THRESHOLD, color=C_SAFE, alpha=0.06)

    ax1.text(0.72, QBER_ABORT_THRESHOLD + 0.012,
             "ABORT ZONE", color=C_ABORT, fontsize=8, fontweight='bold')
    ax1.text(0.72, QBER_ABORT_THRESHOLD - 0.025,
             "SECURE ZONE", color=C_SAFE, fontsize=8, fontweight='bold')

    ax1.set_xlabel("Eve's Interception Rate")
    ax1.set_ylabel("QBER")
    ax1.set_xlim(0, 1)
    ax1.set_ylim(0, 0.35)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
    ax1.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))
    ax1.legend(fontsize=8, facecolor=C_PANEL, edgecolor=C_GRID,
               labelcolor=C_TEXT, loc='upper left')

    # Theoretical 25% line annotation
    ax1.axhline(y=0.25, color=C_WARN, linestyle=':', linewidth=1.2, alpha=0.7)
    ax1.text(0.01, 0.252, "Theoretical max (25%)", color=C_WARN,
             fontsize=7, alpha=0.8)

    # ── 2. Session comparison bar chart ───────────────────────────────────
    ax2 = fig.add_subplot(gs[0, 2])
    styled_ax(ax2, "② Session Comparison")

    labels   = ['No Eve\n(Secure)', 'Eve Present\n(Intercepted)']
    qbers    = [no_eve_result.qber, eve_result.qber]
    colours  = [C_SAFE if q < QBER_ABORT_THRESHOLD else C_ABORT for q in qbers]
    bars     = ax2.bar(labels, qbers, color=colours, width=0.5,
                       edgecolor=C_GRID, linewidth=0.8)
    ax2.axhline(y=QBER_ABORT_THRESHOLD, color=C_THRESH,
                linestyle='--', linewidth=1.5)
    for bar, q in zip(bars, qbers):
        ax2.text(bar.get_x() + bar.get_width() / 2,
                 bar.get_height() + 0.003,
                 f"{q:.1%}", ha='center', color=C_TEXT, fontsize=9,
                 fontweight='bold')
    ax2.set_ylabel("QBER")
    ax2.set_ylim(0, max(qbers) * 1.4 + 0.02)
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))

    # ── 3. Bit agreement heatmap (no Eve) ─────────────────────────────────
    ax3 = fig.add_subplot(gs[1, 0])
    styled_ax(ax3, "③ Sifted Key Agreement (No Eve)")

    n_show = 40
    a_key  = no_eve_result.alice_sifted_key[:n_show]
    b_key  = no_eve_result.bob_sifted_key[:n_show]
    agree  = np.array([1 if a == b else -1 for a, b in zip(a_key, b_key)])

    cmap = plt.cm.colors.LinearSegmentedColormap.from_list(
        'agree', [C_ABORT, C_SAFE])
    mat  = agree.reshape(5, 8)
    ax3.imshow(mat, cmap=cmap, aspect='auto', vmin=-1, vmax=1)
    ax3.set_xticks([]); ax3.set_yticks([])
    agree_pct = (agree == 1).mean()
    ax3.set_xlabel(f"Agreement: {agree_pct:.1%} | Error: {1-agree_pct:.1%}",
                   fontsize=8)

    # ── 4. Bit agreement heatmap (Eve) ────────────────────────────────────
    ax4 = fig.add_subplot(gs[1, 1])
    styled_ax(ax4, "④ Sifted Key Agreement (Eve Active)")

    a_key_e = eve_result.alice_sifted_key[:n_show]
    b_key_e = eve_result.bob_sifted_key[:n_show]
    agree_e = np.array([1 if a == b else -1 for a, b in zip(a_key_e, b_key_e)])
    mat_e   = agree_e.reshape(5, 8)
    ax4.imshow(mat_e, cmap=cmap, aspect='auto', vmin=-1, vmax=1)
    ax4.set_xticks([]); ax4.set_yticks([])
    agree_pct_e = (agree_e == 1).mean()
    ax4.set_xlabel(f"Agreement: {agree_pct_e:.1%} | Error: {1-agree_pct_e:.1%}",
                   fontsize=8)

    red_p  = mpatches.Patch(color=C_ABORT, label='Mismatch')
    cyan_p = mpatches.Patch(color=C_SAFE,  label='Match')
    ax4.legend(handles=[cyan_p, red_p], fontsize=7,
               facecolor=C_PANEL, edgecolor=C_GRID,
               labelcolor=C_TEXT, loc='lower right')

    # ── 5. QTA timing distribution ────────────────────────────────────────
    ax5 = fig.add_subplot(gs[1, 2])
    styled_ax(ax5, "⑤ QTA Arrival-Time Distribution")

    exp_ns    = expected_arrival_ns(CHANNEL_LENGTH_KM)
    n_legit   = 300
    n_eve_pts = 150
    legit_times = np.random.normal(exp_ns, TIMING_JITTER_NS, n_legit)
    eve_times   = np.random.normal(exp_ns + 1.8, TIMING_JITTER_NS * 1.2, n_eve_pts)

    bins = np.linspace(exp_ns - 6, exp_ns + 8, 50)
    ax5.hist(legit_times, bins=bins, color=C_SAFE,   alpha=0.7,
             label='Legitimate', density=True)
    ax5.hist(eve_times,   bins=bins, color=C_EVE,    alpha=0.7,
             label="Eve's delay",  density=True)

    ax5.axvline(exp_ns,                color=C_ALICE,  linestyle='--', linewidth=1.5,
                label=f"Expected ({exp_ns:.0f} ns)")
    ax5.axvspan(exp_ns - QTA_WINDOW_NS, exp_ns + QTA_WINDOW_NS,
                color=C_SAFE, alpha=0.08, label=f"±{QTA_WINDOW_NS} ns window")

    ax5.set_xlabel("Arrival time offset (ns)")
    ax5.set_ylabel("Density")
    ax5.legend(fontsize=7, facecolor=C_PANEL, edgecolor=C_GRID,
               labelcolor=C_TEXT, loc='upper right')

    # ── 6. Protocol flow diagram ───────────────────────────────────────────
    ax6 = fig.add_subplot(gs[2, :])
    ax6.set_facecolor(C_PANEL)
    ax6.set_xlim(0, 10); ax6.set_ylim(0, 1)
    ax6.axis('off')
    ax6.set_title("⑥ BB84 Protocol Flow  (Alice → Eve → Bob)", 
                  color=C_TEXT, fontsize=10, fontweight='bold', pad=8)

    for spine in ax6.spines.values():
        spine.set_edgecolor(C_GRID)

    steps = [
        (0.5,  "Alice\nprepares\nqubits",       C_ALICE),
        (1.8,  "Alice\ntransmits\nover quantum\nchannel", C_ALICE),
        (3.1,  "Eve?\nIntercept\n& Resend",      C_EVE),
        (4.4,  "Bob\nmeasures\nqubits",          C_BOB),
        (5.7,  "Basis\nsifting\n(public channel)", C_WARN),
        (6.9,  "QBER\nestimation\n(sample bits)", C_THRESH),
        (8.1,  "QTA\ntiming\nverification",      C_SAFE),
        (9.3,  "✓ Secure\nKey / ✗ Abort\nSession", C_TEXT),
    ]

    for i, (x, label, colour) in enumerate(steps):
        ax6.add_patch(mpatches.FancyBboxPatch(
            (x - 0.5, 0.12), 1.0, 0.76,
            boxstyle="round,pad=0.05",
            facecolor=colour + "22", edgecolor=colour, linewidth=1.5
        ))
        ax6.text(x, 0.5, label, ha='center', va='center',
                 color=colour, fontsize=7.5, fontweight='bold',
                 multialignment='center')
        if i < len(steps) - 1:
            ax6.annotate("", xy=(x + 0.55, 0.5), xytext=(x + 0.45, 0.5),
                         arrowprops=dict(arrowstyle="->", color=C_MUTED,
                                         lw=1.5))

    out_path = "/mnt/user-data/outputs/bb84_qkd_security_report.png"
    plt.savefig(out_path, dpi=150, bbox_inches='tight',
                facecolor=C_BG, edgecolor='none')
    plt.close()
    return out_path


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("  BB84 QKD Simulation — Securing Quantum Channel")
    print("  3-Node Network: Alice ──── (Eve?) ──── Bob")
    print("=" * 70)

    # ── Session 1: No Eve ──────────────────────────────────────────────────
    print("\n[SESSION 1]  No eavesdropper present")
    s1 = BB84Session(n_qubits=NUM_QUBITS, eve_present=False)
    r1 = s1.run()
    print(f"  Raw qubits          : {r1.raw_key_length}")
    print(f"  After sifting       : {r1.sifted_key_length}")
    print(f"  QBER                : {r1.qber:.4f}  ({r1.qber:.2%})")
    print(f"  QTA violations      : {r1.qta_violations}")
    print(f"  Session verdict     : {'✓ SECURE' if r1.session_secure else '✗ ABORTED'}")

    # ── Session 2: Eve intercepts 100% ────────────────────────────────────
    print("\n[SESSION 2]  Eve intercepts 100% of qubits")
    s2 = BB84Session(n_qubits=NUM_QUBITS, eve_present=True, eve_intercept_rate=1.0)
    r2 = s2.run()
    print(f"  Raw qubits          : {r2.raw_key_length}")
    print(f"  After sifting       : {r2.sifted_key_length}")
    print(f"  QBER                : {r2.qber:.4f}  ({r2.qber:.2%})")
    print(f"  QTA violations      : {r2.qta_violations}")
    print(f"  Session verdict     : {'✓ SECURE' if r2.session_secure else '✗ ABORTED'}")
    if not r2.session_secure:
        print(f"  Abort reason        : {r2.abort_reason}")

    # ── Session 3: Eve at exactly the threshold ───────────────────────────
    # Theoretical: QBER = 0.25 × intercept_rate → threshold at rate ≈ 0.44
    threshold_rate = QBER_ABORT_THRESHOLD / 0.25
    print(f"\n[SESSION 3]  Eve intercepts at threshold rate ({threshold_rate:.0%})")
    s3 = BB84Session(n_qubits=NUM_QUBITS, eve_present=True,
                     eve_intercept_rate=threshold_rate)
    r3 = s3.run()
    print(f"  QBER                : {r3.qber:.4f}  ({r3.qber:.2%})")
    print(f"  Threshold           : {QBER_ABORT_THRESHOLD:.2%}")
    print(f"  Session verdict     : {'✓ SECURE' if r3.session_secure else '✗ ABORTED'}")

    # ── Sweep across interception rates ───────────────────────────────────
    print("\n[SWEEP]  Averaging QBER over 10 trials per interception rate …")
    rates      = [0.0, 0.1, 0.2, 0.3, 0.4, 0.44, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    sweep_data = sweep_interception_rates(rates, trials=10)
    print(f"\n  {'Rate':>6}  {'Mean QBER':>10}  {'Std':>7}  {'Verdict':>10}")
    print(f"  {'-'*44}")
    for rate in rates:
        mean, std = sweep_data[rate]
        verdict   = "ABORT" if mean >= QBER_ABORT_THRESHOLD else "secure"
        print(f"  {rate:>6.0%}  {mean:>10.4f}  {std:>7.4f}  {verdict:>10}")

    # ── Critical threshold from data ──────────────────────────────────────
    abort_rates = [r for r in rates if sweep_data[r][0] >= QBER_ABORT_THRESHOLD]
    if abort_rates:
        critical = min(abort_rates)
        print(f"\n  ▶  Critical interception rate for abort: ~{critical:.0%}")
        print(f"     (Theoretical prediction: {threshold_rate:.1%})")

    # ── QTA summary ───────────────────────────────────────────────────────
    print("\n[QTA]  Quantum Temporal Authentication")
    print(f"  Channel length      : {CHANNEL_LENGTH_KM} km")
    exp_t = expected_arrival_ns(CHANNEL_LENGTH_KM)
    print(f"  Expected arrival    : {exp_t:.2f} ns")
    print(f"  Tolerance window    : ±{QTA_WINDOW_NS} ns")
    print(f"  No-Eve violations   : {r1.qta_violations}")
    print(f"  Eve-100% violations : {r2.qta_violations}")
    print(f"  QTA triggered abort : {r2.qta_triggered}")

    # ── Generate figure ───────────────────────────────────────────────────
    print("\n[PLOT]  Generating security analysis figure …")
    out = generate_report_figure(sweep_data, r1, r2)
    print(f"  Saved → {out}")
    print("\n" + "=" * 70)
    print("  Simulation complete.")
    print("=" * 70)

    return sweep_data, r1, r2


if __name__ == "__main__":
    main()
