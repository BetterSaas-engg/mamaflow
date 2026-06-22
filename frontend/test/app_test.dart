import 'package:flutter_test/flutter_test.dart';
import 'package:mamaflow/app.dart';

void main() {
  testWidgets('app boots to the Mamaflow home placeholder', (tester) async {
    await tester.pumpWidget(const MamaflowApp());
    await tester.pumpAndSettle();
    expect(find.text('Mamaflow'), findsOneWidget);
  });
}
