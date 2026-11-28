package app.ebookaudio.pairing

import java.net.URI
import java.net.URISyntaxException
import java.net.URLDecoder

/** A paired PC: where it is and the token that lets this phone in (D-037). */
data class Pairing(val baseUrl: String, val token: String, val pcName: String = "")

/**
 * Reads the link in the PC's QR code: `http://<address>:<port>/#token=<token>` (desktop/server/network.py
 * pair_url). The address may be a host name, an IPv4 address or a bracketed IPv6 address.
 */
object PairUrl {
    private val TOKEN = Regex("[A-Za-z0-9_-]{16,128}")

    fun parse(text: String): Pairing? {
        val uri = try {
            URI(text.trim())
        } catch (e: URISyntaxException) {
            return null
        }
        val scheme = uri.scheme?.lowercase() ?: return null
        if (scheme != "http" && scheme != "https") return null
        val host = uri.host ?: return null // an IPv6 host comes back in brackets
        if (uri.rawUserInfo != null || uri.rawQuery != null) return null
        if ((uri.rawPath ?: "") !in setOf("", "/")) return null
        val fragment = uri.rawFragment ?: return null
        if (!fragment.startsWith("token=")) return null
        val token = URLDecoder.decode(fragment.removePrefix("token="), "UTF-8")
        if (!TOKEN.matches(token)) return null
        val port = if (uri.port == -1) "" else ":${uri.port}"
        return Pairing("$scheme://$host$port", token)
    }
}
