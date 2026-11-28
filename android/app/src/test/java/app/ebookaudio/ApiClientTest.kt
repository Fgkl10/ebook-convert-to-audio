package app.ebookaudio

import app.ebookaudio.api.ApiClient
import app.ebookaudio.api.ApiError
import app.ebookaudio.api.NotPaired
import app.ebookaudio.api.UploadFile
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/** AND-08: the Convert tab's requests: multipart uploads, the approve body, cancel/discard/delete and errors. */
class ApiClientTest {
    private val server = MockWebServer()
    private val token = "AbC-123_xyzAbC-123_xyzAbC-123_xy"
    private lateinit var api: ApiClient

    @Before
    fun start() {
        server.start()
        api = ApiClient(server.url("/").toString().trimEnd('/'), token, OkHttpClient())
    }

    @After
    fun stop() = server.shutdown()

    private fun ok(body: String) = server.enqueue(MockResponse().setBody(body))

    @Test
    fun uploadStreamsTheFileWithItsFields() = runBlocking {
        val bytes = ByteArray(200_000) { (it % 97).toByte() }
        ok("""{"draft_id": "d1"}""")
        val progress = mutableListOf<Long>()
        val created = api.upload(UploadFile("My Book.epub", bytes.size.toLong()) { bytes.inputStream() },
            "bm_george", 1.25, auto = true, ocr = "never") { progress += it }
        assertEquals("d1", created.draftId)
        val r = server.takeRequest()
        assertEquals("POST", r.method)
        assertEquals("/api/v1/drafts", r.path)
        assertEquals("Bearer $token", r.getHeader("Authorization"))
        val body = r.body.readByteArray()
        val text = String(body, Charsets.ISO_8859_1)
        listOf("name=\"voice\"", "bm_george", "name=\"speed\"", "1.25", "name=\"auto\"", "true",
            "name=\"ocr\"", "never", "filename=\"My Book.epub\"").forEach { assertTrue(it, it in text) }
        // the file's bytes arrive unchanged
        val start = text.indexOf("\r\n\r\n", text.indexOf("filename=")) + 4
        assertTrue(bytes.contentEquals(body.copyOfRange(start, start + bytes.size)))
        assertEquals(bytes.size.toLong(), progress.last())
    }

    @Test
    fun cleanedUploadGoesToItsOwnRoute() = runBlocking {
        ok("""{"draft_id": "d2", "job_id": "j2"}""")
        val created = api.uploadCleaned(UploadFile("b.std.epub", 3) { "abc".byteInputStream() }, "af_heart", 1.0)
        assertEquals("j2", created.jobId)
        assertEquals("/api/v1/drafts/cleaned", server.takeRequest().path)
    }

    @Test
    fun approveSendsNullChaptersForAll() = runBlocking {
        ok("""{"job_id": "j"}""")
        ok("""{"job_id": "k"}""")
        api.approve("d 1", "af_heart", 1.0, null)
        api.approve("d 1", "af_heart", 0.9, listOf(2, 5))
        val all = server.takeRequest()
        assertEquals("/api/v1/drafts/d%201/approve", all.path)
        assertEquals("application/json; charset=utf-8", all.getHeader("Content-Type"))
        assertEquals("""{"voice":"af_heart","speed":1.0,"chapters":null}""", all.body.readUtf8())
        assertEquals("""{"voice":"af_heart","speed":0.9,"chapters":[2,5]}""", server.takeRequest().body.readUtf8())
    }

    @Test
    fun cancelDiscardDelete() = runBlocking {
        val job = """{"id": "j", "status": "cancelled"}"""
        ok(job); ok(job); ok("""{"ok": true}"""); ok("""{"ok": true}""")
        api.cancelDraft("d")
        api.cancelJob("j")
        api.discardDraft("d")
        api.deleteBook("b")
        assertEquals(listOf("POST /api/v1/drafts/d/cancel", "POST /api/v1/jobs/j/cancel",
            "DELETE /api/v1/drafts/d", "DELETE /api/v1/books/b"),
            (1..4).map { server.takeRequest().let { r -> "${r.method} ${r.path}" } })
    }

    @Test
    fun errorsCarryTheServersMessage() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(409).setBody("""{"detail": "The book is being converted"}"""))
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"detail": "Pair this device"}"""))
        try {
            api.deleteBook("b"); throw AssertionError("expected 409")
        } catch (e: ApiError) {
            assertEquals(409, e.code)
            assertEquals("The book is being converted", e.message)
        }
        try {
            api.drafts(); throw AssertionError("expected 401")
        } catch (_: NotPaired) {
        }
    }

    @Test
    fun voiceSampleUrlCarriesTheToken() {
        assertEquals("${api.baseUrl}/api/v1/voices/af_heart/sample?token=$token", api.voiceSampleUrl("af_heart"))
    }
}
