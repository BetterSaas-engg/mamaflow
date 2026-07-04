import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../items/item.dart';
import '../items/items_controller.dart';

/// Opens a URL in an external app; returns whether it launched. Injectable so
/// widget tests don't hit the platform channel.
typedef UrlOpener = Future<bool> Function(String url);

/// Only https links are launchable — defense-in-depth so a non-https or
/// custom-scheme URL can never be handed to the OS launcher, regardless of
/// where the link came from. Today the only caller passes the server-stamped
/// Gmail https link.
bool isLaunchableUrl(String url) => Uri.tryParse(url)?.scheme == 'https';

Future<bool> _defaultOpener(String url) {
  if (!isLaunchableUrl(url)) return Future.value(false);
  return launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
}

/// Full detail for one item: every populated field + an "Open source email"
/// action (Gmail deep link) + mark done/dismiss.
class ItemDetailScreen extends ConsumerWidget {
  const ItemDetailScreen({super.key, required this.item, UrlOpener? opener})
      : opener = opener ?? _defaultOpener;

  final Item item;
  final UrlOpener opener;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final rows = <(String, String?)>[
      ('When', [item.date, item.time].whereType<String>().join(' ')),
      ('Location', item.location),
      ('Child', item.childName),
      ('Type', item.eventType),
      ('To do', item.actionRequired),
      ('From', item.sourceSender),
      ('Status', item.status),
    ];
    final link = item.sourceEmailLink;

    return Scaffold(
      appBar: AppBar(title: Text(item.title)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          for (final (label, value) in rows)
            if (value != null && value.isNotEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(width: 96, child: Text(label,
                        style: const TextStyle(color: Colors.grey))),
                    Expanded(child: Text(value)),
                  ],
                ),
              ),
          const SizedBox(height: 24),
          if (link != null)
            FilledButton.icon(
              icon: const Icon(Icons.mail_outline),
              label: const Text('Open source email'),
              onPressed: () async {
                final ok = await opener(link);
                if (!ok && context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Could not open the email.')),
                  );
                }
              },
            ),
          if (item.status == 'open') ...[
            const SizedBox(height: 8),
            OverflowBar(
              children: [
                TextButton(
                  onPressed: () {
                    ref.read(itemsProvider.notifier).setStatus(item.id, 'done');
                    Navigator.of(context).pop();
                  },
                  child: const Text('Mark done'),
                ),
                TextButton(
                  onPressed: () {
                    ref.read(itemsProvider.notifier).setStatus(item.id, 'dismissed');
                    Navigator.of(context).pop();
                  },
                  child: const Text('Dismiss'),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
