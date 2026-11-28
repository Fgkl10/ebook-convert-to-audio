package app.ebookaudio.pairing

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalResources
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import app.ebookaudio.R
import app.ebookaudio.api.ApiClient
import app.ebookaudio.api.NotPaired
import app.ebookaudio.graph
import kotlinx.coroutines.launch
import java.io.IOException

/** Pair with the PC: scan the QR code on its page (or paste the link it holds), check it with GET /info, save it. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PairScreen(onPaired: () -> Unit, onBack: (() -> Unit)?) {
    val context = LocalContext.current
    val res = LocalResources.current
    val graph = context.graph
    val scope = rememberCoroutineScope()
    var link by rememberSaveable { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var lastScan by remember { mutableStateOf("") }
    var lastScanAt by remember { mutableLongStateOf(0L) }
    var camera by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
            PackageManager.PERMISSION_GRANTED)
    }
    val askCamera = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { camera = it }

    fun pair(text: String) {
        if (busy) return
        val pairing = PairUrl.parse(text)
        if (pairing == null) {
            error = res.getString(R.string.pair_bad_code)
            return
        }
        busy = true
        error = null
        scope.launch {
            try {
                val info = ApiClient(pairing.baseUrl, pairing.token, graph.http).info()
                if (info.apiVersion != 1) {
                    error = res.getString(R.string.pair_api_version, info.apiVersion)
                } else {
                    graph.settings.pair(pairing.copy(pcName = info.name))
                    onPaired()
                }
            } catch (e: NotPaired) {
                error = res.getString(R.string.pair_refused)
            } catch (e: IOException) {
                error = res.getString(R.string.pair_cant_reach, pairing.baseUrl)
            } finally {
                busy = false
            }
        }
    }

    Scaffold(
        contentWindowInsets = WindowInsets(0),
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.pair_with_pc)) },
                navigationIcon = {
                    if (onBack != null) IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back))
                    }
                },
            )
        },
    ) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(stringResource(R.string.pair_intro))
            Surface(
                modifier = Modifier.widthIn(max = 360.dp).fillMaxWidth().aspectRatio(1f).clip(RoundedCornerShape(12.dp)),
                tonalElevation = 2.dp,
            ) {
                if (camera) {
                    QrScanner(onText = { text ->
                        val now = System.currentTimeMillis()
                        if (text != lastScan || now - lastScanAt > 4_000) { // don't retry the same code every frame
                            lastScan = text
                            lastScanAt = now
                            pair(text)
                        }
                    }, modifier = Modifier.fillMaxSize())
                } else {
                    Box(contentAlignment = Alignment.Center) {
                        Button(onClick = { askCamera.launch(Manifest.permission.CAMERA) }) {
                            Text(stringResource(R.string.pair_scan_camera))
                        }
                    }
                }
            }
            if (busy) CircularProgressIndicator()
            error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            Text(stringResource(R.string.pair_or_paste), style = MaterialTheme.typography.bodySmall)
            OutlinedTextField(value = link, onValueChange = { link = it }, singleLine = true,
                label = { Text(stringResource(R.string.pair_link)) }, modifier = Modifier.fillMaxWidth())
            Button(onClick = { pair(link) }, enabled = link.isNotBlank() && !busy) { Text(stringResource(R.string.pair)) }
        }
    }
}
