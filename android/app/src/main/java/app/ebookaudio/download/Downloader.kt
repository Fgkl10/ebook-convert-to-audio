package app.ebookaudio.download

import app.ebookaudio.api.ApiClient
import app.ebookaudio.api.Book
import app.ebookaudio.library.LocalLibrary
import app.ebookaudio.library.Versions
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.util.concurrent.CancellationException

/**
 * Copies a book from the PC to the phone (A-006). Each chapter goes to `<audio>.part`; a retry continues it with
 * `Range: bytes=<have>-` (the PC answers 206), then the file is renamed into place and the local book.json is
 * rewritten, so every finished chapter is playable at once. A changed chapter (D-038) replaces the old copy only
 * when its new file is complete.
 */
class Downloader(private val api: ApiClient, private val library: LocalLibrary) {
    fun interface Progress {
        fun update(doneBytes: Long, totalBytes: Long, chapter: String)
    }

    /** Downloads the missing or changed chapters ([wanted] numbers, or all). Returns the local book. */
    fun download(
        bookId: String,
        wanted: Set<Int>? = null,
        progress: Progress = Progress { _, _, _ -> },
        isStopped: () -> Boolean = { false },
    ): Book {
        val server = api.bookBlocking(bookId)
        var local = library.book(bookId)
        val todo = Versions.toDownload(local, server, wanted)
        val total = todo.sumOf { it.sizeBytes }
        var done = 0L
        library.dir(bookId).mkdirs()
        server.cover?.let { name ->
            val cover = library.file(bookId, name)
            if (!cover.exists()) fetch(api.fileRequestUrl(bookId, name), cover)
        }
        for (chapter in todo) {
            if (isStopped()) throw CancellationException("Download stopped")
            progress.update(done, total, chapter.title)
            fetch(api.fileRequestUrl(bookId, chapter.audio), library.audio(bookId, chapter)) { n ->
                progress.update(done + n, total, chapter.title)
            }
            done += chapter.sizeBytes
            local = Versions.merge(local, server, chapter)
            library.save(local)
        }
        progress.update(total, total, "")
        return Versions.merge(local, server).also { library.save(it) }
    }

    /** One file, resumable. [onBytes] gets the bytes of this file written so far. */
    fun fetch(url: String, dest: File, onBytes: (Long) -> Unit = {}) {
        val part = File(dest.path + ".part")
        val have = if (part.exists()) part.length() else 0L
        val request = Request.Builder().url(url).apply { if (have > 0) header("Range", "bytes=$have-") }.build()
        api.client.newCall(request).execute().use { r ->
            ApiClient.check(r)
            if (r.code == 416) { // the part file is already whole
                LocalLibrary.moveInto(part, dest)
                return
            }
            val append = r.code == 206
            // the whole file's size: from "Content-Range: bytes a-b/size" on a resume, else the body's length
            val expected = r.headers["Content-Range"]?.substringAfterLast('/')?.toLongOrNull()
                ?: if (append) null else r.body.contentLength().takeIf { it >= 0 }
            var written = if (append) have else 0L
            FileOutputStream(part, append).use { out ->
                r.body.byteStream().use { input ->
                    val buffer = ByteArray(64 * 1024)
                    var lastReport = 0L
                    while (true) {
                        val n = input.read(buffer)
                        if (n < 0) break
                        out.write(buffer, 0, n)
                        written += n
                        if (written - lastReport >= 256 * 1024) {
                            onBytes(written)
                            lastReport = written
                        }
                    }
                }
            }
            if (expected != null && written != expected) throw IOException("Download cut off at $written of $expected bytes")
            onBytes(written)
        }
        LocalLibrary.moveInto(part, dest)
    }
}
