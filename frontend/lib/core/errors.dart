import 'package:dio/dio.dart';

/// Turn an exception into something worth showing a parent.
///
/// The backend's `detail` is the useful string — it distinguishes a wrong app
/// password from an over-cap plan from a mailbox already connected elsewhere.
/// Collapsing everything to "Something went wrong" throws that away, which is
/// why this exists in one place rather than being re-derived per screen.
String messageFor(Object error, {String fallback = 'Something went wrong. Try again.'}) {
  if (error is DioException) {
    final data = error.response?.data;
    // Guarded: `detail` is not always a String — FastAPI returns a LIST of
    // validation objects for a 422, and casting that blind threw inside the
    // error handler itself.
    if (data is Map && data['detail'] is String) return data['detail'] as String;
  }
  return fallback;
}

/// Whether the user simply backed out of a store purchase sheet.
///
/// A cancel is a deliberate act, not a failure — surfacing it as an error
/// reads as "your payment broke" when nothing broke at all.
bool isPurchaseCancelled(Object error) {
  final text = error.toString().toLowerCase();
  return text.contains('cancel') || text.contains('user_cancelled');
}
