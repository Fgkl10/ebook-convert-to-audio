package app.ebookaudio.convert

import app.ebookaudio.api.Draft
import app.ebookaudio.api.DraftDetail
import app.ebookaudio.api.Job

/**
 * The Convert tab's rules, the same as the PC's web page (desktop/web/app.js) so both clients agree (A-011). Pure
 * functions, unit-tested in ConvertRulesTest.
 */
object ConvertRules {
    private val STATUS = mapOf(
        "cleaning" to "cleaning", "review" to "ready for review", "queued" to "waiting to convert",
        "converting" to "converting", "done" to "converted", "error" to "failed",
    )

    /** Drafts still being cleaned or reviewed; the others were approved (app.js CLEAN_STATES). */
    fun isCleaning(d: Draft) = d.status in setOf("cleaning", "review", "error")

    /** "ready for review", or "converted 3 of 12" when only some chapters are in the library (D-035). */
    fun statusLabel(d: Draft): String {
        val some = if (d.converted.isNotEmpty() && d.converted.size < d.chapters)
            "converted ${d.converted.size} of ${d.chapters}" else ""
        if (some.isNotEmpty() && d.status == "done") return some
        return (STATUS[d.status] ?: d.status) + if (some.isNotEmpty()) " · $some" else ""
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

    fun approveLabel(d: DraftDetail, picked: Set<Int>): String {
        val all = d.report?.chapters?.size ?: 0
        val n = picked.size
        return when {
            n == all && d.status == "done" -> "Convert all again"
            n == all -> "Approve & convert"
            else -> "Convert $n chapter${if (n == 1) "" else "s"}"
        }
    }

    /** null for "all chapters" (what the server expects), else the sorted picks. */
    fun approveChapters(d: DraftDetail, picked: Set<Int>): List<Int>? =
        if (picked.size == (d.report?.chapters?.size ?: 0)) null else picked.sorted()

    /** A warning when kept chapters of the book use another voice or speed than the new ones would. */
    fun mixedVoiceWarning(d: DraftDetail, picked: Set<Int>, voice: String, speed: Double): String? {
        val kept = d.converted.count { it !in picked }
        val bookVoice = d.bookVoice ?: return null
        if (kept == 0) return null
        if (voice == bookVoice && speed == d.bookSpeed) return null
        return "Other chapters of this book use $bookVoice at ${d.bookSpeed}×; the book will mix voices."
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
