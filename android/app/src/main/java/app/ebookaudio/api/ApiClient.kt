package app.ebookaudio.api

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.MediaType
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okio.BufferedSink
import okio.source
import java.io.IOException
import java.io.InputStream
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

/** The PC answered 401: the token is missing, wrong or was replaced with --new-token (D-037). */
class NotPaired : IOException("This phone isn't paired with the PC: scan the QR code on the PC's page again")

/** Any other refusal, with the server's {"detail": "..."} message. */
class ApiError(val code: Int, message: String) : IOException(message)

/** A book file to upload, streamed from [open] (a ContentResolver stream: never held in memory, A-012). Each call
 * of [open] must return a fresh stream from the start: a retry reads the file again. */
class UploadFile(val name: String, val size: Long, val open: () -> InputStream)

/** Calls to one paired PC. Every request carries `Authorization: Bearer <token>`. */
class ApiClient(val baseUrl: String, private val token: String, http: OkHttpClient) {
    val client: OkHttpClient = http.newBuilder()
        .addInterceptor { chain ->
            chain.proceed(chain.request().newBuilder().header("Authorization", "Bearer $token").build())
        }
        .build()

    /** Uploads can be hundreds of MB over a slow VPN. */
    private val uploads: OkHttpClient = client.newBuilder()
        .writeTimeout(10, TimeUnit.MINUTES)
        .readTimeout(10, TimeUnit.MINUTES)
        .build()

    fun url(path: String): String = "$baseUrl/api/v1$path"

    /** A file URL the player or image loader fetches by itself, so the token rides in the query (D-037). */
    fun fileUrl(bookId: String, name: String): String =
        url("/books/${enc(bookId)}/files/${enc(name)}") + "?token=" + enc(token)

    /** A file URL for this client's own requests (the header carries the token). */
    fun fileRequestUrl(bookId: String, name: String): String = url("/books/${enc(bookId)}/files/${enc(name)}")

    /** About 5 s of a voice reading a fixed sentence, for the player (the token rides in the query). */
    fun voiceSampleUrl(voice: String): String = url("/voices/${enc(voice)}/sample") + "?token=" + enc(token)

    private fun call(request: Request, http: OkHttpClient = client): String =
        http.newCall(request).execute().use { r ->
            check(r)
            r.body.string()
        }

    /** GET a JSON path, blocking. */
    fun get(path: String): String = call(Request.Builder().url(url(path)).build())

    private fun post(path: String, json: String = "{}"): String =
        call(Request.Builder().url(url(path)).post(json.toRequestBody(JSON_TYPE)).build())

    private fun delete(path: String): String = call(Request.Builder().url(url(path)).delete().build())

    private suspend inline fun <reified T> io(crossinline block: () -> String): T =
        withContext(Dispatchers.IO) { JSON.decodeFromString<T>(block()) }

    suspend fun info(): Info = io { get("/info") }
    suspend fun books(): List<BookSummary> = io { get("/books") }
    suspend fun book(id: String): Book = withContext(Dispatchers.IO) { bookBlocking(id) }
    fun bookBlocking(id: String): Book = JSON.decodeFromString(get("/books/${enc(id)}"))
    suspend fun deleteBook(id: String) { io<Ok> { delete("/books/${enc(id)}") } }

    suspend fun drafts(): List<Draft> = io { get("/drafts") }
    suspend fun draft(id: String): DraftDetail = io { get("/drafts/${enc(id)}") }
    suspend fun draftChapter(id: String, index: Int): DraftChapter = io { get("/drafts/${enc(id)}/chapters/$index") }
    suspend fun jobs(): List<Job> = io { get("/jobs") }

    /** Converts the chosen chapters (1-based), or all when [chapters] is null. */
    suspend fun approve(id: String, voice: String, speed: Double, chapters: List<Int>?): JobCreated = io {
        // the default Json writes "chapters": null, which the server reads as "all"
        post("/drafts/${enc(id)}/approve", Json.encodeToString(ApproveRequest.serializer(),
            ApproveRequest(voice, speed, chapters)))
    }
    suspend fun cancelDraft(id: String): Job = io { post("/drafts/${enc(id)}/cancel") }
    suspend fun discardDraft(id: String) { io<Ok> { delete("/drafts/${enc(id)}") } }
    suspend fun cancelJob(id: String): Job = io { post("/jobs/${enc(id)}/cancel") }

    /** Uploads a book to clean (POST /drafts); [auto] converts right after cleaning. */
    suspend fun upload(file: UploadFile, voice: String, speed: Double, auto: Boolean, ocr: String,
                       progress: (Long) -> Unit = {}): DraftCreated =
        io { multipart("/drafts", file, progress, "voice" to voice, "speed" to speed.toString(),
            "auto" to auto.toString(), "ocr" to ocr) }

    /** Uploads an already-cleaned .std.epub (POST /drafts/cleaned); it converts right away. */
    suspend fun uploadCleaned(file: UploadFile, voice: String, speed: Double,
                              progress: (Long) -> Unit = {}): DraftCreated =
        io { multipart("/drafts/cleaned", file, progress, "voice" to voice, "speed" to speed.toString()) }

    private fun multipart(path: String, file: UploadFile, progress: (Long) -> Unit,
                          vararg fields: Pair<String, String>): String {
        val body = MultipartBody.Builder().setType(MultipartBody.FORM).apply {
            fields.forEach { (k, v) -> addFormDataPart(k, v) }
            addFormDataPart("file", file.name, StreamBody(file, progress))
        }.build()
        return call(Request.Builder().url(url(path)).post(body).build(), uploads)
    }

    /**
     * Streams the file into the request; reports bytes written. Not one-shot: each write reopens the file, so OkHttp
     * can send it again on a fresh connection when a pooled one turns out closed (the server drops idle connections
     * after 5 s, e.g. while a dialog was open).
     */
    private class StreamBody(private val file: UploadFile, private val progress: (Long) -> Unit) : RequestBody() {
        override fun contentType(): MediaType = "application/octet-stream".toMediaType()
        override fun contentLength(): Long = if (file.size > 0) file.size else -1
        override fun isOneShot(): Boolean = false
        override fun writeTo(sink: BufferedSink) {
            file.open().source().use { source ->
                var written = 0L
                while (true) {
                    val n = source.read(sink.buffer, 64 * 1024L)
                    if (n == -1L) break
                    sink.emitCompleteSegments()
                    written += n
                    progress(written)
                }
            }
        }
    }

    companion object {
        private val JSON_TYPE = "application/json".toMediaType()

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

@kotlinx.serialization.Serializable
data class Ok(val ok: Boolean = true)
