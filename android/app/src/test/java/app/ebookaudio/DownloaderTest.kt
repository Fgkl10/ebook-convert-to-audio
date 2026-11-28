package app.ebookaudio

import app.ebookaudio.api.ApiClient
import app.ebookaudio.api.Book
import app.ebookaudio.api.BookChapter
import app.ebookaudio.api.JSON
import app.ebookaudio.api.NotPaired
import app.ebookaudio.download.Downloader
import app.ebookaudio.library.LocalLibrary
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import okhttp3.mockwebserver.SocketPolicy
import okio.Buffer
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.io.IOException

/** AND-05: downloads with the token, resume with Range, keep only whole files, and fetch only what changed. */
class DownloaderTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private val server = MockWebServer()
    private val token = "AbC-123_xyzAbC-123_xyzAbC-123_xy"
    private val audio = mapOf(
        "ch000.m4a" to ByteArray(300_000) { (it % 251).toByte() },
        "ch001.m4a" to ByteArray(120_000) { (it % 13).toByte() },
    )
    private var updated = mapOf(1 to 1_000L, 2 to 1_000L)
    private var cutOff: String? = null // a file whose transfer the server breaks off
    private val requests = mutableListOf<RecordedRequest>()
    private lateinit var library: LocalLibrary
    private lateinit var api: ApiClient

    private fun serverBook() = Book(
        id = "book-1", title = "Book", author = "Someone", complete = true,
        chapters = audio.keys.sorted().mapIndexed { i, name ->
            BookChapter(index = i, number = i + 1, title = "Chapter ${i + 1}", audio = name, durationMs = 1_000,
                sizeBytes = audio.getValue(name).size.toLong(), updatedMs = updated.getValue(i + 1))
        },
    )

    @Before
    fun start() {
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                requests += request
                if (request.getHeader("Authorization") != "Bearer $token") {
                    return MockResponse().setResponseCode(401).setBody("""{"detail": "Pair this device"}""")
                }
                val path = request.path!!.substringBefore('?')
                if (path == "/api/v1/books/book-1") {
                    return MockResponse().setBody(JSON.encodeToString(Book.serializer(), serverBook()))
                }
                val name = path.removePrefix("/api/v1/books/book-1/files/")
                val bytes = audio[name] ?: return MockResponse().setResponseCode(404)
                val range = request.getHeader("Range")
                val response = if (range != null) {
                    val from = range.removePrefix("bytes=").removeSuffix("-").toInt()
                    MockResponse().setResponseCode(206)
                        .setHeader("Content-Range", "bytes $from-${bytes.size - 1}/${bytes.size}")
                        .setBody(Buffer().write(bytes, from, bytes.size - from))
                } else {
                    MockResponse().setBody(Buffer().write(bytes))
                }
                if (name == cutOff) response.setSocketPolicy(SocketPolicy.DISCONNECT_DURING_RESPONSE_BODY)
                return response
            }
        }
        server.start()
        library = LocalLibrary(File(tmp.root, "books"))
        api = ApiClient(server.url("/").toString().trimEnd('/'), token, OkHttpClient())
    }

    @After
    fun stop() = server.shutdown()

    private fun file(name: String) = File(library.dir("book-1"), name)

    @Test
    fun downloadsTheWholeBook() {
        val progress = mutableListOf<Long>()
        val book = Downloader(api, library).download("book-1", progress = { done, _, _ -> progress += done })
        assertEquals(listOf(1, 2), book.chapters.map { it.number })
        audio.forEach { (name, bytes) -> assertArrayEquals(bytes, file(name).readBytes()) }
        assertEquals(book, library.book("book-1"))
        assertEquals(420_000L, progress.last())
        assertTrue(requests.all { it.getHeader("Authorization") == "Bearer $token" })
        assertTrue(tmp.root.walk().none { it.name.endsWith(".part") || it.name.endsWith(".tmp") })
    }

    @Test
    fun aCutOffChapterIsNeverUsedAndResumesWithRange() {
        cutOff = "ch000.m4a"
        try {
            Downloader(api, library).download("book-1")
            throw AssertionError("expected the cut to fail the download")
        } catch (e: IOException) {
            // expected
        }
        assertFalse(file("ch000.m4a").exists())        // no half file under the real name
        assertNull(library.book("book-1"))                  // and not listed
        val part = file("ch000.m4a.part")
        assertTrue(part.length() in 1 until 300_000)

        cutOff = null
        requests.clear()
        val book = Downloader(api, library).download("book-1")
        assertEquals(listOf(1, 2), book.chapters.map { it.number })
        assertArrayEquals(audio.getValue("ch000.m4a"), file("ch000.m4a").readBytes())
        val resumed = requests.first { it.path!!.endsWith("ch000.m4a") }
        assertTrue(resumed.getHeader("Range")!!.startsWith("bytes="))
        assertFalse(part.exists())
    }

    @Test
    fun fetchesOnlyChangedOrMissingChapters() {
        Downloader(api, library).download("book-1", wanted = setOf(1))
        assertEquals(listOf(1), library.book("book-1")!!.chapters.map { it.number })

        updated = mapOf(1 to 2_000L, 2 to 1_000L) // chapter 1 re-converted on the PC
        requests.clear()
        Downloader(api, library).download("book-1")
        val fetched = requests.map { it.path!!.substringAfterLast('/') }.filter { it.endsWith(".m4a") }
        assertEquals(listOf("ch000.m4a", "ch001.m4a"), fetched)
        assertEquals(2_000L, library.book("book-1")!!.chapters[0].updatedMs)

        requests.clear()
        Downloader(api, library).download("book-1") // nothing changed: nothing fetched
        assertTrue(requests.none { it.path!!.endsWith(".m4a") })
    }

    @Test(expected = NotPaired::class)
    fun aWrongTokenMeansNotPaired() {
        Downloader(ApiClient(api.baseUrl, "wrong-token-wrong-token-wrong-to", OkHttpClient()), library).download("book-1")
    }

    @Test
    fun libraryRefusesPathsOutsideItsFolder() {
        listOf("../x", "UPPER", "", "a/b").forEach { id ->
            assertTrue(id, runCatching { library.dir(id) }.isFailure)
        }
        listOf("../ch000.m4a", ".hidden", "a/b.m4a").forEach { name ->
            assertTrue(name, runCatching { library.file("book-1", name) }.isFailure)
        }
    }
}
