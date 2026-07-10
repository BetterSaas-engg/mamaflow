/// A family item (event or action) as returned by GET /api/v1/items.
/// Mirrors the backend ItemRead schema; `date`/`time` are strings (the backend
/// stores them as-is from extraction).
class Item {
  const Item({
    required this.id,
    required this.itemType,
    required this.status,
    this.eventTitle,
    this.actionRequired,
    this.date,
    this.time,
    this.location,
    this.childName,
    this.eventType,
    this.sourceSender,
    this.sourceEmailLink,
  });

  final String id;
  final String itemType; // "event" | "action"
  final String status; // "open" | "done" | "dismissed"
  final String? eventTitle;
  final String? actionRequired;
  final String? date;
  final String? time;
  final String? location;
  final String? childName;
  final String? eventType;
  final String? sourceSender;
  final String? sourceEmailLink;

  bool get isEvent => itemType == 'event';

  /// Best display label for a list row.
  String get title =>
      eventTitle ?? actionRequired ?? (isEvent ? '(untitled event)' : '(untitled action)');

  /// Defensive variant for list parsing: one malformed row (partial write,
  /// migration hiccup) returns null instead of taking down the whole list —
  /// callers skip nulls.
  static Item? tryParse(Object? json) {
    if (json is! Map) return null;
    try {
      return Item.fromJson(Map<String, dynamic>.from(json));
    } catch (_) {
      return null;
    }
  }

  factory Item.fromJson(Map<String, dynamic> json) => Item(
        id: json['id'] as String,
        itemType: json['item_type'] as String,
        status: json['status'] as String,
        eventTitle: json['event_title'] as String?,
        actionRequired: json['action_required'] as String?,
        date: json['date'] as String?,
        time: json['time'] as String?,
        location: json['location'] as String?,
        childName: json['child_name'] as String?,
        eventType: json['event_type'] as String?,
        sourceSender: json['source_sender'] as String?,
        sourceEmailLink: json['source_email_link'] as String?,
      );
}
