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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.media3.session.MediaController
import app.ebookaudio.graph
import app.ebookaudio.settings.Settings
import app.ebookaudio.ui.Format
import coil3.compose.AsyncImage
import kotlinx.coroutines.launch

val SPEEDS = listOf(0.75f, 1f, 1.25f, 1.5f, 1.75f, 2f)

fun speedText(speed: Float): String =
    (if (speed == speed.toInt().toFloat()) speed.toInt().toString() else speed.toString()) + "×"

/** "Sleep in 23:41", "Sleep at end of chapter", or null when the timer is off. */
fun sleepText(np: NowPlaying): String? = when (np.sleepMode) {
    "minutes" -> np.sleepLeftMs?.let { "Sleep in ${Format.clock(it)}" }
    "chapter" -> "Sleep at end of chapter" + (np.sleepLeftMs?.let { " (${Format.clock(it)})" } ?: "")
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
                title = { Text(np?.bookTitle ?: "Player", maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") } },
                actions = {
                    if (np != null && controller != null) {
                        IconButton(onClick = { scope.launch { settings.setShowText(!showText) } }) {
                            if (showText) Icon(Icons.Filled.Image, "Show the cover")
                            else Icon(Icons.AutoMirrored.Filled.Subject, "Show the text")
                        }
                        Box {
                            IconButton(onClick = { moreMenu = true }) { Icon(Icons.Filled.MoreVert, "More") }
                            DropdownMenu(expanded = moreMenu, onDismissRequest = { moreMenu = false }) {
                                DropdownMenuItem(text = { Text("Larger text") }, enabled = textSize < Settings.TEXT_SIZE_MAX,
                                    onClick = { scope.launch { settings.setTextSize(textSize + Settings.TEXT_SIZE_STEP) } })
                                DropdownMenuItem(text = { Text("Smaller text") }, enabled = textSize > Settings.TEXT_SIZE_MIN,
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
                Text("Nothing is playing. Pick a book in the library.")
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
                    if (showText && sentences == null) Text("Loading the text…")
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
                            "minutes" -> np.sleepLeftMs?.let { Format.clock(it) } ?: "Sleep"
                            "chapter" -> "Ch. end"
                            else -> "Sleep"
                        }, color = if (np.sleepMode != "off") MaterialTheme.colorScheme.primary
                        else MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    DropdownMenu(expanded = sleepMenu, onDismissRequest = { sleepMenu = false }) {
                        SleepTimer.PRESETS.forEach { m ->
                            DropdownMenuItem(text = { Text("$m minutes") }, onClick = {
                                sleepMenu = false
                                PlaybackService.setSleep(controller, m)
                            })
                        }
                        DropdownMenuItem(text = { Text("Other…") }, onClick = { sleepMenu = false; customSleep = true })
                        DropdownMenuItem(text = { Text("End of this chapter") }, onClick = {
                            sleepMenu = false
                            PlaybackService.setSleep(controller, null)
                        })
                        if (np.sleepMode != "off") {
                            HorizontalDivider()
                            DropdownMenuItem(text = { Text("Turn off") }, onClick = {
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
            title = { Text("Sleep timer") },
            text = {
                OutlinedTextField(minutes, { minutes = it.filter(Char::isDigit).take(4) }, label = { Text("Minutes") },
                    singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
            },
            confirmButton = {
                TextButton(enabled = value != null, onClick = {
                    customSleep = false
                    PlaybackService.setSleep(controller, value)
                }) { Text("Start") }
            },
            dismissButton = { TextButton(onClick = { customSleep = false }) { Text("Cancel") } },
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
                Icon(Icons.Filled.SkipPrevious, "Previous chapter")
            }
            IconButton(onClick = { controller.seekBack() }) { Icon(Icons.Filled.Replay10, "Back 10 seconds") }
            FilledIconButton(onClick = { if (np.isPlaying) controller.pause() else controller.play() },
                modifier = Modifier.size(64.dp)) {
                Icon(if (np.isPlaying) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                    if (np.isPlaying) "Pause" else "Play", Modifier.size(36.dp))
            }
            IconButton(onClick = { controller.seekForward() }) { Icon(Icons.Filled.Forward30, "Forward 30 seconds") }
            IconButton(onClick = { controller.seekToNextMediaItem() }, enabled = np.hasNext) {
                Icon(Icons.Filled.SkipNext, "Next chapter")
            }
        }
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween) {
            val prev = SentenceSync.previousStart(sentences, np.positionMs)
            val next = SentenceSync.nextStart(sentences, np.positionMs)
            // like the web reader: a sentence button also starts playback
            TextButton(onClick = { prev?.let { controller.seekTo(it); controller.play() } }, enabled = prev != null) {
                Text("‹ Sentence")
            }
            Box {
                TextButton(onClick = { onSpeedMenu(true) }) { Text("Speed ${speedText(np.speed)}") }
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
                Text("Sentence ›")
            }
        }
        if (np.buffering) Text("Loading…", style = MaterialTheme.typography.bodySmall)
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
                Icon(if (np.isPlaying) Icons.Filled.Pause else Icons.Filled.PlayArrow, if (np.isPlaying) "Pause" else "Play")
            }
        }
    }
}
