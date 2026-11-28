package app.ebookaudio.library

import app.ebookaudio.api.Book
import app.ebookaudio.api.BookChapter

/** Which chapters the phone has, and which changed on the PC since (D-038: size and time are the version). */
object Versions {
    enum class State { NOT_DOWNLOADED, DOWNLOADED, UPDATE_AVAILABLE }

    fun state(local: BookChapter?, server: BookChapter?): State = when {
        local == null -> State.NOT_DOWNLOADED
        server == null -> State.DOWNLOADED // gone from the PC: keep the phone's copy
        local.sizeBytes != server.sizeBytes || local.updatedMs != server.updatedMs -> State.UPDATE_AVAILABLE
        else -> State.DOWNLOADED
    }

    /** The server's chapters to fetch: missing or changed ones, limited to [wanted] chapter numbers when given. */
    fun toDownload(local: Book?, server: Book, wanted: Set<Int>? = null): List<BookChapter> {
        val have = local?.chapters?.associateBy { it.number } ?: emptyMap()
        return server.chapters
            .filter { wanted == null || it.number in wanted }
            .filter { state(have[it.number], it) != State.DOWNLOADED }
            .sortedBy { it.number }
    }

    /** The local manifest after [chapter] was downloaded: the server's book facts, the phone's chapters. */
    fun merge(local: Book?, server: Book, chapter: BookChapter? = null): Book {
        val kept = local?.chapters.orEmpty().filter { chapter == null || it.number != chapter.number }
        val chapters = (kept + listOfNotNull(chapter)).sortedBy { it.number }.mapIndexed { i, c -> c.copy(index = i) }
        return server.copy(chapters = chapters, durationMs = chapters.sumOf { it.durationMs })
    }
}
