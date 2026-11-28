package app.ebookaudio.player

import android.app.PendingIntent
import android.content.Intent
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.session.MediaSession
import androidx.media3.session.MediaSessionService
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
        })
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        session = MediaSession.Builder(this, player).setSessionActivity(open).build()
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
