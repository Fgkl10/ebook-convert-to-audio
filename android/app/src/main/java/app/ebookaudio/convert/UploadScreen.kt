package app.ebookaudio.convert

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.media3.session.MediaController
import app.ebookaudio.api.ApiClient
import app.ebookaudio.api.Info
import app.ebookaudio.api.UploadFile
import app.ebookaudio.graph
import app.ebookaudio.ui.Format
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.IOException

/** A book file chosen on the phone: its Uri, display name and size (from the ContentResolver). */
data class PickedFile(val uri: Uri, val name: String, val size: Long)

fun Context.picked(uri: Uri): PickedFile {
    var name = uri.lastPathSegment?.substringAfterLast('/') ?: "book"
    var size = -1L
    runCatching {
        contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)
            ?.use { c ->
                if (c.moveToFirst()) {
                    c.getString(0)?.let { name = it }
                    if (!c.isNull(1)) size = c.getLong(1)
                }
            }
    }
    return PickedFile(uri, name, size)
}

private val MIME_TYPES = arrayOf("application/epub+zip", "application/pdf", "text/plain", "application/octet-stream")

/** Upload a book to the PC: to clean (and review), or already cleaned (converts at once). Like the web page. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun UploadScreen(initial: Uri?, book: MediaController?, onBack: () -> Unit, onUploaded: () -> Unit) {
    val context = LocalContext.current
    val graph = context.graph
    val scope = rememberCoroutineScope()
    val sample = rememberSamplePlayer()
    var file by remember { mutableStateOf(initial?.let { context.picked(it) }) }
    var api by remember { mutableStateOf<ApiClient?>(null) }
    var info by remember { mutableStateOf<Info?>(null) }
    var voice by remember { mutableStateOf("") }
    var speed by remember { mutableDoubleStateOf(1.0) }
    var auto by remember { mutableStateOf(false) }
    var ocr by remember { mutableStateOf("auto") }
    var cleaned by remember { mutableStateOf(false) }
    var sent by remember { mutableLongStateOf(-1L) } // -1: not uploading
    var message by remember { mutableStateOf<String?>(null) }
    var offerClean by remember { mutableStateOf(false) }

    val pick = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) { file = context.picked(uri); message = null }
    }

    LaunchedEffect(Unit) {
        try {
            api = graph.api()
            info = api?.info()
            info?.let { voice = it.defaultVoice.ifBlank { it.voices.firstOrNull().orEmpty() } }
        } catch (e: IOException) {
            message = e.message ?: "Can't reach the PC"
        }
    }

    fun upload(asCleaned: Boolean) {
        val a = api ?: return
        val f = file ?: return
        message = null
        sent = 0
        scope.launch {
            try {
                val upload = UploadFile(f.name, f.size) {
                    context.contentResolver.openInputStream(f.uri) ?: throw IOException("Can't read ${f.name}")
                }
                withContext(Dispatchers.IO) {
                    if (asCleaned) a.uploadCleaned(upload, voice, speed) { sent = it }
                    else a.upload(upload, voice, speed, auto, if (ConvertRules.isPdf(f.name)) ocr else "auto") { sent = it }
                }
                onUploaded()
            } catch (e: IOException) {
                sent = -1
                if (asCleaned && ConvertRules.isNotCleaned(e.message)) offerClean = true
                else message = e.message ?: "Upload failed"
            }
        }
    }

    Scaffold(
        contentWindowInsets = WindowInsets(0),
        topBar = {
            TopAppBar(
                title = { Text("Add a book") },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") } },
            )
        },
    ) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    val f = file
                    if (f == null) Text("Pick an EPUB, PDF or TXT file.")
                    else Text(f.name + if (f.size > 0) " · ${Format.size(f.size)}" else "",
                        style = MaterialTheme.typography.titleSmall)
                    if (f != null && !ConvertRules.isUploadable(f.name)) {
                        Text("Only .epub, .pdf and .txt books can be converted.", color = MaterialTheme.colorScheme.error)
                    }
                    OutlinedButton(onClick = { pick.launch(MIME_TYPES) }, enabled = sent < 0) {
                        Text(if (f == null) "Choose a file" else "Choose another file")
                    }
                }
            }

            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Already cleaned (.std.epub)")
                    Text("From the PC's cleaner or Sigil: converts right away, no review.",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Switch(checked = cleaned, onCheckedChange = { cleaned = it })
            }

            info?.let { i ->
                VoiceAndSpeed(i.voices, voice, speed, { voice = it }, { speed = it }, api, sample, book)
            }

            if (!cleaned) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Skip review")
                        Text("Convert right after cleaning, without checking the chapters first.",
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Switch(checked = auto, onCheckedChange = { auto = it })
                }
                val pdf = file?.let { ConvertRules.isPdf(it.name) } == true
                Text("OCR (scanned PDFs)", style = MaterialTheme.typography.titleSmall)
                Row {
                    listOf("auto", "always", "never").forEach { mode ->
                        Row(
                            Modifier.selectable(selected = ocr == mode, enabled = pdf, role = Role.RadioButton,
                                onClick = { ocr = mode }).padding(end = 12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            RadioButton(selected = ocr == mode, onClick = null, enabled = pdf)
                            Text(mode)
                        }
                    }
                }
                if (!pdf) Text("OCR reads scanned PDFs. EPUB and TXT files have their own text, so they need no OCR.",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }

            val f = file
            val ready = f != null && api != null && sent < 0 &&
                (if (cleaned) ConvertRules.canBeCleaned(f.name) else ConvertRules.isUploadable(f.name))
            if (cleaned && f != null && !ConvertRules.canBeCleaned(f.name)) {
                Text("A cleaned book is an .epub (.std.epub).", color = MaterialTheme.colorScheme.error)
            }
            Button(onClick = { upload(cleaned) }, enabled = ready, modifier = Modifier.fillMaxWidth()) {
                Text(when {
                    cleaned -> "Upload & convert"
                    auto -> "Upload, clean & convert"
                    else -> "Upload & clean"
                })
            }
            if (sent >= 0) {
                val total = f?.size ?: -1
                if (total > 0) LinearProgressIndicator(progress = { sent.toFloat() / total }, modifier = Modifier.fillMaxWidth())
                else LinearProgressIndicator(Modifier.fillMaxWidth())
                Text("Uploading… ${Format.size(sent)}" + if (total > 0) " of ${Format.size(total)}" else "",
                    style = MaterialTheme.typography.bodySmall)
                Text("Keep this screen open until the upload finishes.", style = MaterialTheme.typography.bodySmall)
            }
            message?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        }
    }

    if (offerClean) {
        AlertDialog(
            onDismissRequest = { offerClean = false },
            title = { Text("Not cleaned yet") },
            text = { Text("\"${file?.name}\" is not cleaned yet, so it can't be converted directly. Clean it now? " +
                "It will appear under \"Cleaned, to review\".") },
            confirmButton = {
                TextButton(onClick = { offerClean = false; cleaned = false; auto = false; ocr = "auto"; upload(false) }) {
                    Text("Clean it")
                }
            },
            dismissButton = { TextButton(onClick = { offerClean = false }) { Text("Cancel") } },
        )
    }
}
