import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import 'item.dart';
import 'items_service.dart';
import 'sync_service.dart';

final itemsServiceProvider =
    Provider<ItemsService>((ref) => ItemsService(ref.watch(apiClientProvider)));

final syncServiceProvider =
    Provider<SyncService>((ref) => SyncService(ref.watch(apiClientProvider)));

/// Loads the user's items and exposes mutations. Fetches open items by default;
/// [showCompleted] flips to done items ("Show completed" toggle on the home).
class ItemsController extends AsyncNotifier<List<Item>> {
  String _status = 'open';

  String get statusFilter => _status;

  @override
  Future<List<Item>> build() => ref.read(itemsServiceProvider).list(status: _status);

  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(
        () => ref.read(itemsServiceProvider).list(status: _status));
  }

  /// Toggle between open items (false) and completed/done items (true).
  Future<void> showCompleted(bool completed) async {
    _status = completed ? 'done' : 'open';
    await refresh();
  }

  Future<void> setStatus(String id, String status) async {
    await ref.read(itemsServiceProvider).updateStatus(id, status);
    await refresh();
  }
}

final itemsProvider =
    AsyncNotifierProvider<ItemsController, List<Item>>(ItemsController.new);
