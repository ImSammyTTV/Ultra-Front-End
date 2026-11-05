package com.imsammyttv.ultrafrontend

import android.content.Context
import android.content.Intent
import android.media.AudioManager
import android.media.MediaPlayer
import android.net.Uri
import android.provider.DocumentsContract
import androidx.core.content.FileProvider
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * The page's /api calls, answered with the same shapes as server.py on Windows and Mac. What Android can't do
 * (accounts, PC libraries, the in-game overlay, recording…) answers with nothing, and the page leaves it out.
 */
class Backend(private val ctx: Context, private val version: String) {
    private val audio = ctx.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private var player: MediaPlayer? = null
    private val update = JSONObject().put("state", "").put("error", "")
    @Volatile private var latest: JSONObject? = null  // {version, notes, apk}

    fun handle(r: Request): Response {
        if (!r.path.startsWith("/api/")) return asset(r.path)
        if (r.method == "POST" && r.headers["x-frontend"] != "1") return Response.error(403, "Forbidden")
        val body = if (r.method == "POST" && r.body.isNotEmpty()) JSONObject(String(r.body, Charsets.UTF_8)) else JSONObject()
        if (!Library.scanned) Library.scan()
        return when (r.method to r.path) {
            "GET" to "/api/ping" -> ok(JSONObject().put("ok", true).put("scanned", true).put("page", 0).put("build", version).put("version", version).put("root", ""))
            "GET" to "/api/library" -> ok(JSONObject().put("games", Library.publicGames()).put("errors", JSONArray(Library.errors)).put("scanned", true))
            "GET" to "/api/settings" -> ok(settings())
            "GET" to "/api/profile" -> ok(profile())
            "GET" to "/api/pad" -> ok(Pad.wait(r.query["after"]?.toLongOrNull() ?: 0))
            "GET" to "/api/cover" -> cover(r.query["id"] ?: "")
            "GET" to "/api/game" -> ok(details(r.query["id"] ?: ""))
            "GET" to "/api/hero" -> ok(JSONObject().put("hero", ""))
            "GET" to "/api/launching" -> ok(JSONObject().put("waiting", false).put("exited", false))
            "GET" to "/api/running" -> ok(JSONObject().put("games", JSONArray()).put("folders", 0))
            "GET" to "/api/volume" -> ok(volume())
            "GET" to "/api/update" -> ok(updateView())
            "GET" to "/api/systems/queue" -> ok(queue())
            "GET" to "/api/whatsnew" -> ok(whatsNew())
            "GET" to "/api/whatsnew/unseen" -> ok(JSONObject().put("unseen", unseen()))
            "GET" to "/api/padraw", "GET" to "/api/xinput" -> ok(JSONObject().put("pads", JSONArray()))
            "GET" to "/api/downloads" -> ok(JSONObject().put("items", JSONArray()))
            "GET" to "/api/friends" -> ok(JSONObject().put("friends", JSONArray()))
            "GET" to "/api/news" -> ok(JSONObject().put("items", JSONArray()))
            "GET" to "/api/album" -> ok(JSONObject().put("items", JSONArray()))
            "GET" to "/api/nowplaying" -> ok(JSONObject())
            "GET" to "/api/overlay" -> ok(JSONObject().put("open", false))
            "GET" to "/api/hud" -> ok(JSONObject().put("mode", "off").put("fps", false))
            "POST" to "/api/profile" -> ok(setProfile(body))
            "POST" to "/api/options" -> ok(setOptions(body))
            "POST" to "/api/launch" -> launch(body)
            "POST" to "/api/game/favorite" -> override(body) { o -> if (body.optBoolean("favorite")) o.put("favorite", true) else o.remove("favorite") }
            "POST" to "/api/game/hide" -> override(body) { o -> if (body.optBoolean("hidden")) o.put("hidden", true) else o.remove("hidden") }
            "POST" to "/api/game/collection" -> collection(body)
            "POST" to "/api/game/rename" -> rename(body)
            "POST" to "/api/game/info" -> override(body) { o ->
                if (body.optBoolean("reset")) { o.remove("description"); o.remove("infoAs") }
                body.optString("description").takeIf { body.has("description") }?.let { if (it.isBlank()) o.remove("description") else o.put("description", it.take(4000)) }
            }
            "POST" to "/api/systems/choose" -> chooseSystems(body)
            "POST" to "/api/systems/add" -> changeSystem(body.optString("system"), true)
            "POST" to "/api/systems/remove" -> changeSystem(body.optString("system"), false)
            "POST" to "/api/systems/bios" -> openRomFolder(body.optString("system"), bios = true)
            "POST" to "/api/emulators/find" -> ok(settings().put("found", findEmulators()))
            "POST" to "/api/emulators/set" -> setEmulator(body.optString("system"))
            "POST" to "/api/emulators/clear" -> { Store.edit("config.json") { it.optJSONObject("emulators")?.remove(body.optString("system")) }; ok(settings()) }
            "POST" to "/api/emulators/site", "POST" to "/api/emulators/install" -> emulatorSite(body.optString("system"))
            "POST" to "/api/romroot/default" -> setRomRoot(Library.defaultRomRoot(), pick = false)
            "POST" to "/api/romroot/choose" -> setRomRoot(null, pick = true)
            "POST" to "/api/romroot/open" -> openRomFolder("", bios = false)
            "POST" to "/api/rescan" -> { Library.scan(); ok(JSONObject().put("ok", true)) }
            "POST" to "/api/volume" -> ok(setVolume(body))
            "POST" to "/api/introsound" -> { sound(body); ok(JSONObject().put("ok", true)) }
            "POST" to "/api/system" -> if (body.optString("action") == "exit") { MainActivity.instance?.quit(); ok(JSONObject().put("ok", true)) }
                else Response.error(400, "Android doesn’t let apps do that: use your device’s power button")
            "POST" to "/api/update" -> ok(updateStep(body.optString("action")))
            "POST" to "/api/whatsnew" -> { Store.edit("whatsnew.json") { it.put("seen", version) }; ok(JSONObject().put("unseen", false)) }
            else -> ok(if (r.method == "POST") JSONObject().put("ok", true) else JSONObject())
        }
    }

