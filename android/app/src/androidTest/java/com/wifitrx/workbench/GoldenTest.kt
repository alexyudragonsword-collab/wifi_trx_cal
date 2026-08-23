package com.wifitrx.workbench

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.math.abs

/** On-device golden check: the same physics on the phone.
 *
 * Replays the three analyses recorded by android/tools/make_golden.py on
 * the desktop and compares metric-by-metric.  Numeric tolerance 0.05 dB
 * absolute or 1e-3 relative — Android BLAS/FFT builds differ from the
 * desktop's, bit identity is not the claim; non-numeric values must
 * match exactly.
 */
@RunWith(AndroidJUnit4::class)
class GoldenTest {

    /** The Reference tab reads shipped SVGs off the filesystem, and the
     * Inspector renders the shared section tables.  Neither was exercised
     * on-device before, which is how a missing assets/ tree reached the
     * phone as a FileNotFoundError while every desktop test passed. */
    @Test
    fun referenceAndInspectorRenderOnDevice() {
        val inst = InstrumentationRegistry.getInstrumentation()
        if (!Python.isStarted())
            Python.start(AndroidPlatform(inst.targetContext))
        val bridge = Python.getInstance().getModule("bridge")

        val ref = JSONObject(bridge.callAttr("reference_data").toString())
        assertTrue("reference_data: ${ref.optString("error")}",
                   ref.getBoolean("ok"))
        val entries = ref.getJSONArray("entries")
        var svgs = 0
        for (i in 0 until entries.length())
            if (entries.getJSONObject(i).has("svg")) svgs++
        assertTrue("no schematic SVG reached the device", svgs > 0)

        // a minimal but structurally real document: findings + sections
        val doc = """{"format":"wifitrx-cal-state-v1","provenance":
            {"tool":"test"},"results":[{"name":"step","passed":true,
            "metrics_after":{"m":1.0}}]}"""
        val insp = JSONObject(
            bridge.callAttr("inspect_cal_state", doc).toString())
        assertTrue("inspect: ${insp.optString("error")}",
                   insp.getBoolean("ok"))
        assertTrue("inspector showed no tables",
                   insp.getJSONArray("sections").length() > 0)
    }

    @Test
    fun metricsMatchDesktopGolden() {
        val inst = InstrumentationRegistry.getInstrumentation()
        if (!Python.isStarted())
            Python.start(AndroidPlatform(inst.targetContext))
        val bridge = Python.getInstance().getModule("bridge")

        val golden = org.json.JSONArray(
            inst.context.assets.open("golden.json")
                .bufferedReader().use { it.readText() })

        for (i in 0 until golden.length()) {
            val case = golden.getJSONObject(i)
            val key = case.getString("key")
            val out = JSONObject(bridge.callAttr(
                "run", key, case.getJSONObject("params").toString())
                .toString())
            assertTrue("$key failed: ${out.optString("error")}",
                       out.getBoolean("ok"))
            assertTrue("$key page count",
                       out.getJSONArray("pages").length() ==
                           case.getInt("n_pages"))

            val want = case.getJSONObject("metrics")
            val got = out.getJSONObject("metrics")
            for (name in want.keys()) {
                val w = want.get(name)
                val g = got.opt(name)
                if (w is Number) {
                    val wv = w.toDouble()
                    val gv = (g as Number).toDouble()
                    val ok = abs(gv - wv) <= 0.05 ||
                        abs(gv - wv) <= 1e-3 * abs(wv)
                    assertTrue("$key.$name: desktop=$wv device=$gv", ok)
                } else {
                    assertTrue("$key.$name: desktop=$w device=$g",
                               w.toString() == g.toString())
                }
            }
        }
    }
}
