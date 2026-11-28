package app.ebookaudio.player

import android.content.ComponentName
import android.content.Context
import android.net.Uri
import androidx.core.content.ContextCompat
import androidx.core.net.toUri
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.session.MediaController
import androidx.media3.session.SessionToken
import app.ebookaudio.api.ApiClient
import app.ebookaudio.api.Book
import app.ebookaudio.library.LocalLibrary
import com.google.common.util.concurrent.ListenableFuture
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/** The screens' handle on [PlaybackService]: connected while the activity is started. */
class PlayerConnection(private val context: Context) {
    private var future: ListenableFuture<MediaController>? = null
    private val _controller = MutableStateFlow<MediaController?>(null)
    val controller: StateFlow<MediaController?> = _controller

    fun connect() {
        if (future != null) return
        val token = SessionToken(context, ComponentName(context, PlaybackService::class.java))
        val f = MediaController.Builder(context, token).buildAsync()
        future = f
        f.addListener({ _controller.value = runCatching { f.get() }.getOrNull() }, ContextCompat.getMainExecutor(context))
    }

    fun disconnect() {
        future?.let { MediaController.releaseFuture(it) }
        future = null
        _controller.value = null
    }
}

/** What to play for a book: each chapter from the phone if downloaded, else streamed from the PC (if paired). */
object Playlist {
    fun items(book: Book, local: Book?, library: LocalLibrary, api: ApiClient?): List<MediaItem> {
        val have = local?.chapters?.associateBy { it.number } ?: emptyMap()
        val cover = local?.let { library.cover(it) }?.let { Uri.fromFile(it) }
            ?: book.cover?.let { name -> api?.let { it.fileUrl(book.id, name).toUri() } }
        val chapters = (book.chapters.map { it.number } + have.keys).distinct().sorted()
        return chapters.mapNotNull { number ->
            val downloaded = have[number]
            val chapter = downloaded ?: book.chapters.first { it.number == number }
            val uri = when {
                downloaded != null -> Uri.fromFile(library.audio(book.id, downloaded))
                api != null -> api.fileUrl(book.id, chapter.audio).toUri()
                else -> return@mapNotNull null
            }
            MediaItem.Builder()
                .setMediaId(MediaIds.of(book.id, number))
                .setUri(uri)
                .setMediaMetadata(
                    MediaMetadata.Builder()
                        .setTitle(chapter.title)
                        .setAlbumTitle(book.title)
                        .setArtist(book.author)
                        .setTrackNumber(number)
                        .setArtworkUri(cover)
                        .setMediaType(MediaMetadata.MEDIA_TYPE_AUDIO_BOOK_CHAPTER)
                        .build(),
                )
                .build()
        }
    }

    /** Starts [book] at chapter number [chapter] (the first playable one if missing) and [ms]. */
    fun play(controller: MediaController, items: List<MediaItem>, chapter: Int?, ms: Long, speed: Float) {
        if (items.isEmpty()) return
        val found = items.indexOfFirst { MediaIds.parse(it.mediaId)?.second == chapter }
        // a chapter that can't be played (not downloaded, PC out of reach) starts the book from its first chapter
        controller.setMediaItems(items, found.coerceAtLeast(0), if (found >= 0) ms else 0)
        controller.setPlaybackSpeed(speed)
        controller.prepare()
        controller.play()
    }
}
