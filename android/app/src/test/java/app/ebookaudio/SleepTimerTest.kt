package app.ebookaudio

import app.ebookaudio.player.SleepTimer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** AND-10: the sleep timer counts listening time, fades the last 10 s, and stops. */
class SleepTimerTest {
    @Test
    fun minutesCountDownAndExpire() {
        val t = SleepTimer()
        assertNull(t.remainingMs(0, 1f))
        t.set(15)
        assertEquals(15 * 60_000L, t.remainingMs(0, 1f))
        t.advance(14 * 60_000L)
        assertEquals(60_000L, t.remainingMs(0, 1f))
        assertFalse(t.expired)
        t.advance(90_000) // never below zero
        assertEquals(0L, t.remainingMs(0, 1f))
        assertTrue(t.expired)
        t.off()
        assertEquals(SleepTimer.Mode.Off, t.mode)
        assertFalse(t.expired)
    }

    @Test
    fun fadeOutOverTheLastTenSeconds() {
        val t = SleepTimer()
        assertEquals(1f, t.volume(0, 1f), 0f) // off: full volume
        t.set(1)
        assertEquals(1f, t.volume(0, 1f), 0f)
        t.advance(55_000)                     // 5 s left
        assertEquals(0.5f, t.volume(0, 1f), 0.001f)
        t.advance(5_000)
        assertEquals(0f, t.volume(0, 1f), 0f)
    }

    @Test
    fun endOfChapterUsesTheChaptersRemainingTimeAtTheSpeed() {
        val t = SleepTimer()
        t.endOfChapter()
        t.advance(3_600_000) // time doesn't matter for this mode
        assertFalse(t.expired)
        assertEquals(60_000L, t.remainingMs(60_000, 1f))
        assertEquals(30_000L, t.remainingMs(60_000, 2f))   // at 2× a minute of audio takes 30 s
        assertEquals(0.5f, t.volume(10_000, 2f), 0.001f)   // 10 s of audio at 2× = 5 s left
    }

    @Test
    fun minutesAreChecked() {
        val t = SleepTimer()
        listOf(0, -5, SleepTimer.MAX_MINUTES + 1).forEach {
            assertTrue(runCatching { t.set(it) }.isFailure)
        }
        t.set(SleepTimer.MAX_MINUTES)
    }
}
