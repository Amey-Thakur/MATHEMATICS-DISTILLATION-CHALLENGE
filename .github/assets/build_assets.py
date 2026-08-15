"""Build the figures used by the READMEs.

Everything here is drawn from this repository's own material: the Stage 1
scores this team actually recorded, and an order 5 counterexample the Stage 2
solver actually found. Nothing is borrowed from the competition site.

    python .github/assets/build_assets.py

Standard library only, so it runs anywhere with no setup.
"""

from pathlib import Path

OUT = Path(__file__).resolve().parent

# House palette, shared by all three SAIR repositories so they read as one set.
PAPER = "#FAFBFC"
INK = "#12141A"
SOFT = "#4A5663"
FAINT = "#6B7684"
RULE = "#D8DEE6"
ACCENT = "#8250DF"      # this repository: proof and logic
ACCEPT = "#2EA043"
REJECT = "#CF222E"

FONT = "Segoe UI, Helvetica Neue, Arial, sans-serif"
MONO = "SFMono-Regular, Consolas, Liberation Mono, monospace"

# An order 5 magma the Stage 2 solver found for itself, kept verbatim from
# stage2/solvers/hybrid/found_witnesses.json.
WITNESS = [
    [0, 0, 0, 0, 0],
    [1, 1, 0, 0, 0],
    [2, 0, 2, 0, 0],
    [3, 2, 3, 3, 2],
    [3, 3, 4, 4, 4],
]

# Stage 1, as measured on the public problem sets. Accuracy and F1, per cent.
STAGE1 = [
    ("Gemma 4 31B IT", [(68.3, 66.3), (54.3, 60.1), (44.5, 56.5)]),
    ("GPT-OSS 120B", [(61.0, 64.4), (50.5, 56.5), (53.2, 64.1)]),
    ("Llama 3.3 70B", [(50.2, 1.3), (49.7, 0.0), (49.8, 0.0)]),
]
SETS = ["normal", "hard", "extra hard"]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size=13, fill=INK, weight=400, anchor="start", font=FONT,
         spacing=None, opacity=None):
    extra = ""
    if spacing:
        extra += f' letter-spacing="{spacing}"'
    if opacity is not None:
        extra += f' opacity="{opacity}"'
    return (f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" '
            f'fill="{fill}" font-weight="{weight}" text-anchor="{anchor}"'
            f'{extra}>{esc(s)}</text>')


