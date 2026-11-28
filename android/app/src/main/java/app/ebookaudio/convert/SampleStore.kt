package app.ebookaudio.convert

import java.io.File

/**
 * Voice samples the phone has played, kept so they replay at once and without the PC (A-023). One file per voice id;
 * Settings shows their size and deletes them.
 */
class SampleStore(private val dir: File) {
    private val safe = Regex("^[A-Za-z0-9_.-]{1,80}$")

    /** Where [voice]'s sample is kept, or null for an id that can't be a file name. */
    fun file(voice: String): File? = if (safe.matches(voice) && !voice.startsWith(".")) File(dir, "$voice.m4a") else null

    /** The kept sample, or null. */
    fun get(voice: String): File? = file(voice)?.takeIf { it.isFile && it.length() > 0 }

    /** Keep [audio] for [voice]: written to a temp file and renamed, so a half-written sample is never played. */
    fun put(voice: String, audio: ByteArray): File? {
        val target = file(voice) ?: return null
        dir.mkdirs()
        val tmp = File(dir, "$voice.m4a.tmp")
        tmp.writeBytes(audio)
        if (!tmp.renameTo(target)) {
            target.delete()
            if (!tmp.renameTo(target)) return null.also { tmp.delete() }
        }
        return target
    }

    fun sizeBytes(): Long = dir.listFiles()?.sumOf { it.length() } ?: 0L

    fun count(): Int = dir.listFiles { f -> f.name.endsWith(".m4a") }?.size ?: 0

    fun clear() {
        dir.listFiles()?.forEach { it.delete() }
    }
}