    private fun ok(o: JSONObject) = Response.json(o.toString())

    // ---------------------------------------------------------------- the page itself (app/ is in the APK's assets)
    private fun asset(path: String): Response {
        val p = path.trimStart('/').ifEmpty { "index.html" }
        if (".." in p) return Response.error(404, "Not found")
        val type = when (p.substringAfterLast('.').lowercase()) {
            "html" -> "text/html; charset=utf-8"; "js" -> "text/javascript; charset=utf-8"; "css" -> "text/css; charset=utf-8"
            "json" -> "application/json"; "png" -> "image/png"; "jpg", "jpeg" -> "image/jpeg"; "webp" -> "image/webp"
            "svg" -> "image/svg+xml"; "wav" -> "audio/wav"; "mp3" -> "audio/mpeg"; "woff2" -> "font/woff2"; "ttf" -> "font/ttf"
            "ico" -> "image/x-icon"; "gif" -> "image/gif"; else -> "application/octet-stream"
        }
        return try { Response(200, type, stream = ctx.assets.open(p), cache = "no-cache") } catch (e: Exception) { Response.error(404, "Not found") }
    }

    // ---------------------------------------------------------------- settings
    private fun config() = Store.load("config.json")

    private fun profile(): JSONObject {
        val p = config().optJSONObject("profile") ?: JSONObject()
        return JSONObject().put("name", p.optString("name")).put("avatar", p.optString("avatar")).put("timezone", p.optString("timezone", "auto"))
            .put("setupDone", p.optBoolean("setupDone")).put("picture", "")
    }

