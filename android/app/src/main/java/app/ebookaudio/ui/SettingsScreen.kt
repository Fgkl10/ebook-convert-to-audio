package app.ebookaudio.ui

import android.content.Intent
import android.net.Uri
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
import androidx.compose.ui.unit.dp
import app.ebookaudio.graph
import kotlinx.coroutines.launch

/** The paired PC, storage, and how to keep HyperOS from stopping playback. */
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
                title = { Text("Settings") },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") } },
            )
        },
    ) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Section("PC") {
                val p = pairing
                Text(if (p != null) "${p.pcName.ifBlank { "PC" }} at ${p.baseUrl}" else "Not paired")
                Button(onClick = onPair) { Text(if (p != null) "Pair again" else "Pair with the PC") }
                if (p != null) OutlinedButton(onClick = { confirm = "unpair" }) { Text("Unpair") }
            }
            Section("Storage") {
                Text("Books on this phone use ${Format.size(used)}.")
                if (used > 0) OutlinedButton(onClick = { confirm = "delete" }) { Text("Delete all downloads") }
            }
            Section("Playing with the screen off (HyperOS)") {
                Text("HyperOS may stop the app in the background. So that books keep playing:")
                Text("1. App info → Battery saver → No restrictions\n" +
                    "2. App info → Autostart → on\n" +
                    "3. In Recents, pull the app's card down to lock it", style = MaterialTheme.typography.bodyMedium)
                Button(onClick = {
                    context.startActivity(Intent(ACTION_APPLICATION_DETAILS_SETTINGS,
                        Uri.fromParts("package", context.packageName, null)))
                }) { Text("Open app info") }
            }
        }
    }

    confirm?.let { what ->
        AlertDialog(
            onDismissRequest = { confirm = null },
            title = { Text(if (what == "unpair") "Unpair from the PC?" else "Delete all downloads?") },
            text = {
                Text(if (what == "unpair") "Books on this phone still play. To use the PC again, scan its QR code."
                else "The books stay on the PC. Listening positions are kept.")
            },
            confirmButton = {
                TextButton(onClick = {
                    confirm = null
                    if (what == "unpair") scope.launch { graph.settings.unpair() }
                    else {
                        graph.library.deleteAll()
                        used = graph.library.sizeBytes()
                    }
                }) { Text(if (what == "unpair") "Unpair" else "Delete") }
            },
            dismissButton = { TextButton(onClick = { confirm = null }) { Text("Cancel") } },
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
