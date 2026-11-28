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
import androidx.compose.ui.platform.LocalResources
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.media3.session.MediaController
import app.ebookaudio.R
import app.ebookaudio.api.ApiClient
import app.ebookaudio.api.Info
import app.ebookaudio.api.NotPaired
import app.ebookaudio.api.UploadFile
import app.ebookaudio.graph
import app.ebookaudio.ui.Format
import app.ebookaudio.ui.errorText
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
    val res = LocalResources.current
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
            message = res.errorText(e)
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
                    context.contentResolver.openInputStream(f.uri) ?: throw IOException(res.getString(R.string.cant_read, f.name))
                }
                withContext(Dispatchers.IO) {
                    if (asCleaned) a.uploadCleaned(upload, voice, speed) { sent = it }
                    else a.upload(upload, voice, speed, auto, if (ConvertRules.isPdf(f.name)) ocr else "auto") { sent = it }
                }
                onUploaded()
            } catch (e: IOException) {
                sent = -1
                if (asCleaned && ConvertRules.isNotCleaned(e.message)) offerClean = true
                else message = if (e is NotPaired) res.errorText(e) else e.message ?: res.getString(R.string.upload_failed)
            }
        }
    }

    Scaffold(
        contentWindowInsets = WindowInsets(0),
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.add_book)) },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back)) }
                },
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
                    if (f == null) Text(stringResource(R.string.pick_file_hint))
                    else Text(f.name + if (f.size > 0) " · ${Format.size(f.size)}" else "",
                        style = MaterialTheme.typography.titleSmall)
                    if (f != null && !ConvertRules.isUploadable(f.name)) {
                        Text(stringResource(R.string.only_formats), color = MaterialTheme.colorScheme.error)
                    }
                    OutlinedButton(onClick = { pick.launch(MIME_TYPES) }, enabled = sent < 0) {
                        Text(stringResource(if (f == null) R.string.choose_file else R.string.choose_another))
                    }
                }
            }

            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(stringResource(R.string.already_cleaned))
                    Text(stringResource(R.string.already_cleaned_hint),
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
                        Text(stringResource(R.string.skip_review))
                        Text(stringResource(R.string.skip_review_hint),
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Switch(checked = auto, onCheckedChange = { auto = it })
                }
                val pdf = file?.let { ConvertRules.isPdf(it.name) } == true
                Text(stringResource(R.string.ocr_title), style = MaterialTheme.typography.titleSmall)
                Row {
                    listOf("auto" to R.string.ocr_auto, "always" to R.string.ocr_always, "never" to R.string.ocr_never)
                        .forEach { (mode, label) ->
                        Row(
                            Modifier.selectable(selected = ocr == mode, enabled = pdf, role = Role.RadioButton,
                                onClick = { ocr = mode }).padding(end = 12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            RadioButton(selected = ocr == mode, onClick = null, enabled = pdf)
                            Text(stringResource(label))
                        }
                    }
                }
                if (!pdf) Text(stringResource(R.string.ocr_hint),
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }

            val f = file
            val ready = f != null && api != null && sent < 0 &&
                (if (cleaned) ConvertRules.canBeCleaned(f.name) else ConvertRules.isUploadable(f.name))
            if (cleaned && f != null && !ConvertRules.canBeCleaned(f.name)) {
                Text(stringResource(R.string.cleaned_is_epub), color = MaterialTheme.colorScheme.error)
            }
            Button(onClick = { upload(cleaned) }, enabled = ready, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(when {
                    cleaned -> R.string.upload_convert
                    auto -> R.string.upload_clean_convert
                    else -> R.string.upload_clean
                }))
            }
            if (sent >= 0) {
                val total = f?.size ?: -1
                if (total > 0) LinearProgressIndicator(progress = { sent.toFloat() / total }, modifier = Modifier.fillMaxWidth())
                else LinearProgressIndicator(Modifier.fillMaxWidth())
                Text(if (total > 0) stringResource(R.string.uploading_of, Format.size(sent), Format.size(total))
                    else stringResource(R.string.uploading, Format.size(sent)), style = MaterialTheme.typography.bodySmall)
                Text(stringResource(R.string.keep_open), style = MaterialTheme.typography.bodySmall)
            }
            message?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        }
    }

    if (offerClean) {
        AlertDialog(
            onDismissRequest = { offerClean = false },
            title = { Text(stringResource(R.string.not_cleaned_title)) },
            text = { Text(stringResource(R.string.not_cleaned_text, file?.name.orEmpty())) },
            confirmButton = {
                TextButton(onClick = { offerClean = false; cleaned = false; auto = false; ocr = "auto"; upload(false) }) {
                    Text(stringResource(R.string.clean_it))
                }
            },
            dismissButton = { TextButton(onClick = { offerClean = false }) { Text(stringResource(R.string.cancel)) } },
        )
    }
}