    private fun setProfile(b: JSONObject): JSONObject {
        Store.edit("config.json") { c ->
            val p = c.optJSONObject("profile") ?: JSONObject().also { c.put("profile", it) }
            if (b.has("name")) p.put("name", b.optString("name").trim().take(32))
            if (b.has("avatar")) p.put("avatar", b.optString("avatar").replace(Regex("[^a-z0-9-]"), "").take(24))
            if (b.has("timezone")) p.put("timezone", b.optString("timezone").takeIf { Regex("[A-Za-z]+(/[A-Za-z0-9_+-]+){1,2}").matches(it) } ?: "auto")
            if (b.has("setupDone")) p.put("setupDone", b.optBoolean("setupDone"))
        }
        return profile()
    }

    private val optionKeys = listOf("onlineCovers", "artBackground", "showUninstalled", "steamLocal", "guideOpens", "wiiMotion")

    private fun options(): JSONObject {
        val o = config().optJSONObject("options") ?: JSONObject()
        return JSONObject().also { r -> optionKeys.forEach { r.put(it, o.optBoolean(it, true)) }; r.put("startup", JSONObject.NULL) }
    }

    private fun setOptions(b: JSONObject): JSONObject {
        Store.edit("config.json") { c ->
            val o = c.optJSONObject("options") ?: JSONObject().also { c.put("options", it) }
            optionKeys.filter { b.has(it) }.forEach { o.put(it, b.optBoolean(it)) }
        }
        return settings()
    }

    private fun chosenSystems(): Set<String> = config().optJSONArray("systems")?.let { Systems.strings(it).toSet() } ?: emptySet()

    private fun settings(): JSONObject {
        val chosen = chosenSystems() + Library.counts.filter { it.value > 0 }.keys
        val platforms = JSONArray()
        for (s in Systems.list) {
            val emu = Launcher.emulatorFor(s.name)
            val first = s.emulators.firstOrNull()
            val p = JSONObject().put("name", s.name).put("group", s.group).put("chosen", s.name in chosen)
                .put("count", Library.counts[s.name] ?: 0).put("emulator", emu?.let { Launcher.name(it) } ?: "")
                .put("install", JSONObject.NULL).put("recommended", first?.let { Launcher.name(it) } ?: JSONObject.NULL)
                .put("site", if (first != null) "play" else JSONObject.NULL).put("steps", JSONObject.NULL).put("job", JSONObject.NULL)
            if (s.name in chosen) p.put("bios", JSONObject().put("label", "Nothing needed").put("ok", true).put("folder", false).put("needs", JSONArray()).put("note", JSONObject.NULL))
            platforms.put(p)
        }
        return JSONObject().put("options", options()).put("services", JSONObject()).put("libraries", JSONArray()).put("accounts", JSONObject())
            .put("errors", JSONArray(Library.errors)).put("steamDetected", false).put("steamSuggestedId", "").put("localSteamCount", 0)
            .put("romRoot", config().optString("romRoot")).put("platforms", platforms).put("queue", queue()).put("profile", profile())
            .put("update", updateView()).put("extras", JSONObject()).put("launchers", JSONArray()).put("autologon", JSONObject().put("available", false))
    }

    private fun queue() = JSONObject().put("jobs", JSONArray()).put("busy", false).put("batch", 0)

    // ---------------------------------------------------------------- games
    private fun game(b: JSONObject) = Library.byId[b.optString("id")] ?: throw IllegalArgumentException("Game not found")

    private fun override(b: JSONObject, change: (JSONObject) -> Unit): Response {
        val g = game(b)
        Store.edit("overrides.json") { all ->
            val o = all.optJSONObject(g.id) ?: JSONObject()
            change(o)
            if (o.length() == 0) all.remove(g.id) else all.put(g.id, o)
        }
        return ok(JSONObject().put("ok", true))
    }

    private fun collection(b: JSONObject): Response {
        val name = b.optString("name").trim().take(40)
        if (name.isEmpty()) throw IllegalArgumentException("Type a name for the collection")
        return override(b) { o ->
            val names = (o.optJSONArray("collections")?.let { Systems.strings(it) } ?: emptyList()).filter { it != name } + (if (b.optBoolean("member")) listOf(name) else emptyList())
            if (names.isEmpty()) o.remove("collections") else o.put("collections", JSONArray(names))
        }
    }

