package app.ebookaudio.player

import android.app.PendingIntent
import android.content.Intent
import android.os.Bundle
import android.os.SystemClock
import androidx.annotation.OptIn
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.session.MediaController
import androidx.media3.session.MediaSession
import androidx.media3.session.MediaSessionService
import androidx.media3.session.SessionCommand
import androidx.media3.session.SessionError
import androidx.media3.session.SessionResult
import com.google.common.util.concurrent.Futures
import com.google.common.util.concurrent.ListenableFuture
import app.ebookaudio.graph
import app.ebookaudio.settings.Position
import app.ebookaudio.ui.MainActivity
import kotlinx.coroutines.Job
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Plays the book in the background (A-007). Media3's MediaSessionService gives the media notification, the lock
 * screen controls, headset buttons and Bluetooth controls; the screens talk to it through a MediaController.
 * Each item is one chapter, with media id "<book_id>|<chapter number>". The position is saved every 5 s while
 * playing and whenever playback pauses or moves to another chapter.
 */
class PlaybackService : MediaSessionService() {
    private var session: MediaSession? = null
    private val scope = MainScope()
    private var ticker: Job? = null

    override fun onCreate() {
        super.onCreate()
        val player = ExoPlayer.Builder(this)
            .setAudioAttributes(
                AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_SPEECH).build(),
                true, // handle audio focus: pause for a call or another app's audio
            )
            .setHandleAudioBecomingNoisy(true) // headphones unplugged: pause
            .setWakeMode(C.WAKE_MODE_NETWORK) // keep CPU and Wi-Fi awake while streaming with the screen off
            .setSeekBackIncrementMs(SEEK_BACK_MS)
            .setSeekForwardIncrementMs(SEEK_FORWARD_MS)
            .build()
        player.addListener(object : Player.Listener {
            override fun onIsPlayingChanged(isPlaying: Boolean) {
                savePosition()
                ticker?.cancel()
                if (isPlaying) ticker = scope.launch {
                    while (isActive) {
                        delay(5_000)
                        savePosition()
                    }
                }
            }

            override fun onMediaItemTransition(mediaItem: MediaItem?, reason: Int) = savePosition()

            override fun onPlayWhenReadyChanged(playWhenReady: Boolean, reason: Int) {
                // "end of chapter" sleep timer: ExoPlayer paused at the end of the item
                if (!playWhenReady && reason == Player.PLAY_WHEN_READY_CHANGE_REASON_END_OF_MEDIA_ITEM) stopSleep()
            }

            override fun onPlaybackStateChanged(state: Int) {
                // the book's last chapter ended: playback is over, so is the timer
                if (state == Player.STATE_ENDED && sleep.mode != SleepTimer.Mode.Off) stopSleep()
            }
        })
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        session = MediaSession.Builder(this, player).setSessionActivity(open).setCallback(SleepCommands()).build()
        sleepTicker = scope.launch { // the sleep timer counts real time spent playing, 4 times a second
            var last = SystemClock.elapsedRealtime()
            while (isActive) {
                delay(250)
                val now = SystemClock.elapsedRealtime()
                if (player.isPlaying) sleep.advance(now - last)
                last = now
                applySleep(player)
            }
        }
    }

    private val sleep = SleepTimer()
    private var sleepTicker: Job? = null
    private var shownRemaining: Long? = -1

    /** The timer's effect on the player: fade, pause when it runs out, and the time left for the screens. */
    private fun applySleep(player: Player) {
        if (sleep.mode == SleepTimer.Mode.Off) return
        val left = (player.duration - player.currentPosition).takeIf { player.duration > 0 } ?: Long.MAX_VALUE
        val speed = player.playbackParameters.speed
        player.volume = sleep.volume(left, speed)
        if (sleep.expired) {
            player.pause()
            stopSleep()
            return
        }
        publishSleep(sleep.remainingMs(left, speed))
    }

    // pauseAtEndOfMediaItems and the default session/player commands are Media3 "unstable" API (A-016)
    @OptIn(UnstableApi::class)
    private fun startSleep(minutes: Int?) {
        val player = session?.player as? ExoPlayer ?: return
        if (minutes == null) sleep.endOfChapter() else sleep.set(minutes)
        player.pauseAtEndOfMediaItems = minutes == null
        player.volume = 1f
        applySleep(player)
    }

    @OptIn(UnstableApi::class)
    private fun stopSleep() {
        sleep.off()
        (session?.player as? ExoPlayer)?.let {
            it.pauseAtEndOfMediaItems = false
            it.volume = 1f
        }
        publishSleep(null)
    }

    /** Session extras the screens read: the mode and the time left (rounded to seconds to limit updates). */
    private fun publishSleep(remainingMs: Long?) {
        val rounded = remainingMs?.let { (it + 999) / 1000 * 1000 }
        if (rounded == shownRemaining) return
        shownRemaining = rounded
        session?.setSessionExtras(Bundle().apply {
            putString(SLEEP_MODE, when (sleep.mode) {
                SleepTimer.Mode.Off -> "off"
                is SleepTimer.Mode.Minutes -> "minutes"
                SleepTimer.Mode.EndOfChapter -> "chapter"
            })
            if (rounded != null) putLong(SLEEP_LEFT_MS, rounded)
        })
    }

    /** Lets the app's own controller send the sleep timer command; other controllers get the default commands. */
    private inner class SleepCommands : MediaSession.Callback {
        @OptIn(UnstableApi::class)
        override fun onConnect(session: MediaSession, controller: MediaSession.ControllerInfo): MediaSession.ConnectionResult =
            MediaSession.ConnectionResult.accept(
                MediaSession.ConnectionResult.DEFAULT_SESSION_COMMANDS.buildUpon().add(SLEEP_COMMAND).build(),
                MediaSession.ConnectionResult.DEFAULT_PLAYER_COMMANDS,
            )

        override fun onCustomCommand(
            session: MediaSession, controller: MediaSession.ControllerInfo, customCommand: SessionCommand, args: Bundle,
        ): ListenableFuture<SessionResult> {
            if (customCommand.customAction != SLEEP_ACTION) {
                return Futures.immediateFuture(SessionResult(SessionError.ERROR_NOT_SUPPORTED))
            }
            when (args.getString(SLEEP_MODE)) {
                "minutes" -> args.getInt(SLEEP_MINUTES).takeIf { it in 1..SleepTimer.MAX_MINUTES }?.let { startSleep(it) }
                "chapter" -> startSleep(null)
                else -> stopSleep()
            }
            return Futures.immediateFuture(SessionResult(SessionResult.RESULT_SUCCESS))
        }
    }

    private fun savePosition() {
        val player = session?.player ?: return
        val (bookId, chapter) = MediaIds.parse(player.currentMediaItem?.mediaId) ?: return
        val position = Position(chapter, player.currentPosition.coerceAtLeast(0))
        val settings = graph.settings
        graph.scope.launch { settings.savePosition(bookId, position) }
    }

    override fun onGetSession(controllerInfo: MediaSession.ControllerInfo): MediaSession? = session

    override fun onTaskRemoved(rootIntent: Intent?) {
        // Swiping the app away while paused stops the service; while playing it keeps going (a music-player habit).
        val player = session?.player
        if (player == null || !player.playWhenReady || player.mediaItemCount == 0) {
            savePosition()
            stopSelf()
        }
    }

    override fun onDestroy() {
        savePosition()
        ticker?.cancel()
        sleepTicker?.cancel()
        scope.cancel()
        session?.run {
            player.release()
            release()
        }
        session = null
        super.onDestroy()
    }

    companion object {
        const val SEEK_BACK_MS = 10_000L
        const val SEEK_FORWARD_MS = 30_000L

        const val SLEEP_ACTION = "app.ebookaudio.SLEEP"
        val SLEEP_COMMAND = SessionCommand(SLEEP_ACTION, Bundle.EMPTY)
        /** Command argument and session extra: "off", "minutes" or "chapter". */
        const val SLEEP_MODE = "sleep_mode"
        const val SLEEP_MINUTES = "sleep_minutes"
        /** Session extra: real time left before the stop, in ms (whole seconds). */
        const val SLEEP_LEFT_MS = "sleep_left_ms"

        /** Sets the sleep timer: [minutes], or the end of the chapter when null; [off] stops it. */
        fun setSleep(controller: MediaController, minutes: Int?, off: Boolean = false) {
            val args = Bundle().apply {
                putString(SLEEP_MODE, when { off -> "off"; minutes == null -> "chapter"; else -> "minutes" })
                if (minutes != null) putInt(SLEEP_MINUTES, minutes)
            }
            controller.sendCustomCommand(SLEEP_COMMAND, args)
        }
    }
}

/** Media ids of chapters: "<book_id>|<chapter number>". */
object MediaIds {
    fun of(bookId: String, chapter: Int) = "$bookId|$chapter"

    fun parse(id: String?): Pair<String, Int>? {
        val parts = id?.split("|") ?: return null
        if (parts.size != 2 || parts[0].isEmpty()) return null
        return parts[1].toIntOrNull()?.let { parts[0] to it }
    }
}
