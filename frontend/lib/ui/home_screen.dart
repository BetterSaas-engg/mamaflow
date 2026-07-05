import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../items/filters.dart';
import '../items/grouping.dart';
import '../items/item.dart';
import '../items/items_controller.dart';
import '../items/sync_service.dart';
import 'item_detail_screen.dart';
import 'settings_screen.dart';

/// The signed-in home: the user's items as a grouped agenda (Overdue / Today /
/// This week / Later / To-do), filterable by child/type, with a "Show
/// completed" toggle. Rows tap through to [ItemDetailScreen].
class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});
  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  String? _child; // single-select chip: one of child/type is set at a time
  String? _type;
  bool _completed = false;
  SyncStatus? _syncStatus; // non-null while a sync is in flight

  @override
  Widget build(BuildContext context) {
    final items = ref.watch(itemsProvider);
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        icon: const Icon(Icons.sync),
        label: const Text('Sync inbox'),
        onPressed: () => _sync(context),
      ),
      appBar: AppBar(
        title: const Text('Mamaflow'),
        actions: [
          IconButton(
            tooltip: _completed ? 'Show open' : 'Show completed',
            icon: Icon(_completed ? Icons.inbox : Icons.done_all),
            onPressed: () {
              setState(() => _completed = !_completed);
              ref.read(itemsProvider.notifier).showCompleted(_completed);
            },
          ),
          IconButton(
            tooltip: 'Settings',
            icon: const Icon(Icons.settings),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const SettingsScreen()),
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          if (_syncStatus != null) _SyncProgressCard(status: _syncStatus!),
          Expanded(
            child: items.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => _Centered(
                message: 'Could not load items.',
                actionLabel: 'Retry',
                onAction: () => ref.read(itemsProvider.notifier).refresh(),
              ),
              data: (list) => RefreshIndicator(
                onRefresh: () => ref.read(itemsProvider.notifier).refresh(),
                child: _body(list),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _body(List<Item> all) {
    final filtered = applyChipFilter(all, child: _child, type: _type);
    final sections = groupItems(filtered, DateTime.now());
    final children = childValues(all);
    final types = typeValues(all);

    return CustomScrollView(
      slivers: [
        if (children.isNotEmpty || types.isNotEmpty)
          SliverToBoxAdapter(child: _chips(children, types)),
        if (sections.isEmpty)
          const SliverFillRemaining(
            hasScrollBody: false,
            child: Center(child: Text('No items yet.\nPull down to refresh.',
                textAlign: TextAlign.center)),
          ),
        for (final section in sections) ...[
          SliverToBoxAdapter(child: _header(section.title)),
          SliverList.separated(
            itemCount: section.items.length,
            separatorBuilder: (_, _) => const Divider(height: 1),
            itemBuilder: (context, i) => _ItemTile(item: section.items[i]),
          ),
        ],
      ],
    );
  }

  Widget _chips(List<String> children, List<String> types) => SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Row(
          children: [
            FilterChip(
              label: const Text('All'),
              selected: _child == null && _type == null,
              onSelected: (_) => setState(() { _child = null; _type = null; }),
            ),
            for (final c in children) ...[
              const SizedBox(width: 6),
              FilterChip(
                label: Text(c),
                selected: _child == c,
                onSelected: (_) => setState(() { _child = c; _type = null; }),
              ),
            ],
            for (final t in types) ...[
              const SizedBox(width: 6),
              FilterChip(
                label: Text(t),
                selected: _type == t,
                onSelected: (_) => setState(() { _type = t; _child = null; }),
              ),
            ],
          ],
        ),
      );

  Widget _header(String title) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
        child: Text(title,
            style: const TextStyle(
                fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.5,
                color: Colors.grey)),
      );

  Future<void> _sync(BuildContext context) async {
    final messenger = ScaffoldMessenger.of(context);
    setState(() => _syncStatus = const SyncStatus(status: 'running'));
    try {
      await for (final s in ref.read(syncServiceProvider).run()) {
        if (s.status == 'failed') {
          throw SyncFailedException(s.error ?? 'Sync failed. Try again.');
        }
        setState(() => _syncStatus = s);
      }
      final created = _syncStatus?.itemsCreated ?? 0;
      await ref.read(itemsProvider.notifier).refresh();
      ref.invalidate(calendarItemsProvider);
      setState(() => _syncStatus = null);
      messenger.showSnackBar(SnackBar(content: Text('Synced — $created new item(s)')));
    } on SyncFailedException catch (e) {
      setState(() => _syncStatus = null);
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    } catch (_) {
      setState(() => _syncStatus = null);
      messenger.showSnackBar(const SnackBar(content: Text('Sync failed. Try again.')));
    }
  }
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
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => ItemDetailScreen(item: item)),
      ),
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

class _SyncProgressCard extends StatelessWidget {
  const _SyncProgressCard({required this.status});
  final SyncStatus status;

  @override
  Widget build(BuildContext context) {
    final total = status.toProcess;
    final done = status.processed;
    final value = (total != null && total > 0 && done != null) ? done / total : null;
    final line = total == null
        ? 'Syncing your inbox…'
        : 'Scanned ${status.messagesScanned ?? 0} · processed ${done ?? 0} / $total · ${status.itemsCreated ?? 0} items';
    return Card(
      margin: const EdgeInsets.all(12),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(line, style: const TextStyle(fontSize: 12)),
            const SizedBox(height: 8),
            LinearProgressIndicator(value: value),
          ],
        ),
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
