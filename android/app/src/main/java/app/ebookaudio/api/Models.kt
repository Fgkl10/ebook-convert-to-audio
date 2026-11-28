package app.ebookaudio.api

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/**
 * The parts of the PC's JSON API v1 the player uses (desktop/server/api.py). Unknown fields are ignored, so the
 * server may add fields without breaking the app; tests/test_android_contract.py keeps the fixtures these are
 * tested against in step with the server.
 */
val JSON = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    coerceInputValues = true
}

@Serializable
data class Info(
    @SerialName("api_version") val apiVersion: Int,
    val name: String = "",
    val url: String = "",
    val voices: List<String> = emptyList(),
    @SerialName("default_voice") val defaultVoice: String = "",
    /** The voices by the language they speak (desktop D-043); empty from a PC older than that. */
    @SerialName("languages") val languageList: List<VoiceLanguage> = emptyList(),
) {
    /** By language; a PC before D-043 has English voices only. */
    val languages: List<VoiceLanguage>
        get() = languageList.ifEmpty { listOf(VoiceLanguage("en", voices, defaultVoice.ifBlank { voices.firstOrNull().orEmpty() })) }
}

@Serializable
data class VoiceLanguage(
    /** "en" or "zh". */
    val code: String,
    val voices: List<String> = emptyList(),
    @SerialName("default_voice") val defaultVoice: String = "",
)

@Serializable
data class BookSummary(
    val id: String,
    val title: String,
    val author: String? = null,
    val cover: String? = null,
    val voice: String? = null,
    val complete: Boolean = false,
    val chapters: Int = 0,
    @SerialName("chapters_total") val chaptersTotal: Int? = null,
    val converting: Boolean = false,
    @SerialName("duration_ms") val durationMs: Long = 0,
    @SerialName("size_bytes") val sizeBytes: Long = 0,
)

@Serializable
data class Sentence(
    val i: Int,
    val p: Int = 0,
    val text: String,
    @SerialName("start_ms") val startMs: Long,
    @SerialName("end_ms") val endMs: Long? = null,
)

@Serializable
data class BookChapter(
    val index: Int = 0,
    /** 1-based number in the cleaned book; stays the same as more chapters are converted (D-035). */
    val number: Int,
    val title: String,
    /** File name of the chapter audio, e.g. ch002.m4a. */
    val audio: String,
    @SerialName("duration_ms") val durationMs: Long = 0,
    /** With [updatedMs], the chapter's version: a re-converted chapter keeps its file name (D-038). */
    @SerialName("size_bytes") val sizeBytes: Long = 0,
    @SerialName("updated_ms") val updatedMs: Long = 0,
    val sentences: List<Sentence> = emptyList(),
)

@Serializable
data class Book(
    val id: String,
    val title: String,
    val author: String? = null,
    val cover: String? = null,
    val voice: String? = null,
    val speed: Double? = null,
    val complete: Boolean = false,
    @SerialName("duration_ms") val durationMs: Long = 0,
    val chapters: List<BookChapter> = emptyList(),
)
