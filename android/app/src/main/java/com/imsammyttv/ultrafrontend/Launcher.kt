package com.imsammyttv.ultrafrontend

import android.content.ComponentName
import android.content.Intent
import android.net.Uri
import android.os.Environment
import android.provider.DocumentsContract
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File

/** Starting games: Android games by their own launch intent, ROMs in an emulator by the intent ES-DE's tables give for it. */
object Launcher {
    @Volatile private var session: Pair<String, Long>? = null  // the game being played, and since when

    /** The emulator a console's games start in: the one chosen in Settings › Systems, else the first installed one. */
    fun emulatorFor(system: String): Emu? {
        val info = Systems.byName[system] ?: return null
        val chosen = Store.load("config.json").optJSONObject("emulators")?.optJSONObject(system)
        if (chosen != null) {
            info.emulators.firstOrNull { it.label == chosen.optString("label") && it.emu == chosen.optString("emu") }?.let { if (component(it) != null) return it }
        }
        return info.emulators.firstOrNull { component(it) != null }
    }

    /** The installed app an emulator entry starts, if any. */
    fun component(e: Emu): ComponentName? {
        for (entry in Systems.packages[e.emu] ?: return null) {
            val pkg = entry.substringBefore('/')
            if (!Library.installed(pkg)) continue
            val act = entry.substringAfter('/', "")
            if (act.isEmpty()) return Library.launchIntent(pkg)?.component
            return ComponentName(pkg, if (act.startsWith(".")) pkg + act else act)
        }
        return null
    }

    /** The emulators on this device that can play a console, for Settings › Systems. */
    fun installedFor(system: String) = Systems.byName[system]?.emulators?.filter { component(it) != null } ?: emptyList()

    /** Display name: "RetroArch · Snes9x" for a RetroArch core, else the emulator's own name. */
    fun name(e: Emu) = if (e.emu == "RETROARCH") "RetroArch · ${e.label}" else e.label

    fun launch(g: Game) {
        val ctx = Library.ctx
        val intent: Intent
        if (g.pkg != null) {
            intent = Library.launchIntent(g.pkg) ?: throw IllegalArgumentException("${g.title} can't be opened")
        } else {
            val e = emulatorFor(g.system!!)
                ?: throw IllegalArgumentException("No emulator for ${g.system} on this device yet. Install one, then choose it in Settings › Systems")
            intent = build(e, g.file!!)
        }
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        ctx.startActivity(intent)
        endSession()
        session = g.id to System.currentTimeMillis()
        Store.edit("play.json") { p ->
            val o = p.optJSONObject(g.id) ?: JSONObject().also { p.put(g.id, it) }
            o.put("lastPlayed", System.currentTimeMillis() / 1000)
        }
    }

    /** Back in the frontend: the time played goes to the game. */
    fun endSession() {
        val (id, start) = session ?: return
        session = null
        val minutes = ((System.currentTimeMillis() - start) / 60000).toInt()
        if (minutes <= 0) return
        Store.edit("play.json") { p ->
            val o = p.optJSONObject(id) ?: JSONObject().also { p.put(id, it) }
            o.put("minutes", o.optInt("minutes") + minutes)
        }
    }

    // ES-DE command tokens: %ACTION%=x %CATEGORY%=x %DATA%=x %MIMETYPE%=x %EXTRA_k%=v %EXTRABOOL_k%=b %EXTRAARRAY_k%=a,b
    // %ACTIVITY_CLEAR_TASK% %ACTIVITY_CLEAR_TOP%; values use %ROM% %ROMSAF% %ROMPROVIDER% %ROMPATH% %BASENAME% %EXTERNALDATA%
    // %INTERNALDATA% %ANDROIDPACKAGE%
    fun build(e: Emu, rom: File): Intent {
        val comp = component(e) ?: throw IllegalArgumentException("${name(e)} isn't installed")
        val pkg = comp.packageName
        val intent = Intent().setComponent(comp)
        val grants = ArrayList<Uri>()
        fun value(v: String): String {
            var s = v
            if ("%ROMSAF%" in s) s = s.replace("%ROMSAF%", saf(rom).toString().also { grants.add(Uri.parse(it)) })
            if ("%ROMPROVIDER%" in s) s = s.replace("%ROMPROVIDER%", provider(rom).toString().also { grants.add(Uri.parse(it)) })
            return s.replace("%ROM%", rom.absolutePath).replace("%ROMPATH%", rom.parentFile!!.absolutePath)
                .replace("%BASENAME%", rom.nameWithoutExtension)
                .replace("%EXTERNALDATA%", Environment.getExternalStorageDirectory().absolutePath)
                .replace("%INTERNALDATA%", "/data/data").replace("%ANDROIDPACKAGE%", pkg)
        }
        var data: Uri? = null
        var type: String? = null
        for (tok in e.cmd.trim().split(Regex("\\s+"))) {
            val eq = tok.indexOf("%=")
            val key = if (eq >= 0) tok.substring(0, eq + 1) else tok
            val raw = if (eq >= 0) tok.substring(eq + 2) else ""
            when {
                key == "%ACTION%" -> intent.action = raw
                key == "%CATEGORY%" -> intent.addCategory(raw)
                key == "%DATA%" -> data = Uri.parse(value(raw)).let { if (it.scheme == null) Uri.fromFile(File(it.toString())) else it }
                key == "%MIMETYPE%" -> type = raw
                key == "%ACTIVITY_CLEAR_TASK%" -> intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK)
                key == "%ACTIVITY_CLEAR_TOP%" -> intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
                key.startsWith("%EXTRABOOL_") -> intent.putExtra(key.removePrefix("%EXTRABOOL_").removeSuffix("%"), raw.toBoolean())
                key.startsWith("%EXTRAARRAY_") -> intent.putExtra(key.removePrefix("%EXTRAARRAY_").removeSuffix("%"), raw.split(",").map { value(it) }.toTypedArray())
                key.startsWith("%EXTRA_") -> intent.putExtra(key.removePrefix("%EXTRA_").removeSuffix("%"), value(raw))
            }
        }
        if (data != null || type != null) intent.setDataAndType(data, type)
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        for (u in grants) try {  // extras aren't covered by the flags above
            Library.ctx.grantUriPermission(pkg, u, Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        } catch (_: Exception) {}
        return intent
    }

    /** The ROM as a document of the ROMs folder the user picked (an address the emulator can open with our permission). */
    private fun saf(rom: File): Uri {
        val tree = Store.load("config.json").optString("romTree").takeIf { it.isNotEmpty() }?.let { Uri.parse(it) }
        val base = Environment.getExternalStorageDirectory().absolutePath + "/"
        if (tree != null && rom.absolutePath.startsWith(base)) {
            return DocumentsContract.buildDocumentUriUsingTree(tree, "primary:" + rom.absolutePath.removePrefix(base))
        }
        return provider(rom)
    }

    private fun provider(rom: File): Uri = FileProvider.getUriForFile(Library.ctx, "${Library.ctx.packageName}.files", rom)
}
