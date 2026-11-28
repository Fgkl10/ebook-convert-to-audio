package app.ebookaudio.player

import app.ebookaudio.api.Sentence

/**
 * Which sentence is being read, and where the sentence buttons go (A-015). The same rules as the PC's web reader
 * (desktop/web/app.js: sentenceAt, prevSentence, nextSentence). Times are positions in the chapter's audio, so they
 * don't change with the playback speed.
 */
object SentenceSync {
    /** "Previous" restarts the current sentence when this far into it, else it goes to the sentence before. */
    const val RESTART_MS = 1_500L

    /** Index of the last sentence that starts at or before [positionMs] (0 before the first one; -1 if none). */
    fun at(sentences: List<Sentence>, positionMs: Long): Int {
        if (sentences.isEmpty()) return -1
        var lo = 0
        var hi = sentences.size - 1
        var ans = 0
        while (lo <= hi) {
            val mid = (lo + hi) ushr 1
            if (sentences[mid].startMs <= positionMs) { ans = mid; lo = mid + 1 } else hi = mid - 1
        }
        return ans
    }

    /** Where "previous sentence" seeks: the current sentence's start, or the previous one's when just past it. */
    fun previousStart(sentences: List<Sentence>, positionMs: Long): Long? {
        val i = at(sentences, positionMs)
        if (i < 0) return null
        val start = sentences[i].startMs
        return if (positionMs - start > RESTART_MS || i == 0) start else sentences[i - 1].startMs
    }

    /** Where "next sentence" seeks, or null on the last sentence (then the chapter just plays on). */
    fun nextStart(sentences: List<Sentence>, positionMs: Long): Long? {
        val i = at(sentences, positionMs)
        if (i < 0) return null
        return sentences.getOrNull(i + 1)?.startMs
    }

    /** Sentences grouped into paragraphs, in order (a sentence's `p` is its paragraph number in the chapter). */
    fun paragraphs(sentences: List<Sentence>): List<List<Sentence>> {
        val out = mutableListOf<MutableList<Sentence>>()
        var last: Int? = null
        for (s in sentences) {
            if (s.p != last) { out += mutableListOf<Sentence>(); last = s.p }
            out.last() += s
        }
        return out
    }
}
