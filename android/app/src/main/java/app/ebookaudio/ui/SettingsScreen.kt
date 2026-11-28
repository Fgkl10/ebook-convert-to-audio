package app.ebookaudio.ui

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import app.ebookaudio.R
import app.ebookaudio.graph
import kotlinx.coroutines.launch

/** The paired PC, storage, and how to keep the phone's battery saver from stopping playback (A-018). */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(onBack: () -> Unit, onPair: () -> Unit) {
    val context = LocalContext.current
    val graph = context.graph
    val scope = rememberCoroutineScope()
    val pairing by graph.settings.pairing.collectAsState(null)
    var used by remember { mutableLongStateOf(graph.library.sizeBytes()) }
    var confirm by remember { mutableStateOf<String?>(null) }

    Scaffold(
        contentWindowInsets = WindowInsets(0),
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.settings)) },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back)) }
                },
            )
        },
    ) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Section(stringResource(R.string.settings_pc)) {
                val p = pairing
                Text(if (p != null) {
                    stringResource(R.string.pc_at, p.pcName.ifBlank { stringResource(R.string.settings_pc) }, p.baseUrl)
                } else stringResource(R.string.not_paired))
                Button(onClick = onPair) {
                    Text(stringResource(if (p != null) R.string.pair_again else R.string.pair_with_pc))
                }
                if (p != null) OutlinedButton(onClick = { confirm = "unpair" }) { Text(stringResource(R.string.unpair)) }
            }
            Section(stringResource(R.string.storage)) {
                Text(stringResource(R.string.storage_used, Format.size(used)))
                if (used > 0) OutlinedButton(onClick = { confirm = "delete" }) {
                    Text(stringResource(R.string.delete_all_downloads))
                }
            }
            Section(stringResource(R.string.bg_title)) {
                val vendor = remember { BackgroundTips.vendorOf(Build.MANUFACTURER, Build.BRAND) }
                Text(stringResource(R.string.bg_intro))
                Text(stringResource(vendor.steps), style = MaterialTheme.typography.bodyMedium)
                Button(onClick = {
                    context.startActivity(Intent(ACTION_APPLICATION_DETAILS_SETTINGS,
                        Uri.fromParts("package", context.packageName, null)))
                }) { Text(stringResource(R.string.open_app_info)) }
            }
        }
    }

    confirm?.let { what ->
        AlertDialog(
            onDismissRequest = { confirm = null },
            title = { Text(stringResource(if (what == "unpair") R.string.unpair_title else R.string.delete_all_title)) },
            text = {
                Text(stringResource(if (what == "unpair") R.string.unpair_text else R.string.delete_all_text))
            },
            confirmButton = {
                TextButton(onClick = {
                    confirm = null
                    if (what == "unpair") scope.launch { graph.settings.unpair() }
                    else {
                        graph.library.deleteAll()
                        used = graph.library.sizeBytes()
                    }
                }) { Text(stringResource(if (what == "unpair") R.string.unpair else R.string.delete)) }
            },
            dismissButton = { TextButton(onClick = { confirm = null }) { Text(stringResource(R.string.cancel)) } },
        )
    }
}

@Composable
private fun Section(title: String, content: @Composable () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            content()
        }
    }
}
