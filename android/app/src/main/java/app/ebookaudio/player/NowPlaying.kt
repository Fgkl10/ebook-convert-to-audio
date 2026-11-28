package app.ebookaudio.player

import android.net.Uri
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.State
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.media3.common.Player
import androidx.media3.session.MediaController
import kotlinx.coroutines.delay

/** A snapshot of the player for the screens. */
data class NowPlaying(
    val bookId: String,
    val chapter: Int,
    val title: String,
    val bookTitle: String,
    val artwork: Uri?,
    val isPlaying: Boolean,
    val buffering: Boolean,
    val positionMs: Long,
    val durationMs: Long,
    val speed: Float,
    val hasPrevious: Boolean,
    val hasNext: Boolean,
    /** Sleep timer: "off", "minutes" or "chapter", and the real time left (A-016). */
    val sleepMode: String = "off",
    val sleepLeftMs: Long? = null,
)

fun snapshot(c: MediaController?): NowPlaying? {
    val item = c?.currentMediaItem ?: return null
    val (bookId, chapter) = MediaIds.parse(item.mediaId) ?: return null
    val meta = item.mediaMetadata
    return NowPlaying(
        bookId = bookId,
        chapter = chapter,
        title = meta.title?.toString() ?: "",
        bookTitle = meta.albumTitle?.toString() ?: "",
        artwork = meta.artworkUri,
        isPlaying = c.isPlaying,
        buffering = c.playbackState == Player.STATE_BUFFERING,
        positionMs = c.currentPosition.coerceAtLeast(0),
        durationMs = c.duration.takeIf { it > 0 } ?: 0,
        speed = c.playbackParameters.speed,
        hasPrevious = c.hasPreviousMediaItem(),
        hasNext = c.hasNextMediaItem(),
        sleepMode = c.sessionExtras.getString(PlaybackService.SLEEP_MODE) ?: "off",
        sleepLeftMs = c.sessionExtras.getLong(PlaybackService.SLEEP_LEFT_MS, -1).takeIf { it >= 0 },
    )
}

/** The player's state, refreshed every [intervalMs] while the screen shows it. */
@Composable
fun rememberNowPlaying(controller: MediaController?, intervalMs: Long = 250): State<NowPlaying?> {
    val state = remember { mutableStateOf(snapshot(controller)) }
    LaunchedEffect(controller, intervalMs) {
        while (true) {
            state.value = snapshot(controller)
            delay(intervalMs)
        }
    }
    return state
}
