package app.ebookaudio.library

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.PrimaryTabRow
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import app.ebookaudio.api.ApiClient
import app.ebookaudio.api.Book
import app.ebookaudio.api.BookSummary
import app.ebookaudio.api.NotPaired
import app.ebookaudio.graph
import app.ebookaudio.ui.Format
import coil3.compose.AsyncImage
import java.io.IOException

/** Two lists: the books on this phone (play offline) and the books on the PC (browse, stream, download). */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LibraryScreen(onOpen: (String) -> Unit, onSettings: () -> Unit, onPair: () -> Unit) {
    val graph = LocalContext.current.graph
    var local by remember { mutableStateOf(graph.library.books()) }
    var tab by rememberSaveable { mutableIntStateOf(if (local.isEmpty()) 1 else 0) }
    var api by remember { mutableStateOf<ApiClient?>(null) }
    var remote by remember { mutableStateOf<List<BookSummary>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var notPaired by remember { mutableStateOf(false) }
    var loading by remember { mutableStateOf(false) }
    var refresh by remember { mutableIntStateOf(0) }

    LifecycleResumeEffect(Unit) {
        local = graph.library.books()
        refresh++
        onPauseOrDispose { }
    }
    LaunchedEffect(refresh) {
        loading = true
        try {
            api = graph.api()
            notPaired = api == null
            remote = api?.books()
            error = null
        } catch (e: NotPaired) {
            notPaired = true
            error = e.message
        } catch (e: IOException) {
            error = "Can't reach the PC (${api?.baseUrl}). Is the server running, and ZeroTier on? " +
                "Books on this phone still play."
        } finally {
            loading = false
        }
    }

    Scaffold(
        contentWindowInsets = WindowInsets(0),
        topBar = {
            TopAppBar(
                title = { Text("Library") },
                actions = {
                    IconButton(onClick = { local = graph.library.books(); refresh++ }) { Icon(Icons.Filled.Refresh, "Refresh") }
                    IconButton(onClick = onSettings) { Icon(Icons.Filled.Settings, "Settings") }
                },
            )
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            PrimaryTabRow(selectedTabIndex = tab) {
                Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("On this phone (${local.size})") })
                Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("On the PC") })
            }
            if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            if (tab == 0) {
                if (local.isEmpty()) {
                    Message("No books on this phone yet. Open one on the PC tab and download it to listen offline.")
                }
                LazyColumn {
                    items(local, key = { it.id }) { book ->
                        BookRow(
                            title = book.title,
                            author = book.author,
                            cover = graph.library.cover(book),
                            line = phoneLine(book, graph.library.sizeBytes(book.id)),
                            onClick = { onOpen(book.id) },
                        )
                    }
                }
            } else {
                if (notPaired) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(error ?: "This phone isn't paired with a PC yet.")
                        Button(onClick = onPair) { Text("Pair with the PC") }
                    }
                } else {
                    error?.let { Message(it, isError = true) }
                    val list = remote.orEmpty()
                    if (remote != null && list.isEmpty()) Message("The PC's library is empty. Convert a book on the PC first.")
                    LazyColumn {
                        items(list, key = { it.id }) { book ->
                            val onPhone = local.firstOrNull { it.id == book.id }
                            BookRow(
                                title = book.title,
                                author = book.author,
                                cover = book.cover?.let { name -> api?.fileUrl(book.id, name) },
                                line = pcLine(book, onPhone),
                                onClick = { onOpen(book.id) },
                            )
                        }
                    }
                }
            }
        }
    }
}

private fun phoneLine(book: Book, bytes: Long) =
    "${book.chapters.size} chapters · ${Format.duration(book.durationMs)} · ${Format.size(bytes)}"

private fun pcLine(book: BookSummary, onPhone: Book?): String {
    val chapters = book.chaptersTotal?.let { total ->
        if (book.chapters < total) "${book.chapters} of $total chapters" else "$total chapters"
    } ?: "${book.chapters} chapters"
    val parts = mutableListOf(chapters, Format.duration(book.durationMs), Format.size(book.sizeBytes))
    if (book.converting) parts += "converting"
    if (onPhone != null) parts += "${onPhone.chapters.size} on phone"
    return parts.joinToString(" · ")
}

@Composable
fun Message(text: String, isError: Boolean = false) {
    Text(text, Modifier.padding(16.dp),
        color = if (isError) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
fun BookRow(title: String, author: String?, cover: Any?, line: String, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clickable(onClick = onClick).padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Surface(Modifier.width(48.dp).height(72.dp).clip(RoundedCornerShape(6.dp)), tonalElevation = 2.dp) {
            Box { if (cover != null) AsyncImage(model = cover, contentDescription = null, contentScale = ContentScale.Crop) }
        }
        Column(Modifier.padding(start = 14.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (!author.isNullOrBlank()) Text(author, style = MaterialTheme.typography.bodyMedium, maxLines = 1)
            Text(line, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
