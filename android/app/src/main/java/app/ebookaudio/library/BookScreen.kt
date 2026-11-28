package app.ebookaudio.library

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Update
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
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
import androidx.compose.ui.platform.LocalResources
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.media3.session.MediaController
import app.ebookaudio.R
import app.ebookaudio.api.ApiClient
import app.ebookaudio.api.Book
import app.ebookaudio.api.BookChapter
import app.ebookaudio.download.Downloads
import app.ebookaudio.graph
import app.ebookaudio.player.Playlist
import app.ebookaudio.player.rememberNowPlaying
import app.ebookaudio.ui.Format
import app.ebookaudio.ui.errorText
import coil3.compose.AsyncImage
import kotlinx.coroutines.launch
import java.io.IOException

/** One book: play or continue it, download it (all or chapter by chapter), see what changed on the PC. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BookScreen(bookId: String, controller: MediaController?, onBack: () -> Unit, onPlayer: () -> Unit) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val res = LocalResources.current
    val graph = context.graph
    val library = graph.library
    var local by remember { mutableStateOf(library.book(bookId)) }
    var server by remember { mutableStateOf<Book?>(null) }
    var api by remember { mutableStateOf<ApiClient?>(null) }
    var serverError by remember { mutableStateOf<String?>(null) }
    var confirmDelete by remember { mutableStateOf(false) }
    var menu by remember { mutableStateOf(false) }
    var confirmPcDelete by remember { mutableStateOf(false) }
    var pcMessage by remember { mutableStateOf<String?>(null) }
    val downloadFlow = remember(bookId) { Downloads.state(context, bookId) }
    val (download, failure) = downloadFlow.collectAsState(null to null).value
    val position by remember(bookId) { graph.settings.positionFlow(bookId) }.collectAsState(null)
    val speed by graph.settings.speedFlow.collectAsState(1f)
    val now by rememberNowPlaying(controller)

    LaunchedEffect(bookId) {
        api = graph.api()
        try {
            server = api?.book(bookId)
        } catch (e: IOException) {
            serverError = res.errorText(e)
        }
    }
    LaunchedEffect(download) { local = library.book(bookId) } // a chapter finished, or the download ended

    Scaffold(
        contentWindowInsets = WindowInsets(0),
        topBar = {
            TopAppBar(
                title = { Text(server?.title ?: local?.title ?: "", maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back)) }
                },
                actions = {
                    if (server != null) {
                        IconButton(onClick = { menu = true }) { Icon(Icons.Filled.MoreVert, stringResource(R.string.more)) }
                        DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                            DropdownMenuItem(text = { Text(stringResource(R.string.delete_from_pc)) },
                                onClick = { menu = false; confirmPcDelete = true })
                        }
                    }
                },
            )
        },
    ) { padding ->
        val book = server ?: local
        if (book == null) {
            Message(serverError ?: stringResource(R.string.loading), isError = serverError != null)
            return@Scaffold
        }
        val have = local?.chapters?.associateBy { it.number } ?: emptyMap()
        val onPc = server?.chapters?.associateBy { it.number } ?: emptyMap()
        val numbers = (onPc.keys + have.keys).sorted()
        val toGet = server?.let { Versions.toDownload(local, it) }.orEmpty()

        fun play(chapter: Int?, ms: Long) {
            val c = controller ?: return
            val items = Playlist.items(book, local, library, api)
            Playlist.play(c, items, chapter, ms, speed)
            onPlayer()
        }

        LazyColumn(Modifier.fillMaxSize().padding(padding)) {
            item {
                Row(Modifier.padding(16.dp)) {
                    Surface(Modifier.width(96.dp).height(144.dp).clip(RoundedCornerShape(8.dp)), tonalElevation = 2.dp) {
                        val cover = local?.let { library.cover(it) }
                            ?: book.cover?.let { name -> api?.fileUrl(book.id, name) }
                        if (cover != null) AsyncImage(model = cover, contentDescription = null, contentScale = ContentScale.Crop)
                    }
                    Column(Modifier.padding(start = 16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(book.title, style = MaterialTheme.typography.titleLarge)
                        if (!book.author.isNullOrBlank()) Text(book.author, style = MaterialTheme.typography.bodyMedium)
                        Text(pluralStringResource(R.plurals.chapters_on_phone, numbers.size, have.size, numbers.size) +
                            (if (local != null) " · ${Format.size(library.sizeBytes(bookId))}" else ""),
                            style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            item {
                FlowRow(Modifier.padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    val p = position
                    Button(onClick = { play(p?.chapter, p?.ms ?: 0) }, enabled = controller != null) {
                        Text(if (p != null) stringResource(R.string.continue_at, p.chapter, Format.clock(p.ms))
                            else stringResource(R.string.play))
                    }
                    when {
                        download != null -> OutlinedButton(onClick = { Downloads.cancel(context, bookId) }) {
                            Text(stringResource(R.string.stop_download))
                        }
                        toGet.isNotEmpty() -> OutlinedButton(onClick = { Downloads.start(context, bookId) }) {
                            Text(stringResource(R.string.download_n, toGet.size, Format.size(toGet.sumOf { it.sizeBytes })))
                        }
                    }
                    if (local != null && download == null) {
                        TextButton(onClick = { confirmDelete = true }) { Text(stringResource(R.string.delete_from_phone)) }
                    }
                }
            }
            item {
                Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
                    download?.let { d ->
                        if (d.totalBytes > 0) {
                            LinearProgressIndicator(progress = { d.doneBytes.toFloat() / d.totalBytes },
                                modifier = Modifier.fillMaxWidth())
                        } else {
                            LinearProgressIndicator(Modifier.fillMaxWidth())
                        }
                        Text(if (d.running) stringResource(R.string.download_progress, d.chapter,
                                Format.size(d.doneBytes), Format.size(d.totalBytes))
                            else stringResource(R.string.waiting_network), style = MaterialTheme.typography.bodySmall)
                    }
                    if (download == null && failure != null) {
                        Text(failure, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                    }
                    pcMessage?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.tertiary) }
                    if (server == null && serverError != null) {
                        Text(stringResource(R.string.pc_out_of_reach),
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                    }
                }
            }
            items(numbers, key = { it }) { number ->
                val chapter = onPc[number] ?: have.getValue(number)
                val state = if (server == null) Versions.State.DOWNLOADED else Versions.state(have[number], onPc[number])
                ChapterRow(
                    chapter = chapter,
                    state = state,
                    playing = now?.bookId == bookId && now?.chapter == number,
                    playable = have.containsKey(number) || server != null,
                    onPlay = { play(number, 0) },
                    onDownload = { Downloads.start(context, bookId, listOf(number)) },
                )
            }
        }
    }

    if (confirmPcDelete) {
        AlertDialog(
            onDismissRequest = { confirmPcDelete = false },
            title = { Text(stringResource(R.string.delete_from_pc_title)) },
            text = {
                Text(stringResource(R.string.delete_from_pc_text) +
                    if (local != null) " " + stringResource(R.string.copy_stays) else "")
            },
            confirmButton = {
                TextButton(onClick = {
                    confirmPcDelete = false
                    val a = api ?: return@TextButton
                    scope.launch {
                        try {
                            a.deleteBook(bookId) // 409 while it's converting (A-014)
                            if (local == null) onBack()
                            else { server = null; pcMessage = res.getString(R.string.deleted_from_pc) }
                        } catch (e: IOException) {
                            pcMessage = res.errorText(e)
                        }
                    }
                }) { Text(stringResource(R.string.delete)) }
            },
            dismissButton = { TextButton(onClick = { confirmPcDelete = false }) { Text(stringResource(R.string.cancel)) } },
        )
    }

    if (confirmDelete) {
        AlertDialog(
            onDismissRequest = { confirmDelete = false },
            title = { Text(stringResource(R.string.delete_from_phone_title)) },
            text = { Text(stringResource(R.string.delete_from_phone_text)) },
            confirmButton = {
                TextButton(onClick = {
                    confirmDelete = false
                    if (controller?.currentMediaItem?.mediaId?.startsWith("$bookId|") == true) controller.stop()
                    library.delete(bookId)
                    local = null
                }) { Text(stringResource(R.string.delete)) }
            },
            dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text(stringResource(R.string.cancel)) } },
        )
    }
}

@Composable
private fun ChapterRow(
    chapter: BookChapter,
    state: Versions.State,
    playing: Boolean,
    playable: Boolean,
    onPlay: () -> Unit,
    onDownload: () -> Unit,
) {
    Row(
        Modifier.fillMaxWidth()
            .then(if (playing) Modifier.background(MaterialTheme.colorScheme.secondaryContainer) else Modifier)
            .clickable(enabled = playable, onClick = onPlay)
            .padding(start = 16.dp, end = 4.dp, top = 6.dp, bottom = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text("${chapter.number}. ${chapter.title}", maxLines = 2, overflow = TextOverflow.Ellipsis,
                fontWeight = if (playing) FontWeight.SemiBold else FontWeight.Normal,
                color = if (playable) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.outline)
            Text(Format.clock(chapter.durationMs), style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        when (state) {
            Versions.State.DOWNLOADED -> Icon(Icons.Filled.CheckCircle, stringResource(R.string.on_this_phone),
                Modifier.padding(12.dp).size(20.dp), tint = MaterialTheme.colorScheme.primary)
            Versions.State.NOT_DOWNLOADED -> IconButton(onClick = onDownload) {
                Icon(Icons.Filled.Download, stringResource(R.string.download))
            }
            Versions.State.UPDATE_AVAILABLE -> IconButton(onClick = onDownload) {
                Icon(Icons.Filled.Update, stringResource(R.string.changed_on_pc), tint = MaterialTheme.colorScheme.tertiary)
            }
        }
    }
}
