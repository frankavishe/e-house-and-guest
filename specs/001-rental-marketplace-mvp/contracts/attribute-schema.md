# Contract: Category Attribute Schema

`categories.attribute_schema` is a JSON array of field definitions. It is the only thing an
admin edits to add a rental type's fields (FR-006, SC-006). The backend uses it to
validate `listings.attributes` and to build search filters. The frontend uses it to render
the listing form and the filter panel.

## Field definition

```json
{
  "key": "bedrooms",                       // ^[a-z][a-z0-9_]{1,39}$, unique in schema, immutable
  "type": "integer",                       // integer | decimal | boolean | enum | multi_enum | text
  "label": {"sw": "Vyumba vya kulala", "en": "Bedrooms"},
  "help": {"sw": "...", "en": "..."},      // optional
  "unit": {"sw": "m²", "en": "m²"},        // optional, display only
  "required": true,
  "min": 0, "max": 50,                     // integer/decimal only
  "options": [                             // enum/multi_enum only; option keys immutable once used
    {"value": "4x4", "label": {"sw": "4x4", "en": "4x4"}}
  ],
  "max_length": 200,                       // text only (≤ 500)
  "filter": "range",                       // none | exact | range | any_of
  "show_on_card": false,                   // shown in search result cards
  "group": {"sw": "Maelezo", "en": "Details"},  // optional form section
  "order": 10
}
```

## Rules

| Type | Stored JSON value | Allowed `filter` | Search query param |
|---|---|---|---|
| integer | number (int) | none, exact, range | `attr.k=3` / `attr.k.min=2&attr.k.max=4` |
| decimal | number | none, range | `attr.k.min=` / `attr.k.max=` |
| boolean | true/false | none, exact | `attr.k=true` |
| enum | string (option value) | none, exact, any_of | `attr.k=4x4` / `attr.k=4x4,suv` |
| multi_enum | string[] | none, any_of | `attr.k=wifi,parking` (has any) |
| text | string | none | — |

- Values for keys not in the schema are rejected on write (422).
- The schema itself is validated on admin save: unique keys, both `sw` and `en` labels for
  every label and option, `min ≤ max`, and filters allowed for the type.
- Editing: adding fields and options and changing labels are always allowed. Removing a field
  hides it, and stored values remain. Changing `type` or removing an option still used by
  listings returns 409.
- Stock quantity, price, deposit and location are **listing columns**, not attributes, because
  the engine itself uses them.

## Example: Equipment → Generators (US7-AS1)

```json
[
  {"key": "power_kva", "type": "decimal", "label": {"sw": "Nguvu (kVA)", "en": "Power (kVA)"},
   "required": true, "min": 0.5, "max": 2000, "filter": "range", "show_on_card": true, "order": 1},
  {"key": "fuel_type", "type": "enum", "label": {"sw": "Aina ya mafuta", "en": "Fuel type"},
   "required": true, "filter": "any_of", "order": 2,
   "options": [{"value": "diesel", "label": {"sw": "Dizeli", "en": "Diesel"}},
               {"value": "petrol", "label": {"sw": "Petroli", "en": "Petrol"}}]}
]
```
Category row: `booking_mode = QUANTITY`, `price_units = {item_day}`, `default_unit = item_day`.

## Seed categories (initial schemas live in `backend/seed/categories.yaml`)

| Group | Leaf examples | Mode | Units |
|---|---|---|---|
| Accommodation | rooms, guest-houses, serviced-apartments | DATE_RANGE | night, week, month |
| Accommodation | student-housing, co-living | LEASE | month |
| Workspace | coworking | TIME_SLOT | hour, day |
| Workspace | offices | LEASE | month |
| Venues | event-halls, event-venues | TIME_SLOT | hour, day |
| Storage & Property | warehouses, self-storage | LEASE | month |
| Storage & Property | parking | DATE_RANGE (days) | day, month |
| Vehicles & Mobility | cars, vans, buses, motorbikes, bajaji, trucks | DATE_RANGE (days) | day, week |
| Equipment & Supplies | construction, tents, tables-chairs, lighting, sound-av, bounce-houses, it-equipment, office-supplies | QUANTITY | item_day |
