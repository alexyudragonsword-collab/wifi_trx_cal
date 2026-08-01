"""schemdraw signal-chain schematics, returned as inline-SVG strings.

Figure text stays English (project convention).  Every function takes the
RunContext (unused — schematics are structural, not data-driven) so they
plug into Diagram.build like every other builder.
"""
from __future__ import annotations

import schemdraw
from schemdraw import dsp, elements as elm

# paper-style: monochrome, heavier strokes (reference: classic
# transceiver block diagrams — triangles with gain arrows, circled
# mixers, tall DBB block on the right)
_STYLE = dict(unit=2.2, fontsize=11, lw=1.8)
FILL = "white"


def _svg(d: schemdraw.Drawing) -> str:
    svg = d.get_imagedata("svg").decode()
    svg = svg[svg.index("<svg"):]
    return svg.replace("<svg ", '<svg style="max-width:100%;height:auto" ', 1)


def _gain_arrow(d, amp, dx=0.55, dy=0.7):
    """Diagonal programmable-gain arrow across an Amp triangle."""
    cx = (amp.absanchors["input"].x + amp.absanchors["out"].x) / 2.0
    cy = (amp.absanchors["input"].y + amp.absanchors["out"].y) / 2.0
    d += elm.Arrow(headwidth=0.25, headlength=0.3).at(
        (cx - dx, cy - dy)).to((cx + dx, cy + dy))


