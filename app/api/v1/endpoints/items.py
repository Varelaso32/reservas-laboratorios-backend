from fastapi import APIRouter

from app.schemas.item import Item, ItemCreate

router = APIRouter()

items_db: dict[int, Item] = {}


@router.get("/", response_model=list[Item])
def list_items() -> list[Item]:
    return list(items_db.values())


@router.get("/{item_id}", response_model=Item)
def get_item(item_id: int) -> Item:
    return items_db[item_id]


@router.post("/", response_model=Item, status_code=201)
def create_item(item_in: ItemCreate) -> Item:
    new_id = max(items_db.keys(), default=0) + 1
    item = Item(id=new_id, **item_in.model_dump())
    items_db[new_id] = item
    return item