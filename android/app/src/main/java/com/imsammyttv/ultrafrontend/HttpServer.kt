package com.imsammyttv.ultrafrontend

import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.io.OutputStream
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.URLDecoder
import java.util.concurrent.Executors

/** One request from the page: GET with a query, or POST with a JSON body. */
class Request(val method: String, val path: String, val query: Map<String, String>, val headers: Map<String, String>, val body: ByteArray)

/** An answer: bytes and their type, or a stream (asset files). */
class Response(val status: Int, val type: String, val body: ByteArray? = null, val stream: InputStream? = null, val cache: String = "no-store") {
    companion object {
        fun json(text: String, status: Int = 200) = Response(status, "application/json; charset=utf-8", text.toByteArray())
        fun error(status: Int, message: String) = json(org.json.JSONObject().put("error", message).toString(), status)
    }
}

/**
 * The page's own little server on 127.0.0.1:8137, as on Windows and Mac: the page and its /api calls come from the same
 * address, so app.js runs unchanged. Only this device can reach it (bound to the loopback address).
 */
class HttpServer(private val port: Int, private val handle: (Request) -> Response) {
    private val pool = Executors.newCachedThreadPool()
    private var socket: ServerSocket? = null

    fun start() {
        val s = ServerSocket(port, 50, InetAddress.getByName("127.0.0.1"))
        socket = s
        Thread({
            while (!s.isClosed) {
                val c = try { s.accept() } catch (e: Exception) { break }
                pool.execute { serve(c) }
            }
        }, "http").start()
    }

    fun stop() { try { socket?.close() } catch (_: Exception) {} }

    private fun serve(c: Socket) {
        c.use { sock ->
            sock.soTimeout = 30000
            val input = BufferedInputStream(sock.getInputStream())
            val out = sock.getOutputStream()
            while (true) {  // keep-alive: the page makes many small calls
                val req = try { read(input) } catch (e: Exception) { null } ?: return
                val res = try { handle(req) } catch (e: IllegalArgumentException) {
                    Response.error(400, e.message ?: "Bad request")
                } catch (e: Exception) {
                    android.util.Log.e("UFE", "route ${req.path}", e)
                    Response.error(500, "Something went wrong (${e.javaClass.simpleName}: ${e.message})")
                }
                try { write(out, res) } catch (e: Exception) { return }
                if (req.headers["connection"].equals("close", true)) return
            }
        }
    }

    private fun readLine(input: InputStream): String? {
        val b = ByteArrayOutputStream()
        while (true) {
            val ch = input.read()
            if (ch < 0) return if (b.size() == 0) null else b.toString("UTF-8")
            if (ch == '\n'.code) return b.toString("UTF-8").trimEnd('\r')
            b.write(ch)
            if (b.size() > 16384) throw IllegalStateException("line too long")
        }
    }

    private fun read(input: InputStream): Request? {
        val first = readLine(input) ?: return null
        val parts = first.split(" ")
        if (parts.size < 2) return null
        val headers = HashMap<String, String>()
        while (true) {
            val line = readLine(input) ?: return null
            if (line.isEmpty()) break
            val i = line.indexOf(':')
            if (i > 0) headers[line.substring(0, i).trim().lowercase()] = line.substring(i + 1).trim()
        }
        val size = headers["content-length"]?.toIntOrNull() ?: 0
        if (size < 0 || size > 1_000_000) throw IllegalStateException("too big")
        val body = ByteArray(size)
        var got = 0
        while (got < size) {
            val n = input.read(body, got, size - got)
            if (n < 0) break
            got += n
        }
        val target = parts[1]
        val q = target.indexOf('?')
        val path = URLDecoder.decode(if (q >= 0) target.substring(0, q) else target, "UTF-8")
        val query = HashMap<String, String>()
        if (q >= 0) target.substring(q + 1).split("&").filter { it.isNotEmpty() }.forEach {
            val e = it.indexOf('=')
            if (e > 0) query[URLDecoder.decode(it.substring(0, e), "UTF-8")] = URLDecoder.decode(it.substring(e + 1), "UTF-8")
            else query[URLDecoder.decode(it, "UTF-8")] = ""
        }
        return Request(parts[0].uppercase(), path, query, headers, body)
    }

    private fun write(out: OutputStream, r: Response) {
        val body = r.body ?: r.stream?.use { it.readBytes() } ?: ByteArray(0)
        val head = StringBuilder()
            .append("HTTP/1.1 ${r.status} ${if (r.status < 400) "OK" else "Error"}\r\n")
            .append("Content-Type: ${r.type}\r\n")
            .append("Content-Length: ${body.size}\r\n")
            .append("Cache-Control: ${r.cache}\r\n")
            .append("Connection: keep-alive\r\n\r\n")
        out.write(head.toString().toByteArray())
        out.write(body)
        out.flush()
    }
}