    private fun rename(b: JSONObject): Response {
        val g = game(b)
        val title = b.optString("title").trim().take(120)
        override(b) { o -> if (title.isEmpty() || title == g.original) o.remove("title") else o.put("title", title) }
        g.title = title.ifEmpty { g.original }
        Library.clearCover(g.id)
        return ok(JSONObject().put("ok", true))
    }

    private fun launch(b: JSONObject): Response {
        val g = game(b)
        val err = arrayOfNulls<String>(1)
        val done = java.util.concurrent.CountDownLatch(1)
        MainActivity.instance?.runOnUiThread {
            try { Launcher.launch(g) } catch (e: IllegalArgumentException) { err[0] = e.message } catch (e: Exception) {
                err[0] = "${g.title} couldn’t start (${e.message ?: e.javaClass.simpleName})"
            }
            done.countDown()
        } ?: throw IllegalArgumentException("The app isn't open")
        done.await(10, java.util.concurrent.TimeUnit.SECONDS)
        err[0]?.let { throw IllegalArgumentException(it) }
        return ok(JSONObject().put("ok", true).put("installing", false).put("unpacking", false))
    }

    private fun cover(id: String): Response {
        val g = Library.byId[id] ?: return Response.error(404, "Not found")
        val bytes = Library.cover(g)
        val type = if (bytes.size > 3 && bytes[0] == 0xFF.toByte()) "image/jpeg" else "image/png"
        return Response(200, type, bytes, cache = "max-age=86400")
    }

    private fun details(id: String): JSONObject {
        val g = Library.byId[id] ?: throw IllegalArgumentException("Game not found")
        val own = Store.load("overrides.json").optJSONObject(id)?.optString("description").orEmpty()
        val d = JSONObject().put("description", own).put("genres", JSONArray()).put("developer", "").put("released", "")
            .put("screenshots", JSONArray()).put("trailers", JSONArray()).put("hero", "").put("logo", "").put("heroSoft", false)
            .put("achievements", JSONObject.NULL).put("achPending", false).put("news", JSONObject.NULL)
        if (own.isNotEmpty()) d.put("descSource", "Your own description")
        if (g.pkg != null) try {
            val info = ctx.packageManager.getPackageInfo(g.pkg, 0)
            d.put("developer", "").put("released", java.text.SimpleDateFormat("yyyy", java.util.Locale.US).format(java.util.Date(info.firstInstallTime)))
            if (own.isEmpty()) d.put("description", "Android game, version ${info.versionName ?: "?"}.")
        } catch (_: Exception) {}
        return d
    }

    // ---------------------------------------------------------------- systems and emulators
    private fun makeFolders(systems: Collection<String>): Int {
        val root = Library.romRoot() ?: return 0
        if (!Library.canReadFiles()) return 0
        var made = 0
        for (s in systems) {
            val existing = root.listFiles()?.any { it.isDirectory && Systems.forFolder(it.name) == s } ?: false
            if (!existing && File(root, s.replace("&", "and")).mkdirs()) made++
        }
        return made
    }

    private fun chooseSystems(b: JSONObject): Response {
        val picked = b.optJSONArray("systems")?.let { Systems.strings(it) }?.filter { it in Systems.byName } ?: throw IllegalArgumentException("Send a list of systems")
        Store.edit("config.json") { it.put("systems", JSONArray(picked)) }
        makeFolders(picked)
        return ok(settings())
    }

    private fun changeSystem(system: String, add: Boolean): Response {
        if (system !in Systems.byName) throw IllegalArgumentException("No such system")
        Store.edit("config.json") { c ->
            val now = (c.optJSONArray("systems")?.let { Systems.strings(it) } ?: emptyList()).filter { it != system } + (if (add) listOf(system) else emptyList())
            c.put("systems", JSONArray(now))
        }
        if (add) makeFolders(listOf(system))
        return ok(settings())
    }

    private fun findEmulators() = chosenSystems().count { Launcher.emulatorFor(it) != null }

