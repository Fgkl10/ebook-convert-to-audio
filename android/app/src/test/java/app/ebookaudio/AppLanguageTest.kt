package app.ebookaudio

import app.ebookaudio.ui.AppLanguage
import org.junit.Assert.assertEquals
import org.junit.Test

/** AND-14: the Settings language choice reads back from the app's locale list (A-019). */
class AppLanguageTest {
    @Test
    fun readsTheChoiceBack() {
        for (lang in AppLanguage.entries) assertEquals(lang, AppLanguage.fromTags(lang.tag))
    }

    @Test
    fun regionsAndOtherFormsMapToAScript() {
        assertEquals(AppLanguage.SIMPLIFIED, AppLanguage.fromTags("zh-CN"))
        assertEquals(AppLanguage.SIMPLIFIED, AppLanguage.fromTags("zh"))
        assertEquals(AppLanguage.SIMPLIFIED, AppLanguage.fromTags("zh-Hans-SG"))
        assertEquals(AppLanguage.TRADITIONAL, AppLanguage.fromTags("zh-TW"))
        assertEquals(AppLanguage.TRADITIONAL, AppLanguage.fromTags("zh_HK"))
        assertEquals(AppLanguage.TRADITIONAL, AppLanguage.fromTags("zh-Hant-MO"))
        assertEquals(AppLanguage.ENGLISH, AppLanguage.fromTags("en-US,zh-Hans"))
    }

    @Test
    fun unknownOrEmptyMeansThePhonesLanguage() {
        assertEquals(AppLanguage.SYSTEM, AppLanguage.fromTags(""))
        assertEquals(AppLanguage.SYSTEM, AppLanguage.fromTags(" "))
        assertEquals(AppLanguage.SYSTEM, AppLanguage.fromTags("fr-FR"))
    }
}
