package app.ebookaudio

import app.ebookaudio.api.Book
import app.ebookaudio.api.BookChapter
import app.ebookaudio.library.Versions
import app.ebookaudio.library.Versions.State
import app.ebookaudio.player.MediaIds
import app.ebookaudio.settings.Position
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** AND-04: what needs downloading (D-038 chapter versions), positions and media ids. */
class VersionsTest {
    private fun ch(n: Int, size: Long = 100, updated: Long = 1_000, duration: Long = 60_000) =
        BookChapter(number = n, title = "Chapter $n", audio = "ch%03d.m4a".format(n - 1), durationMs = duration,
            sizeBytes = size, updatedMs = updated)

    private fun book(vararg chapters: BookChapter) = Book(id = "b", title = "B", chapters = chapters.toList())

    @Test
    fun chapterStates() {
        assertEquals(State.NOT_DOWNLOADED, Versions.state(null, ch(1)))
        assertEquals(State.DOWNLOADED, Versions.state(ch(1), ch(1)))
        assertEquals(State.UPDATE_AVAILABLE, Versions.state(ch(1), ch(1, updated = 2_000))) // re-converted
        assertEquals(State.UPDATE_AVAILABLE, Versions.state(ch(1), ch(1, size = 101)))
        assertEquals(State.DOWNLOADED, Versions.state(ch(1), null)) // gone from the PC: keep it
    }

    @Test
    fun toDownloadTakesMissingAndChangedChapters() {
        val server = book(ch(1), ch(2, updated = 2_000), ch(3), ch(5))
        val local = book(ch(1), ch(2))
        assertEquals(listOf(2, 3, 5), Versions.toDownload(local, server).map { it.number })
        assertEquals(listOf(3), Versions.toDownload(local, server, wanted = setOf(1, 3)).map { it.number })
        assertEquals(listOf(1, 2, 3, 5), Versions.toDownload(null, server).map { it.number })
    }

    @Test
    fun mergeKeepsThePhonesChaptersInOrder() {
        val server = book(ch(1), ch(2, updated = 2_000), ch(3)).copy(title = "New title", complete = true)
        val local = book(ch(3), ch(2))
        val merged = Versions.merge(local, server, ch(2, updated = 2_000))
        assertEquals("New title", merged.title)
        assertEquals(listOf(2, 3), merged.chapters.map { it.number })
        assertEquals(listOf(0, 1), merged.chapters.map { it.index })
        assertEquals(2_000, merged.chapters[0].updatedMs)
        assertEquals(120_000, merged.durationMs) // the phone's chapters only
    }

    @Test
    fun positionsAndMediaIds() {
        assertEquals(Position(3, 12_345), Position.decode(Position(3, 12_345).encode()))
        listOf(null, "", "3", "x:1", "3:x", "0:5", "3:-1", "1:2:3").forEach { assertNull(it, Position.decode(it)) }
        assertEquals("my-book-1a2b3c4d" to 7, MediaIds.parse(MediaIds.of("my-book-1a2b3c4d", 7)))
        listOf(null, "", "b", "|3", "b|x", "b|1|2").forEach { assertNull(it, MediaIds.parse(it)) }
    }
}
