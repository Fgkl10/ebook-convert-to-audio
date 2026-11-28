package app.ebookaudio.ui

/**
 * The app's language choice in Settings (A-019). [tag] is what goes to
 * `AppCompatDelegate.setApplicationLocales`; an empty tag means "follow the phone".
 */
enum class AppLanguage(val tag: String) {
    SYSTEM(""),
    ENGLISH("en"),
    SIMPLIFIED("zh-Hans"),
    TRADITIONAL("zh-Hant");

    companion object {
        /**
         * The choice behind the app's current locale list ("" when none is set). The system's own per-app
         * setting may store a region instead of a script, so zh-TW / zh-HK / zh-MO count as Traditional and any
         * other Chinese as Simplified. A language the app doesn't have means the phone's language.
         */
        fun fromTags(tags: String): AppLanguage {
            val first = tags.split(',').first().trim().replace('_', '-').lowercase()
            if (first.isEmpty()) return SYSTEM
            val parts = first.split('-')
            return when (parts[0]) {
                "en" -> ENGLISH
                "zh" -> if (parts.drop(1).any { it in setOf("hant", "tw", "hk", "mo") }) TRADITIONAL else SIMPLIFIED
                else -> SYSTEM
            }
        }
    }
}
