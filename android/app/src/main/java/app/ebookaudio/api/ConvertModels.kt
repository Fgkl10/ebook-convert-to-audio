package app.ebookaudio.api

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive

/** The conversion side of the API (desktop/server/api.py: drafts and jobs), used by the Convert tab (M4b). */

@Serializable
data class Draft(
    val id: String,
    val file: String = "",
    /** cleaning, review, queued, converting, done, error */
    val status: String,
    val message: String = "",
    /** Progress while cleaning (scanned pages read). */
    val done: Int = 0,
    val total: Int = 0,
    val auto: Boolean = false,
    val voice: String = "",
    val speed: Double = 1.0,
    val ocr: String = "auto",
    val error: String? = null,
    val created: Double = 0.0,
    val chapters: Int = 0,
    val checks: Int = 0,
    @SerialName("job_id") val jobId: String? = null,
    @SerialName("book_id") val bookId: String? = null,
    /** The chapters of the last approval (null = all). */
    @SerialName("last_chapters") val lastChapters: List<Int>? = null,
    /** 1-based chapters already in the library book with this text. */
    val converted: List<Int> = emptyList(),
)

/** The cleaning report. The server sends pairs as JSON arrays: chapters [title, characters], removed [reason, text]. */
@Serializable
data class Report(
    val source: String = "",
    val method: String = "",
    @SerialName("chapters") val chapterPairs: List<JsonArray> = emptyList(),
    @SerialName("removed") val removedPairs: List<JsonArray> = emptyList(),
    val unconfirmed: List<String> = emptyList(),
    val notes: List<String> = emptyList(),
    val checks: List<String> = emptyList(),
) {
    /** (title, characters) per chapter. */
    val chapters: List<Pair<String, Int>>
        get() = chapterPairs.map { it[0].jsonPrimitive.content to (it.getOrNull(1)?.jsonPrimitive?.intOrNull ?: 0) }

    /** "reason: first characters" per removed part. */
    val removed: List<String>
        get() = removedPairs.map { it.joinToString(": ") { e -> e.jsonPrimitive.content } }
}

@Serializable
data class DraftDetail(
    val id: String,
    val file: String = "",
    val status: String,
    val voice: String = "",
    val speed: Double = 1.0,
    @SerialName("book_id") val bookId: String? = null,
    @SerialName("last_chapters") val lastChapters: List<Int>? = null,
    val converted: List<Int> = emptyList(),
    val report: Report? = null,
    /** The library book's voice and speed (latest conversion), or null. */
    @SerialName("book_voice") val bookVoice: String? = null,
    @SerialName("book_speed") val bookSpeed: Double? = null,
)

@Serializable
data class DraftChapter(val index: Int, val title: String, val paragraphs: List<String> = emptyList())

@Serializable
data class Job(
    val id: String,
    val file: String = "",
    val voice: String = "",
    val speed: Double = 1.0,
    /** queued, running, done, error, cancelled */
    val status: String,
    /** Sentences made so far, of [total] (0 until known). */
    val done: Int = 0,
    val total: Int = 0,
    val message: String = "",
    @SerialName("book_id") val bookId: String? = null,
    val error: String? = null,
    val created: Double = 0.0,
    @SerialName("draft_id") val draftId: String? = null,
)

@Serializable
data class DraftCreated(@SerialName("draft_id") val draftId: String, @SerialName("job_id") val jobId: String? = null)

@Serializable
data class JobCreated(@SerialName("job_id") val jobId: String)

@Serializable
data class ApproveRequest(val voice: String, val speed: Double, val chapters: List<Int>?)
