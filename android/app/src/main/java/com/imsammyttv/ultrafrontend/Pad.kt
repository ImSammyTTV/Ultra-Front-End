package com.imsammyttv.ultrafrontend

import android.os.Handler
import android.os.Looper
import org.json.JSONArray
import org.json.JSONObject

/**
 * The controller, as the Windows helper sends it: each press becomes an action ("ok", "back", "up"…) that the page
 * picks up with GET /api/pad?after=N (a long poll). Held directions repeat: once after 340 ms, then every 105 ms.
 */
object Pad {
    private val lock = Object()
    private var seq = 0L
    private val events = ArrayDeque<Pair<Long, String>>()
    @Volatile var pads = 0
    private val main = Handler(Looper.getMainLooper())
    private val repeaters = HashMap<String, Runnable>()

    fun emit(action: String) {
        synchronized(lock) {
            seq++
            events.addLast(seq to action)
            while (events.size > 50) events.removeFirst()
            lock.notifyAll()
        }
    }

    /** A direction pressed (true) or let go (false): the first press at once, then the repeats while it's held. */
    fun hold(action: String, down: Boolean) {
        if (!down) { repeaters.remove(action)?.let { main.removeCallbacks(it) }; return }
        if (repeaters.containsKey(action)) return
        emit(action)
        val r = object : Runnable {
            override fun run() { emit(action); main.postDelayed(this, 105) }
        }
        repeaters[action] = r
        main.postDelayed(r, 340)
    }

    fun releaseAll() { repeaters.values.forEach { main.removeCallbacks(it) }; repeaters.clear() }

    fun wait(after: Long, timeoutMs: Long = 20000): JSONObject {
        synchronized(lock) {
            if (after > seq) return JSONObject().put("seq", seq).put("actions", JSONArray()).put("pads", pads)
            val end = System.currentTimeMillis() + timeoutMs
            while (seq <= after) {
                val left = end - System.currentTimeMillis()
                if (left <= 0) break
                lock.wait(left)
            }
            val a = JSONArray()
            events.filter { it.first > after }.forEach { a.put(it.second) }
            return JSONObject().put("seq", seq).put("actions", a).put("pads", pads)
        }
    }
}
