package app.ebookaudio.player

import android.os.SystemClock
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.interaction.DragInteraction
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
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
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
import java.io.IOException

/** The playing chapter's sentences: from the phone's copy, else from the PC; null while loading or unavailable. */
@Composable
fun rememberChapterSentences(bookId: String, chapter: Int): List<Sentence>? {
    val graph = LocalContext.current.graph
    val state by produceState<List<Sentence>?>(null, bookId, chapter) {
        value = graph.library.book(bookId)?.chapters?.firstOrNull { it.number == chapter }?.sentences
            ?.takeIf { it.isNotEmpty() }
            ?: try {
                graph.api()?.book(bookId)?.chapters?.firstOrNull { it.number == chapter }?.sentences
            } catch (e: IOException) {
                null
            }
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
    val highlight = MaterialTheme.colorScheme.primaryContainer
    val onHighlight = MaterialTheme.colorScheme.onPrimaryContainer

    LaunchedEffect(listState) {
        listState.interactionSource.interactions.collect {
            if (it is DragInteraction.Start) manualUntil = SystemClock.uptimeMillis() + MANUAL_SCROLL_MS
        }
    }
    LaunchedEffect(current, textSize) {
        val (p, start, _) = where[current ?: return@LaunchedEffect] ?: return@LaunchedEffect
        if (SystemClock.uptimeMillis() < manualUntil) return@LaunchedEffect
        val third = listState.layoutInfo.viewportSize.height / 3
        if (layouts[p] == null) listState.scrollToItem(p) // not laid out yet: bring it in first
        val layout = layouts[p]
        val lineTop = layout?.let { it.getLineTop(it.getLineForOffset(start)).toInt() } ?: 0
        listState.animateScrollToItem(p, (lineTop - third).coerceAtLeast(0))
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
