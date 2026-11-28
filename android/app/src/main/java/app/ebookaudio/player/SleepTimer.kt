package app.ebookaudio.player

/**
 * The sleep timer's state (A-016), kept free of Android types so it can be unit-tested. The service advances it with
 * the real time that passed while playing (a pause, e.g. for a call, doesn't use the timer up) and applies
 * [volume] and [expired].
 */
class SleepTimer {
    sealed interface Mode {
        data object Off : Mode
        /** Stop after this much more listening time. */
        data class Minutes(val remainingMs: Long) : Mode
        /** Stop when the current chapter ends (ExoPlayer pauses at the end of the item). */
        data object EndOfChapter : Mode
    }

    var mode: Mode = Mode.Off
        private set

    fun set(minutes: Int) {
        require(minutes in 1..MAX_MINUTES) { "minutes must be 1..$MAX_MINUTES" }
        mode = Mode.Minutes(minutes * 60_000L)
    }

    fun endOfChapter() { mode = Mode.EndOfChapter }

    fun off() { mode = Mode.Off }

    /** Counts down by [playedMs] of real time spent playing. */
    fun advance(playedMs: Long) {
        val m = mode
        if (m is Mode.Minutes) mode = Mode.Minutes((m.remainingMs - playedMs.coerceAtLeast(0)).coerceAtLeast(0))
    }

    /** True when a minutes timer has run out: the service pauses and turns the timer off. */
    val expired: Boolean get() = (mode as? Mode.Minutes)?.remainingMs == 0L

    /**
     * Real time left before the stop, or null when off. For "end of chapter" it is the chapter's remaining audio at
     * the current speed.
     */
    fun remainingMs(chapterLeftMs: Long, speed: Float): Long? = when (val m = mode) {
        Mode.Off -> null
        is Mode.Minutes -> m.remainingMs
        Mode.EndOfChapter -> (chapterLeftMs.coerceAtLeast(0) / speed.coerceAtLeast(0.1f)).toLong()
    }

    /** Player volume: 1, fading to 0 over the last [FADE_MS] before the stop. */
    fun volume(chapterLeftMs: Long, speed: Float): Float {
        val left = remainingMs(chapterLeftMs, speed) ?: return 1f
        return if (left >= FADE_MS) 1f else (left.toFloat() / FADE_MS).coerceIn(0f, 1f)
    }

    companion object {
        const val FADE_MS = 10_000L
        const val MAX_MINUTES = 24 * 60
        val PRESETS = listOf(15, 30, 45, 60)
    }
}
