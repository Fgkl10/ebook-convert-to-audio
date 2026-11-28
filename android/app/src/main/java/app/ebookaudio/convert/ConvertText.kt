package app.ebookaudio.convert

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import app.ebookaudio.R

/** Text for the values ConvertRules returns, from the string resources (A-017). */

@Composable
fun draftStatusText(status: String): String = when (status) {
    "cleaning" -> stringResource(R.string.status_cleaning)
    "review" -> stringResource(R.string.status_review)
    "queued" -> stringResource(R.string.status_queued)
    "converting" -> stringResource(R.string.status_converting)
    "done" -> stringResource(R.string.status_done)
    "error" -> stringResource(R.string.status_error)
    else -> status
}

@Composable
fun statusText(label: StatusLabel): String {
    val partial = label.converted?.let { stringResource(R.string.status_partial, it, label.total) }
    val status = label.status?.let { draftStatusText(it) }
    return listOfNotNull(status, partial).joinToString(" · ")
}

@Composable
fun jobStatusText(status: String): String = when (status) {
    "queued" -> stringResource(R.string.job_queued)
    "running" -> stringResource(R.string.job_running)
    "done" -> stringResource(R.string.job_done)
    "error" -> stringResource(R.string.job_error)
    "cancelled" -> stringResource(R.string.job_cancelled)
    else -> status
}

@Composable
fun approveText(label: ApproveLabel): String = when (label) {
    ApproveLabel.AllAgain -> stringResource(R.string.approve_all_again)
    ApproveLabel.All -> stringResource(R.string.approve_all)
    is ApproveLabel.Some -> pluralStringResource(R.plurals.approve_some, label.count, label.count)
}

@Composable
fun mixedVoiceText(m: MixedVoice): String = stringResource(R.string.mixed_voice, m.voice, m.speed.toString())
