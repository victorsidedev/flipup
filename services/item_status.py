from collections import defaultdict

from models.item import Item


def collect_subtree_ids(root_ids: set[int], items: dict[int, Item]) -> set[int]:
    """Expand a set of item ids to include all their descendants within the same item map."""
    children = defaultdict(list)
    for item in items.values():
        if item.parent_item_id is not None:
            children[item.parent_item_id].append(item.id)

    result = set()
    pending = list(root_ids)
    while pending:
        item_id = pending.pop()
        if item_id not in result:
            result.add(item_id)
            pending.extend(children.get(item_id, []))
    return result

