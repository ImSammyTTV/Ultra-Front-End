package com.imsammyttv.ultrafrontend

import android.content.Context
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.Typeface
import android.os.Environment
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import androidx.core.graphics.drawable.toBitmap
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.security.MessageDigest

/** A game on the home screen: an Android game, or a ROM in the ROMs folder. */
class Game(val id: String, var title: String, val source: String, val system: String?, val pkg: String?, val file: File?, val added: Long) {
    val original = title
}

object Library {
    lateinit var ctx: Context
    @Volatile var games: List<Game> = emptyList()
    @Volatile var byId: Map<String, Game> = emptyMap()
    @Volatile var counts: Map<String, Int> = emptyMap()  // console -> ROMs found
    @Volatile var scanned = false
    val errors = mutableListOf<String>()

    fun romRoot(): File? = Store.load("config.json").optString("romRoot").takeIf { it.isNotEmpty() }?.let { File(it) }
    fun defaultRomRoot() = File(Environment.getExternalStorageDirectory(), "ROMs")
    fun canReadFiles() = android.os.Build.VERSION.SDK_INT < 30 || Environment.isExternalStorageManager()

    /** Packages of every emulator we know, so they don't show up as games themselves. */
    private val emulatorPackages by lazy { Systems.packages.values.flatten().map { it.substringBefore('/') }.toSet() }

    fun installed(pkg: String) = try { ctx.packageManager.getPackageInfo(pkg, 0); true } catch (e: PackageManager.NameNotFoundException) { false }

    @Synchronized
    fun scan() {
        val out = ArrayList<Game>()
        val pm = ctx.packageManager
        // Android games: apps the system knows are games, that can be opened
        for (ai in pm.getInstalledApplications(0)) {
            val game = (ai.flags and ApplicationInfo.FLAG_IS_GAME) != 0 || ai.category == ApplicationInfo.CATEGORY_GAME
            if (!game || ai.packageName == ctx.packageName || ai.packageName in emulatorPackages) continue
            if (pm.getLaunchIntentForPackage(ai.packageName) == null && pm.getLeanbackLaunchIntentForPackage(ai.packageName) == null) continue
            val added = try { pm.getPackageInfo(ai.packageName, 0).firstInstallTime / 1000 } catch (e: Exception) { 0L }
            out.add(Game("apk-${ai.packageName}", pm.getApplicationLabel(ai).toString(), "Android", null, ai.packageName, null, added))
        }
        // ROMs: ROMs/<console>/ (and one folder deeper), skipping BIOS folders
        val n = HashMap<String, Int>()
        val root = romRoot()
        if (root != null && canReadFiles()) {
            for (dir in root.listFiles()?.filter { it.isDirectory } ?: emptyList()) {
                val system = Systems.forFolder(dir.name) ?: continue
                val info = Systems.byName[system] ?: continue
                val files = ArrayList<File>()
                fun walk(d: File, depth: Int) {
                    for (f in d.listFiles() ?: return) {
                        if (f.name.startsWith(".")) continue
                        if (f.isDirectory) { if (depth < 2 && !f.name.equals("BIOS", true)) walk(f, depth + 1) }
                        else if (info.ext.any { f.name.lowercase().endsWith(it) }) files.add(f)
                    }
                }
                walk(dir, 0)
                // a game in parts is played from its .m3u or .cue: the parts it lists aren't games of their own
                val listed = files.filter { it.name.lowercase().endsWith(".m3u") || it.name.lowercase().endsWith(".cue") }
                    .flatMap { m -> try { m.readLines().map { File(m.parentFile, it.trim()).path } } catch (e: Exception) { emptyList() } }.toSet()
                for (f in files.filter { it.path !in listed }) {
                    out.add(Game("rom-" + hash(f.path), romTitle(f.nameWithoutExtension), "Emulators", system, null, f, f.lastModified() / 1000))
                }
                n[system] = (n[system] ?: 0) + files.size - files.count { it.path in listed }
            }
        }
        val over = Store.load("overrides.json")
        out.forEach { g -> over.optJSONObject(g.id)?.optString("title")?.takeIf { it.isNotEmpty() }?.let { g.title = it } }
        games = out
        byId = out.associateBy { it.id }
        counts = n
        scanned = true
    }

    fun hash(s: String) = MessageDigest.getInstance("SHA-1").digest(s.toByteArray()).joinToString("") { "%02x".format(it) }.take(12)

    /** "Super Mario World (USA) [!]" -> "Super Mario World" */
    fun romTitle(stem: String) = stem.replace(Regex("""\s*[(\[][^)\]]*[)\]]"""), "").replace('_', ' ').trim().ifEmpty { stem }

    fun publicGames(): JSONArray {
        val over = Store.load("overrides.json")
        val play = Store.load("play.json")
        val a = JSONArray()
        for (g in games) {
            val o = over.optJSONObject(g.id) ?: JSONObject()
            val p = play.optJSONObject(g.id) ?: JSONObject()
            val j = JSONObject().put("id", g.id).put("title", g.title).put("group", g.system ?: "Android").put("source", g.source)
                .put("installed", true).put("minutes", p.optInt("minutes")).put("lastPlayed", p.optLong("lastPlayed"))
                .put("added", g.added).put("cover", "/api/cover?id=${g.id}").put("genres", JSONArray())
            g.system?.let { j.put("system", it) }
            if (o.optBoolean("favorite")) j.put("favorite", true)
            if (o.optBoolean("hidden")) j.put("hidden", true)
            o.optJSONArray("collections")?.let { j.put("collections", it) }
            a.put(j)
        }
        return a
    }

