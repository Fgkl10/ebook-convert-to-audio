package app.ebookaudio.ui

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.LibraryBooks
import androidx.compose.material.icons.filled.Transform
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.IntentCompat
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import app.ebookaudio.convert.ConvertScreen
import app.ebookaudio.convert.ReviewScreen
import app.ebookaudio.convert.UploadScreen
import app.ebookaudio.graph
import app.ebookaudio.library.BookScreen
import app.ebookaudio.library.LibraryScreen
import app.ebookaudio.pairing.PairScreen
import app.ebookaudio.player.MiniPlayer
import app.ebookaudio.player.PlayerConnection
import app.ebookaudio.player.PlayerScreen
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first

class MainActivity : ComponentActivity() {
    private lateinit var connection: PlayerConnection

    /** A book file handed in by "Open with" or Share (A-013), until the upload screen takes it. */
    private val incoming = MutableStateFlow<Uri?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        connection = PlayerConnection(this)
        if (savedInstanceState == null) incoming.value = bookUri(intent)
        setContent { AppTheme { AppNav(connection, incoming) } }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        bookUri(intent)?.let { incoming.value = it }
    }

    override fun onStart() {
        super.onStart()
        connection.connect()
    }

    override fun onStop() {
        connection.disconnect()
        super.onStop()
    }

    private fun bookUri(intent: Intent?): Uri? = when (intent?.action) {
        Intent.ACTION_VIEW -> intent.data
        Intent.ACTION_SEND -> IntentCompat.getParcelableExtra(intent, Intent.EXTRA_STREAM, Uri::class.java)
        else -> null
    }
}

private val TABS = listOf("library", "convert")

/**
 * Library and Convert tabs; Book, Player, Upload, Review, Settings and Pair on top. The mini player sits under every
 * screen but the player and pairing.
 */
@Composable
fun AppNav(connection: PlayerConnection, incoming: MutableStateFlow<Uri?>) {
    val graph = LocalContext.current.graph
    val paired by produceState<Boolean?>(null) { value = graph.settings.pairing.first() != null }
    val controller by connection.controller.collectAsState()
    val askNotifications = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
    LaunchedEffect(Unit) { // the download progress notification (media notifications don't need it)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
    }
    val isPaired = paired
    if (isPaired == null) { // reading settings: a blank frame for a moment
        Surface(Modifier.fillMaxSize()) { }
        return
    }
    val start = if (isPaired || graph.library.books().isNotEmpty()) "library" else "pair"
    val nav = rememberNavController()
    val route = nav.currentBackStackEntryAsState().value?.destination?.route
    val handedIn by incoming.collectAsState()
    var upload by remember { mutableStateOf<Uri?>(null) } // the file the upload screen starts with

    // A file from "Open with" / Share: to the upload screen, through pairing first if needed.
    LaunchedEffect(handedIn) {
        val uri = handedIn ?: return@LaunchedEffect
        incoming.value = null
        upload = uri
        if (graph.settings.pairing.first() != null) nav.navigate("upload") else nav.navigate("pair")
    }

    Surface(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().navigationBarsPadding()) {
            Box(Modifier.weight(1f)) {
                NavHost(nav, startDestination = start) {
                    composable("pair") {
                        PairScreen(
                            onPaired = {
                                nav.navigate("library") { popUpTo(0) }
                                if (upload != null) nav.navigate("upload")
                            },
                            onBack = if (nav.previousBackStackEntry != null) ({ nav.popBackStack() }) else null,
                        )
                    }
                    composable("library") {
                        LibraryScreen(
                            onOpen = { nav.navigate("book/$it") },
                            onSettings = { nav.navigate("settings") },
                            onPair = { nav.navigate("pair") },
                        )
                    }
                    composable("convert") {
                        ConvertScreen(
                            onAdd = { upload = null; nav.navigate("upload") },
                            onReview = { nav.navigate("review/$it") },
                            onListen = { nav.navigate("book/$it") },
                            onSettings = { nav.navigate("settings") },
                            onPair = { nav.navigate("pair") },
                        )
                    }
                    composable("upload") {
                        UploadScreen(
                            initial = upload,
                            book = controller,
                            onBack = { nav.popBackStack() },
                            onUploaded = { upload = null; nav.toTab("convert") },
                        )
                    }
                    composable("review/{id}") { entry ->
                        ReviewScreen(
                            draftId = entry.arguments?.getString("id") ?: "",
                            book = controller,
                            onBack = { nav.popBackStack() },
                            onApproved = { nav.toTab("convert") },
                        )
                    }
                    composable("book/{id}") { entry ->
                        BookScreen(
                            bookId = entry.arguments?.getString("id") ?: "",
                            controller = controller,
                            onBack = { nav.popBackStack() },
                            onPlayer = { nav.navigate("player") },
                        )
                    }
                    composable("player") { PlayerScreen(controller, onBack = { nav.popBackStack() }) }
                    composable("settings") {
                        SettingsScreen(onBack = { nav.popBackStack() }, onPair = { nav.navigate("pair") })
                    }
                }
            }
            if (route != "player" && route != "pair") MiniPlayer(controller) { nav.navigate("player") }
            if (route in TABS) {
                NavigationBar(windowInsets = WindowInsets(0)) {
                    NavigationBarItem(
                        selected = route == "library", onClick = { nav.toTab("library") },
                        icon = { Icon(Icons.AutoMirrored.Filled.LibraryBooks, null) }, label = { Text("Library") },
                    )
                    NavigationBarItem(
                        selected = route == "convert", onClick = { nav.toTab("convert") },
                        icon = { Icon(Icons.Filled.Transform, null) }, label = { Text("Convert") },
                    )
                }
            }
        }
    }
}

/** Switch tabs: Library is the root; Convert sits on it, so Back from Convert returns to Library. */
private fun NavHostController.toTab(tab: String) {
    if (tab == "library") {
        popBackStack("library", inclusive = false)
    } else {
        navigate(tab) {
            popUpTo("library")
            launchSingleTop = true
        }
    }
}
