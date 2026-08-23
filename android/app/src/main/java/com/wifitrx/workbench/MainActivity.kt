package com.wifitrx.workbench

import android.annotation.SuppressLint
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.FileProvider
import androidx.webkit.WebViewAssetLoader
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import java.io.File

/** Thin shell: a WebView over assets/ui plus the Python bridge.
 *
 * All state and logic live on the two far sides (Python analyses, JS UI);
 * this class only ferries JSON strings between them — the Android
 * counterpart of the "decides nothing" rule the desktop inspector page
 * is tested for.
 */
class MainActivity : ComponentActivity() {

    private lateinit var web: WebView
    // runs are strictly serial, so one flag is enough to route the result
    private var lastWasSelfCheck = false

    private val pickJson =
        registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
            if (uri != null) inspectUri(uri)
        }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!Python.isStarted()) Python.start(AndroidPlatform(this))

        val assets = WebViewAssetLoader.Builder()
            .addPathHandler("/ui/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()

        web = WebView(this)
        web.settings.javaScriptEnabled = true
        web.settings.allowFileAccess = false
        web.settings.allowContentAccess = false
        web.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(
                view: WebView, request: WebResourceRequest
            ): WebResourceResponse? = assets.shouldInterceptRequest(request.url)

            // belt to the manifest's braces: no external navigation ever
            override fun shouldOverrideUrlLoading(
                view: WebView, request: WebResourceRequest
            ): Boolean = true
        }
        web.addJavascriptInterface(Bridge(), "Native")
        setContentView(web)
        web.loadUrl("https://appassets.androidplatform.net/ui/ui/index.html")

        AnalysisService.onResult = { json ->
            val fn = if (lastWasSelfCheck) "ui.onSelfCheckResult"
                     else "ui.onRunResult"
            runOnUiThread { emit(fn, json) }
        }
    }

    private fun emit(fn: String, json: String) {
        // JSON is passed as a JS string literal; JSONObject.quote escapes it
        web.evaluateJavascript("$fn(${JSONObject.quote(json)})", null)
    }

    private fun inspectUri(uri: Uri) {
        val text = contentResolver.openInputStream(uri)!!
            .bufferedReader().use { it.readText() }
        val out = Python.getInstance().getModule("bridge")
            .callAttr("inspect_cal_state", text).toString()
        emit("ui.onInspectResult", out)
    }

    inner class Bridge {
        private val py get() = Python.getInstance().getModule("bridge")

        @JavascriptInterface
        fun listSpecs(): String = py.callAttr("list_specs").toString()

        @JavascriptInterface
        fun referenceData(): String = py.callAttr("reference_data").toString()

        @JavascriptInterface
        fun referenceVersion(): String =
            py.callAttr("reference_version").toString()

        /** Export a text artefact (an SVG figure or reference diagram).
         *
         * The desktop offers a save dialog; Android has no equivalent
         * idiom, so the file lands in app storage and goes straight to
         * the share sheet — same treatment cal-state export already gets. */
        @JavascriptInterface
        fun saveText(name: String, text: String): String {
            return try {
                val dir = File(filesDir, "cal_state").apply { mkdirs() }
                val safe = name.replace(Regex("[^A-Za-z0-9_.-]+"), "_")
                val out = File(dir, safe)
                out.writeText(text)
                val uri = FileProvider.getUriForFile(
                    this@MainActivity, "com.wifitrx.workbench.files", out)
                val send = Intent(Intent.ACTION_SEND).apply {
                    type = if (safe.endsWith(".svg")) "image/svg+xml"
                           else "text/plain"
                    putExtra(Intent.EXTRA_STREAM, uri)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
                startActivity(Intent.createChooser(send, "Share $safe"))
                """{"ok": true, "path": ${JSONObject.quote(out.absolutePath)}}"""
            } catch (e: Throwable) {
                """{"ok": false, "error": ${JSONObject.quote(e.toString())}}"""
            }
        }

        @JavascriptInterface
        fun run(key: String, paramsJson: String) {
            lastWasSelfCheck = false
            AnalysisService.launch(this@MainActivity, key, paramsJson)
        }

        @JavascriptInterface
        fun selfCheck() {
            lastWasSelfCheck = true
            AnalysisService.launch(this@MainActivity,
                                   AnalysisService.SELF_CHECK, "{}")
        }

        @JavascriptInterface
        fun saveCalState(): String {
            val dir = File(filesDir, "cal_state").apply { mkdirs() }
            val out = py.callAttr("save_cal_state", dir.absolutePath).toString()
            val parsed = JSONObject(out)
            if (parsed.optBoolean("ok")) {
                val json = File(parsed.getString("path"))
                val uri = FileProvider.getUriForFile(
                    this@MainActivity, "com.wifitrx.workbench.files", json)
                val send = Intent(Intent.ACTION_SEND).apply {
                    type = "application/json"
                    putExtra(Intent.EXTRA_STREAM, uri)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
                startActivity(Intent.createChooser(send, "Share cal-state"))
            }
            return out
        }

        @JavascriptInterface
        fun pickAndInspect() {
            // delivered cal_state.json files often carry a generic MIME
            runOnUiThread { pickJson.launch(arrayOf("*/*")) }
        }
    }
}
