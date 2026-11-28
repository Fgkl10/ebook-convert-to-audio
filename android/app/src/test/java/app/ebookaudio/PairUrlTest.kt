package app.ebookaudio

import app.ebookaudio.pairing.Pairing
import app.ebookaudio.pairing.PairUrl
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** AND-02: the QR code's link (desktop/server/network.py pair_url). */
class PairUrlTest {
    private val token = "AbC-123_xyzAbC-123_xyzAbC-123_xy"

    @Test
    fun readsTheQrCodeLink() {
        assertEquals(Pairing("http://10.251.93.75:8000", token), PairUrl.parse("http://10.251.93.75:8000/#token=$token"))
        assertEquals(Pairing("http://my-pc.example:9000", token), PairUrl.parse("  http://my-pc.example:9000#token=$token\n"))
        assertEquals(Pairing("http://[fe80::1]:8000", token), PairUrl.parse("http://[fe80::1]:8000/#token=$token"))
        assertEquals(Pairing("http://pc", token), PairUrl.parse("http://pc/#token=$token"))
        assertEquals(Pairing("https://pc:8443", token), PairUrl.parse("HTTPS://pc:8443/#token=$token"))
    }

    @Test
    fun refusesAnythingElse() {
        listOf(
            "",
            "hello",
            "http://10.0.0.1:8000/",                         // no token
            "http://10.0.0.1:8000/#token=",                  // empty token
            "http://10.0.0.1:8000/#token=short",             // too short to be ours
            "http://10.0.0.1:8000/#token=$token!",           // not url-safe base64
            "http://10.0.0.1:8000/#other=$token",
            "ftp://10.0.0.1/#token=$token",
            "http://10.0.0.1:8000/books#token=$token",       // a path
            "http://10.0.0.1:8000/?x=1#token=$token",        // a query
            "http://user@10.0.0.1:8000/#token=$token",       // user info
            "10.0.0.1:8000/#token=$token",                   // no scheme
        ).forEach { assertNull(it, PairUrl.parse(it)) }
    }
}
