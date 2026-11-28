package app.ebookaudio.convert

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.session.MediaController
import app.ebookaudio.R
import app.ebookaudio.api.ApiClient

/**
 * A short-lived player for voice samples: separate from the book's PlaybackService, so a sample never replaces the
 * book's queue. Starting a sample pauses the book.
 */
class SamplePlayer(private val player: ExoPlayer) {
    var playing by mutableStateOf<String?>(null)
        private set

    init {
        player.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_ENDED || state == Player.STATE_IDLE) playing = null
            }
        })
    }

    fun toggle(api: ApiClient, voice: String, book: MediaController?) {
        if (playing == voice) {
            player.stop()
            playing = null
            return
        }
        book?.pause()
        player.setMediaItem(MediaItem.fromUri(api.voiceSampleUrl(voice)))
        player.prepare()
        player.play()
        playing = voice
    }

    fun release() = player.release()
}

@Composable
fun rememberSamplePlayer(): SamplePlayer {
    val context = LocalContext.current
    val sample = remember { SamplePlayer(ExoPlayer.Builder(context).build()) }
    DisposableEffect(sample) { onDispose { sample.release() } }
    return sample
}

/** Voice dropdown with a ▶ sample button, and a speed slider (0.5–2.0×, like the PC's page). */
@Composable
fun VoiceAndSpeed(
    voices: List<String>,
    voice: String,
    speed: Double,
    onVoice: (String) -> Unit,
    onSpeed: (Double) -> Unit,
    api: ApiClient?,
    sample: SamplePlayer,
    book: MediaController?,
) {
    var open by remember { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.weight(1f)) {
                OutlinedTextField(
                    value = voice, onValueChange = {}, readOnly = true, label = { Text(stringResource(R.string.voice)) },
                    trailingIcon = { Icon(Icons.Filled.ArrowDropDown, null) },
                    modifier = Modifier.fillMaxWidth(),
                )
                // a transparent layer over the field opens the menu (a read-only field eats the taps)
                Box(Modifier.matchParentSize().clickable { open = true })
                DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                    voices.forEach { v ->
                        DropdownMenuItem(text = { Text(v) }, onClick = { onVoice(v); open = false })
                    }
                }
            }
            IconButton(onClick = { api?.let { sample.toggle(it, voice, book) } }, enabled = api != null) {
                if (sample.playing == voice) Icon(Icons.Filled.Stop, stringResource(R.string.stop_sample))
                else Icon(Icons.Filled.PlayArrow, stringResource(R.string.hear_sample, voice))
            }
        }
        Text(stringResource(R.string.speed_value, "%.2f".format(speed).trimEnd('0').trimEnd('.') + "×"))
        Slider(
            value = speed.toFloat(),
            onValueChange = { onSpeed(Math.round(it * 20) / 20.0) },
            valueRange = 0.5f..2f,
            steps = 29,
        )
    }
}
