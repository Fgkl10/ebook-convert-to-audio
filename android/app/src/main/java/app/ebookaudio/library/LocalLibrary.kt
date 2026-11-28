package app.ebookaudio.library

import app.ebookaudio.api.Book
import app.ebookaudio.api.BookChapter
import app.ebookaudio.api.JSON
import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption

/**
 * Books on the phone, in app-private storage (A-004):
 * `<root>/<book_id>/book.json` (the PC's manifest, listing only the chapters downloaded so far), `chNNN.m4a`,
 * and the cover. Each file is written to a temporary name and renamed, so a cut-off download never leaves a half
 * file under a real name.
 */
class LocalLibrary(val root: File) {
    companion object {
        private val ID = Regex("[a-z0-9-]{1,80}") // the PC's own book id rule (D-032)
        private val NAME = Regex("[A-Za-z0-9._-]{1,120}")

        fun checkName(name: String): String {
            require(NAME.matches(name) && !name.startsWith(".")) { "Bad file name: $name" }
            return name
        }

        fun moveInto(from: File, to: File) {
            Files.move(from.toPath(), to.toPath(), StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE)
        }
    }

    fun dir(id: String): File {
        require(ID.matches(id)) { "Bad book id: $id" }
        return File(root, id)
    }

    fun file(id: String, name: String): File = File(dir(id), checkName(name))

    /** The local manifest, with only the chapters whose audio file is really there. */
    fun book(id: String): Book? {
        val f = File(dir(id), "book.json")
        if (!f.exists()) return null
        val book = runCatching { JSON.decodeFromString<Book>(f.readText()) }.getOrNull() ?: return null
        return book.copy(chapters = book.chapters.filter { file(id, it.audio).exists() })
    }

    fun books(): List<Book> =
        (root.listFiles() ?: emptyArray()).filter { it.isDirectory && ID.matches(it.name) }
            .mapNotNull { book(it.name) }
            .filter { it.chapters.isNotEmpty() }
            .sortedBy { it.title.lowercase() }

    fun save(book: Book) {
        val d = dir(book.id).apply { mkdirs() }
        val tmp = File(d, "book.json.tmp")
        tmp.writeText(JSON.encodeToString(Book.serializer(), book))
        moveInto(tmp, File(d, "book.json"))
    }

    fun audio(id: String, chapter: BookChapter): File = file(id, chapter.audio)

    fun cover(book: Book): File? = book.cover?.let { file(book.id, it) }?.takeIf { it.exists() }

    fun delete(id: String) {
        dir(id).deleteRecursively()
    }

    fun deleteAll() {
        root.listFiles()?.forEach { it.deleteRecursively() }
    }

    fun sizeBytes(id: String? = null): Long =
        (if (id == null) root else dir(id)).walkTopDown().filter { it.isFile }.sumOf { it.length() }
}
