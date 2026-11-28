package app.ebookaudio

import android.app.Application
import android.content.Context
import app.ebookaudio.api.ApiClient
import app.ebookaudio.library.LocalLibrary
import app.ebookaudio.settings.Settings
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.first
import okhttp3.OkHttpClient
import java.io.File
import java.util.concurrent.TimeUnit

class EbookAudioApp : Application() {
    lateinit var graph: AppGraph
        private set

    override fun onCreate() {
        super.onCreate()
        graph = AppGraph(this)
    }
}

/** The app's few long-lived objects, made once (no DI framework: A-003). */
class AppGraph(context: Context) {
    val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .build()
    val settings = Settings(context)
    val library = LocalLibrary(File(context.filesDir, "books"))

    /** Work that must finish even when the screen that started it is gone (saving a position). */
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    /** A client for the paired PC, or null before pairing. */
    suspend fun api(): ApiClient? = settings.pairing.first()?.let { ApiClient(it.baseUrl, it.token, http) }
}

val Context.graph: AppGraph get() = (applicationContext as EbookAudioApp).graph