    // ---------------------------------------------------------------- covers
    private val coverDir by lazy { File(ctx.filesDir, "covers").apply { mkdirs() } }

    /** A cover for the game: the box art from libretro for a ROM (when found), else one drawn here. Kept once made. */
    fun cover(g: Game): ByteArray {
        val f = File(coverDir, "${g.id}.img")
        if (f.isFile) return f.readBytes()
        val online = Store.load("config.json").optJSONObject("options")?.optBoolean("onlineCovers", true) ?: true
        val bytes = (if (g.system != null && online) libretroBoxart(g) else null) ?: drawCover(g)
        f.writeBytes(bytes)
        return bytes
    }

    fun clearCover(id: String) { File(coverDir, "$id.img").delete() }

    private fun libretroBoxart(g: Game): ByteArray? {
        val set = Systems.byName[g.system]?.thumbs ?: return null
        val clean = { s: String -> s.replace(Regex("""[&*/:`<>?\\|"]"""), "_") }
        val stem = g.file!!.nameWithoutExtension
        val names = linkedSetOf(stem, g.original, "${g.original} (USA)", "${g.original} (USA, Europe)", "${g.original} (Europe)",
            "${g.original} (World)", "${g.original} (Japan)")
        for (n in names) {
            val url = "https://thumbnails.libretro.com/${enc(set)}/Named_Boxarts/${enc(clean(n))}.png"
            fetch(url)?.let { return it }
        }
        return null
    }

    private fun enc(s: String) = URLEncoder.encode(s, "UTF-8").replace("+", "%20")

    fun fetch(url: String, limit: Int = 8_000_000): ByteArray? = try {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 8000; c.readTimeout = 15000
        c.setRequestProperty("User-Agent", "UltraFrontEnd-Android")
        if (c.responseCode != 200) null else c.inputStream.use { it.readBytes() }.takeIf { it.size in 1..limit }
    } catch (e: Exception) { null }

    /** 600×900: the app's icon (or the console's name) on a background in its colours, with the title underneath. */
    private fun drawCover(g: Game): ByteArray {
        val w = 600; val h = 900
        val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        val c = Canvas(bmp)
        val icon = g.pkg?.let { try { ctx.packageManager.getApplicationIcon(it).toBitmap(384, 384) } catch (e: Exception) { null } }
        val base = icon?.let { average(it) } ?: Color.HSVToColor(floatArrayOf((g.id.hashCode() and 0xffff) % 360f, .55f, .45f))
        val hsv = FloatArray(3).also { Color.colorToHSV(base, it) }
        val top = Color.HSVToColor(floatArrayOf(hsv[0], hsv[1].coerceAtMost(.7f), .55f))
        val bottom = Color.HSVToColor(floatArrayOf(hsv[0], hsv[1].coerceAtMost(.8f), .14f))
        c.drawRect(0f, 0f, w.toFloat(), h.toFloat(), Paint().apply { shader = LinearGradient(0f, 0f, 0f, h.toFloat(), top, bottom, Shader.TileMode.CLAMP) })
        if (icon != null) {
            val s = 360; val x = (w - s) / 2; val y = 170
            c.drawRoundRect(RectF(x - 6f, y - 6f, x + s + 6f, y + s + 6f), 70f, 70f, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0x40000000 })
            c.drawBitmap(icon, null, Rect(x, y, x + s, y + s), Paint(Paint.FILTER_BITMAP_FLAG))
        } else {
            val p = TextPaint(Paint.ANTI_ALIAS_FLAG).apply { color = 0x99ffffff.toInt(); textSize = 54f; typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD); textAlign = Paint.Align.CENTER }
            c.drawText(g.system ?: "", w / 2f, 150f, p)
        }
        val tp = TextPaint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; textSize = 58f; typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD) }
        val layout = StaticLayout.Builder.obtain(g.title, 0, g.title.length, tp, w - 80).setAlignment(Layout.Alignment.ALIGN_CENTER)
            .setMaxLines(4).setEllipsize(android.text.TextUtils.TruncateAt.END).build()
        c.save(); c.translate(40f, if (icon != null) 600f else (h - layout.height) / 2f); layout.draw(c); c.restore()
        return ByteArrayOutputStream().also { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }.toByteArray()
    }

    private fun average(b: Bitmap): Int {
        val s = Bitmap.createScaledBitmap(b, 16, 16, true)
        var r = 0L; var gg = 0L; var bl = 0L; var n = 0L
        for (x in 0 until 16) for (y in 0 until 16) {
            val p = s.getPixel(x, y)
            if (Color.alpha(p) < 128) continue
            r += Color.red(p); gg += Color.green(p); bl += Color.blue(p); n++
        }
        return if (n == 0L) Color.DKGRAY else Color.rgb((r / n).toInt(), (gg / n).toInt(), (bl / n).toInt())
    }

    fun launchIntent(pkg: String): Intent? = ctx.packageManager.getLaunchIntentForPackage(pkg) ?: ctx.packageManager.getLeanbackLaunchIntentForPackage(pkg)
}
