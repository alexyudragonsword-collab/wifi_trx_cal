package com.wifitrx.workbench

import android.util.Base64
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import org.json.JSONTokener
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** Figure export, on the device that has to open the result.
 *
 * Export shipped in 0.7.1 writing SVG, and SVG is the one image format
 * Android cannot decode anywhere — gallery, file manager, thumbnailer and
 * chat previews all decline it, so the file arrived intact and unopenable.
 * PNG is now the primary export, rasterized by the WebView itself, and
 * this test is the guard that was missing: nothing on-device had ever
 * executed the export path at all.
 *
 * It drives the real shipped UI (assets/ui/index.html + app.js), not a
 * copy of the function — a rasterizer that works only in the test is
 * worth nothing.
 */
@RunWith(AndroidJUnit4::class)
class ExportTest {

    private val inst get() = InstrumentationRegistry.getInstrumentation()

    /** Load the shipped UI in a WebView and return it, page-load done. */
    private fun loadShippedUi(): WebView {
        var web: WebView? = null
        val loaded = CountDownLatch(1)
        inst.runOnMainSync {
            val w = WebView(inst.targetContext)
            w.settings.javaScriptEnabled = true
            w.settings.allowFileAccess = true      // file:///android_asset
            w.webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView, url: String) =
                    loaded.countDown()
            }
            w.loadUrl("file:///android_asset/ui/index.html")
            web = w
        }
        assertTrue("the shipped UI never finished loading",
                   loaded.await(30, TimeUnit.SECONDS))
        return web!!
    }

    /** evaluateJavascript, decoded from its JSON envelope. */
    private fun eval(web: WebView, js: String): String? {
        var out: String? = null
        val done = CountDownLatch(1)
        inst.runOnMainSync {
            web.evaluateJavascript(js) { r -> out = r; done.countDown() }
        }
        assertTrue("JS never came back", done.await(30, TimeUnit.SECONDS))
        val v = JSONTokener(out ?: "null").nextValue()
        return if (v is String) v else null
    }

    /** The toolbar's data readout, in the renderer that has to compute it.
     *
     * Pure arithmetic, so it needs no analysis run — but it is arithmetic
     * shipped as JavaScript, and a readout that is silently wrong is
     * worse than none: it reads like a measurement. */
    @Test
    fun toolbarReportsDataCoordinatesOnDevice() {
        val web = loadShippedUi()
        assertEquals("app.js did not expose the coordinate mapping",
                     "function", eval(web, "typeof window.dataAtPoint"))

        // a 100x50 viewer; one axes over the middle 60%, x 0..10, y -60..0
        val probe = """(() => {
            const axes = [{x0:0.2, y0:0.2, x1:0.8, y1:0.8,
                           xlim:[0,10], ylim:[-60,0],
                           xscale:'linear', yscale:'linear',
                           xlabel:'x', ylabel:'y'}];
            const size = {w:100, h:50}, view = {x:0, y:0, k:1};
            return JSON.stringify({
              mid: window.dataAtPoint(axes, size, view, 50, 25),
              corner: window.dataAtPoint(axes, size, view, 20, 10),
              outside: window.dataAtPoint(axes, size, view, 5, 5),
              zoomed: window.dataAtPoint(axes, size, {x:-100, y:-25, k:2},
                                         0, 25)});
        })()"""
        val r = JSONObject(eval(web, probe)!!)

        val mid = r.getJSONObject("mid")           // axes centre
        assertEquals(5.0, mid.getDouble("x"), 1e-9)
        assertEquals(-30.0, mid.getDouble("y"), 1e-9)

        // figure fractions count y from the bottom: the axes' top-left
        // corner is xlim[0] and ylim[1], not ylim[0]
        val corner = r.getJSONObject("corner")
        assertEquals(0.0, corner.getDouble("x"), 1e-9)
        assertEquals(0.0, corner.getDouble("y"), 1e-9)

        assertTrue("a point off the axes must report nothing",
                   r.isNull("outside"))

        // the same data point, found through a panned and zoomed view
        val zoomed = r.getJSONObject("zoomed")
        assertEquals(5.0, zoomed.getDouble("x"), 1e-9)
        assertEquals(-30.0, zoomed.getDouble("y"), 1e-9)
    }

    /** The cursor's two halves, on the device: the samples it snaps to
     * have to survive the bridge, and the projection it draws them with
     * has to invert the one that reads them.
     *
     * A cursor that lands beside the point it names is worse than none —
     * it looks like a measurement either way. */
    @Test
    fun cursorSamplesAndProjectionSurviveOnDevice() {
        if (!Python.isStarted()) Python.start(AndroidPlatform(inst.targetContext))
        val bridge = Python.getInstance().getModule("bridge")

        // spur_planner is the cheapest analysis that plots something a
        // marker can sit on (bars), so this stays affordable on an AVD
        val run = JSONObject(bridge.callAttr(
            "run", "spur_planner", """{"bw_mhz":320,"band":"6g"}""").toString())
        assertTrue("run: ${run.optString("error")}", run.getBoolean("ok"))
        val raw = bridge.callAttr("page_series", 0).toString()
        assertTrue("NaN reaches JSON.parse as a syntax error, not a value",
                   !raw.contains("NaN") && !raw.contains("Infinity"))
        val page = JSONObject(raw)
        assertTrue("page_series: ${page.optString("error")}",
                   page.getBoolean("ok"))
        val series = page.getJSONArray("series")
        assertTrue("no samples reached the device", series.length() > 0)
        val first = series.getJSONObject(0)
        assertTrue("nothing to snap to", first.optBoolean("snap"))
        val xs = first.getJSONArray("x")
        assertTrue("empty series", xs.length() > 0)

        // project a real sample to the screen and read it back
        val web = loadShippedUi()
        val x = xs.getDouble(0)
        val y = first.getJSONArray("y").getDouble(0)
        val probe = """(() => {
            const a = ${run.getJSONArray("pages").getJSONObject(0)
                          .getJSONArray("axes").getJSONObject(0)};
            const size = {w: 400, h: 300}, view = {x: 0, y: 0, k: 1};
            const p = window.pointAtData(size, view, a, $x, $y);
            const back = window.dataAtPoint([a], size, view, p.px, p.py);
            return JSON.stringify({px: p.px, py: p.py,
                                   x: back && back.x, y: back && back.y});
        })()"""
        val got = JSONObject(eval(web, probe)!!)
        assertEquals("x did not survive the round trip",
                     x, got.getDouble("x"), Math.abs(x) * 1e-9 + 1e-9)
        assertEquals("y did not survive the round trip",
                     y, got.getDouble("y"), Math.abs(y) * 1e-9 + 1e-9)
        assertTrue("the sample projected outside the figure",
                   got.getDouble("px") in 0.0..400.0 &&
                   got.getDouble("py") in 0.0..300.0)
    }

    @Test
    fun figuresRasterizeToPngOnDevice() {
        if (!Python.isStarted()) Python.start(AndroidPlatform(inst.targetContext))
        val bridge = Python.getInstance().getModule("bridge")

        // a real shipped diagram, straight off the device's filesystem —
        // the same bytes the Reference tab hands the export button
        val ref = JSONObject(bridge.callAttr("reference_data").toString())
        assertTrue("reference_data: ${ref.optString("error")}",
                   ref.getBoolean("ok"))
        val entries = ref.getJSONArray("entries")
        var svg: String? = null
        for (i in 0 until entries.length()) {
            val e = entries.getJSONObject(i)
            if (e.has("svg")) { svg = e.getString("svg"); break }
        }
        assertTrue("no shipped SVG to export", svg != null)
        val svgText = svg!!

        val web = loadShippedUi()
        assertEquals("app.js did not expose the rasterizer", "function",
                     eval(web, "typeof window.rasterizePng"))

        // the rasterizer is async; park the outcome and poll for it
        eval(web, "window.__pngResult = null; " +
                  "window.rasterizePng(${JSONObject.quote(svgText)})" +
                  ".then(b => window.__pngResult = b)" +
                  ".catch(e => window.__pngResult = 'ERR:' + e.message); ''")
        var b64: String? = null
        for (attempt in 0 until 60) {
            b64 = eval(web, "window.__pngResult")
            if (b64 != null) break
            Thread.sleep(500)
        }
        assertTrue("rasterizing timed out", b64 != null)
        assertTrue("rasterizing failed: $b64", !b64!!.startsWith("ERR:"))

        val png = Base64.decode(b64, Base64.DEFAULT)
        // PNG magic — proves it is the format a phone can actually open,
        // which was the whole point of the change
        assertTrue("not a PNG: first bytes ${png.take(4)}",
                   png.size > 8 && png[0] == 0x89.toByte() &&
                   png[1] == 'P'.code.toByte() && png[2] == 'N'.code.toByte() &&
                   png[3] == 'G'.code.toByte())
        // a blank canvas would still carry the magic; a real figure is big
        assertTrue("suspiciously small PNG: ${png.size} bytes",
                   png.size > 10_000)
    }
}
