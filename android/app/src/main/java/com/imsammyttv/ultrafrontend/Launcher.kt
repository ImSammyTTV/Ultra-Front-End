package com.imsammyttv.ultrafrontend

import android.content.ComponentName
import android.content.Intent
import android.net.Uri
import android.os.Environment
import android.provider.DocumentsContract
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File

/** Starting games: Android games by their own launch intent, ROMs in the emulator chosen for their console (emulators.json). */
object Launcher {
    @Volatile private var session: Pair<String, Long>? = null  // the game being played, and since when

    /** The emulator a console's games start in: the one chosen in Settings › Systems, else the first installed one. */
    fun emulatorFor(system: String): Emu? {
        val info = Systems.byName[system] ?: return null
        val chosen = Store.load("config.json").optJSONObject("emulators")?.optJSONObject(system)?.optString("id")
        if (!chosen.isNullOrEmpty()) info.emulators.firstOrNull { it.id == chosen }?.let { if (installedPackage(it) != null) return it }
        return info.emulators.firstOrNull { installedPackage(it) != null }
    }

    /** Which of the emulator's packages is on this device, if any. */
    fun installedPackage(e: Emu) = e.packages.firstOrNull { Library.installed(it) }

    /** The emulators on this device that can play a console, for Settings › Systems. */
    fun installedFor(system: String) = Systems.byName[system]?.emulators?.filter { installedPackage(it) != null } ?: emptyList()

    fun name(e: Emu) = e.name

    fun launch(g: Game) {
        val intent: Intent
        if (g.pkg != null) {
            intent = Library.launchIntent(g.pkg) ?: throw IllegalArgumentException("${g.title} can't be opened")
        } else {
            val e = emulatorFor(g.system!!)
                ?: throw IllegalArgumentException("No emulator for ${g.system} on this device yet. Install one, then choose it in Settings › Systems")
            intent = build(e, g.file!!)
        }
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        Library.ctx.startActivity(intent)
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

    fun build(e: Emu, rom: File): Intent {
        val pkg = installedPackage(e) ?: throw IllegalArgumentException("${e.name} isn't installed")
        val grants = ArrayList<Uri>()
        fun fill(v: String): String {
            var s = v
            if ("{uri}" in s) s = s.replace("{uri}", documentUri(rom).also { grants.add(it) }.toString())
            return s.replace("{path}", rom.absolutePath).replace("{fileuri}", Uri.fromFile(rom).toString())
                .replace("{name}", rom.nameWithoutExtension).replace("{package}", pkg).replace("{core}", e.core ?: "")
                .replace("{storage}", Environment.getExternalStorageDirectory().absolutePath)
        }
        val intent = if (e.activity != null) Intent().setComponent(ComponentName(pkg, if (e.activity.startsWith(".")) pkg + e.activity else e.activity))
            else (Library.launchIntent(pkg) ?: Intent().setPackage(pkg))
        e.action?.let { intent.action = fill(it) }  // melonDS: "{package}.LAUNCH_ROM"
        val data = e.data?.let { Uri.parse(fill(it)) }
        if (data != null || e.mime != null) intent.setDataAndType(data, e.mime)
        for ((k, v) in e.extras) intent.putExtra(k, fill(v))
        for (f in e.flags) when (f) {
            "clearTask" -> intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK)
            "clearTop" -> intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
        }
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        for (u in grants) try {  // an address passed as an extra isn't covered by the flags above
            Library.ctx.grantUriPermission(pkg, u, Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        } catch (_: Exception) {}
        return intent
    }

    /** The ROM as a document of the ROMs folder the user picked (which emulators may open with our permission), else
     *  through our own file provider. */
    private fun documentUri(rom: File): Uri {
        val tree = Store.load("config.json").optString("romTree").takeIf { it.isNotEmpty() }?.let { Uri.parse(it) }
        val base = Environment.getExternalStorageDirectory().absolutePath + "/"
        if (tree != null && rom.absolutePath.startsWith(base)) {
            return DocumentsContract.buildDocumentUriUsingTree(tree, "primary:" + rom.absolutePath.removePrefix(base))
        }
        return FileProvider.getUriForFile(Library.ctx, "${Library.ctx.packageName}.files", rom)
    }
}
