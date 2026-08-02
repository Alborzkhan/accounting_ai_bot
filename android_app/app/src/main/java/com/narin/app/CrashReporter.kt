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
        // نشانه‌ی شروع: یعنی اپ به Application رسیده و می‌تواند به سرور وصل شود
        sendSync("APP-START v${BuildConfig.VERSION_NAME} (${Build.VERSION.RELEASE}/API ${Build.VERSION.SDK_INT}) ${Build.MANUFACTURER} ${Build.MODEL}")
        val defaultHandler = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            try {
                val sw = StringWriter()
                throwable.printStackTrace(PrintWriter(sw))
                val report = buildString {
                    appendLine("APP: v${BuildConfig.VERSION_NAME} (code ${BuildConfig.VERSION_CODE})")
                    appendLine("DEVICE: ${Build.MANUFACTURER} ${Build.MODEL} (${Build.VERSION.RELEASE}, API ${Build.VERSION.SDK_INT})")
                    appendLine("THREAD: ${thread.name}")
                    appendLine("EXCEPTION: ${throwable.javaClass.name}: ${throwable.message}")
                    appendLine("STACK:")
                    appendLine(sw.toString())
                }
                Log.e("NarinCrash", report)
                // ارسال همزمان (blocking) تا قبل از مرگ پروسه حتماً برسد
                sendSync(report)
            } catch (e: Exception) {
                Log.e("NarinCrash", "failed to send crash: ${e.message}")
            } finally {
                defaultHandler?.uncaughtException(thread, throwable)
            }
        }
    }

    private fun sendSync(report: String) {
        try {
            val base = BuildConfig.APP_BASE_URL.substringBeforeLast("/")
            val url = URL("$base/crash-report")
            val conn = url.openConnection() as HttpURLConnection
            conn.requestMethod = "POST"
            conn.connectTimeout = 8000
            conn.readTimeout = 8000
            conn.setRequestProperty("Content-Type", "application/json")
            conn.doOutput = true
            val json = "{\"text\": ${escapeJson(report)}}"
            conn.outputStream.use { it.write(json.toByteArray()) }
            conn.responseCode
            conn.disconnect()
        } catch (e: Exception) {
            Log.e("NarinCrash", "sendSync error: ${e.message}")
        }
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