def hero():
    """The decision this repository automates, as a six second loop."""
    W, H = 1200, 460
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
         f'width="{W}" height="{H}" role="img" aria-label="Two magma laws go '
         f'in and one machine-checked Lean certificate comes out: a proof when '
         f'the implication holds, a finite counterexample when it fails">']
    p.append(f'<rect width="{W}" height="{H}" fill="{PAPER}"/>')
    p.append(f'<rect x="0" y="0" width="10" height="{H}" fill="{ACCENT}"/>')

    p.append(text(56, 62, "EQUATIONAL IMPLICATION", 12, ACCENT, 600,
                  spacing="0.34em"))
    p.append(text(56, 104, "Does one magma law force another?", 30, INK, 600))
    p.append(text(56, 136,
                  "Every answer ships a certificate a machine can check.",
                  16, SOFT))

    # The question, left column.
    p.append(f'<rect x="56" y="182" width="330" height="196" rx="10" '
             f'fill="#FFFFFF" stroke="{RULE}"/>')
    p.append(text(80, 216, "GIVEN", 11, FAINT, 600, spacing="0.28em"))
    p.append(text(80, 254, "Equation 1", 12, FAINT))
    p.append(text(80, 282, "x = x ◇ y", 22, INK, 500, font=MONO))
    p.append(text(80, 316, "Equation 2", 12, FAINT))
    p.append(text(80, 344, "x = x ◇ x", 22, INK, 500, font=MONO))

    # Two lanes, alternating emphasis.
    for i, (y, colour, label) in enumerate(
            [(228, ACCEPT, "implies"), (330, REJECT, "does not imply")]):
        delay = f"{i * 3}s"
        p.append(f'<g opacity="0.28"><animate attributeName="opacity" '
                 f'values="0.28;1;1;0.28;0.28" keyTimes="0;0.08;0.42;0.5;1" '
                 f'dur="6s" begin="{delay}" repeatCount="indefinite"/>'
                 f'<path d="M 400 {y} H 470" stroke="{colour}" stroke-width="2" '
                 f'fill="none"/>'
                 f'<path d="M 470 {y} l -9 -5 v 10 z" fill="{colour}"/>'
                 f'{text(404, y - 12, label, 12, colour, 600)}</g>')

    # True lane: the Lean proof.
    p.append(f'<g opacity="0.3"><animate attributeName="opacity" '
             f'values="0.3;1;1;0.3;0.3" keyTimes="0;0.08;0.42;0.5;1" dur="6s" '
             f'begin="0s" repeatCount="indefinite"/>'
             f'<rect x="490" y="182" width="654" height="92" rx="10" '
             f'fill="#FFFFFF" stroke="{ACCEPT}"/>'
             f'{text(514, 210, "LEAN 4 PROOF", 11, ACCEPT, 600, spacing="0.28em")}'
             f'{text(514, 242, "intro G _ h", 15, INK, 400, font=MONO)}'
             f'{text(514, 262, "rw [← h x x]", 15, INK, 400, font=MONO)}'
             f'</g>')

    # False lane: a real witness table, filling in cell by cell.
    p.append(f'<g opacity="0.3"><animate attributeName="opacity" '
             f'values="0.3;0.3;0.3;1;1;0.3" '
             f'keyTimes="0;0.42;0.5;0.58;0.92;1" dur="6s" begin="0s" '
             f'repeatCount="indefinite"/>'
             f'<rect x="490" y="292" width="654" height="118" rx="10" '
             f'fill="#FFFFFF" stroke="{REJECT}"/>'
             f'{text(514, 320, "FINITE COUNTEREXAMPLE, ORDER 5", 11, REJECT, 600, spacing="0.28em")}')
    cell, x0, y0 = 20, 516, 336
    for r, row in enumerate(WITNESS):
        for c, v in enumerate(row):
            bx, by = x0 + c * cell, y0 + r * cell
            begin = f"{3 + (r * 5 + c) * 0.045:.3f}s"
            p.append(f'<g opacity="0"><animate attributeName="opacity" '
                     f'values="0;1;1;0" keyTimes="0;0.04;0.62;0.66" dur="6s" '
                     f'begin="{begin}" repeatCount="indefinite"/>'
                     f'<rect x="{bx}" y="{by}" width="{cell - 2}" '
                     f'height="{cell - 2}" rx="3" fill="{REJECT}" '
                     f'opacity="0.09"/>'
                     f'{text(bx + (cell - 2) / 2, by + 14, str(v), 12, REJECT, 500, "middle", MONO)}'
                     f'</g>')
    p.append(text(636, 356, "the hypothesis holds on every pair", 14, SOFT))
    p.append(text(636, 378, "the goal fails on one, so the implication is false",
                  14, SOFT))
    p.append(text(636, 400, "checked exhaustively before it is ever sent",
                  13, FAINT))
    p.append("</g>")

    p.append(f'<path d="M 56 {H - 34} H {W - 56}" stroke="{RULE}"/>')
    p.append(text(56, H - 12, "A deterministic Lean judge accepts or rejects. "
                              "There is no partial credit.", 13, FAINT))
    p.append("</svg>")
    (OUT / "hero.svg").write_text("\n".join(p), encoding="utf-8")


