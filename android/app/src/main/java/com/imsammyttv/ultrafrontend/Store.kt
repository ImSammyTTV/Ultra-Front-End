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

class Emu(val label: String, val emu: String, val cmd: String)
class SystemInfo(val name: String, val group: String, val thumbs: String?, val ext: Set<String>, val emulators: List<Emu>)

/** The consoles and their Android emulators (assets/systems.json, made by tools/make_android_tables.py). */
object Systems {
    lateinit var list: List<SystemInfo>
    lateinit var byName: Map<String, SystemInfo>
    lateinit var packages: Map<String, List<String>>  // emulator -> "package/activity" entries, preferred first
    private lateinit var patterns: List<Pair<Pattern, String>>

    fun load(ctx: Context) {
        val o = JSONObject(ctx.assets.open("systems.json").bufferedReader().readText())
        val s = o.getJSONArray("systems")
        list = (0 until s.length()).map { i ->
            val x = s.getJSONObject(i)
            val e = x.getJSONArray("emulators")
            SystemInfo(x.getString("name"), x.getString("group"), x.optString("thumbs").takeIf { it.isNotEmpty() && it != "null" },
                strings(x.getJSONArray("ext")).toSet(),
                (0 until e.length()).map { j -> e.getJSONObject(j).let { Emu(it.getString("label"), it.getString("emu"), it.getString("cmd")) } })
        }
        byName = list.associateBy { it.name }
        val p = o.getJSONObject("packages")
        packages = p.keys().asSequence().associateWith { strings(p.getJSONArray(it)) }
        val pt = o.getJSONArray("patterns")
        patterns = (0 until pt.length()).map { pt.getJSONArray(it).let { a -> Pattern.compile(a.getString(0), Pattern.CASE_INSENSITIVE) to a.getString(1) } }
    }

    /** The console a ROMs subfolder is for, from its name ("SNES", "Super Nintendo", "psx"…). */
    fun forFolder(name: String): String? {
        byName.keys.firstOrNull { it.equals(name, true) }?.let { return it }
        return patterns.firstOrNull { it.first.matcher(name).find() }?.second
    }

    fun strings(a: JSONArray) = (0 until a.length()).map { a.getString(it) }
}
