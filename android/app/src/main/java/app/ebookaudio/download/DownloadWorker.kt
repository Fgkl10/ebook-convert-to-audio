package app.ebookaudio.download

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.ServiceInfo
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.ForegroundInfo
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkInfo
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import app.ebookaudio.R
import app.ebookaudio.api.NotPaired
import app.ebookaudio.graph
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.withContext
import java.io.IOException
import java.util.concurrent.TimeUnit

/** A download's state for the screens. */
data class DownloadState(val running: Boolean, val doneBytes: Long, val totalBytes: Long, val chapter: String)

/** Downloads run in WorkManager, so they continue with the app in the background and retry after a network cut. */
object Downloads {
    private const val BOOK = "book"
    private const val CHAPTERS = "chapters"
    const val DONE = "done"
    const val TOTAL = "total"
    const val CHAPTER = "chapter"
    const val ERROR = "error"

    private fun name(bookId: String) = "download-$bookId"

    /** Downloads [chapters] (numbers) of a book, or every missing or changed chapter when null. */
    fun start(context: Context, bookId: String, chapters: Collection<Int>? = null) {
        val request = OneTimeWorkRequestBuilder<DownloadWorker>()
            .setInputData(workDataOf(BOOK to bookId, CHAPTERS to (chapters?.toIntArray() ?: IntArray(0))))
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 10, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(name(bookId), ExistingWorkPolicy.APPEND_OR_REPLACE, request)
    }

    fun cancel(context: Context, bookId: String) {
        WorkManager.getInstance(context).cancelUniqueWork(name(bookId))
    }

    /** The current download of a book (null when none is waiting or running), and the last failure's message. */
    fun state(context: Context, bookId: String): Flow<Pair<DownloadState?, String?>> =
        WorkManager.getInstance(context).getWorkInfosForUniqueWorkFlow(name(bookId)).map { infos ->
            val active = infos.firstOrNull { !it.state.isFinished }
            val failed = infos.lastOrNull { it.state == WorkInfo.State.FAILED }?.outputData?.getString(ERROR)
            active?.let {
                DownloadState(
                    running = it.state == WorkInfo.State.RUNNING,
                    doneBytes = it.progress.getLong(DONE, 0),
                    totalBytes = it.progress.getLong(TOTAL, 0),
                    chapter = it.progress.getString(CHAPTER) ?: "",
                )
            } to failed
        }

    internal fun bookOf(worker: CoroutineWorker) = worker.inputData.getString(BOOK)
    internal fun chaptersOf(worker: CoroutineWorker) =
        worker.inputData.getIntArray(CHAPTERS)?.toSet()?.takeIf { it.isNotEmpty() }
}

class DownloadWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    private val channel = "downloads"
    private val notificationId = 1000 + Math.floorMod(Downloads.bookOf(this)?.hashCode() ?: 0, 1000)

    override suspend fun doWork(): Result {
        val bookId = Downloads.bookOf(this) ?: return Result.failure()
        val graph = applicationContext.graph
        val ctx = applicationContext
        val api = graph.api() ?: return Result.failure(workDataOf(Downloads.ERROR to ctx.getString(R.string.not_paired_error)))
        val downloading = ctx.getString(R.string.dl_downloading)
        runCatching { setForeground(foreground(downloading, 0, 0)) } // best effort: works while the app is open
        var lastUpdate = 0L
        return try {
            withContext(Dispatchers.IO) {
                Downloader(api, graph.library).download(bookId, Downloads.chaptersOf(this@DownloadWorker),
                    progress = { done, total, chapter ->
                        val now = System.currentTimeMillis()
                        if (now - lastUpdate > 400 || done == total) {
                            lastUpdate = now
                            setProgressAsync(workDataOf(Downloads.DONE to done, Downloads.TOTAL to total,
                                Downloads.CHAPTER to chapter))
                            notify(foreground(chapter.ifEmpty { downloading }, done, total))
                        }
                    },
                    isStopped = { isStopped })
            }
            Result.success()
        } catch (e: NotPaired) {
            Result.failure(workDataOf(Downloads.ERROR to ctx.getString(R.string.not_paired_error)))
        } catch (e: IOException) {
            if (runAttemptCount < 5) Result.retry()
            else Result.failure(workDataOf(Downloads.ERROR to ctx.getString(R.string.dl_failed, e.message.orEmpty())))
        } catch (e: IllegalArgumentException) {
            Result.failure(workDataOf(Downloads.ERROR to (e.message ?: ctx.getString(R.string.dl_bad_data))))
        }
    }

    private fun notify(info: ForegroundInfo) {
        runCatching {
            val nm = applicationContext.getSystemService(NotificationManager::class.java)
            nm.notify(info.notificationId, info.notification)
        }
    }

    private fun foreground(text: String, done: Long, total: Long): ForegroundInfo {
        val nm = applicationContext.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(channel, applicationContext.getString(R.string.dl_channel),
            NotificationManager.IMPORTANCE_LOW))
        val percent = if (total > 0) (done * 100 / total).toInt() else 0
        val notification = NotificationCompat.Builder(applicationContext, channel)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle(applicationContext.getString(R.string.dl_title))
            .setContentText(text)
            .setProgress(100, percent, total == 0L)
            .setOngoing(true)
            .setSilent(true)
            .build()
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ForegroundInfo(notificationId, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            ForegroundInfo(notificationId, notification)
        }
    }
}