    /** Settings › Systems › Choose program: the next emulator on this device that plays the console. */
    private fun setEmulator(system: String): Response {
        if (system !in Systems.byName) throw IllegalArgumentException("No such console")
        val have = Launcher.installedFor(system)
        if (have.isEmpty()) throw IllegalArgumentException("No emulator for $system is installed on this device. Install one (${Systems.byName[system]!!.emulators.firstOrNull()?.let { Launcher.name(it) } ?: "see the console's page"}), then come back")
        val now = Launcher.emulatorFor(system)
        val next = have[(have.indexOf(now) + 1) % have.size]
        Store.edit("config.json") { c ->
            val e = c.optJSONObject("emulators") ?: JSONObject().also { c.put("emulators", it) }
            e.put(system, JSONObject().put("id", next.id))
        }
        return ok(settings())
    }

    /** Where to get the console's first emulator: its Google Play page, or its own site when it isn't on Google Play. */
    private fun emulatorSite(system: String): Response {
        val e = Systems.byName[system]?.emulators?.firstOrNull() ?: throw IllegalArgumentException("No emulator known for this console")
        val site = e.site ?: "https://play.google.com/store/apps/details?id=${e.packages.first()}"
        val play = Regex("""play\.google\.com/store/apps/details\?id=([\w.]+)""").find(site)?.groupValues?.get(1)
        MainActivity.instance?.open(*listOfNotNull(play?.let { Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=$it")) },
            Intent(Intent.ACTION_VIEW, Uri.parse(site))).toTypedArray())
        return ok(JSONObject().put("ok", true))
    }

    // ---------------------------------------------------------------- the ROMs folder
    private fun setRomRoot(given: File?, pick: Boolean): Response {
        val act = MainActivity.instance ?: throw IllegalArgumentException("The app isn't open")
        if (!Library.canReadFiles() && !act.askAllFiles()) {
            throw IllegalArgumentException("Allow “All files access” for Ultra Front End so it can read your ROMs, then try again")
        }
        var tree: Uri? = null
        val folder: File = if (pick) {
            tree = act.pickFolder() ?: return ok(JSONObject().put("cancelled", true))
            treePath(tree) ?: throw IllegalArgumentException("Choose a folder on this device’s internal storage")
        } else given!!
        folder.mkdirs()
        Store.edit("config.json") { c ->
            c.put("romRoot", folder.absolutePath)
            if (tree != null) c.put("romTree", tree.toString()) else c.remove("romTree")
        }
        val made = makeFolders(chosenSystems())
        Library.scan()
        return ok(settings().put("made", made).put("found", findEmulators()))
    }

    /** content://…/tree/primary:ROMs -> /storage/emulated/0/ROMs */
    private fun treePath(tree: Uri): File? {
        val id = DocumentsContract.getTreeDocumentId(tree)
        if (!id.startsWith("primary:")) return null
        return File(android.os.Environment.getExternalStorageDirectory(), id.removePrefix("primary:"))
    }

    private fun openRomFolder(system: String, bios: Boolean): Response {
        val root = Library.romRoot() ?: throw IllegalArgumentException("Set up your ROMs folder first")
        var f = root
        if (system.isNotEmpty()) f = root.listFiles()?.firstOrNull { it.isDirectory && Systems.forFolder(it.name) == system } ?: File(root, system)
        if (bios) f = File(f, "BIOS").apply { mkdirs() }
        val rel = f.absolutePath.removePrefix(android.os.Environment.getExternalStorageDirectory().absolutePath + "/")
        val uri = DocumentsContract.buildDocumentUri("com.android.externalstorage.documents", "primary:$rel")
        MainActivity.instance?.open(Intent(Intent.ACTION_VIEW).setDataAndType(uri, DocumentsContract.Document.MIME_TYPE_DIR),
            Intent(Intent.ACTION_VIEW).setDataAndType(uri, "resource/folder"))
        return ok(JSONObject().put("ok", true))
    }

    // ---------------------------------------------------------------- sound and volume
    private fun volume(): JSONObject {
        val max = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
        val now = audio.getStreamVolume(AudioManager.STREAM_MUSIC)
        return JSONObject().put("volume", if (max > 0) Math.round(now * 100f / max) else 0).put("muted", audio.isStreamMute(AudioManager.STREAM_MUSIC))
    }

    private fun setVolume(b: JSONObject): JSONObject {
        if (b.has("mute")) audio.adjustStreamVolume(AudioManager.STREAM_MUSIC, if (b.optBoolean("mute")) AudioManager.ADJUST_MUTE else AudioManager.ADJUST_UNMUTE, 0)
        if (b.has("delta")) {
            val max = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
            val want = (volume().getInt("volume") + b.optInt("delta")).coerceIn(0, 100)
            audio.setStreamVolume(AudioManager.STREAM_MUSIC, Math.round(want * max / 100f), 0)
        }
        return volume()
    }

    @Synchronized
    private fun sound(b: JSONObject) {
        player?.release(); player = null
        if (!b.optBoolean("play")) return
        val name = if (b.optBoolean("outro")) "outro.wav" else "intro.wav"
        try {
            ctx.assets.openFd("assets/$name").use { fd ->
                player = MediaPlayer().apply { setDataSource(fd.fileDescriptor, fd.startOffset, fd.length); prepare(); start() }
            }
        } catch (e: Exception) { android.util.Log.w("UFE", "sound", e) }
    }

    // ---------------------------------------------------------------- updates and what's new
    private val repo = "ImSammyTTV/Ultra-Front-End"

    private fun key(v: String) = v.split(".").map { it.toIntOrNull() ?: 0 }.let { it + List(3) { 0 } }.take(3).fold(0L) { a, n -> a * 1000 + n }

    private fun updateView(): JSONObject {
        val l = latest
        val newer = l != null && key(l.optString("version")) > key(version)
        return JSONObject().put("version", version).put("off", "").put("state", update.optString("state")).put("error", update.optString("error"))
            .put("latest", if (newer) l!!.optString("version") else JSONObject.NULL).put("notes", if (newer) l!!.optString("notes") else "")
            .put("updated", Store.load("update.json").opt("updated") ?: JSONObject.NULL)
    }

    /** True when GitHub answered. */
    fun checkUpdate(): Boolean {
        try {
            val c = URL("https://api.github.com/repos/$repo/releases/latest").openConnection() as HttpURLConnection
            c.setRequestProperty("Accept", "application/vnd.github+json"); c.setRequestProperty("User-Agent", "UltraFrontEnd-Android")
            c.connectTimeout = 10000; c.readTimeout = 15000
            val r = JSONObject(c.inputStream.use { it.readBytes() }.toString(Charsets.UTF_8))
            val assets = r.optJSONArray("assets") ?: JSONArray()
            val apk = (0 until assets.length()).map { assets.getJSONObject(it) }.firstOrNull { it.optString("name") == "UltraFrontEnd-android.apk" }
            latest = if (apk == null) null else JSONObject().put("version", r.optString("tag_name").trimStart('v', 'V'))
                .put("notes", r.optString("body")).put("apk", apk.optString("browser_download_url"))
            update.put("error", "")
            return true
        } catch (e: Exception) { update.put("error", "Couldn't reach GitHub. Check the internet connection"); return false }
    }

    private fun updateStep(action: String): JSONObject {
        when (action) {
            "seen" -> Store.edit("update.json") { it.put("updated", JSONObject.NULL) }
            "check" -> { update.put("state", "checking"); Thread { checkUpdate(); update.put("state", "") }.start(); Thread.sleep(300) }
            "install" -> Thread { install() }.start()
        }
        return updateView()
    }

    private fun install() {
        val l = latest ?: return
        update.put("state", "downloading")
        val bytes = Library.fetch(l.optString("apk"), 300_000_000)
        if (bytes == null) { update.put("state", "").put("error", "The download didn't finish. Try again"); return }
        val f = File(ctx.cacheDir, "UltraFrontEnd-android.apk").apply { writeBytes(bytes) }
        Store.edit("update.json") { it.put("updated", l.optString("version")) }
        update.put("state", "")
        val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", f)
        MainActivity.instance?.installApk(uri)
    }

    private fun unseen(): Boolean {
        val seen = Store.load("whatsnew.json").optString("seen")
        if (seen.isEmpty()) { Store.edit("whatsnew.json") { it.put("seen", version) }; return false }
        return key(seen) < key(version)
    }

    @Volatile private var news: Pair<Long, JSONObject>? = null

    private fun whatsNew(): JSONObject {
        news?.let { if (System.currentTimeMillis() - it.first < 3_600_000) return it.second }
        val items = JSONArray()
        var error = ""
        try {
            val c = URL("https://api.github.com/repos/$repo/releases?per_page=12").openConnection() as HttpURLConnection
            c.setRequestProperty("Accept", "application/vnd.github+json"); c.setRequestProperty("User-Agent", "UltraFrontEnd-Android")
            c.connectTimeout = 10000; c.readTimeout = 15000
            val a = JSONArray(c.inputStream.use { it.readBytes() }.toString(Charsets.UTF_8))
            for (i in 0 until a.length()) {
                val x = a.getJSONObject(i)
                if (x.optBoolean("draft") || x.optBoolean("prerelease")) continue
                val v = x.optString("tag_name").trimStart('v', 'V')
                val blocks = Markdown.blocks(x.optString("body"))
                val text = (0 until blocks.length()).map { blocks.getJSONObject(it) }.filter { it.optString("t") in setOf("p", "li") }.joinToString(" ") { it.optString("text") }
                val date = try { java.time.Instant.parse(x.optString("published_at")).epochSecond } catch (e: Exception) { 0L }
                items.put(JSONObject().put("version", v).put("title", x.optString("name").ifEmpty { "Ultra Front End $v" }).put("date", date)
                    .put("page", x.optString("html_url")).put("summary", if (text.length > 280) text.take(280) + "…" else text).put("body", blocks)
                    .put("state", if (key(v) == key(version)) "installed" else if (key(v) > key(version)) "update" else ""))
            }
        } catch (e: Exception) { error = "Couldn't reach GitHub. Check the internet connection" }
        val r = JSONObject().put("items", items).put("error", error).put("version", version).put("unseen", unseen())
        if (items.length() > 0) news = System.currentTimeMillis() to r
        return r
    }
}

/** Release notes (Markdown) as the plain blocks the reader shows, as server.py's markdown_blocks does. */
object Markdown {
    private fun inline(t: String) = t.replace(Regex("""!\[[^\]]*]\([^)]*\)"""), "").replace(Regex("""\[([^\]]+)]\([^)]*\)"""), "$1")
        .replace(Regex("""(\*\*|__)(.+?)\1"""), "$2").replace(Regex("""(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)"""), "$1")
        .replace(Regex("`([^`]*)`"), "$1").trim()

    fun blocks(md: String): JSONArray {
        val out = JSONArray()
        val para = ArrayList<String>()
        var skip = false
        fun add(t: String, text: String) {
            if (t == "h") skip = Regex("(download|install(ing|ation)?)\\b", RegexOption.IGNORE_CASE).containsMatchIn(text)
            if (!skip && text.isNotEmpty()) out.put(JSONObject().put("t", t).put("text", text))
        }
        fun flush() { if (para.isNotEmpty()) { add("p", inline(para.joinToString(" "))); para.clear() } }
        for (line in md.replace("\r\n", "\n").split("\n")) {
            val s = line.trim()
            val head = Regex("#{1,6}\\s+(.*)").matchEntire(s)
            val item = Regex("(?:[-*+]|\\d+[.)])\\s+(.*)").matchEntire(s)
            when {
                s.isEmpty() || Regex("(-{3,}|\\*{3,}|_{3,})").matches(s) -> flush()
                head != null -> { flush(); add("h", inline(head.groupValues[1])) }
                item != null -> { flush(); add("li", inline(item.groupValues[1])) }
                else -> para.add(s)
            }
        }
        flush()
        return out
    }
}
