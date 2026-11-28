package app.ebookaudio.player

import android.view.WindowManager
import androidx.activity.compose.LocalActivity
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Subject
import androidx.compose.material.icons.filled.Bedtime
import androidx.compose.material.icons.filled.Forward30
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Replay10
import androidx.compose.material.icons.filled.SkipNext
import androidx.compose.material.icons.filled.SkipPrevious
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.media3.session.MediaController
import app.ebookaudio.R
import app.ebookaudio.graph
import app.ebookaudio.settings.Settings
import app.ebookaudio.ui.Format
import coil3.compose.AsyncImage
import kotlinx.coroutines.launch

val SPEEDS = listOf(0.75f, 1f, 1.25f, 1.5f, 1.75f, 2f)

fun speedText(speed: Float): String =
    (if (speed == speed.toInt().toFloat()) speed.toInt().toString() else speed.toString()) + "×"

/** "Sleep in 23:41", "Sleep at end of chapter", or null when the timer is off. */
@Composable
fun sleepText(np: NowPlaying): String? = when (np.sleepMode) {
    "minutes" -> np.sleepLeftMs?.let { stringResource(R.string.sleep_in, Format.clock(it)) }
    "chapter" -> np.sleepLeftMs?.let { stringResource(R.string.sleep_at_chapter_end_left, Format.clock(it)) }
        ?: stringResource(R.string.sleep_at_chapter_end)
    else -> null
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PlayerScreen(controller: MediaController?, onBack: () -> Unit) {
    val now by rememberNowPlaying(controller, intervalMs = 100) // the highlight follows within 0.1 s
    val settings = LocalContext.current.graph.settings
    val scope = rememberCoroutineScope()
    val showText by settings.showTextFlow.collectAsState(true)
    val textSize by settings.textSizeFlow.collectAsState(Settings.TEXT_SIZE_DEFAULT)
    var dragging by remember { mutableStateOf<Float?>(null) }
    var speedMenu by remember { mutableStateOf(false) }
    var sleepMenu by remember { mutableStateOf(false) }
    var moreMenu by remember { mutableStateOf(false) }
    var customSleep by remember { mutableStateOf(false) }
    val np = now
    val sentences = np?.let { rememberChapterSentences(it.bookId, it.chapter) }

    // keep the screen on while the text is shown and playing (A-015)
    val window = LocalActivity.current?.window
    val keepOn = showText && !sentences.isNullOrEmpty() && np?.isPlaying == true
    DisposableEffect(keepOn, window) {
        if (keepOn) window?.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        else window?.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        onDispose { window?.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
    }

    Scaffold(
        contentWindowInsets = WindowInsets(0),
        topBar = {
            TopAppBar(
                title = {
                    Text(np?.bookTitle ?: stringResource(R.string.player), maxLines = 1, overflow = TextOverflow.Ellipsis)
                },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back)) }
                },
                actions = {
                    if (np != null && controller != null) {
                        IconButton(onClick = { scope.launch { settings.setShowText(!showText) } }) {
                            if (showText) Icon(Icons.Filled.Image, stringResource(R.string.show_cover))
                            else Icon(Icons.AutoMirrored.Filled.Subject, stringResource(R.string.show_text))
                        }
                        Box {
                            IconButton(onClick = { moreMenu = true }) {
                                Icon(Icons.Filled.MoreVert, stringResource(R.string.more))
                            }
                            DropdownMenu(expanded = moreMenu, onDismissRequest = { moreMenu = false }) {
                                DropdownMenuItem(text = { Text(stringResource(R.string.larger_text)) },
                                    enabled = textSize < Settings.TEXT_SIZE_MAX,
                                    onClick = { scope.launch { settings.setTextSize(textSize + Settings.TEXT_SIZE_STEP) } })
                                DropdownMenuItem(text = { Text(stringResource(R.string.smaller_text)) },
                                    enabled = textSize > Settings.TEXT_SIZE_MIN,
                                    onClick = { scope.launch { settings.setTextSize(textSize - Settings.TEXT_SIZE_STEP) } })
                            }
                        }
                    }
                },
            )
        },
    ) { padding ->
        if (np == null || controller == null) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Text(stringResource(R.string.nothing_playing))
            }
            return@Scaffold
        }
        Column(Modifier.fillMaxSize().padding(padding)) {
            val list = sentences.orEmpty()
            if (showText && list.isNotEmpty()) {
                ReadAlong(list, dragging?.toLong() ?: np.positionMs, textSize, onSeek = { controller.seekTo(it); controller.play() },
                    modifier = Modifier.weight(1f).fillMaxWidth())
            } else {
                Box(Modifier.weight(1f).fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) {
                    if (showText && sentences == null) Text(stringResource(R.string.loading_text))
                    else AsyncImage(
                        model = np.artwork,
                        contentDescription = null,
                        contentScale = ContentScale.Crop,
                        modifier = Modifier.widthIn(max = 280.dp).fillMaxWidth().aspectRatio(2f / 3f)
                            .clip(RoundedCornerShape(12.dp)),
                    )
                }
            }
            Controls(np, controller, list, dragging, { dragging = it }, speedMenu, { speedMenu = it },
                onSpeed = { s -> scope.launch { settings.setSpeed(s) } }) {
                // the sleep timer, in the bottom row: "Sleep", or the time left while set
                Box {
                    TextButton(onClick = { sleepMenu = true }) {
                        Icon(Icons.Filled.Bedtime, null, Modifier.size(18.dp).padding(end = 4.dp))
                        Text(when (np.sleepMode) {
                            "minutes" -> np.sleepLeftMs?.let { Format.clock(it) } ?: stringResource(R.string.sleep)
                            "chapter" -> stringResource(R.string.sleep_chapter_end_short)
                            else -> stringResource(R.string.sleep)
                        }, color = if (np.sleepMode != "off") MaterialTheme.colorScheme.primary
                        else MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    DropdownMenu(expanded = sleepMenu, onDismissRequest = { sleepMenu = false }) {
                        SleepTimer.PRESETS.forEach { m ->
                            DropdownMenuItem(text = { Text(pluralStringResource(R.plurals.sleep_minutes, m, m)) }, onClick = {
                                sleepMenu = false
                                PlaybackService.setSleep(controller, m)
                            })
                        }
                        DropdownMenuItem(text = { Text(stringResource(R.string.sleep_other)) },
                            onClick = { sleepMenu = false; customSleep = true })
                        DropdownMenuItem(text = { Text(stringResource(R.string.sleep_end_of_chapter)) }, onClick = {
                            sleepMenu = false
                            PlaybackService.setSleep(controller, null)
                        })
                        if (np.sleepMode != "off") {
                            HorizontalDivider()
                            DropdownMenuItem(text = { Text(stringResource(R.string.sleep_turn_off)) }, onClick = {
                                sleepMenu = false
                                PlaybackService.setSleep(controller, null, off = true)
                            })
                        }
                    }
                }
            }
        }
    }

    if (customSleep && controller != null) {
        var minutes by remember { mutableStateOf("") }
        val value = minutes.toIntOrNull()?.takeIf { it in 1..SleepTimer.MAX_MINUTES }
        AlertDialog(
            onDismissRequest = { customSleep = false },
            title = { Text(stringResource(R.string.sleep_timer)) },
            text = {
                OutlinedTextField(minutes, { minutes = it.filter(Char::isDigit).take(4) },
                    label = { Text(stringResource(R.string.minutes)) },
                    singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
            },
            confirmButton = {
                TextButton(enabled = value != null, onClick = {
                    customSleep = false
                    PlaybackService.setSleep(controller, value)
                }) { Text(stringResource(R.string.start)) }
            },
            dismissButton = { TextButton(onClick = { customSleep = false }) { Text(stringResource(R.string.cancel)) } },
        )
    }
}

@Composable
private fun Controls(
    np: NowPlaying,
    controller: MediaController,
    sentences: List<app.ebookaudio.api.Sentence>,
    dragging: Float?,
    onDrag: (Float?) -> Unit,
    speedMenu: Boolean,
    onSpeedMenu: (Boolean) -> Unit,
    onSpeed: (Float) -> Unit,
    sleepButton: @Composable () -> Unit,
) {
    Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally) {
        Text("${np.chapter}. ${np.title}", style = MaterialTheme.typography.titleMedium, maxLines = 1,
            overflow = TextOverflow.Ellipsis)
        Slider(
            value = dragging ?: np.positionMs.toFloat(),
            valueRange = 0f..np.durationMs.coerceAtLeast(1).toFloat(),
            onValueChange = { onDrag(it) },
            onValueChangeFinished = {
                dragging?.let { controller.seekTo(it.toLong()) }
                onDrag(null)
            },
        )
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(Format.clock(dragging?.toLong() ?: np.positionMs), style = MaterialTheme.typography.bodySmall)
            Text(Format.clock(np.durationMs), style = MaterialTheme.typography.bodySmall)
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            IconButton(onClick = { controller.seekToPreviousMediaItem() }, enabled = np.hasPrevious) {
                Icon(Icons.Filled.SkipPrevious, stringResource(R.string.previous_chapter))
            }
            IconButton(onClick = { controller.seekBack() }) {
                Icon(Icons.Filled.Replay10, stringResource(R.string.back_10))
            }
            FilledIconButton(onClick = { if (np.isPlaying) controller.pause() else controller.play() },
                modifier = Modifier.size(64.dp)) {
                Icon(if (np.isPlaying) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                    stringResource(if (np.isPlaying) R.string.pause else R.string.play), Modifier.size(36.dp))
            }
            IconButton(onClick = { controller.seekForward() }) {
                Icon(Icons.Filled.Forward30, stringResource(R.string.forward_30))
            }
            IconButton(onClick = { controller.seekToNextMediaItem() }, enabled = np.hasNext) {
                Icon(Icons.Filled.SkipNext, stringResource(R.string.next_chapter))
            }
        }
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween) {
            val prev = SentenceSync.previousStart(sentences, np.positionMs)
            val next = SentenceSync.nextStart(sentences, np.positionMs)
            // like the web reader: a sentence button also starts playback
            TextButton(onClick = { prev?.let { controller.seekTo(it); controller.play() } }, enabled = prev != null) {
                Text(stringResource(R.string.sentence_previous))
            }
            Box {
                TextButton(onClick = { onSpeedMenu(true) }) {
                    Text(stringResource(R.string.speed_value, speedText(np.speed)))
                }
                DropdownMenu(expanded = speedMenu, onDismissRequest = { onSpeedMenu(false) }) {
                    SPEEDS.forEach { s ->
                        DropdownMenuItem(text = { Text(speedText(s)) }, onClick = {
                            onSpeedMenu(false)
                            controller.setPlaybackSpeed(s)
                            onSpeed(s)
                        })
                    }
                }
            }
            sleepButton()
            TextButton(onClick = { next?.let { controller.seekTo(it); controller.play() } }, enabled = next != null) {
                Text(stringResource(R.string.sentence_next))
            }
        }
        if (np.buffering) Text(stringResource(R.string.loading), style = MaterialTheme.typography.bodySmall)
    }
}

/** The bar under every screen while a book is loaded: tap to open the player. */
@Composable
fun MiniPlayer(controller: MediaController?, onOpen: () -> Unit) {
    val now by rememberNowPlaying(controller)
    val np = now ?: return
    Surface(tonalElevation = 3.dp, modifier = Modifier.fillMaxWidth().clickable(onClick = onOpen)) {
        Row(Modifier.padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            AsyncImage(model = np.artwork, contentDescription = null, contentScale = ContentScale.Crop,
                modifier = Modifier.size(44.dp).clip(RoundedCornerShape(6.dp)))
            Column(Modifier.weight(1f).padding(horizontal = 12.dp)) {
                Text(np.title, maxLines = 1, overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.bodyMedium)
                Text(sleepText(np)?.let { "☾ $it" } ?: np.bookTitle, maxLines = 1, overflow = TextOverflow.Ellipsis,
                    style = MaterialTheme.typography.bodySmall)
            }
            IconButton(onClick = { if (np.isPlaying) controller?.pause() else controller?.play() }) {
                Icon(if (np.isPlaying) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                    stringResource(if (np.isPlaying) R.string.pause else R.string.play))
            }
        }
    }
}
