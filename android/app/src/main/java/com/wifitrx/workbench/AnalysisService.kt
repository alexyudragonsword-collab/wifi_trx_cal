package com.wifitrx.workbench

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder
import android.os.PowerManager
import com.chaquo.python.Python
import kotlin.concurrent.thread

/** Foreground service so a minutes-long calibration survives the screen
 * turning off or the activity being backgrounded.  Runs are strictly
 * serial (the analyses mutate chain state); there is no mid-run cancel —
 * the analysis functions have no cancellation points, which is a
 * documented limitation, not an oversight.
 */
class AnalysisService : Service() {

    companion object {
        /** Sentinel key: the self-check replays several analyses and is
         * just as long-running, so it rides the same foreground service
         * rather than blocking the UI thread. */
        const val SELF_CHECK = "__self_check__"

        // Result hand-off to whatever activity is alive; a run whose
        // activity died still completes and the notification closes.
        var onResult: ((String) -> Unit)? = null

        fun launch(ctx: Context, key: String, paramsJson: String) {
            ctx.startForegroundService(
                Intent(ctx, AnalysisService::class.java)
                    .putExtra("key", key)
                    .putExtra("params", paramsJson))
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent, flags: Int, id: Int): Int {
        startForeground(1, note("running ${intent.getStringExtra("key")}…"))
        val wake = (getSystemService(Context.POWER_SERVICE) as PowerManager)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "wifitrx:run")
        wake.acquire(30 * 60 * 1000L)
        thread(name = "wifitrx-analysis") {
            val key = intent.getStringExtra("key")
            val out = try {
                val bridge = Python.getInstance().getModule("bridge")
                if (key == SELF_CHECK) bridge.callAttr("self_check").toString()
                else bridge.callAttr("run", key,
                                     intent.getStringExtra("params")).toString()
            } catch (e: Throwable) {
                """{"ok": false, "error": ${org.json.JSONObject.quote(
                    e.toString())}}"""
            } finally {
                wake.release()
            }
            onResult?.invoke(out)
            stopSelf()
        }
        return START_NOT_STICKY
    }

    private fun note(text: String): Notification {
        val ch = NotificationChannel("run", "Analysis runs",
                                     NotificationManager.IMPORTANCE_LOW)
        (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
            .createNotificationChannel(ch)
        return Notification.Builder(this, "run")
            .setContentTitle("wifitrx workbench")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .build()
    }
}
