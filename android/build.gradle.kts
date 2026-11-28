// Plugins are declared here once (apply false) so they share one classloader: the Kotlin plugins below raise the
// Kotlin version that AGP's built-in Kotlin support uses (A-002).
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
}
