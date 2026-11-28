package app.ebookaudio.convert

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import app.ebookaudio.api.ApiClient
import app.ebookaudio.api.Draft
import app.ebookaudio.api.Job
import app.ebookaudio.api.NotPaired
import app.ebookaudio.graph
import app.ebookaudio.library.Message
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.IOException

/** What the PC is cleaning and converting, like the web page's Clean and Convert tabs (A-011). Polls every 2 s. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ConvertScreen(
    onAdd: () -> Unit,
    onReview: (String) -> Unit,
    onListen: (String) -> Unit,
    onSettings: () -> Unit,
    onPair: () -> Unit,
) {
    val graph = LocalContext.current.graph
    val scope = rememberCoroutineScope()
    var api by remember { mutableStateOf<ApiClient?>(null) }
    var drafts by remember { mutableStateOf<List<Draft>?>(null) }
    var jobs by remember { mutableStateOf<List<Job>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    var notPaired by remember { mutableStateOf(false) }
    var confirm by remember { mutableStateOf<Confirm?>(null) }

    suspend fun refresh() {
        try {
            val a = api ?: graph.api().also { api = it }
            if (a == null) { notPaired = true; return }
            jobs = a.jobs()
            drafts = a.drafts()
            error = null
        } catch (e: NotPaired) {
            notPaired = true
        } catch (e: IOException) {
            error = "Can't reach the PC (${api?.baseUrl}). Is the server running, and ZeroTier on?"
        }
    }

    LifecycleResumeEffect(Unit) {
        val poll = scope.launch { while (isActive) { refresh(); delay(2_000) } }
        onPauseOrDispose { poll.cancel() }
    }

    fun act(block: suspend (ApiClient) -> Unit) {
        val a = api ?: return
        scope.launch {
            try { block(a) } catch (e: IOException) { error = e.message }
            refresh()
        }
    }

    Scaffold(
        contentWindowInsets = WindowInsets(0),
        topBar = {
            TopAppBar(
                title = { Text("Convert on the PC") },
                actions = { IconButton(onClick = onSettings) { Icon(Icons.Filled.Settings, "Settings") } },
            )
        },
        floatingActionButton = {
            if (!notPaired) ExtendedFloatingActionButton(onClick = onAdd, icon = { Icon(Icons.Filled.Add, null) },
                text = { Text("Add a book") })
        },
    ) { padding ->
        if (notPaired) {
            Column(Modifier.padding(padding).padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Pair with the PC to convert books from this phone.")
                OutlinedButton(onClick = onPair) { Text("Pair with the PC") }
            }
            return@Scaffold
        }
        val all = drafts
        LazyColumn(Modifier.fillMaxSize().padding(padding), contentPadding = PaddingValues(bottom = 88.dp)) {
            error?.let { item { Message(it, isError = true) } }
            if (all == null) {
                item { LinearProgressIndicator(Modifier.fillMaxWidth().padding(16.dp)) }
                return@LazyColumn
            }
            val visible = ConvertRules.visibleJobs(jobs, System.currentTimeMillis() / 1000.0)
            section("Conversions running", visible.isEmpty(), "No conversions running.")
            items(visible, key = { "job-" + it.id }) { j ->
                JobCard(j, onCancel = {
                    confirm = Confirm(cancelText) { it.cancelJob(j.id) }
                })
            }
            val cleaning = all.filter(ConvertRules::isCleaning)
            section("Cleaned, to review", cleaning.isEmpty(), "Nothing here. Add a book to clean it on the PC.")
            items(cleaning, key = { "draft-" + it.id }) { d ->
                DraftCard(d, onReview, onListen, onCancel = {}, onDiscard = { confirm = Confirm(discardText) { it.discardDraft(d.id) } })
            }
            val approved = all.filterNot(ConvertRules::isCleaning)
            section("Approved", approved.isEmpty(), "No approved books yet.")
            items(approved, key = { "draft-" + it.id }) { d ->
                DraftCard(d, onReview, onListen,
                    onCancel = { confirm = Confirm(cancelText) { it.cancelDraft(d.id) } },
                    onDiscard = { confirm = Confirm(discardText) { it.discardDraft(d.id) } })
            }
        }
    }

    confirm?.let { c ->
        AlertDialog(
            onDismissRequest = { confirm = null },
            text = { Text(c.text) },
            confirmButton = { TextButton(onClick = { confirm = null; act { c.action(it) } }) { Text("Yes") } },
            dismissButton = { TextButton(onClick = { confirm = null }) { Text("No") } },
        )
    }
}

/** A question before an action on the PC. */
private class Confirm(val text: String, val action: suspend (ApiClient) -> Unit)

private const val cancelText = "Cancel this conversion? Finished chapters stay in the library; approving again " +
    "resumes where it stopped."

private const val discardText = "Discard this cleaned book? The uploaded file and the cleaned version are deleted " +
    "on the PC. A converted book stays in the library."

private fun LazyListScope.section(title: String, empty: Boolean, emptyText: String) {
    item(key = "title-$title") {
        Text(title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(16.dp, 16.dp, 16.dp, 4.dp))
    }
    if (empty) item(key = "empty-$title") { Message(emptyText) }
}

@Composable
private fun JobCard(j: Job, onCancel: () -> Unit) {
    Card(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(j.file, style = MaterialTheme.typography.titleSmall)
            val pct = if (j.total > 0) 100f * j.done / j.total else 0f
            Text(j.status + if (j.total > 0) " · ${j.done}/${j.total} sentences · ${"%.1f".format(pct)}%" else "",
                style = MaterialTheme.typography.bodySmall)
            if (j.status == "running") LinearProgressIndicator(progress = { pct / 100 }, modifier = Modifier.fillMaxWidth())
            val note = j.error ?: j.message
            if (note.isNotBlank()) Text(note, style = MaterialTheme.typography.bodySmall,
                color = if (j.error != null) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant)
            if (ConvertRules.canCancel(j)) TextButton(onClick = onCancel) { Text("Cancel") }
        }
    }
}

@Composable
private fun DraftCard(
    d: Draft,
    onReview: (String) -> Unit,
    onListen: (String) -> Unit,
    onCancel: () -> Unit,
    onDiscard: () -> Unit,
) {
    Card(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(d.file, style = MaterialTheme.typography.titleSmall)
            val info = if (d.chapters > 0) " · ${d.chapters} ch" + (if (d.checks > 0) " · ${d.checks} to check" else "") else ""
            Text(ConvertRules.statusLabel(d) + info, style = MaterialTheme.typography.bodySmall)
            if (d.status == "cleaning" && d.total > 0) {
                LinearProgressIndicator(progress = { d.done.toFloat() / d.total }, modifier = Modifier.fillMaxWidth())
            }
            val note = d.error ?: d.message
            if (note.isNotBlank()) Text(note, style = MaterialTheme.typography.bodySmall,
                color = if (d.error != null) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                if (ConvertRules.canCancel(d)) TextButton(onClick = onCancel) { Text("Cancel") }
                if (ConvertRules.canReview(d)) TextButton(onClick = { onReview(d.id) }) {
                    Text(if (d.status == "done") "Review again" else "Review")
                }
                if (ConvertRules.canListen(d)) TextButton(onClick = { onListen(d.bookId!!) }) { Text("Listen") }
                if (ConvertRules.canDiscard(d)) TextButton(onClick = onDiscard) { Text("Discard") }
            }
        }
    }
}
