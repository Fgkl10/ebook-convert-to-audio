package app.ebookaudio

import app.ebookaudio.convert.SampleStore
import app.ebookaudio.ui.Format
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

/** AND-15: voice samples played on the phone are kept, replaced whole, and deleted from Settings (A-023). */
class SampleStoreTest {
    @get:Rule val tmp = TemporaryFolder()

    @Test
    fun keepsReplacesAndClears() {
        val store = SampleStore(tmp.root.resolve("voice-samples"))
        assertNull(store.get("af_heart"))
        assertEquals(0, store.count())
        store.put("af_heart", byteArrayOf(1, 2, 3))
        store.put("zm_025", byteArrayOf(4))
        assertArrayEquals(byteArrayOf(1, 2, 3), store.get("af_heart")!!.readBytes())
        store.put("af_heart", byteArrayOf(9))  // made again on the PC: replaced
        assertArrayEquals(byteArrayOf(9), store.get("af_heart")!!.readBytes())
        assertEquals(2, store.count())
        assertEquals(2L, store.sizeBytes())
        assertEquals(listOf("af_heart.m4a", "zm_025.m4a"), tmp.root.resolve("voice-samples").list()!!.sorted())  // no .tmp left
        store.clear()
        assertEquals(0, store.count())
        assertNull(store.get("zm_025"))
    }

    @Test
    fun sizeInSettings() {
        assertEquals("0.0 KB", Format.smallSize(0).replace(',', '.'))
        assertEquals("45.3 KB", Format.smallSize(45_300).replace(',', '.'))
        assertEquals("6.1 MB", Format.smallSize(6_100_000).replace(',', '.'))
    }

    @Test
    fun refusesIdsThatAreNotFileNames() {
        val store = SampleStore(tmp.root)
        listOf("../x", "a/b", ".hidden", "", "a\\b").forEach { assertNull(it, store.put(it, byteArrayOf(1))) }
        assertEquals(0, store.count())
    }
}
