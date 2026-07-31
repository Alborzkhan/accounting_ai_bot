package com.narin.app

import android.app.Application
import android.os.Build
import android.util.Log
import java.io.PrintWriter
import java.io.StringWriter
import java.net.HttpURLConnection
import java.net.URL

/**
 * ثبت‌نام اولیه‌ی اپ + گزارش‌دهی خطا.
 * هر خطای پیش‌بینی‌نشده به سرور فرستاده می‌شود تا در log سمت سرور دیده شود.
 */
class CrashReporter : Application() {

    override fun onCreate() {
        super.onCreate()
        val defaultHandler = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            try {
                val sw = StringWriter()
                throwable.printStackTrace(PrintWriter(sw))
                val report = buildString {
                    appendLine("DEVICE: ${Build.MANUFACTURER} ${Build.MODEL} (${Build.VERSION.RELEASE}, API ${Build.VERSION.SDK_INT})")
                    appendLine("THREAD: ${thread.name}")
                    appendLine("EXCEPTION: ${throwable.javaClass.name}: ${throwable.message}")
                    appendLine("STACK:")
                    appendLine(sw.toString())
                }
                Log.e("NarinCrash", report)
                sendCrash(report)
            } catch (e: Exception) {
                Log.e("NarinCrash", "failed to send crash: ${e.message}")
            } finally {
                defaultHandler?.uncaughtException(thread, throwable)
            }
        }
    }

    private fun sendCrash(report: String) {
        Thread {
            try {
                val base = BuildConfig.APP_BASE_URL.substringBeforeLast("/")
                val url = URL("$base/crash-report")
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.connectTimeout = 5000
                conn.readTimeout = 5000
                conn.setRequestProperty("Content-Type", "application/json")
                conn.doOutput = true
                val json = "{\"text\": ${escapeJson(report)}}"
                conn.outputStream.use { it.write(json.toByteArray()) }
                conn.responseCode
                conn.disconnect()
            } catch (e: Exception) {
                // سکوت؛ فقط دیباگ
            }
        }.start()
    }

    private fun escapeJson(s: String): String {
        val sb = StringBuilder("\"")
        for (c in s) {
            when (c) {
                '"' -> sb.append("\\\"")
                '\\' -> sb.append("\\\\")
                '\n' -> sb.append("\\n")
                '\r' -> sb.append("\\r")
                '\t' -> sb.append("\\t")
                else -> if (c.code < 0x20) sb.append("\\u%04x".format(c.code)) else sb.append(c)
            }
        }
        sb.append("\"")
        return sb.toString()
    }
}
