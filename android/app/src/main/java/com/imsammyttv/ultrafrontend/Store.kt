package com.imsammyttv.ultrafrontend

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.regex.Pattern

/** The app's data files (config.json, overrides.json, play.json…), kept in its private folder. */
object Store {
    lateinit var dir: File

    @Synchronized
    fun load(name: String): JSONObject = try { JSONObject(File(dir, name).readText()) } catch (e: Exception) { JSONObject() }

    @Synchronized
    fun save(name: String, o: JSONObject) {
        val tmp = File(dir, "$name.tmp")
        tmp.writeText(o.toString())
        if (!tmp.renameTo(File(dir, name))) { File(dir, name).delete(); tmp.renameTo(File(dir, name)) }
    }

    /** Change one file: read, change, write, under one lock. */
    @Synchronized
    fun edit(name: String, change: (JSONObject) -> Unit): JSONObject {
        val o = load(name)
        change(o)
        save(name, o)
        return o
    }
}

/**
 * An Android emulator app (or one RetroArch core) and how a game is started in it: assets/emulators.json, written by
 * hand from each emulator's own source. Values may use {uri} (the ROM as a document of the ROMs folder), {path} (its
 * file path), {fileuri}, {name} (file name without extension), {package}, {storage} (/storage/emulated/0) and {core}.
 */
class Emu(val id: String, val name: String, val packages: List<String>, val activity: String?, val action: String?,
          val data: String?, val mime: String?, val extras: Map<String, String>, val flags: List<String>, val core: String?, val site: String?)

class SystemInfo(val name: String, val group: String, val thumbs: String?, val ext: Set<String>, val emulators: List<Emu>)

/** The consoles (assets/systems.json, made from server.py by tools/make_android_systems.py) and their emulators. */
object Systems {
    lateinit var list: List<SystemInfo>
    lateinit var byName: Map<String, SystemInfo>
    private lateinit var patterns: List<Pair<Pattern, String>>

    fun load(ctx: Context) {
        val o = JSONObject(ctx.assets.open("systems.json").bufferedReader().readText())
        val e = JSONObject(ctx.assets.open("emulators.json").bufferedReader().readText())
        val apps = e.getJSONObject("apps")
        val per = e.getJSONObject("systems")
        fun emu(ref: String): Emu? {
            val app = apps.optJSONObject(ref.substringBefore(':')) ?: return null
            val core = ref.substringAfter(':', "").ifEmpty { null }
            val coreName = core?.let { app.optJSONObject("cores")?.optString(it)?.ifEmpty { null } ?: it }
            val ex = app.optJSONObject("extras")
            return Emu(ref, if (coreName != null) "${app.getString("name")} · $coreName" else app.getString("name"),
                strings(app.getJSONArray("packages")), app.optString("activity").ifEmpty { null }, app.optString("action").ifEmpty { null },
                app.optString("data").ifEmpty { null }, app.optString("mime").ifEmpty { null },
                ex?.keys()?.asSequence()?.associateWith { ex.getString(it) } ?: emptyMap(),
                app.optJSONArray("flags")?.let { strings(it) } ?: emptyList(), core, app.optString("site").ifEmpty { null })
        }
        val s = o.getJSONArray("systems")
        list = (0 until s.length()).map { i ->
            val x = s.getJSONObject(i)
            val name = x.getString("name")
            SystemInfo(name, x.getString("group"), x.optString("thumbs").takeIf { it.isNotEmpty() && it != "null" },
                strings(x.getJSONArray("ext")).map { it.lowercase() }.toSet(),
                per.optJSONArray(name)?.let { a -> strings(a).mapNotNull { emu(it) } } ?: emptyList())
        }
        byName = list.associateBy { it.name }
        val pt = o.getJSONArray("patterns")
        patterns = (0 until pt.length()).map { pt.getJSONArray(it).let { a -> Pattern.compile(a.getString(0), Pattern.CASE_INSENSITIVE) to a.getString(1) } }
    }

    /** Every package of every emulator, so they don't show up as games themselves. */
    fun allPackages(): Set<String> = list.flatMap { s -> s.emulators.flatMap { it.packages } }.toSet()

    /** The console a ROMs subfolder is for, from its name ("SNES", "Super Nintendo", "psx"…). */
    fun forFolder(name: String): String? {
        byName.keys.firstOrNull { it.equals(name, true) }?.let { return it }
        return patterns.firstOrNull { it.first.matcher(name).find() }?.second
    }

    fun strings(a: JSONArray) = (0 until a.length()).map { a.getString(it) }
}
