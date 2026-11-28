package app.ebookaudio.convert

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalResources
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.media3.session.MediaController
import app.ebookaudio.R
import app.ebookaudio.api.ApiClient
import app.ebookaudio.api.DraftChapter
import app.ebookaudio.api.DraftDetail
import app.ebookaudio.api.Info
import app.ebookaudio.graph
import app.ebookaudio.library.Message
import app.ebookaudio.ui.errorText
import kotlinx.coroutines.launch
import java.io.IOException

/** Review a cleaned book before converting: the report, the chapters (text and choice), voice and speed (A-011). */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReviewScreen(draftId: String, book: MediaController?, onBack: () -> Unit, onApproved: () -> Unit) {
    val graph = LocalContext.current.graph
    val res = LocalResources.current
    val scope = rememberCoroutineScope()
    val sample = rememberSamplePlayer()
    var api by remember { mutableStateOf<ApiClient?>(null) }
    var info by remember { mutableStateOf<Info?>(null) }
    var draft by remember { mutableStateOf<DraftDetail?>(null) }
    var picked by remember { mutableStateOf(emptySet<Int>()) }
    var voice by remember { mutableStateOf("") }
    var speed by remember { mutableDoubleStateOf(1.0) }
    var error by remember { mutableStateOf<String?>(null) }
    var reading by remember { mutableStateOf<DraftChapter?>(null) }
    var busy by remember { mutableStateOf(false) }
    var confirmDiscard by remember { mutableStateOf(false) }

    LaunchedEffect(draftId) {
        try {
            api = graph.api()
            val a = api ?: return@LaunchedEffect
            info = a.info()
            val d = a.draft(draftId)
            draft = d
            picked = ConvertRules.defaultPicks(d)
            // chapters added to a book keep its voice unless the user picks another (D-035); the language starts on
            // the book's own (D-043)
            voice = ConvertRules.voiceFor(info?.languages.orEmpty(), d.bookVoice ?: d.voice, d.report?.language ?: "en")
            speed = d.bookSpeed ?: d.speed
        } catch (e: IOException) {
            error = res.errorText(e)
        }
    }

    fun open(index: Int) {
        val a = api ?: return
        scope.launch {
            try { reading = a.draftChapter(draftId, index) } catch (e: IOException) { error = res.errorText(e) }
        }
    }

    fun approve() {
        val a = api ?: return
        val d = draft ?: return
        busy = true
        scope.launch {
            try {
                a.approve(draftId, voice, speed, ConvertRules.approveChapters(d, picked))
                onApproved()
            } catch (e: IOException) {
                error = res.errorText(e)
            } finally {
                busy = false
            }
        }
    }

    Scaffold(
        contentWindowInsets = WindowInsets(0),
        topBar = {
            TopAppBar(
                title = { Text(draft?.file ?: stringResource(R.string.review), maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back)) } },
            )
        },
    ) { padding ->
        val d = draft
        val report = d?.report
        if (d == null || report == null) {
            Message(error ?: stringResource(if (d != null) R.string.not_cleaned_yet else R.string.loading), isError = error != null)
            return@Scaffold
        }
        val chapters = report.chapters
        LazyColumn(Modifier.fillMaxSize().padding(padding)) {
            item {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(report.method, style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (report.checks.isNotEmpty()) {
                        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.tertiaryContainer)) {
                            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Text(stringResource(R.string.check_by_hand, report.checks.size), style = MaterialTheme.typography.titleSmall)
                                report.checks.forEach { Text("• $it", style = MaterialTheme.typography.bodySmall) }
                            }
                        }
                    }
                    Details(stringResource(R.string.report_removed), report.removed)
                    Details(stringResource(R.string.report_toc_ignored), report.unconfirmed)
                    Details(stringResource(R.string.report_notes), report.notes)
                }
            }
            item {
                Row(Modifier.padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(R.string.chapters_header, chapters.size), style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.weight(1f))
                    TextButton(onClick = { picked = (1..chapters.size).toSet() }) { Text(stringResource(R.string.pick_all)) }
                    TextButton(onClick = { picked = emptySet() }) { Text(stringResource(R.string.pick_none)) }
                    TextButton(onClick = { picked = ConvertRules.newOnly(d) }) { Text(stringResource(R.string.pick_new)) }
                }
                Text(stringResource(R.string.tap_chapter_hint), Modifier.padding(horizontal = 16.dp),
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            itemsIndexed(chapters) { i, (title, chars) ->
                val n = i + 1
                Row(
                    Modifier.fillMaxWidth().clickable { open(i) }.padding(horizontal = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Checkbox(checked = n in picked, onCheckedChange = { on -> picked = if (on) picked + n else picked - n })
                    Column(Modifier.weight(1f)) {
                        Text("$n. $title", maxLines = 2, overflow = TextOverflow.Ellipsis)
                        val size = stringResource(R.string.chapter_chars, "%,d".format(chars))
                        Text(if (n in d.converted) size + " · " + stringResource(R.string.chapter_converted) else size,
                            style = MaterialTheme.typography.bodySmall,
                            color = if (n in d.converted) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
            item {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    info?.let { VoiceAndSpeed(it.languages, voice, speed, { v -> voice = v }, { s -> speed = s }, api, sample, book) }
                    ConvertRules.mixedVoiceWarning(d, picked, voice, speed)?.let {
                        Text(mixedVoiceText(it), color = MaterialTheme.colorScheme.tertiary, style = MaterialTheme.typography.bodySmall)
                    }
                    error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = ::approve, enabled = !busy && ConvertRules.canApprove(d, picked)) {
                            Text(approveText(ConvertRules.approveLabel(d, picked)))
                        }
                        TextButton(onClick = { confirmDiscard = true }) { Text(stringResource(R.string.discard)) }
                    }
                }
            }
        }
    }

    reading?.let { ch ->
        ModalBottomSheet(onDismissRequest = { reading = null }) {
            LazyColumn(Modifier.padding(horizontal = 20.dp)) {
                item { Text(ch.title, style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(bottom = 12.dp)) }
                itemsIndexed(ch.paragraphs) { _, p -> Text(p, Modifier.padding(bottom = 10.dp)) }
            }
        }
    }

    if (confirmDiscard) {
        AlertDialog(
            onDismissRequest = { confirmDiscard = false },
            text = { Text(stringResource(R.string.confirm_discard_review)) },
            confirmButton = {
                TextButton(onClick = {
                    confirmDiscard = false
                    val a = api ?: return@TextButton
                    scope.launch {
                        try { a.discardDraft(draftId); onBack() } catch (e: IOException) { error = res.errorText(e) }
                    }
                }) { Text(stringResource(R.string.discard)) }
            },
            dismissButton = { TextButton(onClick = { confirmDiscard = false }) { Text(stringResource(R.string.cancel)) } },
        )
    }
}

/** A collapsible list (the web page's <details>). */
@Composable
private fun Details(title: String, items: List<String>) {
    if (items.isEmpty()) return
    var open by remember { mutableStateOf(false) }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.clickable { open = !open }.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(R.string.details_count, title, items.size), Modifier.weight(1f), style = MaterialTheme.typography.titleSmall)
                Icon(if (open) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore, null)
            }
            if (open) items.forEach { Text("• $it", style = MaterialTheme.typography.bodySmall) }
        }
    }
}