def stage1_scores():
    """What Stage 1 measured, including the failure worth knowing about."""
    W, H = 1100, 470
    left, top, plot_h = 96, 96, 268
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
         f'width="{W}" height="{H}" role="img" aria-label="Stage 1 accuracy '
         f'and F1 for three evaluation models across three difficulty sets. '
         f'Llama 3.3 70B sits at chance accuracy with an F1 near zero because '
         f'it answers a single class">']
    p.append(f'<rect width="{W}" height="{H}" fill="{PAPER}"/>')
    p.append(text(left, 46, "STAGE 1, MEASURED", 12, ACCENT, 600,
                  spacing="0.34em"))
    p.append(text(left, 74, "Accuracy against F1, by model and difficulty",
                  20, INK, 600))

    base = top + plot_h

    # Grid and axis, 0 to 80 per cent.
    for v in range(0, 81, 20):
        y = base - v / 80 * plot_h
        p.append(f'<path d="M {left} {y} H {W - 210}" stroke="{RULE}"/>')
        p.append(text(left - 14, y + 4, f"{v}", 12, FAINT, anchor="end"))

    # Chance line at 50 per cent, the thing the eye should find first.
    y50 = base - 50 / 80 * plot_h
    p.append(f'<path d="M {left} {y50} H {W - 210}" stroke="{FAINT}" '
             f'stroke-dasharray="5 4"/>')
    p.append(text(W - 206, y50 + 4, "chance, 50", 12, FAINT))

    group_w = (W - 210 - left) / (len(STAGE1) * len(SETS))
    bar_w = group_w * 0.3
    idx = 0
    for m, (model, rows) in enumerate(STAGE1):
        for s, (acc, f1) in enumerate(rows):
            gx = left + idx * group_w
            for j, (val, colour, op) in enumerate(
                    [(acc, ACCENT, 1.0), (f1, ACCENT, 0.38)]):
                h = val / 80 * plot_h
                bx = gx + group_w * 0.16 + j * (bar_w + 4)
                p.append(f'<rect x="{bx:.1f}" y="{base - h:.1f}" '
                         f'width="{bar_w:.1f}" height="{h:.1f}" rx="2" '
                         f'fill="{colour}" opacity="{op}"/>')
                if val < 5:
                    p.append(text(bx + bar_w / 2, base - h - 8, f"{val:g}", 11,
                                  REJECT, 600, "middle"))
            p.append(text(gx + group_w / 2, base + 20, SETS[s], 11, FAINT,
                          anchor="middle"))
            idx += 1
        cx = left + (m * len(SETS) + len(SETS) / 2) * group_w
        p.append(text(cx, base + 44, model, 13, INK, 600, anchor="middle"))
        if m:
            gx = left + m * len(SETS) * group_w
            p.append(f'<path d="M {gx:.1f} {top} V {base + 30}" '
                     f'stroke="{RULE}"/>')

    p.append(f'<rect x="{W - 200}" y="{top + 10}" width="14" height="14" '
             f'rx="2" fill="{ACCENT}"/>')
    p.append(text(W - 178, top + 22, "accuracy", 13, SOFT))
    p.append(f'<rect x="{W - 200}" y="{top + 38}" width="14" height="14" '
             f'rx="2" fill="{ACCENT}" opacity="0.38"/>')
    p.append(text(W - 178, top + 50, "F1", 13, SOFT))

    p.append(f'<path d="M {left} {H - 52} H {W - 96}" stroke="{RULE}"/>')
    p.append(text(left, H - 30,
                  "Llama 3.3 70B parses every prompt and still scores an F1 "
                  "near zero: it answers one class throughout,", 13, SOFT))
    p.append(text(left, H - 12,
                  "so accuracy alone would have reported it as a working "
                  "model on a balanced set.", 13, SOFT))
    p.append("</svg>")
    (OUT / "stage1-scores.svg").write_text("\n".join(p), encoding="utf-8")


if __name__ == "__main__":
    hero()
    stage1_scores()
    for f in sorted(OUT.glob("*.svg")):
        print(f"  {f.name}  {f.stat().st_size:,} bytes")
