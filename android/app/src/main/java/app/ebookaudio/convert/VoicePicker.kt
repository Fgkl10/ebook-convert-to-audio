package app.ebookaudio.convert

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.ui.platform.LocalResources
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.session.MediaController
import app.ebookaudio.R
import app.ebookaudio.api.ApiClient
import app.ebookaudio.api.VoiceLanguage
import app.ebookaudio.ui.DropdownField

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

/** The words of ConvertRules.voiceLabel, by key. */
private val VOICE_WORDS = mapOf(
    "label" to R.string.voice_label, "label_plain" to R.string.voice_label_plain, "join" to R.string.voice_join,
    "us_female" to R.string.voice_us_female, "us_male" to R.string.voice_us_male,
    "gb_female" to R.string.voice_gb_female, "gb_male" to R.string.voice_gb_male,
    "female" to R.string.voice_female, "male" to R.string.voice_male,
    "numbered_female" to R.string.voice_numbered_female, "numbered_male" to R.string.voice_numbered_male,
    "low" to R.string.trait_low, "high" to R.string.trait_high, "slow" to R.string.trait_slow,
    "fast" to R.string.trait_fast,
)

@Composable
private fun languageName(code: String) = when (code) {
    "en" -> stringResource(R.string.voice_lang_en)
    "zh" -> stringResource(R.string.voice_lang_zh)
    else -> code
}

/**
 * Language and Voice dropdowns (the Voice list follows the Language, desktop D-043) with a ▶ sample button, and a
 * speed slider (0.5–2.0×, like the PC's page).
 */
@Composable
fun VoiceAndSpeed(
    languages: List<VoiceLanguage>,
    voice: String,
    speed: Double,
    onVoice: (String) -> Unit,
    onSpeed: (Double) -> Unit,
    api: ApiClient?,
    sample: SamplePlayer,
    book: MediaController?,
) {
    val lang = ConvertRules.languageOf(languages, voice) ?: languages.firstOrNull()?.code.orEmpty()
    val current = languages.firstOrNull { it.code == lang }
    val voices = current?.voices.orEmpty()
    val res = LocalResources.current
    val labels = remember(current, res) {
        val word = { key: String -> res.getString(VOICE_WORDS.getValue(key)) }
        val byId = current?.details.orEmpty().associateBy { it.id }
        voices.associateWith { id -> byId[id]?.let { ConvertRules.voiceLabel(it, word) } ?: id }
    }
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        if (languages.size > 1) {
            DropdownField(stringResource(R.string.voice_language), languageName(lang),
                languages.map { it.code to languageName(it.code) },
                { code -> onVoice(ConvertRules.voiceFor(languages, voice, code)) }, Modifier.fillMaxWidth())
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            DropdownField(stringResource(R.string.voice), labels[voice] ?: voice, voices.map { it to labels.getValue(it) },
                onVoice, Modifier.weight(1f))
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
