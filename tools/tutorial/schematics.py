"""schemdraw signal-chain schematics, returned as inline-SVG strings.

Figure text stays English (project convention).  Every function takes the
RunContext (unused — schematics are structural, not data-driven) so they
plug into Diagram.build like every other builder.
"""
from __future__ import annotations

import schemdraw
from schemdraw import dsp

_STYLE = dict(unit=2.2, fontsize=11)
FILL = "#eef3f8"


def _svg(d: schemdraw.Drawing) -> str:
    svg = d.get_imagedata("svg").decode()
    svg = svg[svg.index("<svg"):]
    return svg.replace("<svg ", '<svg style="max-width:100%;height:auto" ', 1)


def architecture(ctx=None) -> str:
    """Direct-conversion transceiver with both observation paths.

    Both rows flow left to right; the loopback wire returns the coupler
    tap down to the LNA input on the left.
    """
    with schemdraw.Drawing(show=False, **_STYLE) as d:
        # ------- TX row
        d += dsp.Box(w=1.6, h=1).label("digital\nTX").fill("#fdf3e3")
        d += dsp.Arrow().length(0.8)
        d += dsp.Dac().label("DAC", "top").fill(FILL)
        d += dsp.Arrow().length(0.7)
        d += dsp.Filter(response="lp").label("LPF", "top").fill(FILL)
        d += dsp.Arrow().length(0.7)
        d += dsp.Amp().label("VGA", "top").fill(FILL)
        d += dsp.Arrow().length(0.7)
        mix_tx = dsp.Mixer().label("IQ mod", "top").fill(FILL)
        d += mix_tx
        d += dsp.Arrow().at(mix_tx.E).length(0.7)
        pa = dsp.Amp().label("PA", "top").fill("#fde8e8")
        d += pa
        d += dsp.Arrow().at(pa.out).length(0.8)
        cpl = dsp.Box(w=1.2, h=0.9).label("coupler").fill(FILL)
        d += cpl
        d += dsp.Arrow().at(cpl.E).length(0.6)
        d += dsp.Antenna()

        # ------- LO / PLL between the rows
        lo = dsp.Oscillator().at((mix_tx.S[0], mix_tx.S[1] - 2.0)).label(
            "LO 0/90", "left")
        d += lo
        d += dsp.Arrow().at(lo.N).to(mix_tx.S)
        pll = dsp.Box(w=1.8, h=0.9).at(
            (lo.S[0] - 0.9, lo.S[1] - 1.4)).label("frac-N PLL").fill(FILL)
        d += pll
        d += dsp.Arrow().at(pll.N).to(lo.S)

        # ------- observation paths off the coupler tap
        env = dsp.Square().theta(0).at(
            (cpl.S[0] + 1.6, cpl.S[1] - 1.6)).label(
            "env det |.|²", "right").fill("#e8f4e8")
        d += env
        d += dsp.Wire("|-").at(cpl.S).to(env.W)
        att = dsp.Box(w=1.6, h=0.8).theta(0).at(
            (cpl.S[0] - 2.8, cpl.S[1] - 2.6)).label(
            "loopback atten").fill("#e8f4e8")
        d += att
        d += dsp.Wire("|-").at(cpl.S).to(att.E)

        # ------- RX row, left to right, below everything
        y_rx = pll.S[1] - 2.2
        lna = dsp.Amp().at((0.6, y_rx)).label("LNA", "top").fill(FILL)
        d += lna
        # loopback return wire: atten down to LNA input
        d += dsp.Wire("-|").at(att.W).to((lna.input[0] - 0.5,
                                          att.W[1]))
        d += dsp.Wire("|-").at((lna.input[0] - 0.5, att.W[1])).to(lna.input)
        d += dsp.Arrow().at(lna.out).length(0.7)
        mix_rx = dsp.Mixer().label("IQ demod", "top").fill(FILL)
        d += mix_rx
        d += dsp.Wire("-|").at(lo.S).to(mix_rx.N)
        d += dsp.Arrow().at(mix_rx.E).length(0.7)
        d += dsp.Filter(response="lp").label("LPF", "top").fill(FILL)
        d += dsp.Arrow().length(0.7)
        d += dsp.Amp().label("VGA", "top").fill(FILL)
        d += dsp.Arrow().length(0.7)
        d += dsp.Adc().label("ADC", "top").fill(FILL)
        d += dsp.Arrow().length(0.8)
        d += dsp.Box(w=1.6, h=1).label("digital\nRX").fill("#fdf3e3")
    return _svg(d)