def architecture(ctx=None) -> str:
    """Direct-conversion transceiver, paper-style layout: RX row on top,
    TX row below flowing right-to-left out of the tall DBB block on the
    right, LO generation (DCO + divider + frac-N ADPLL) in between, and
    the two observation paths (Pdet, switched loopback attenuator) off
    the coupler."""
    Y_RX, Y_TX = 6.0, 0.0
    # NOTE fixed dsp elements inherit the drawing's current direction —
    # every element gets an explicit theta so a mirrored element (DAC,
    # PA on the right-to-left TX row) can't rotate everything after it
    with schemdraw.Drawing(show=False, **_STYLE) as d:
        # ------- DBB: one tall block on the right, both rows terminate on it
        dbb = dsp.Box(w=1.3, h=8.0).theta(0).anchor("W").at(
            (10.6, 3.0)).label("DBB")
        d += dbb

        # ------- antenna + T/R switch node (top left)
        ant = dsp.Antenna().theta(0).at((0.5, 6.4))
        d += ant
        d += elm.Line().at((0.5, 6.4)).to((0.5, Y_RX))
        d += elm.Dot(radius=0.06).at((0.5, Y_RX))

        # ------- RX row, left to right
        sw_rx = elm.Switch().at((0.5, Y_RX)).to((1.9, Y_RX))
        d += sw_rx
        lna = dsp.Amp().theta(0).anchor("input").at((2.2, Y_RX)).label(
            "LNA", "top", ofst=0.45)
        d += lna
        _gain_arrow(d, lna)
        mix_rx = dsp.Mixer().theta(0).anchor("W").at(
            (lna.out[0] + 0.55, Y_RX))
        d += mix_rx
        d += elm.Arrow().at(lna.out).to(mix_rx.W)
        filt_rx = dsp.Filter(response="lp").theta(0).anchor("W").at(
            (mix_rx.E[0] + 0.55, Y_RX)).label("LPF", "top")
        d += filt_rx
        d += elm.Arrow().at(mix_rx.E).to(filt_rx.W)
        vga = dsp.Amp().theta(0).anchor("input").at(
            (filt_rx.E[0] + 0.55, Y_RX)).label("VGA", "top", ofst=0.45)
        d += vga
        _gain_arrow(d, vga)
        d += elm.Arrow().at(filt_rx.E).to(vga.input)
        adc = dsp.Adc().theta(0).anchor("W").at(
            (vga.out[0] + 0.55, Y_RX)).label("ADC")
        d += adc
        d += elm.Arrow().at(vga.out).to(adc.W)
        d += elm.Arrow().at(adc.E).to((dbb.W[0], Y_RX))

        # ------- TX row, right to left out of the DBB (DAC and PA are
        # mirrored so their triangles point along the signal flow)
        dac = dsp.Dac().theta(180).anchor("W").at((9.9, Y_TX)).label(
            "DAC", "top")
        d += dac
        d += elm.Arrow().at((dbb.W[0], Y_TX)).to((9.9, Y_TX))
        filt_tx = dsp.Filter(response="lp").theta(0).anchor("E").at(
            (dac.E[0] - 0.55, Y_TX)).label("LPF", "top")
        d += filt_tx
        d += elm.Arrow().at(dac.E).to(filt_tx.E)
        mix_tx = dsp.Mixer().theta(0).anchor("E").at(
            (filt_tx.W[0] - 0.55, Y_TX)).label("IQ mod", "top")
        d += mix_tx
        d += elm.Arrow().at(filt_tx.W).to(mix_tx.E)
        pa = dsp.Amp().theta(180).anchor("input").at(
            (mix_tx.W[0] - 0.55, Y_TX)).label("PA", "top", ofst=0.45)
        d += pa
        d += elm.Arrow().at(mix_tx.W).to(pa.input)
        cpl = dsp.Box(w=1.2, h=0.9).theta(0).anchor("E").at(
            (pa.out[0] - 0.45, Y_TX)).label("coupler", fontsize=9)
        d += cpl
        d += elm.Arrow().at(pa.out).to(cpl.E)
        # TX throw of the T/R switch: coupler out, up the left edge
        d += elm.Line().at(cpl.W).to((0.5, Y_TX))
        sw_tx = elm.Switch().at((0.5, Y_TX)).to((0.5, Y_RX - 0.55))
        d += sw_tx
        d += elm.Line().at((0.5, Y_RX - 0.55)).to((0.5, Y_RX))

        # ------- observation paths off the coupler tap
        tap = (cpl.S[0], cpl.S[1] - 0.9)
        d += elm.Line().at(cpl.S).to(tap)
        d += elm.Dot(radius=0.06).at(tap)
        pdet = dsp.Box(w=1.6, h=0.8).theta(0).anchor("W").at(
            (tap[0] + 1.0, tap[1])).label("Pdet |·|²", fontsize=9)
        d += pdet
        d += elm.Line().at(tap).to(pdet.W)
        # cal loopback: attenuator hangs below the coupler, then a
        # switched riser (crossing the TX row) back to the LNA input
        att = dsp.Box(w=1.9, h=0.8).theta(0).anchor("N").at(
            (tap[0], tap[1] - 0.8)).label("atten 34–40 dB", fontsize=8)
        d += att
        d += elm.Line().at(tap).to(att.N)
        x_lb = lna.input[0]
        d += elm.Line().at(att.S).to((x_lb, att.S[1]))
        sw_lb = elm.Switch().at((x_lb, att.S[1])).to((x_lb, Y_TX - 0.6))
        d += sw_lb
        d += elm.Line().at((x_lb, Y_TX - 0.6)).to(lna.input)
        d += elm.Dot(radius=0.06).at(lna.input)
        d += elm.Label().at((x_lb + 0.8, 3.3)).label(
            "cal\nloopback", fontsize=9)

        # ------- LO generation between the rows
        dco = dsp.Oscillator().theta(0).anchor("center").at(
            (8.7, 3.3)).label("DCO @ 2f₀", "top", fontsize=9)
        d += dco
        div2 = dsp.Box(w=0.9, h=0.7).theta(0).anchor("E").at(
            (7.8, 3.3)).label("÷2")
        d += div2
        d += elm.Arrow().at(dco.W).to(div2.E)
        # quadrature LO to both mixers
        lo_node = (div2.W[0] - 0.35, 3.3)
        d += elm.Line().at(div2.W).to(lo_node)
        d += elm.Dot(radius=0.06).at(lo_node)
        d += dsp.Wire("-|").at(lo_node).to(mix_rx.S).label(
            "0°/90°", "left", fontsize=9)
        d += elm.Arrowhead().at(mix_rx.S).theta(90)
        d += dsp.Wire("-|").at(lo_node).to(mix_tx.N)
        d += elm.Arrowhead().at(mix_tx.N).theta(-90)
        adpll = dsp.Box(w=2.0, h=0.9).theta(0).anchor("center").at(
            (8.7, 1.6)).label("frac-N\nADPLL", fontsize=9)
        d += adpll
        d += elm.Arrow().at(adpll.N).to(dco.S)
        d += elm.Arrow().at((6.9, 1.6)).to(adpll.W).label(
            "f_ref", "left", fontsize=9)
        d += elm.Arrow().at((dbb.W[0], 1.6)).to(adpll.E).label(
            "FCW", "top", fontsize=9)
    return _svg(d)


