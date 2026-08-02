import java.io.File
import java.util.regex.Pattern

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// خواندن آدرس سرور از strings.xml تا فقط یک‌جا تنظیم شود
fun readAppBaseUrl(): String {
    val stringsFile = File(projectDir, "src/main/res/values/strings.xml")
    if (!stringsFile.exists()) return "https://example.com/app"
    val content = stringsFile.readText()
    val m = Pattern.compile("<string name=\"app_base_url\">(.*?)</string>").matcher(content)
    return if (m.find()) m.group(1).trim() else "https://example.com/app"
}

val appBaseUrl = readAppBaseUrl()

android {
    namespace = "com.narin.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.narin.app"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"

        // آدرس سرور به BuildConfig راه پیدا می‌کند (MainActivity از این استفاده می‌کند)
        buildConfigField("String", "APP_BASE_URL", "\"$appBaseUrl\"")
    }

    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
}
