import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/core/api_client.dart';
import 'package:mamaflow/items/items_service.dart';
import 'package:mocktail/mocktail.dart';

class _MockApi extends Mock implements ApiClient {}

void main() {
  setUpAll(() => registerFallbackValue(<String, dynamic>{}));

  test('list() parses items and forwards date/type filters', () async {
    final api = _MockApi();
    when(() => api.getJson(any(), query: any(named: 'query'))).thenAnswer((_) async => {
          'items': [
            {
              'id': 'i1',
              'item_type': 'event',
              'status': 'open',
              'event_title': 'Soccer',
              'date': '2026-06-20',
              'event_type': 'sports',
            }
          ]
        });
    final svc = ItemsService(api);

    final items = await svc.list(from: '2026-06-01', to: '2026-06-30', type: 'event');

    expect(items, hasLength(1));
    expect(items.first.id, 'i1');
    expect(items.first.eventTitle, 'Soccer');
    expect(items.first.date, '2026-06-20');
    expect(items.first.status, 'open');
    final captured =
        verify(() => api.getJson(captureAny(), query: captureAny(named: 'query'))).captured;
    expect(captured[0], '/api/v1/items');
    expect(captured[1], {'from': '2026-06-01', 'to': '2026-06-30', 'type': 'event'});
  });

  test('list() sends no query when unfiltered', () async {
    final api = _MockApi();
    when(() => api.getJson(any(), query: any(named: 'query')))
        .thenAnswer((_) async => {'items': <dynamic>[]});
    final svc = ItemsService(api);

    final items = await svc.list();

    expect(items, isEmpty);
    final captured =
        verify(() => api.getJson(captureAny(), query: captureAny(named: 'query'))).captured;
    expect(captured[1], isNull);
  });

  test('updateStatus() patches the item and returns the updated row', () async {
    final api = _MockApi();
    when(() => api.patchJson(any(), any())).thenAnswer((_) async =>
        {'id': 'i1', 'item_type': 'action', 'status': 'done', 'event_title': 'Register'});
    final svc = ItemsService(api);

    final item = await svc.updateStatus('i1', 'done');

    expect(item.status, 'done');
    final captured = verify(() => api.patchJson(captureAny(), captureAny())).captured;
    expect(captured[0], '/api/v1/items/i1');
    expect(captured[1], {'status': 'done'});
  });

  test('list() skips malformed rows instead of failing the whole list', () async {
    final api = _MockApi();
    when(() => api.getJson(any(), query: any(named: 'query'))).thenAnswer((_) async => {
          'items': [
            {'id': 'good', 'item_type': 'event', 'status': 'open'},
            {'id': 'bad-no-status', 'item_type': 'event'},
            {'id': null, 'item_type': 'event', 'status': 'open'},
            'not-a-map',
          ]
        });
    final svc = ItemsService(api);

    final items = await svc.list();

    expect(items.map((i) => i.id).toList(), ['good']);
  });

  test('list passes status as a query param', () async {
    final api = _MockApi();
    when(() => api.getJson(any(), query: any(named: 'query')))
        .thenAnswer((_) async => {'items': []});
    final svc = ItemsService(api);

    await svc.list(status: 'done');

    final captured = verify(() => api.getJson('/api/v1/items',
        query: captureAny(named: 'query'))).captured.single as Map;
    expect(captured['status'], 'done');
  });
}
