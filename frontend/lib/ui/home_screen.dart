import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/session_controller.dart';
import '../items/item.dart';
import '../items/items_controller.dart';

/// The signed-in home: the user's extracted events + actions, with mark
/// done/dismiss and pull-to-refresh. Reads GET /api/v1/items.
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final items = ref.watch(itemsProvider);
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        icon: const Icon(Icons.sync),
        label: const Text('Sync inbox'),
        onPressed: () => _sync(context, ref),
      ),
      appBar: AppBar(
        title: const Text('Mamaflow'),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.read(itemsProvider.notifier).refresh(),
          ),
          IconButton(
            tooltip: 'Sign out',
            icon: const Icon(Icons.logout),
            onPressed: () => ref.read(sessionProvider.notifier).signOut(),
          ),
        ],
      ),
      body: items.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => _Centered(
          message: 'Could not load items.',
          actionLabel: 'Retry',
          onAction: () => ref.read(itemsProvider.notifier).refresh(),
        ),
        data: (list) => RefreshIndicator(
          onRefresh: () => ref.read(itemsProvider.notifier).refresh(),
          child: list.isEmpty
              ? _emptyList()
              : ListView.separated(
                  itemCount: list.length,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (context, i) => _ItemTile(item: list[i]),
                ),
        ),
      ),
    );
  }

  Future<void> _sync(BuildContext context, WidgetRef ref) async {
    final messenger = ScaffoldMessenger.of(context);
    messenger.showSnackBar(const SnackBar(content: Text('Syncing inbox…')));
    try {
      final created = await ref.read(syncServiceProvider).run();
      await ref.read(itemsProvider.notifier).refresh();
      messenger.showSnackBar(SnackBar(content: Text('Synced — $created new item(s)')));
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Sync failed. Try again.')));
    }
  }

  // A scrollable so pull-to-refresh works even when there are no items.
  Widget _emptyList() => ListView(
        children: const [
          SizedBox(height: 120),
          Center(child: Text('No items yet.\nPull down to refresh.', textAlign: TextAlign.center)),
        ],
      );
}

class _ItemTile extends ConsumerWidget {
  const _ItemTile({required this.item});
  final Item item;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final done = item.status == 'done';
    final dismissed = item.status == 'dismissed';
    final closed = done || dismissed;

    final subtitleParts = <String>[
      if (item.date != null) [item.date, item.time].whereType<String>().join(' '),
      if (item.eventType != null) item.eventType!,
      if (item.childName != null) item.childName!,
    ].where((s) => s.isNotEmpty).toList();

    return ListTile(
      leading: Icon(item.isEvent ? Icons.event : Icons.check_circle_outline),
      title: Text(
        item.title,
        style: closed
            ? const TextStyle(decoration: TextDecoration.lineThrough, color: Colors.grey)
            : null,
      ),
      subtitle: subtitleParts.isEmpty ? null : Text(subtitleParts.join('  ·  ')),
      trailing: closed
          ? Chip(label: Text(item.status))
          : PopupMenuButton<String>(
              onSelected: (status) =>
                  ref.read(itemsProvider.notifier).setStatus(item.id, status),
              itemBuilder: (context) => const [
                PopupMenuItem(value: 'done', child: Text('Mark done')),
                PopupMenuItem(value: 'dismissed', child: Text('Dismiss')),
              ],
            ),
    );
  }
}

class _Centered extends StatelessWidget {
  const _Centered({required this.message, required this.actionLabel, required this.onAction});
  final String message;
  final String actionLabel;
  final VoidCallback onAction;

  @override
  Widget build(BuildContext context) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(message),
            const SizedBox(height: 12),
            FilledButton(onPressed: onAction, child: Text(actionLabel)),
          ],
        ),
      );
}
