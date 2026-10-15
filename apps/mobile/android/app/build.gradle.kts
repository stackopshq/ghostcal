import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Release signing comes from `android/key.properties` (gitignored, with the keystore), see
// `android/key.properties.example`. Without it the release APK is left unsigned, so it cannot
// be installed: a build signed with the debug key must never be distributed by mistake.
val keystoreProperties = Properties().apply {
    val file = rootProject.file("key.properties")
    if (file.exists()) file.inputStream().use { load(it) }
}

android {
    namespace = "ch.stackops.ghostcal"
    // 37 et non `flutter.compileSdkVersion`, qui vaut 36 : `flutter_secure_storage` 11 —
    // celui qui scelle la phrase derrière le matériel — se compile contre 37 et refuse
    // que ses dépendants visent moins. Sans cela le paquet Android ne se construit plus
    // du tout, ce qui est passé inaperçu : la biométrie a été posée sans que personne ne
    // reconstruise pour Android.
    //
    // La version de compilation n'est pas le `minSdk`, qui reste à 24 comme le veut la
    // charte : compiler contre des API récentes n'engage pas l'appareil sur lequel on
    // s'installe.
    compileSdk = 37
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
        // flutter_local_notifications schedules with java.time, desugared for older Android.
        isCoreLibraryDesugaringEnabled = true
    }

    defaultConfig {
        applicationId = "ch.stackops.ghostcal"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (keystoreProperties.isNotEmpty()) {
            create("release") {
                storeFile = rootProject.file(keystoreProperties.getProperty("storeFile"))
                storePassword = keystoreProperties.getProperty("storePassword")
                keyAlias = keystoreProperties.getProperty("keyAlias")
                keyPassword = keystoreProperties.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.findByName("release")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")
}
