package app.ebookaudio.ui

import android.content.res.Resources
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import app.ebookaudio.R
import app.ebookaudio.api.NotPaired
import java.io.IOException

/** "1 h 5 min" / "42 min" in the app's language (A-017). */
@Composable
fun durationText(ms: Long): String {
    val minutes = ((ms + 30_000) / 60_000).toInt()
    return if (minutes >= 60) stringResource(R.string.duration_h_min, minutes / 60, minutes % 60)
    else stringResource(R.string.duration_min, minutes)
}

/**
 * What to show for a failed call: "not paired" in the app's language, else the server's or the network's message
 * (those stay in English, from the PC or OkHttp), else a generic "can't reach the PC".
 */
fun Resources.errorText(e: IOException): String =
    if (e is NotPaired) getString(R.string.not_paired_error) else e.message ?: getString(R.string.cant_reach_pc)
