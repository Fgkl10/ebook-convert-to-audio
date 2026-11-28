package app.ebookaudio.player

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Forward30
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Replay10
import androidx.compose.material.icons.filled.SkipNext
import androidx.compose.material.icons.filled.SkipPrevious
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
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
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.media3.session.MediaController
import app.ebookaudio.graph
import app.ebookaudio.ui.Format
import coil3.compose.AsyncImage
import kotlinx.coroutines.launch

val SPEEDS = listOf(0.75f, 1f, 1.25f, 1.5f, 1.75f, 2f)

fun speedText(speed: Float): String =
    (if (speed == speed.toInt().toFloat()) speed.toInt().toString() else speed.toString()) + "×"

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PlayerScreen(controller: MediaController?, onBack: () -> Unit) {
    val now by rememberNowPlaying(controller)
    val settings = LocalContext.current.graph.settings
    val scope = rememberCoroutineScope()
    var dragging by remember { mutableStateOf<Float?>(null) }
    var speedMenu by remember { mutableStateOf(false) }
    Scaffold(
        contentWindowInsets = WindowInsets(0),
        topBar = {
            TopAppBar(
                title = { Text(now?.bookTitle ?: "Player", maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") } },
            )
        },
    ) { padding ->
        val np = now
        if (np == null || controller == null) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Text("Nothing is playing. Pick a book in the library.")
            }
            return@Scaffold
        }
        Column(
            Modifier.fillMaxSize().padding(padding).padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            AsyncImage(
                model = np.artwork,
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier.widthIn(max = 280.dp).fillMaxWidth().aspectRatio(2f / 3f)
                    .clip(RoundedCornerShape(12.dp)),
            )
            Text("Chapter ${np.chapter}", style = MaterialTheme.typography.labelLarge)
            Text(np.title, style = MaterialTheme.typography.titleLarge, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Slider(
                value = dragging ?: np.positionMs.toFloat(),
                valueRange = 0f..np.durationMs.coerceAtLeast(1).toFloat(),
                onValueChange = { dragging = it },
                onValueChangeFinished = {
                    dragging?.let { controller.seekTo(it.toLong()) }
                    dragging = null
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
                    modifier = Modifier.size(72.dp)) {
                    Icon(if (np.isPlaying) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                        if (np.isPlaying) "Pause" else "Play", Modifier.size(40.dp))
                }
                IconButton(onClick = { controller.seekForward() }) { Icon(Icons.Filled.Forward30, "Forward 30 seconds") }
                IconButton(onClick = { controller.seekToNextMediaItem() }, enabled = np.hasNext) {
                    Icon(Icons.Filled.SkipNext, "Next chapter")
                }
            }
            Box {
                TextButton(onClick = { speedMenu = true }) { Text("Speed ${speedText(np.speed)}") }
                DropdownMenu(expanded = speedMenu, onDismissRequest = { speedMenu = false }) {
                    SPEEDS.forEach { s ->
                        DropdownMenuItem(text = { Text(speedText(s)) }, onClick = {
                            speedMenu = false
                            controller.setPlaybackSpeed(s)
                            scope.launch { settings.setSpeed(s) }
                        })
                    }
                }
            }
            if (np.buffering) Text("Loading…", style = MaterialTheme.typography.bodySmall)
            Spacer(Modifier.height(8.dp))
        }
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
                Text(np.bookTitle, maxLines = 1, overflow = TextOverflow.Ellipsis,
                    style = MaterialTheme.typography.bodySmall)
            }
            IconButton(onClick = { if (np.isPlaying) controller?.pause() else controller?.play() }) {
                Icon(if (np.isPlaying) Icons.Filled.Pause else Icons.Filled.PlayArrow, if (np.isPlaying) "Pause" else "Play")
            }
        }
    }
}
