package app.ebookaudio

import app.ebookaudio.api.Book
import app.ebookaudio.api.BookSummary
import app.ebookaudio.api.Info
import app.ebookaudio.api.JSON
import app.ebookaudio.pairing.PairUrl
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * AND-03: the app reads what the PC sends. The fixtures are real server responses, kept in step with the server by
 * tests/test_android_contract.py (AND-01).
 */
class ModelsTest {
    private fun fixture(name: String): String =
        javaClass.classLoader!!.getResource("api/$name")!!.readText()

    @Test
    fun info() {
        val info = JSON.decodeFromString<Info>(fixture("info.json"))
        assertEquals(1, info.apiVersion)
        assertTrue("af_heart" in info.voices)
        // every address's pair_url is a link the scanner accepts
        val urls = JSON.parseToJsonElement(fixture("info.json")).jsonObject["urls"]!!.jsonArray
        assertTrue(urls.isNotEmpty())
        urls.forEach { u ->
            val pairing = PairUrl.parse(u.jsonObject["pair_url"]!!.jsonPrimitive.content)!!
            assertEquals(u.jsonObject["url"]!!.jsonPrimitive.content, pairing.baseUrl)
        }
    }

    @Test
    fun books() {
        val books = JSON.decodeFromString<List<BookSummary>>(fixture("books.json"))
        assertEquals(1, books.size)
        with(books[0]) {
            assertTrue(chapters > 0 && durationMs > 0 && sizeBytes > 0)
            assertEquals(chapters, chaptersTotal)
        }
    }

    @Test
    fun book() {
        val book = JSON.decodeFromString<Book>(fixture("book.json"))
        assertTrue(book.chapters.isNotEmpty())
        book.chapters.forEachIndexed { i, c ->
            assertEquals(i, c.index)
            assertEquals("ch%03d.m4a".format(c.number - 1), c.audio)
            assertTrue(c.sizeBytes > 0 && c.updatedMs > 1_000_000_000_000 && c.durationMs > 0)
            assertTrue(c.sentences.isNotEmpty())
            assertEquals(c.durationMs, c.sentences.last().endMs) // M5's sentence sync relies on this
        }
        // a round trip keeps everything the app uses
        assertEquals(book, JSON.decodeFromString<Book>(JSON.encodeToString(Book.serializer(), book)))
    }

    @Test
    fun ignoresFieldsItDoesNotKnow() {
        val b = JSON.decodeFromString<BookSummary>("""{"id": "x", "title": "T", "new_field": [1, 2], "author": null}""")
        assertEquals(BookSummary(id = "x", title = "T"), b)
    }
}
