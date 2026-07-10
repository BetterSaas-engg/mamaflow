import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/items/item.dart';
import 'package:mamaflow/items/items_controller.dart';
import 'package:mamaflow/items/items_service.dart';
import 'package:mamaflow/ui/item_detail_screen.dart';
import 'package:mocktail/mocktail.dart';

class _MockService extends Mock implements ItemsService {}

Item _item({String? link}) => Item(
      id: '1', itemType: 'event', status: 'open',
      eventTitle: 'Dentist', date: '2026-07-08', time: '10:00 AM',
      location: 'Grandview', childName: 'Emma', eventType: 'medical',
      sourceEmailLink: link,
    );

Widget _host(Item item, {UrlOpener? opener}) => ProviderScope(
      child: MaterialApp(home: ItemDetailScreen(item: item, opener: opener)),
    );

/// Host with a base route so pop() behavior is observable, and with the items
/// service mocked so status mutations are controllable.
Widget _navHost(Item item, ItemsService svc) => ProviderScope(
      overrides: [itemsServiceProvider.overrideWithValue(svc)],
      child: MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => ItemDetailScreen(item: item)),
              ),
              child: const Text('open-detail'),
            ),
          ),
        ),
      ),
    );

void main() {
  group('isLaunchableUrl', () {
    test('accepts https URLs', () {
      expect(isLaunchableUrl('https://mail.google.com/x'), true);
    });

    test('rejects http URLs', () {
      expect(isLaunchableUrl('http://mail.google.com/x'), false);
    });

    test('rejects javascript: scheme', () {
      expect(isLaunchableUrl('javascript:alert(1)'), false);
    });

    test('rejects malformed URLs', () {
      expect(isLaunchableUrl('not a url'), false);
    });
  });

  testWidgets('shows item fields', (tester) async {
    await tester.pumpWidget(_host(_item(link: 'https://mail.google.com/x')));
    expect(find.text('Dentist'), findsOneWidget);
    expect(find.text('Grandview'), findsOneWidget);
    expect(find.text('Emma'), findsOneWidget);
  });

  testWidgets('Open source email launches the link', (tester) async {
    String? opened;
    await tester.pumpWidget(_host(_item(link: 'https://mail.google.com/x'),
        opener: (url) async { opened = url; return true; }));
    await tester.tap(find.text('Open source email'));
    await tester.pump();
    expect(opened, 'https://mail.google.com/x');
  });

  testWidgets('hides the button when there is no source link', (tester) async {
    await tester.pumpWidget(_host(_item(link: null)));
    expect(find.text('Open source email'), findsNothing);
  });

  testWidgets('Mark done pops back only after the update succeeds',
      (tester) async {
    final svc = _MockService();
    when(() => svc.list(status: any(named: 'status')))
        .thenAnswer((_) async => const <Item>[]);
    when(() => svc.updateStatus(any(), any())).thenAnswer(
        (_) async => const Item(id: '1', itemType: 'event', status: 'done'));

    await tester.pumpWidget(_navHost(_item(), svc));
    await tester.tap(find.text('open-detail'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Mark done'));
    await tester.pumpAndSettle();

    expect(find.text('open-detail'), findsOneWidget); // back on the base route
    expect(find.text('Dentist'), findsNothing);
  });

  testWidgets('a failed update keeps the screen open and shows an error',
      (tester) async {
    final svc = _MockService();
    when(() => svc.list(status: any(named: 'status')))
        .thenAnswer((_) async => const <Item>[]);
    when(() => svc.updateStatus(any(), any())).thenThrow(Exception('offline'));

    await tester.pumpWidget(_navHost(_item(), svc));
    await tester.tap(find.text('open-detail'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Mark done'));
    await tester.pumpAndSettle();

    expect(find.text('Dentist'), findsWidgets); // did NOT pop
    expect(find.text('Could not update the item.'), findsOneWidget);
  });
}
