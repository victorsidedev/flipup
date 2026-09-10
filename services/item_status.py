from models.item import Item
from schemas.sale import SaleResponse


def find_sale_source(
    item_id: int,
    items: dict[int, Item],
    sales: dict[int, SaleResponse],
) -> int | None:
    """Use the nearest direct sale, including the item's own sale, if present."""
    visited = set()
    while item_id in items and item_id not in visited:
        visited.add(item_id)
        if item_id in sales:
            return item_id
        item_id = items[item_id].parent_item_id
    return None
