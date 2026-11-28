import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

/**
 * The release signing key (A-020). GitHub Actions passes it in environment variables; on the PC it is read from
 * the git-ignored `android/keystore/release.properties`. Without either, builds use the usual debug key.
 */
data class SigningKey(val file: File, val storePassword: String, val alias: String, val keyPassword: String)

val signingKey: SigningKey? = System.getenv("ANDROID_KEYSTORE_PATH")?.takeIf { it.isNotBlank() }?.let { path ->
    SigningKey(
        file(path),
        System.getenv("ANDROID_KEYSTORE_PASSWORD").orEmpty(),
        System.getenv("ANDROID_KEY_ALIAS").orEmpty(),
        System.getenv("ANDROID_KEY_PASSWORD").orEmpty(),
    )
} ?: rootProject.file("keystore/release.properties").takeIf { it.isFile }?.let { f ->
    val p = Properties().apply { f.inputStream().use { load(it) } }
    SigningKey(
        rootProject.file("keystore/" + p.getProperty("storeFile")),
        p.getProperty("storePassword"),
        p.getProperty("keyAlias"),
        p.getProperty("keyPassword"),
    )
}

/** `git rev-list --count HEAD`; 1 outside a git checkout (or a shallow one with one commit). */
val commitCount: Int = runCatching {
    providers.exec {
        commandLine("git", "rev-list", "--count", "HEAD")
        isIgnoreExitValue = true
    }.standardOutput.asText.get().trim().toInt()
}.getOrDefault(1).coerceAtLeast(1)

android {
    namespace = "app.ebookaudio"
    // The newest AndroidX libraries need the Android 17.2 SDK (API 37.2) to compile against. targetSdk 37 only
    // changes behavior on Android 16+; the app runs on any Android phone from Android 8 (minSdk 26).
    compileSdk {
        version = release(37) { minorApiLevel = 2 }
    }

    defaultConfig {
        applicationId = "app.ebookaudio"
        minSdk = 26
        targetSdk = 37
        // The number of commits (A-020), on the PC and on GitHub alike, so a newer build always installs over an
        // older one from either place. GitHub Actions sets the version name from the tag (v0.5.0 -> 0.5.0).
        versionCode = commitCount
        versionName = System.getenv("VERSION_NAME")?.takeIf { it.isNotBlank() } ?: "0.5.0"
    }

    signingConfigs {
        if (signingKey != null) {
            create("release") {
                storeFile = signingKey.file
                storePassword = signingKey.storePassword
                keyAlias = signingKey.alias
                keyPassword = signingKey.keyPassword
            }
        }
    }

    buildTypes {
        // Debug builds use the same key when it is there, so a PC build and a GitHub APK install over each other.
        val key = signingConfigs.findByName("release")
        debug {
            if (key != null) signingConfig = key
        }
        release {
            isMinifyEnabled = false
            if (key != null) signingConfig = key
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        compose = true
    }
    // English, Simplified and Traditional Chinese (A-017): the generated locale config lists them for the per-app
    // language setting on Android 13+; res/resources.properties names English as the default.
    androidResources {
        generateLocaleConfig = true
    }
    testOptions {
        unitTests.isReturnDefaultValues = true
    }
    lint {
        abortOnError = true
        warningsAsErrors = false
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.appcompat) // in-app language choice on Android 8–12 (A-019)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.service)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.compose.material.icons)
    debugImplementation(libs.compose.ui.tooling)
    implementation(libs.media3.exoplayer)
    implementation(libs.media3.session)
    implementation(libs.datastore.preferences)
    implementation(libs.work.runtime)
    implementation(libs.camerax.camera2)
    implementation(libs.camerax.lifecycle)
    implementation(libs.camerax.view)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.okhttp)
    implementation(libs.coil.compose)
    implementation(libs.coil.network.okhttp)
    implementation(libs.zxing.core)

    testImplementation(libs.junit)
    testImplementation(libs.okhttp.mockwebserver)
    testImplementation(libs.kotlinx.coroutines.test)
}
