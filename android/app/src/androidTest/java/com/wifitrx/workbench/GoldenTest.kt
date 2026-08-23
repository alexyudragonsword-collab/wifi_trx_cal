package com.wifitrx.workbench

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** On-device checks: the same physics, and the pages that read files.
 *
 * The golden comparison itself lives in bridge.self_check() — the very
 * function the app's Self-check tab calls — so CI and the phone cannot
 * adjudicate by different rules.  This test only asserts its verdict.
 */
@RunWith(AndroidJUnit4::class)
class GoldenTest {

    private fun bridge(): PyObject {
        val inst = InstrumentationRegistry.getInstrumentation()
        if (!Python.isStarted())
            Python.start(AndroidPlatform(inst.targetContext))
        return Python.getInstance().getModule("bridge")
    }

    /** The Reference tab reads shipped SVGs off the filesystem, and the
     * Inspector renders the shared section tables.  Neither was exercised
     * on-device before, which is how a missing assets/ tree reached the
     * phone as a FileNotFoundError while every desktop test passed. */
    @Test
    fun referenceAndInspectorRenderOnDevice() {
        val bridge = bridge()

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
        val out = JSONObject(bridge().callAttr("self_check").toString())
        assertTrue("self_check: ${out.optString("error")}",
                   out.getBoolean("ok"))

        // name every failing metric, so a red run is diagnosable from the
        // log alone rather than needing a device in hand
        val failures = StringBuilder()
        val cases = out.getJSONArray("cases")
        for (i in 0 until cases.length()) {
            val c = cases.getJSONObject(i)
            if (c.getBoolean("passed")) continue
            val rows = c.getJSONArray("rows")
            for (j in 0 until rows.length()) {
                val r = rows.getJSONObject(j)
                if (r.getString("verdict") != "ok")
                    failures.append("\n  ${c.getString("key")}.")
                        .append(r.getString("metric"))
                        .append(": desktop=${r.get("desktop")}")
                        .append(" device=${r.get("device")}")
                        .append(" delta=${r.getString("delta")}")
            }
        }
        assertTrue("golden mismatch on ${out.getJSONObject("platform")}"
                   + failures, out.getBoolean("passed"))
    }
}
