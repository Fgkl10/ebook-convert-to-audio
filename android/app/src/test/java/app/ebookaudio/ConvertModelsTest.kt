package app.ebookaudio

import app.ebookaudio.api.Draft
import app.ebookaudio.api.DraftChapter
import app.ebookaudio.api.DraftDetail
import app.ebookaudio.api.JSON
import app.ebookaudio.api.Job
import app.ebookaudio.api.Report
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** AND-06: the Convert tab reads what the PC sends (fixtures from tests/test_android_contract.py, AND-01). */
class ConvertModelsTest {
    private fun fixture(name: String): String = javaClass.classLoader!!.getResource("api/$name")!!.readText()

    @Test
    fun drafts() {
        val drafts = JSON.decodeFromString<List<Draft>>(fixture("drafts.json"))
        assertEquals(1, drafts.size)
        with(drafts[0]) {
            assertEquals("story.txt", file)
            assertEquals("done", status)
            assertEquals(listOf(1, 2), converted)
            assertTrue(chapters == 2 && bookId != null && jobId != null)
        }
    }

    @Test
    fun draftDetailAndReport() {
        val d = JSON.decodeFromString<DraftDetail>(fixture("draft.json"))
        val report = d.report!!
        assertEquals(listOf("Chapter 1", "Chapter 2"), report.chapters.map { it.first })
        assertTrue(report.chapters.all { it.second > 0 })
        assertEquals("af_heart", d.bookVoice)
        assertEquals(1.0, d.bookSpeed!!, 0.0)
    }

    @Test
    fun reportPairs() { // the fixture's story removes nothing: check the pair decoding by hand
        val r = JSON.decodeFromString<Report>(
            """{"chapters": [["One", 12], ["Two", 3400]], "removed": [["page number", "17"], ["blank", ""]],
               "checks": ["Look at chapter 2"]}""")
        assertEquals(listOf("One" to 12, "Two" to 3400), r.chapters)
        assertEquals(listOf("page number: 17", "blank: "), r.removed)
        assertEquals(listOf("Look at chapter 2"), r.checks)
    }

    @Test
    fun chapterAndJobs() {
        val ch = JSON.decodeFromString<DraftChapter>(fixture("draft_chapter.json"))
        assertEquals(0, ch.index)
        assertTrue(ch.paragraphs.isNotEmpty())
        val jobs = JSON.decodeFromString<List<Job>>(fixture("jobs.json"))
        with(jobs.single()) {
            assertEquals("done", status)
            assertEquals(done, total)
            assertTrue(draftId != null && bookId != null)
        }
    }
}
