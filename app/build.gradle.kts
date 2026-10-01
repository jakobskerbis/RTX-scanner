plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "si.jakob.rtxskener"
    compileSdk = 34

    defaultConfig {
        applicationId = "si.jakob.rtxskener"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    signingConfigs {
        create("rtx") {
            storeFile = file("rtx.jks")
            storePassword = "rtxskener"
            keyAlias = "rtx"
            keyPassword = "rtxskener"
        }
    }

    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("rtx")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }

    lint {
        abortOnError = false
        checkReleaseBuilds = false
    }
}

dependencies {
    implementation("org.jsoup:jsoup:1.17.2")
}
