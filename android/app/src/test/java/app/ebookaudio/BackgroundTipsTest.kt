package app.ebookaudio

import app.ebookaudio.ui.BackgroundTips
import app.ebookaudio.ui.Vendor
import org.junit.Assert.assertEquals
import org.junit.Test

/** AND-12: the Settings screen picks the battery steps for the phone's maker (A-018). */
class BackgroundTipsTest {
    @Test
    fun manufacturers() {
        assertEquals(Vendor.XIAOMI, BackgroundTips.vendorOf("Xiaomi"))
        assertEquals(Vendor.XIAOMI, BackgroundTips.vendorOf("Redmi"))
        assertEquals(Vendor.XIAOMI, BackgroundTips.vendorOf("POCO"))
        assertEquals(Vendor.HUAWEI, BackgroundTips.vendorOf("HUAWEI"))
        assertEquals(Vendor.HUAWEI, BackgroundTips.vendorOf("HONOR"))
        assertEquals(Vendor.SAMSUNG, BackgroundTips.vendorOf("samsung"))
        assertEquals(Vendor.OPPO, BackgroundTips.vendorOf("OnePlus"))
        assertEquals(Vendor.OPPO, BackgroundTips.vendorOf("realme"))
        assertEquals(Vendor.VIVO, BackgroundTips.vendorOf("vivo"))
        assertEquals(Vendor.VIVO, BackgroundTips.vendorOf(" iQOO "))
    }

    @Test
    fun brandWhenTheManufacturerIsUnknown() {
        assertEquals(Vendor.XIAOMI, BackgroundTips.vendorOf("Unknown", "Redmi"))
        assertEquals(Vendor.SAMSUNG, BackgroundTips.vendorOf(null, "samsung"))
    }

    @Test
    fun othersGetTheGenericSteps() {
        assertEquals(Vendor.OTHER, BackgroundTips.vendorOf("Google", "google"))
        assertEquals(Vendor.OTHER, BackgroundTips.vendorOf("motorola"))
        assertEquals(Vendor.OTHER, BackgroundTips.vendorOf(null, null))
        assertEquals(Vendor.OTHER, BackgroundTips.vendorOf(""))
    }
}
