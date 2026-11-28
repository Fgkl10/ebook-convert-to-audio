package app.ebookaudio

import app.ebookaudio.api.Sentence
import app.ebookaudio.player.SentenceSync
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** AND-09: which sentence is read, and where the sentence buttons go (same rules as the web reader). */
class SentenceSyncTest {
    // three sentences: 0–2 s, 2–5 s (paragraph 0), 5–9 s (paragraph 1); the first starts after 300 ms of silence
    private val s = listOf(
        Sentence(i = 0, p = 0, text = "One.", startMs = 300, endMs = 2_000),
        Sentence(i = 1, p = 0, text = "Two.", startMs = 2_000, endMs = 5_000),
        Sentence(i = 2, p = 1, text = "Three.", startMs = 5_000, endMs = 9_000),
    )

    @Test
    fun sentenceAtAPosition() {
        assertEquals(-1, SentenceSync.at(emptyList(), 1_000))
        assertEquals(0, SentenceSync.at(s, 0))        // before the first sentence: the first
        assertEquals(0, SentenceSync.at(s, 1_999))
        assertEquals(1, SentenceSync.at(s, 2_000))    // a start belongs to its sentence
        assertEquals(2, SentenceSync.at(s, 8_000))
        assertEquals(2, SentenceSync.at(s, 60_000))   // past the end: the last
        val many = (0 until 1_000).map { Sentence(i = it, text = "x", startMs = it * 1_000L) }
        (0 until 1_000).forEach { assertEquals(it, SentenceSync.at(many, it * 1_000L + 999)) }
    }

    @Test
    fun previousSentence() {
        assertEquals(2_000L, SentenceSync.previousStart(s, 4_000))  // 2 s into "Two": restart it
        assertEquals(300L, SentenceSync.previousStart(s, 3_000))    // 1 s into "Two": back to "One"
        assertEquals(300L, SentenceSync.previousStart(s, 500))      // in the first sentence: its start
        assertNull(SentenceSync.previousStart(emptyList(), 500))
    }

    @Test
    fun nextSentence() {
        assertEquals(2_000L, SentenceSync.nextStart(s, 0))
        assertEquals(5_000L, SentenceSync.nextStart(s, 2_000))
        assertNull(SentenceSync.nextStart(s, 6_000))                // last sentence: none
    }

    @Test
    fun paragraphs() {
        assertEquals(listOf(listOf(0, 1), listOf(2)), SentenceSync.paragraphs(s).map { p -> p.map { it.i } })
        assertEquals(emptyList<List<Sentence>>(), SentenceSync.paragraphs(emptyList()))
    }
}
