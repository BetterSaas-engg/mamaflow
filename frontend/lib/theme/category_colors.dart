import 'package:flutter/material.dart';

/// Per-category accent color + icon for family items, driven by the free-form
/// `eventType` string from extraction. Known families get a curated warm color;
/// anything unknown gets a stable, non-clashing color picked deterministically
/// from a warm palette by hash — so a novel type always looks intentional.
///
/// FIREWALL note: this maps only the *type label* to a color for display. It
/// never reads or leaves the device with any content.

const Color _rose = Color(0xFFE5737B); // medical / health
const Color _green = Color(0xFF5FA97E); // sports
const Color _blue = Color(0xFF5B8DEF); // school
const Color _amber = Color(0xFFF2A65A); // birthday / party
const Color _lavender = Color(0xFF9B8AC4); // default / other

/// Warm fallback palette for unrecognized types (stable by hash).
const List<Color> _fallback = [
  Color(0xFFE5737B), Color(0xFF5FA97E), Color(0xFF5B8DEF), Color(0xFFF2A65A),
  Color(0xFF9B8AC4), Color(0xFFE08D5B), Color(0xFF4FA89B), Color(0xFFC96B84),
];

String _norm(String? s) => (s ?? '').trim().toLowerCase();

bool _hasAny(String s, List<String> keys) => keys.any(s.contains);

/// Accent color for an item's category. `eventType` may be null (actions) or a
/// type outside the known set — both resolve to a stable color.
Color categoryColor(String? eventType) {
  final t = _norm(eventType);
  if (t.isEmpty) return _lavender;
  if (_hasAny(t, ['medical', 'health', 'doctor', 'dentist', 'appointment'])) {
    return _rose;
  }
  if (_hasAny(t, ['sport', 'soccer', 'practice', 'game', 'swim'])) return _green;
  if (_hasAny(t, ['school', 'class', 'homework', 'exam'])) return _blue;
  if (_hasAny(t, ['birthday', 'party', 'social'])) return _amber;
  if (t == 'other') return _lavender;
  // Unknown type: deterministic, stable pick (never clashes run-to-run).
  return _fallback[t.hashCode.abs() % _fallback.length];
}

/// Leading icon for an item's category. Actions (no eventType) use the
/// check-circle icon, matching the pre-redesign semantics.
IconData categoryIcon(String? eventType) {
  final t = _norm(eventType);
  if (t.isEmpty) return Icons.check_circle_outline;
  if (_hasAny(t, ['medical', 'health', 'doctor', 'dentist', 'appointment'])) {
    return Icons.medical_services_outlined;
  }
  if (_hasAny(t, ['sport', 'soccer', 'practice', 'game', 'swim'])) {
    return Icons.sports_soccer;
  }
  if (_hasAny(t, ['school', 'class', 'homework', 'exam'])) {
    return Icons.school_outlined;
  }
  if (_hasAny(t, ['birthday', 'party', 'social'])) return Icons.cake_outlined;
  return Icons.event_outlined;
}
