import '../core/api_client.dart';
import 'item.dart';

/// Reads + updates the authenticated user's items via the API. The JWT is
/// attached by ApiClient's interceptor; this service is user-agnostic.
class ItemsService {
  ItemsService(this._api);

  final ApiClient _api;

  Future<List<Item>> list({String? from, String? to, String? type, String? status}) async {
    final query = <String, dynamic>{
      'from': ?from,
      'to': ?to,
      'type': ?type,
      'status': ?status,
    };
    final resp = await _api.getJson(
      '/api/v1/items',
      query: query.isEmpty ? null : query,
    );
    final raw = (resp['items'] as List?) ?? const [];
    return raw.map(Item.tryParse).whereType<Item>().toList(growable: false);
  }

  /// status: "done" | "dismissed".
  Future<Item> updateStatus(String id, String status) async {
    final resp = await _api.patchJson('/api/v1/items/$id', {'status': status});
    return Item.fromJson(resp);
  }
}
