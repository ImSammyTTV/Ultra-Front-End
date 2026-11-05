import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// One version for every platform: the one in server.py
val appVersion: String = Regex("""^VERSION = "([0-9.]+)"""", RegexOption.MULTILINE)
    .find(rootProject.file("../server.py").readText())!!.groupValues[1]
val parts = appVersion.split(".").map { it.toInt() } + listOf(0, 0, 0)

// The release key lives outside the repo (see android/README.md); without it the build is signed with the debug key
val keyProps = Properties().apply {
    val f = file(System.getenv("UFE_ANDROID_KEY") ?: "${System.getProperty("user.home")}/.ultrafrontend-signing/android-key.properties")
    if (f.isFile) f.inputStream().use { load(it) }
}

android {
    namespace = "com.imsammyttv.ultrafrontend"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.imsammyttv.ultrafrontend"
        minSdk = 26
        targetSdk = 35
        versionCode = parts[0] * 10000 + parts[1] * 100 + parts[2]
        versionName = appVersion
    }
    signingConfigs {
        if (keyProps.getProperty("storeFile") != null) create("release") {
            storeFile = file(keyProps.getProperty("storeFile"))
            storePassword = keyProps.getProperty("storePassword")
            keyAlias = keyProps.getProperty("keyAlias")
            keyPassword = keyProps.getProperty("keyPassword")
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("release") ?: signingConfigs.getByName("debug")
        }
    }
    sourceSets["main"].assets.srcDirs("src/main/assets", "../../app")  // the same page as Windows and Mac
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
}
