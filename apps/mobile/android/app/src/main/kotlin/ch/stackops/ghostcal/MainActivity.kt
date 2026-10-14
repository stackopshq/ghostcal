package ch.stackops.ghostcal

import io.flutter.embedding.android.FlutterFragmentActivity

// A FragmentActivity, not a plain Activity: local_auth and the biometric-bound
// flutter_secure_storage show BiometricPrompt, which needs one.
class MainActivity : FlutterFragmentActivity()
