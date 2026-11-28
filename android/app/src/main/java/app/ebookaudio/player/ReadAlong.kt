package app.ebookaudio.player

import android.os.SystemClock
import android.util.Log
import androidx.compose.foundation.gestures.animateScrollBy
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.ebookaudio.api.Sentence
import app.ebookaudio.graph
import kotlinx.coroutines.CancellationException

/**
 * The playing chapter's sentences: from the phone's copy, else from the PC. Null while loading; empty when there is
 * no text (PC unreachable offline, not paired, an old book): then the player shows the cover.
 */
@Composable
fun rememberChapterSentences(bookId: String, chapter: Int): List<Sentence>? {
    val graph = LocalContext.current.graph
    val state by produceState<List<Sentence>?>(null, bookId, chapter) {
        value = try {
            graph.library.book(bookId)?.chapters?.firstOrNull { it.number == chapter }?.sentences
                ?.takeIf { it.isNotEmpty() }
                ?: graph.api()?.book(bookId)?.chapters?.firstOrNull { it.number == chapter }?.sentences
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) { // network, 401, a changed format: read along is optional, playback goes on
            Log.w("ReadAlong", "no text for $bookId chapter $chapter: $e")
            null
        }.orEmpty()
    }
    return state
}

/**
 * The chapter text with the sentence being read highlighted and kept a third of the way down (A-015). Tapping a
 * sentence plays from it. Scrolling by hand stops the automatic scrolling for [MANUAL_SCROLL_MS], like the web reader.
 */
@Composable
fun ReadAlong(
    sentences: List<Sentence>,
    positionMs: Long,
    textSize: Float,
    onSeek: (Long) -> Unit,
    modifier: Modifier = Modifier,
) {
    val paragraphs = remember(sentences) { SentenceSync.paragraphs(sentences) }
    // for each sentence: its paragraph and its character range in that paragraph's text
    val where = remember(paragraphs) {
        buildMap {
            paragraphs.forEachIndexed { p, list ->
                var offset = 0
                list.forEach { s ->
                    put(s.i, Triple(p, offset, offset + s.text.length))
                    offset += s.text.length + 1
                }
            }
        }
    }
    val current = SentenceSync.at(sentences, positionMs).let { sentences.getOrNull(it)?.i }
    val listState = rememberLazyListState()
    val layouts = remember(paragraphs) { mutableStateMapOf<Int, TextLayoutResult>() }
    var manualUntil by remember { mutableLongStateOf(0L) }
    val autoScrolling = remember { mutableStateOf(false) }
    val highlight = MaterialTheme.colorScheme.primaryContainer
    val onHighlight = MaterialTheme.colorScheme.onPrimaryContainer

    // a hand scroll (while dragging or flinging, and MANUAL_SCROLL_MS after) stops the automatic scrolling
    LaunchedEffect(listState) {
        snapshotFlow { listState.isScrollInProgress && !autoScrolling.value }.collect { byHand ->
            if (byHand) manualUntil = Long.MAX_VALUE
            else if (manualUntil == Long.MAX_VALUE) manualUntil = SystemClock.uptimeMillis() + MANUAL_SCROLL_MS
        }
    }
    LaunchedEffect(current, textSize) {
        val (p, start, _) = where[current ?: return@LaunchedEffect] ?: return@LaunchedEffect
        if (SystemClock.uptimeMillis() < manualUntil) return@LaunchedEffect
        autoScrolling.value = true
        try {
            val third = listState.layoutInfo.viewportSize.height / 3
            if (listState.layoutInfo.visibleItemsInfo.none { it.index == p }) listState.scrollToItem(p)
            val item = listState.layoutInfo.visibleItemsInfo.firstOrNull { it.index == p } ?: return@LaunchedEffect
            val layout = layouts[p]
            val lineTop = layout?.let { it.getLineTop(it.getLineForOffset(start)).toInt() } ?: 0
            // the sentence's line goes a third of the way down the text area
            listState.animateScrollBy((item.offset + lineTop - third).toFloat())
        } finally {
            autoScrolling.value = false
        }
    }

    Box(modifier) {
        LazyColumn(state = listState, modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(horizontal = 20.dp, vertical = 24.dp)) {
            itemsIndexed(paragraphs) { p, list ->
                val mine = current?.takeIf { c -> list.any { it.i == c } } // only this paragraph's highlight
                val text = remember(list, mine, highlight) {
                    buildAnnotatedString {
                        list.forEachIndexed { k, s ->
                            if (k > 0) append(' ')
                            if (s.i == mine) withStyle(SpanStyle(background = highlight, color = onHighlight)) { append(s.text) }
                            else append(s.text)
                        }
                    }
                }
                Text(
                    text,
                    fontSize = textSize.sp,
                    lineHeight = (textSize * 1.5f).sp,
                    onTextLayout = { layouts[p] = it },
                    modifier = Modifier.padding(bottom = 14.dp).pointerInput(list) {
                        detectTapGestures { pos ->
                            val offset = layouts[p]?.getOffsetForPosition(pos) ?: return@detectTapGestures
                            val tapped = list.firstOrNull { s ->
                                val (_, a, b) = where.getValue(s.i)
                                offset in a..b
                            } ?: return@detectTapGestures
                            manualUntil = 0 // follow the new sentence right away
                            onSeek(tapped.startMs)
                        }
                    },
                )
            }
        }
        if (paragraphs.isEmpty()) Text("No text for this chapter.", Modifier.align(Alignment.Center))
    }
}

const val MANUAL_SCROLL_MS = 4_000L
