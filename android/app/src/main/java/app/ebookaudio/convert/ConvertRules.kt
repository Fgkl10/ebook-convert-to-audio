package app.ebookaudio.convert

import app.ebookaudio.api.Draft
import app.ebookaudio.api.DraftDetail
import app.ebookaudio.api.Job

/**
 * A draft's status line: [status] (a draft status, or null to show only the partial count) and, when only some
 * chapters are in the library, [converted] of [total]. The screen turns it into text (A-017).
 */
data class StatusLabel(val status: String?, val converted: Int? = null, val total: Int = 0)

/** The approve button: convert all again, approve all, or convert [Some.count] chapters. */
sealed interface ApproveLabel {
    data object AllAgain : ApproveLabel
    data object All : ApproveLabel
    data class Some(val count: Int) : ApproveLabel
}

/** Kept chapters of the book use [voice] at [speed]×, unlike the new ones. */
data class MixedVoice(val voice: String, val speed: Double?)

/**
 * The Convert tab's rules, the same as the PC's web page (desktop/web/app.js) so both clients agree (A-011). Pure
 * functions, unit-tested in ConvertRulesTest. They return values, not text, so the screens can localize them.
 */
object ConvertRules {
    /** Drafts still being cleaned or reviewed; the others were approved (app.js CLEAN_STATES). */
    fun isCleaning(d: Draft) = d.status in setOf("cleaning", "review", "error")

    /** "ready for review", or "converted 3 of 12" when only some chapters are in the library (D-035). */
    fun statusLabel(d: Draft): StatusLabel {
        val some = d.converted.isNotEmpty() && d.converted.size < d.chapters
        if (!some) return StatusLabel(d.status)
        return StatusLabel(if (d.status == "done") null else d.status, d.converted.size, d.chapters)
    }

    fun canCancel(d: Draft) = d.status in setOf("queued", "converting")
    fun canReview(d: Draft) = d.status in setOf("review", "done")
    fun canListen(d: Draft) = d.status == "done" && d.bookId != null
    fun canDiscard(d: Draft) = d.status in setOf("review", "done", "error")

    /** Jobs worth showing: not finished, or finished in the last 10 minutes. */
    fun visibleJobs(jobs: List<Job>, nowSeconds: Double): List<Job> =
        jobs.filter { it.status !in setOf("done", "cancelled") || nowSeconds - it.created < 600 }

    fun canCancel(j: Job) = j.status in setOf("queued", "running")

    /**
     * The chapters ticked when a review opens (1-based): the ones not converted yet; after an interrupted or failed
     * run (status back to review with a last approval), only the ones that run was doing.
     */
    fun defaultPicks(d: DraftDetail): Set<Int> {
        val count = d.report?.chapters?.size ?: 0
        val converted = d.converted.toSet()
        val last = d.lastChapters
        val resume = last != null && d.status == "review"
        return (1..count).filter { it !in converted && (!resume || it in last) }.toSet()
    }

    /** Chapters not converted yet (the "New only" button). */
    fun newOnly(d: DraftDetail): Set<Int> =
        (1..(d.report?.chapters?.size ?: 0)).filter { it !in d.converted.toSet() }.toSet()

    fun canApprove(d: DraftDetail, picked: Set<Int>) = picked.isNotEmpty() && d.status in setOf("review", "done")

    fun approveLabel(d: DraftDetail, picked: Set<Int>): ApproveLabel {
        val all = d.report?.chapters?.size ?: 0
        val n = picked.size
        return when {
            n == all && d.status == "done" -> ApproveLabel.AllAgain
            n == all -> ApproveLabel.All
            else -> ApproveLabel.Some(n)
        }
    }

    /** null for "all chapters" (what the server expects), else the sorted picks. */
    fun approveChapters(d: DraftDetail, picked: Set<Int>): List<Int>? =
        if (picked.size == (d.report?.chapters?.size ?: 0)) null else picked.sorted()

    /** A warning when kept chapters of the book use another voice or speed than the new ones would. */
    fun mixedVoiceWarning(d: DraftDetail, picked: Set<Int>, voice: String, speed: Double): MixedVoice? {
        val kept = d.converted.count { it !in picked }
        val bookVoice = d.bookVoice ?: return null
        if (kept == 0) return null
        if (voice == bookVoice && speed == d.bookSpeed) return null
        return MixedVoice(bookVoice, d.bookSpeed)
    }

    private val UPLOADABLE = Regex("""\.(epub|pdf|txt)$""", RegexOption.IGNORE_CASE)

    /** Book files the server cleans. */
    fun isUploadable(name: String) = UPLOADABLE.containsMatchIn(name)

    /** Only an EPUB can be an already-cleaned book (.std.epub). */
    fun canBeCleaned(name: String) = name.endsWith(".epub", ignoreCase = true)

    fun isPdf(name: String) = name.endsWith(".pdf", ignoreCase = true)

    /** The server's answer to a cleaned upload of a book that isn't cleaned (offer to clean it instead). */
    fun isNotCleaned(message: String?) = message?.contains("Not a cleaned book") == true
}
