# R8 keep rules for release builds (debug builds don't minify).
#
# Room instantiates database implementations by reflection
# (Class.forName(name + "_Impl")). WorkManager — pulled in transitively by
# google_mobile_ads — creates androidx.work.impl.WorkDatabase this way at
# process startup (androidx.startup.InitializationProvider). Without these
# keeps, R8 strips the generated _Impl class and the app crashes before the
# splash screen (reproduced 2026-07-26 on the first release APK).
-keep class * extends androidx.room.RoomDatabase { <init>(); }
-keep class androidx.work.impl.WorkDatabase_Impl { *; }
