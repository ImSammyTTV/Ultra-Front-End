package com.imsammyttv.ultrafrontend

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.Settings
import android.view.InputDevice
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit

/** The whole app: one full-screen WebView showing the same page as on Windows and Mac, served by HttpServer. */
class MainActivity : Activity() {
    companion object {
        @Volatile var instance: MainActivity? = null
        private var server: HttpServer? = null
        private var backend: Backend? = null
        const val PORT = 8137
        private const val PICK_FOLDER = 1
    }

    private lateinit var web: WebView
    private var folderResult: CompletableFuture<Uri?>? = null
    private var allFilesResult: CompletableFuture<Boolean>? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(saved: Bundle?) {
        super.onCreate(saved)
        instance = this
        Store.dir = filesDir
        Library.ctx = applicationContext
        if (server == null) {
            Systems.load(this)
            val version = packageManager.getPackageInfo(packageName, 0).versionName ?: "0"
            val b = Backend(applicationContext, version)
            backend = b
            server = HttpServer(PORT) { b.handle(it) }.also { it.start() }
            Thread {
                Library.scan()
                while (true) {  // new versions: hourly, or soon again when GitHub couldn't be reached (no network yet at boot)
                    Thread.sleep(if (b.checkUpdate()) 3_600_000L else 120_000L)
                }
            }.apply { isDaemon = true }.start()
        }
        if (applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE != 0) WebView.setWebContentsDebuggingEnabled(true)
        web = WebView(this)
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false
            loadWithOverviewMode = true
            useWideViewPort = true
        }
        web.setBackgroundColor(0xff000000.toInt())
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, req: android.webkit.WebResourceRequest): Boolean {
                val u = req.url
                if (u.host == "127.0.0.1") return false
                open(Intent(Intent.ACTION_VIEW, u))  // links out (a release page, a store page) open in the browser
                return true
            }
        }
        web.webChromeClient = WebChromeClient()
        web.addJavascriptInterface(Bridge(), "AndroidApp")
        web.isFocusable = true
        setContentView(web)
        fullScreen()
        web.loadUrl("http://127.0.0.1:$PORT/")
    }

    inner class Bridge {
        @JavascriptInterface fun quit() = runOnUiThread { finishAndRemoveTask() }
    }

    private fun fullScreen() {
        if (Build.VERSION.SDK_INT >= 30) {
            window.insetsController?.let {
                it.hide(WindowInsets.Type.systemBars())
                it.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            }
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_FULLSCREEN or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
        }
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) fullScreen()
    }

    override fun onResume() {
        super.onResume()
        instance = this
        Launcher.endSession()  // back from a game: its time played is counted
        allFilesResult?.let { it.complete(Library.canReadFiles()); allFilesResult = null }  // back from the permission screen
        Pad.pads = countPads()
    }

    override fun onPause() {
        super.onPause()
        Pad.releaseAll()
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        web.destroy()
        super.onDestroy()
    }

    fun quit() = runOnUiThread { finishAndRemoveTask() }

    /** Opens the first intent something can handle. */
    fun open(vararg intents: Intent) = runOnUiThread {
        for (i in intents) try { startActivity(i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); return@runOnUiThread } catch (_: Exception) {}
    }

    fun installApk(uri: Uri) = runOnUiThread {
        if (Build.VERSION.SDK_INT >= 26 && !packageManager.canRequestPackageInstalls()) {
            open(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName")))
            return@runOnUiThread
        }
        open(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
    }

    // ---------------------------------------------------------------- asked from the server's threads, answered here
    /** The folder picker; blocks the calling (server) thread until the user picks or backs out. */
    fun pickFolder(): Uri? {
        val f = CompletableFuture<Uri?>()
        folderResult = f
        runOnUiThread {
            val i = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION or
                Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
            try { startActivityForResult(i, PICK_FOLDER) } catch (e: Exception) { f.complete(null) }
        }
        return try { f.get(10, TimeUnit.MINUTES) } catch (e: Exception) { null }
    }

    /** "All files access" (Android 11+), so ROMs can be read by path as the emulators do. */
    fun askAllFiles(): Boolean {
        if (Library.canReadFiles()) return true
        val f = CompletableFuture<Boolean>()
        runOnUiThread {
            allFilesResult = f
            open(Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION, Uri.parse("package:$packageName")),
                Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION))
        }
        return try { f.get(10, TimeUnit.MINUTES) } catch (e: Exception) { false }
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != PICK_FOLDER) return
        val uri = if (resultCode == RESULT_OK) data?.data else null
        if (uri != null) try {
            contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        } catch (_: Exception) {}
        folderResult?.complete(uri)
        folderResult = null
    }

    // ---------------------------------------------------------------- the controller
    private fun countPads() = InputDevice.getDeviceIds().count { id ->
        val d = InputDevice.getDevice(id) ?: return@count false
        !d.isVirtual && (d.sources and InputDevice.SOURCE_GAMEPAD == InputDevice.SOURCE_GAMEPAD || d.sources and InputDevice.SOURCE_JOYSTICK == InputDevice.SOURCE_JOYSTICK)
    }

    private fun padAction(code: Int): String? = when (code) {
        KeyEvent.KEYCODE_BUTTON_A, KeyEvent.KEYCODE_DPAD_CENTER -> "ok"
        KeyEvent.KEYCODE_BUTTON_B -> "back"
        KeyEvent.KEYCODE_BUTTON_Y, KeyEvent.KEYCODE_BUTTON_START -> "options"
        KeyEvent.KEYCODE_BUTTON_L1 -> "prevTab"
        KeyEvent.KEYCODE_BUTTON_R1 -> "nextTab"
        KeyEvent.KEYCODE_BUTTON_SELECT, KeyEvent.KEYCODE_BUTTON_MODE -> "system"
        else -> null
    }

    private fun direction(code: Int): String? = when (code) {
        KeyEvent.KEYCODE_DPAD_UP -> "up"; KeyEvent.KEYCODE_DPAD_DOWN -> "down"
        KeyEvent.KEYCODE_DPAD_LEFT -> "left"; KeyEvent.KEYCODE_DPAD_RIGHT -> "right"; else -> null
    }

    override fun dispatchKeyEvent(e: KeyEvent): Boolean {
        val fromPad = e.source and InputDevice.SOURCE_GAMEPAD == InputDevice.SOURCE_GAMEPAD ||
            e.source and InputDevice.SOURCE_JOYSTICK == InputDevice.SOURCE_JOYSTICK || e.source and InputDevice.SOURCE_DPAD == InputDevice.SOURCE_DPAD
        if (e.keyCode == KeyEvent.KEYCODE_BACK && !fromPad) {  // the system Back gesture or button: the page's Back
            if (e.action == KeyEvent.ACTION_UP) Pad.emit("back")
            return true
        }
        if (!fromPad) return super.dispatchKeyEvent(e)  // a keyboard: the page reads its keys itself
        Pad.pads = maxOf(Pad.pads, 1)
        direction(e.keyCode)?.let { Pad.hold(it, e.action == KeyEvent.ACTION_DOWN); return true }
        val act = padAction(e.keyCode) ?: if (e.keyCode == KeyEvent.KEYCODE_BACK) "back" else null
        if (act != null) {
            if (e.action == KeyEvent.ACTION_DOWN && e.repeatCount == 0) Pad.emit(act)
            return true
        }
        return super.dispatchKeyEvent(e)
    }

    private val held = HashMap<String, Boolean>()

    override fun dispatchGenericMotionEvent(e: MotionEvent): Boolean {
        if (e.source and InputDevice.SOURCE_JOYSTICK != InputDevice.SOURCE_JOYSTICK || e.action != MotionEvent.ACTION_MOVE) return super.dispatchGenericMotionEvent(e)
        val x = e.getAxisValue(MotionEvent.AXIS_X).let { if (Math.abs(it) > .55f) it else e.getAxisValue(MotionEvent.AXIS_HAT_X) }
        val y = e.getAxisValue(MotionEvent.AXIS_Y).let { if (Math.abs(it) > .55f) it else e.getAxisValue(MotionEvent.AXIS_HAT_Y) }
        mapOf("left" to (x < -.55f), "right" to (x > .55f), "up" to (y < -.55f), "down" to (y > .55f)).forEach { (dir, on) ->
            if ((held[dir] ?: false) != on) { held[dir] = on; Pad.hold(dir, on) }
        }
        return true
    }
}
