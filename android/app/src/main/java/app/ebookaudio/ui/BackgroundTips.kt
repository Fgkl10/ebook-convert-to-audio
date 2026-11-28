package app.ebookaudio.ui

import androidx.annotation.StringRes
import app.ebookaudio.R

/**
 * Which phone maker's battery settings to explain on the Settings screen (A-018). Many Android skins stop background
 * apps on their own; each hides the switch somewhere else. Pure, unit-tested in BackgroundTipsTest.
 */
enum class Vendor(@param:StringRes val steps: Int) {
    XIAOMI(R.string.bg_steps_xiaomi),   // HyperOS, MIUI (Xiaomi, Redmi, POCO)
    HUAWEI(R.string.bg_steps_huawei),   // HarmonyOS, EMUI, MagicOS (Huawei, Honor)
    SAMSUNG(R.string.bg_steps_samsung), // One UI
    OPPO(R.string.bg_steps_oppo),       // ColorOS, OxygenOS, realme UI (OPPO, OnePlus, realme)
    VIVO(R.string.bg_steps_vivo),       // OriginOS, Funtouch OS (vivo, iQOO)
    OTHER(R.string.bg_steps_other),     // stock Android, Pixel, Motorola, Nokia, …
}

object BackgroundTips {
    private val BY_NAME = mapOf(
        "xiaomi" to Vendor.XIAOMI, "redmi" to Vendor.XIAOMI, "poco" to Vendor.XIAOMI,
        "huawei" to Vendor.HUAWEI, "honor" to Vendor.HUAWEI,
        "samsung" to Vendor.SAMSUNG,
        "oppo" to Vendor.OPPO, "oneplus" to Vendor.OPPO, "realme" to Vendor.OPPO,
        "vivo" to Vendor.VIVO, "iqoo" to Vendor.VIVO,
    )

    /** The vendor from Build.MANUFACTURER, else Build.BRAND (some phones report only one of them usefully). */
    fun vendorOf(manufacturer: String?, brand: String? = null): Vendor =
        listOfNotNull(manufacturer, brand).firstNotNullOfOrNull { BY_NAME[it.trim().lowercase()] } ?: Vendor.OTHER
}
