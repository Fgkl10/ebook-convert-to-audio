package app.ebookaudio.ui

import android.Manifest
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
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import app.ebookaudio.graph
import app.ebookaudio.library.BookScreen
import app.ebookaudio.library.LibraryScreen
import app.ebookaudio.pairing.PairScreen
import app.ebookaudio.player.MiniPlayer
import app.ebookaudio.player.PlayerConnection
import app.ebookaudio.player.PlayerScreen
import kotlinx.coroutines.flow.first

class MainActivity : ComponentActivity() {
    private lateinit var connection: PlayerConnection

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        connection = PlayerConnection(this)
        setContent { AppTheme { AppNav(connection) } }
    }

    override fun onStart() {
        super.onStart()
        connection.connect()
    }

    override fun onStop() {
        connection.disconnect()
        super.onStop()
    }
}

/** Pair → Library → Book → Player, plus Settings; the mini player sits under every screen but the player. */
@Composable
fun AppNav(connection: PlayerConnection) {
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
    Surface(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().navigationBarsPadding()) {
            Box(Modifier.weight(1f)) {
                NavHost(nav, startDestination = start) {
                    composable("pair") {
                        PairScreen(
                            onPaired = { nav.navigate("library") { popUpTo(0) } },
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
        }
    }
}