def envdet_path(ctx=None) -> str:
    """The RX-independent observation path used by tx_lo_leak_envdet /
    tx_lpf_corner."""
    with schemdraw.Drawing(show=False, **_STYLE) as d:
        d += dsp.Box(w=1.9, h=1).label("TX chain\n(tone + leak)").fill(FILL)
        d += dsp.Arrow().length(0.8)
        d += dsp.Amp().label("PA", "top").fill("#fde8e8")
        d += dsp.Arrow().length(0.8)
        d += dsp.Square().label("|.|²", "top").fill("#e8f4e8")
        d += dsp.Arrow().length(0.8)
        d += dsp.Filter(response="lp").label("video LPF", "top").fill(FILL)
        d += dsp.Arrow().length(0.8)
        d += dsp.Adc().label("slow ADC", "top").fill(FILL)
        d += dsp.Arrow().length(0.8)
        d += dsp.Box(w=2.3, h=1).label("beat power\nat f₀ / 2f").fill(
            "#fdf3e3")
    return _svg(d)


def loopback_offset(ctx=None) -> str:
    """On-chip loopback with the RX-LO frequency offset."""
    with schemdraw.Drawing(show=False, **_STYLE) as d:
        tx = dsp.Box(w=2.0, h=1).label("TX @ f_LO").fill(FILL)
        d += tx
        d += dsp.Arrow().length(0.9)
        att = dsp.Box(w=1.6, h=0.9).label("atten\n~40 dB").fill("#e8f4e8")
        d += att
        d += dsp.Arrow().length(0.9)
        rx = dsp.Box(w=2.6, h=1).label("RX @ f_LO + Δf").fill(FILL)
        d += rx
        d += dsp.Arrow().length(0.9)
        d += dsp.Box(w=2.6, h=1.1).label("FFT bins:\nTX leak → −Δf\nRX DC → 0"
                                         ).fill("#fdf3e3")
    return _svg(d)


def ila_loop(ctx=None) -> str:
    """Indirect-learning DPD: postinverse fitted, then copied."""
    with schemdraw.Drawing(show=False, **_STYLE) as d:
        dpd = dsp.Box(w=1.7, h=1).label("DPD\n(GMP)").fill(FILL)
        d += dpd
        d += dsp.Arrow().length(0.8).label("u", "top")
        pa = dsp.Amp().label("PA", "top").fill("#fde8e8")
        d += pa
        d += dsp.Arrow().at(pa.out).length(1.0).label("y", "top")
        d += dsp.Dot()
        cap = dsp.Box(w=2.2, h=1).at(pa.out, dx=1.0, dy=-2.0).label(
            "capture / G₀\n(aligned)").fill("#e8f4e8")
        d += cap
        d += dsp.Wire("|-").at(pa.out, dx=1.0).to(cap.N)
        fit = dsp.Box(w=2.4, h=1).at(cap.W, dx=-2.2, dy=0).label(
            "LS fit postinverse\ny/G₀ → u").fill("#fdf3e3")
        d += fit
        d += dsp.Arrow().at(cap.W).to(fit.E)
        d += dsp.Wire("-|").at(fit.W, dx=-0.7).to(dpd.S).label(
            "copy coefficients", "left", fontsize=9)
        d += dsp.Arrowhead().at(dpd.S)
    return _svg(d)
