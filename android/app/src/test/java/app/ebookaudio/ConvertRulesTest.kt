package app.ebookaudio

import app.ebookaudio.api.Draft
import app.ebookaudio.api.DraftDetail
import app.ebookaudio.api.Job
import app.ebookaudio.api.Report
import app.ebookaudio.convert.ConvertRules
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** AND-07: the Convert tab follows the web page's rules (desktop/web/app.js, A-011). */
class ConvertRulesTest {
    private fun report(n: Int) = Report(chapterPairs = (1..n).map { JsonArray(listOf(JsonPrimitive("Ch $it"), JsonPrimitive(100))) })

    private fun detail(
        status: String = "review", chapters: Int = 4, converted: List<Int> = emptyList(), last: List<Int>? = null,
        bookVoice: String? = null, bookSpeed: Double? = null,
    ) = DraftDetail(id = "d", status = status, report = report(chapters), converted = converted, lastChapters = last,
        bookVoice = bookVoice, bookSpeed = bookSpeed)

    @Test
    fun statusLabels() {
        assertEquals("ready for review", ConvertRules.statusLabel(Draft("d", status = "review")))
        assertEquals("converted 2 of 5", ConvertRules.statusLabel(Draft("d", status = "done", chapters = 5, converted = listOf(1, 2))))
        assertEquals("converted", ConvertRules.statusLabel(Draft("d", status = "done", chapters = 2, converted = listOf(1, 2))))
        assertEquals("converting · converted 1 of 3",
            ConvertRules.statusLabel(Draft("d", status = "converting", chapters = 3, converted = listOf(1))))
        assertEquals("odd", ConvertRules.statusLabel(Draft("d", status = "odd")))
    }

    @Test
    fun buttonsPerStatus() {
        fun d(s: String) = Draft("d", status = s, bookId = "b")
        assertTrue(ConvertRules.isCleaning(d("cleaning")) && ConvertRules.isCleaning(d("error")))
        assertFalse(ConvertRules.isCleaning(d("queued")))
        assertTrue(ConvertRules.canCancel(d("queued")) && ConvertRules.canCancel(d("converting")))
        assertFalse(ConvertRules.canCancel(d("review")))
        assertTrue(ConvertRules.canReview(d("done")) && !ConvertRules.canReview(d("converting")))
        assertTrue(ConvertRules.canListen(d("done")) && !ConvertRules.canListen(Draft("d", status = "done")))
        assertFalse(ConvertRules.canDiscard(d("converting")))
    }

    @Test
    fun visibleJobs() {
        val now = 10_000.0
        val jobs = listOf(
            Job("a", status = "running", created = 0.0),
            Job("b", status = "done", created = now - 60),
            Job("c", status = "done", created = now - 700),
            Job("d", status = "cancelled", created = now - 700),
            Job("e", status = "error", created = 0.0),
        )
        assertEquals(listOf("a", "b", "e"), ConvertRules.visibleJobs(jobs, now).map { it.id })
    }

    @Test
    fun defaultPicks() {
        assertEquals(setOf(1, 2, 3, 4), ConvertRules.defaultPicks(detail()))
        assertEquals(setOf(3, 4), ConvertRules.defaultPicks(detail(converted = listOf(1, 2))))
        // an interrupted run is back in review: only the chapters it was doing, minus the finished ones
        assertEquals(setOf(3), ConvertRules.defaultPicks(detail(converted = listOf(2), last = listOf(2, 3))))
        // after a finished run the last approval doesn't narrow the picks
        assertEquals(setOf(4), ConvertRules.defaultPicks(detail(status = "done", converted = listOf(1, 2, 3), last = listOf(3))))
        assertEquals(setOf(3, 4), ConvertRules.newOnly(detail(converted = listOf(1, 2))))
    }

    @Test
    fun approve() {
        val d = detail()
        assertEquals("Approve & convert", ConvertRules.approveLabel(d, setOf(1, 2, 3, 4)))
        assertEquals("Convert all again", ConvertRules.approveLabel(detail(status = "done"), setOf(1, 2, 3, 4)))
        assertEquals("Convert 1 chapter", ConvertRules.approveLabel(d, setOf(2)))
        assertEquals("Convert 2 chapters", ConvertRules.approveLabel(d, setOf(2, 4)))
        assertNull(ConvertRules.approveChapters(d, setOf(1, 2, 3, 4)))
        assertEquals(listOf(2, 4), ConvertRules.approveChapters(d, setOf(4, 2)))
        assertFalse(ConvertRules.canApprove(d, emptySet()))
        assertFalse(ConvertRules.canApprove(detail(status = "converting"), setOf(1)))
        assertTrue(ConvertRules.canApprove(detail(status = "done"), setOf(1)))
    }

    @Test
    fun mixedVoiceWarning() {
        val d = detail(converted = listOf(1, 2), bookVoice = "af_heart", bookSpeed = 1.0)
        assertNull(ConvertRules.mixedVoiceWarning(d, setOf(3), "af_heart", 1.0))          // same voice
        assertTrue(ConvertRules.mixedVoiceWarning(d, setOf(3), "bm_george", 1.0)!!.contains("af_heart at 1.0×"))
        assertTrue(ConvertRules.mixedVoiceWarning(d, setOf(3), "af_heart", 1.2) != null) // other speed
        assertNull(ConvertRules.mixedVoiceWarning(d, setOf(1, 2, 3), "bm_george", 1.0))   // nothing kept
        assertNull(ConvertRules.mixedVoiceWarning(detail(), setOf(1), "bm_george", 1.0))  // no book yet
    }

    @Test
    fun files() {
        listOf("a.epub", "B.PDF", "notes.txt", "x.std.epub").forEach { assertTrue(it, ConvertRules.isUploadable(it)) }
        listOf("a.mobi", "a.epub.zip", "pdf", "a.docx").forEach { assertFalse(it, ConvertRules.isUploadable(it)) }
        assertTrue(ConvertRules.canBeCleaned("x.std.epub") && !ConvertRules.canBeCleaned("x.pdf"))
        assertTrue(ConvertRules.isNotCleaned("Not a cleaned book (.std.epub): clean it on the Clean page first."))
        assertFalse(ConvertRules.isNotCleaned(null))
    }
}
