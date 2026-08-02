package com.narin.app

import android.Manifest
import android.app.Activity
import android.app.DownloadManager
import android.content.Context
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.view.View
import android.webkit.CookieManager
import android.webkit.URLUtil
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView

/**
 * نسخه‌ی ساده و مطمئن: یک Activity ساده (بدون AppCompat) که فقط یک WebView را باز می‌کند.
 * تمام کد در try/catch است تا به‌جای crash، خطا روی صفحه نشان داده شود.
 */
class MainActivity : Activity() {

    private var webView: WebView? = null
    private var progressBar: ProgressBar? = null
    private var errorLayout: LinearLayout? = null
    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    private val baseUrl: String get() = BuildConfig.APP_BASE_URL

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        try {
            setContentView(R.layout.activity_main)
            webView = findViewById(R.id.webView)
            progressBar = findViewById(R.id.progressBar)
            errorLayout = findViewById(R.id.errorLayout)
            val retryButton = findViewById<Button>(R.id.retryButton)

            setupWebView()
            registerNetworkMonitor()

            retryButton.setOnClickListener { loadApp() }
            requestPermissionsCompat()
            loadApp()
        } catch (e: Throwable) {
            showFatalError("خطا در راه‌اندازی: ${e.javaClass.name}: ${e.message}")
        }
    }

    private fun setupWebView() {
        val wv = webView ?: return
        val settings: WebSettings = wv.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.databaseEnabled = true
        settings.mediaPlaybackRequiresUserGesture = false
        settings.setSupportZoom(false)

        CookieManager.getInstance().setAcceptCookie(true)

        wv.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView, url: String?, favicon: android.graphics.Bitmap?) {
                progressBar?.visibility = View.VISIBLE
                errorLayout?.visibility = View.GONE
            }
            override fun onPageFinished(view: WebView, url: String?) {
                progressBar?.visibility = View.GONE
                errorLayout?.visibility = View.GONE
            }
            @Deprecated("Deprecated in Java")
            override fun onReceivedError(
                view: WebView,
                errorCode: Int,
                description: String,
                failingUrl: String
            ) {
                if (failingUrl == baseUrl || failingUrl.startsWith(baseUrl.substringBeforeLast("/"))) {
                    showConnectionError()
                }
            }
        }
    }

    private fun loadApp() {
        try {
            errorLayout?.visibility = View.GONE
            webView?.loadUrl(baseUrl)
        } catch (e: Throwable) {
            showFatalError("خطا در بارگذاری: ${e.javaClass.name}: ${e.message}")
        }
    }

    private fun showConnectionError() {
        progressBar?.visibility = View.GONE
        errorLayout?.visibility = View.VISIBLE
    }

    private fun showFatalError(msg: String) {
        try {
            val tv = TextView(this)
            tv.text = msg
            tv.setTextSize(16f)
            tv.setPadding(24, 24, 24, 24)
            setContentView(tv)
        } catch (e: Throwable) {
            // آخرین راه
        }
    }

    private fun requestPermissionsCompat() {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                val missing = ArrayList<String>()
                if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED)
                    missing.add(Manifest.permission.RECORD_AUDIO)
                if (Build.VERSION.SDK_INT >= 33 &&
                    checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
                    missing.add(Manifest.permission.POST_NOTIFICATIONS)
                if (missing.isNotEmpty())
                    requestPermissions(missing.toTypedArray(), 100)
            }
        } catch (e: Throwable) {
            // بی‌خیال
        }
    }

    private fun registerNetworkMonitor() {
        try {
            val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
            val request = NetworkRequest.Builder()
                .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .build()
            networkCallback = object : ConnectivityManager.NetworkCallback() {
                override fun onAvailable(network: Network) {
                    runOnUiThread {
                        if (webView?.url.isNullOrEmpty() && errorLayout?.visibility == View.VISIBLE) {
                            loadApp()
                        }
                    }
                }
            }
            cm.registerNetworkCallback(request, networkCallback!!)
        } catch (e: Throwable) {
            // بی‌خیال
        }
    }

    override fun onBackPressed() {
        val wv = webView
        if (wv != null && wv.canGoBack()) {
            wv.goBack()
        } else {
            super.onBackPressed()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        try {
            networkCallback?.let {
                (getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager)
                    .unregisterNetworkCallback(it)
            }
        } catch (e: Throwable) {
            // بی‌خیال
        }
    }
}
