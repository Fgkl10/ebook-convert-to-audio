package app.ebookaudio.settings

import android.content.Context
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.floatPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import app.ebookaudio.pairing.Pairing
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.store by preferencesDataStore("settings")

/** Where a book was left: the chapter's number in the book (D-035) and the time in it. */
data class Position(val chapter: Int, val ms: Long) {
    fun encode(): String = "$chapter:$ms"

    companion object {
        fun decode(text: String?): Position? {
            val parts = text?.split(":") ?: return null
            if (parts.size != 2) return null
            val chapter = parts[0].toIntOrNull() ?: return null
            val ms = parts[1].toLongOrNull() ?: return null
            return if (chapter >= 1 && ms >= 0) Position(chapter, ms) else null
        }
    }
}

/** Small settings in app-private DataStore: the paired PC, playback speed, and each book's position. */
class Settings(private val context: Context) {
    private val baseUrl = stringPreferencesKey("base_url")
    private val token = stringPreferencesKey("token")
    private val pcName = stringPreferencesKey("pc_name")
    private val speed = floatPreferencesKey("speed")
    private val lastBook = stringPreferencesKey("last_book")
    private fun positionKey(bookId: String): Preferences.Key<String> = stringPreferencesKey("pos:$bookId")

    val pairing: Flow<Pairing?> = context.store.data.map { p ->
        val b = p[baseUrl]
        val t = p[token]
        if (b != null && t != null) Pairing(b, t, p[pcName] ?: "") else null
    }

    suspend fun pair(pairing: Pairing) = context.store.edit {
        it[baseUrl] = pairing.baseUrl
        it[token] = pairing.token
        it[pcName] = pairing.pcName
    }

    suspend fun unpair() = context.store.edit {
        it.remove(baseUrl)
        it.remove(token)
        it.remove(pcName)
    }

    val speedFlow: Flow<Float> = context.store.data.map { it[speed] ?: 1f }
    suspend fun setSpeed(value: Float) = context.store.edit { it[speed] = value }

    val lastBookFlow: Flow<String?> = context.store.data.map { it[lastBook] }

    fun positionFlow(bookId: String): Flow<Position?> =
        context.store.data.map { Position.decode(it[positionKey(bookId)]) }

    suspend fun position(bookId: String): Position? = positionFlow(bookId).first()

    suspend fun savePosition(bookId: String, position: Position) = context.store.edit {
        it[positionKey(bookId)] = position.encode()
        it[lastBook] = bookId
    }

    suspend fun forget(bookId: String) = context.store.edit { it.remove(positionKey(bookId)) }
}
