package app.ebookaudio.api

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import java.io.IOException
import java.net.URLEncoder

/** The PC answered 401: the token is missing, wrong or was replaced with --new-token (D-037). */
class NotPaired : IOException("This phone isn't paired with the PC: scan the QR code on the PC's page again")

/** Any other refusal, with the server's {"detail": "..."} message. */
class ApiError(val code: Int, message: String) : IOException(message)

/** Calls to one paired PC. Every request carries `Authorization: Bearer <token>`. */
class ApiClient(val baseUrl: String, private val token: String, http: OkHttpClient) {
    val client: OkHttpClient = http.newBuilder()
        .addInterceptor { chain ->
            chain.proceed(chain.request().newBuilder().header("Authorization", "Bearer $token").build())
        }
        .build()

    fun url(path: String): String = "$baseUrl/api/v1$path"

    /** A file URL the player or image loader fetches by itself, so the token rides in the query (D-037). */
    fun fileUrl(bookId: String, name: String): String =
        url("/books/${enc(bookId)}/files/${enc(name)}") + "?token=" + enc(token)

    /** A file URL for this client's own requests (the header carries the token). */
    fun fileRequestUrl(bookId: String, name: String): String = url("/books/${enc(bookId)}/files/${enc(name)}")

    /** GET a JSON path, blocking. */
    fun get(path: String): String =
        client.newCall(Request.Builder().url(url(path)).build()).execute().use { r ->
            check(r)
            r.body.string()
        }

    suspend fun info(): Info = withContext(Dispatchers.IO) { JSON.decodeFromString<Info>(get("/info")) }
    suspend fun books(): List<BookSummary> = withContext(Dispatchers.IO) { JSON.decodeFromString(get("/books")) }
    suspend fun book(id: String): Book = withContext(Dispatchers.IO) { bookBlocking(id) }
    fun bookBlocking(id: String): Book = JSON.decodeFromString(get("/books/${enc(id)}"))

    companion object {
        fun enc(s: String): String = URLEncoder.encode(s, "UTF-8").replace("+", "%20")

        /** Throws [NotPaired] for 401 and [ApiError] for any other error status. */
        fun check(r: Response) {
            if (r.code == 401) throw NotPaired()
            if (!r.isSuccessful && r.code != 416) throw ApiError(r.code, detail(r))
        }

        private fun detail(r: Response): String {
            val body = runCatching { r.peekBody(16_384).string() }.getOrDefault("")
            val detail = runCatching { JSON.parseToJsonElement(body).jsonObject["detail"]?.jsonPrimitive?.content }
                .getOrNull()
            return detail ?: "The PC answered ${r.code}"
        }
    }
}