def envdet_path(ctx=None) -> str:
    """The RX-independent observation path used by tx_lo_leak_envdet /
    tx_lpf_corner."""
    with schemdraw.Drawing(show=False, **_STYLE) as d:
        d += dsp.Box(w=1.9, h=1).label("TX chain\n(tone + leak)").fill(FILL)
        d += dsp.Arrow().length(0.8)
        d += dsp.Amp().label("PA", "top").fill(FILL)
        d += dsp.Arrow().length(0.8)
        d += dsp.Square().label("|.|²", "top").fill(FILL)
        d += dsp.Arrow().length(0.8)
        d += dsp.Filter(response="lp").label("video LPF", "top").fill(FILL)
        d += dsp.Arrow().length(0.8)
        d += dsp.Adc().label("slow ADC", "top").fill(FILL)
        d += dsp.Arrow().length(0.8)
        d += dsp.Box(w=2.3, h=1).label("beat power\nat f₀ / 2f").fill(
            FILL)
    return _svg(d)


def loopback_offset(ctx=None) -> str:
    """On-chip loopback with the RX-LO frequency offset."""
    with schemdraw.Drawing(show=False, **_STYLE) as d:
        tx = dsp.Box(w=2.0, h=1).label("TX @ LO").fill(FILL)
        d += tx
        d += dsp.Arrow().length(0.9)
        att = dsp.Box(w=1.6, h=0.9).label("atten\n~40 dB").fill(FILL)
        d += att
        d += dsp.Arrow().length(0.9)
        rx = dsp.Box(w=2.6, h=1).label("RX @ LO + Δf").fill(FILL)
        d += rx
        d += dsp.Arrow().length(0.9)
        d += dsp.Box(w=2.6, h=1.1).label("FFT bins:\nTX leak → −Δf\nRX DC → 0"
                                         ).fill(FILL)
    return _svg(d)


def ila_loop(ctx=None) -> str:
    """Indirect-learning DPD: postinverse fitted, then copied.

    Forward path along the top, learning path along the bottom (boxes
    placed by explicit anchor so the two learning blocks cannot
    overlap).
    """
    with schemdraw.Drawing(show=False, **_STYLE) as d:
        dpd = dsp.Box(w=1.8, h=1).theta(0).anchor("W").at((0.0, 0.0)).label(
            "DPD\n(GMP)")
        d += dpd
        pa = dsp.Amp().theta(0).anchor("input").at((dpd.E[0] + 1.0, 0.0)).label(
            "PA", "top", ofst=0.45)
        d += pa
        d += elm.Arrow().at(dpd.E).to(pa.input).label("u", "top", fontsize=10)
        tap_x = pa.out[0] + 1.2
        d += elm.Arrow().at(pa.out).to((tap_x, 0.0)).label(
            "y", "top", fontsize=10)
        d += elm.Dot(radius=0.06).at((tap_x, 0.0))

        y_fit = -2.4
        cap = dsp.Box(w=2.4, h=1.0).theta(0).anchor("E").at(
            (tap_x + 0.9, y_fit)).label("capture / G₀\n(aligned)", fontsize=9)
        d += cap
        d += dsp.Wire("|-").at((tap_x, 0.0)).to(cap.E)
        fit = dsp.Box(w=3.0, h=1.0).theta(0).anchor("E").at(
            (cap.W[0] - 1.0, y_fit)).label(
            "LS fit postinverse\ny/G₀ → u", fontsize=9)
        d += fit
        d += elm.Arrow().at(cap.W).to(fit.E)
        d += dsp.Wire("-|").at(fit.W).to(dpd.S)
        d += elm.Arrowhead().at(dpd.S).theta(90)
        d += elm.Label().at((dpd.S[0] + 1.3, y_fit + 1.0)).label(
            "copy coefficients", fontsize=9)
    return _svg(d)
