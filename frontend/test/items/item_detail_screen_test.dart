import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/items/item.dart';
import 'package:mamaflow/ui/item_detail_screen.dart';

Item _item({String? link}) => Item(
      id: '1', itemType: 'event', status: 'open',
      eventTitle: 'Dentist', date: '2026-07-08', time: '10:00 AM',
      location: 'Grandview', childName: 'Emma', eventType: 'medical',
      sourceEmailLink: link,
    );

Widget _host(Item item, {UrlOpener? opener}) => ProviderScope(
      child: MaterialApp(home: ItemDetailScreen(item: item, opener: opener)),
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
}
