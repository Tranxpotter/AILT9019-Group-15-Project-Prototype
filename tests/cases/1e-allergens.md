# Test 1e — Allergen safety & dietary/allergen categorization

**Date:** 2026-10-31 · **Mode:** Demo + LLM · **Scope:** deterministic allergen exclusion, plus the boundary between dietary labels and allergen safety.

## Categorization

| Term | Category | Canonical field | Behavior |
|---|---|---|---|
| vegetarian | Dietary preference | `dietary: vegetarian` | Venue must carry the label |
| vegan | Dietary preference | `dietary: vegan` | Venue must carry the label |
| halal | Dietary/religious | `dietary: halal` | Venue must carry the label |
| no-pork | Dietary/religious | `dietary: no-pork` + `avoid: pork` | Venue must carry the label |
| gluten-free | Dietary certification | `dietary: gluten-free` | Venue must carry the label |
| nut-free | Dietary certification | `dietary: nut-free` | Venue must carry the label |
| fish | Allergen (safety) | `allergens: fish` | Hard-exclude venues with fish ingredients |
| crustacean / shellfish | Allergen (safety) | `allergens: crustacean` | Hard-exclude prawn/shrimp/crab/lobster |
| mollusk / shellfish | Allergen (safety) | `allergens: mollusk` | Hard-exclude oyster/clam/squid/octopus |
| peanut | Allergen (safety) | `allergens: peanut` | Hard-exclude peanuts |
| tree-nut | Allergen (safety) | `allergens: tree-nut` | Hard-exclude tree nuts |
| gluten | Allergen (safety) | `allergens: gluten` | Hard-exclude wheat/gluten |
| dairy | Allergen (safety) | `allergens: dairy` | Hard-exclude dairy |
| egg | Allergen (safety) | `allergens: egg` | Hard-exclude egg |
| soy | Allergen (safety) | `allergens: soy` | Hard-exclude soy |
| sesame | Allergen (safety) | `allergens: sesame` | Hard-exclude sesame |

**Intent rule:** allergy phrasing (`allergic to nuts`, `nut allergy`, `celiac`, `gluten intolerance`) → `allergens` only. Explicit diet phrasing (`nut-free`, `gluten-free`) → `dietary` only. Saying both applies both intentionally.

## Case A — Seafood exclusion
**Input:** `Lunch, no seafood`

**Expected:**
- Parsed badge: `meal: lunch · allergens: crustacean+fish+mollusk`
- Cards: **Café 88, Sun Kee Curry House, Green Bowl Salad Bar**
- Must **NOT** show: Water Street Noodle House, Pokfulam Thai & Grill, Dim Sum Dynasty, Hana Sushi, Jade Garden Vegetarian, and **Sweet Corner Desserts** (dessert venue, excluded for full meals)
- Summary: **“For safety, I excluded restaurants containing crustaceans, fish, mollusks.”**

## Case B — Nut allergy (not a dietary label)
**Input:** `cheap lunch I am allergic to nuts though`

**Expected:**
- Parsed badge: `meal: lunch · price: $ · allergens: peanut+tree-nut` — **no `dietary: nut-free`**
- If the LLM returns `dietary: nut-free` as well, the backend drops it for this allergy request (unless the message explicitly asks for a nut-free kitchen).
- **No cards.** Sweet Corner Desserts is excluded as a dessert venue (not a full lunch); Sun Kee Curry House is excluded because its Paneer Butter Masala contains cashew gravy (tree-nut). Café 88 / Green Bowl are `$$`.
- Summary says **“No suitable restaurant found.”**

## Case C — Explicit nut-free diet (dietary label)
**Input:** `nut-free lunch`

**Expected:**
- Parsed badge: `meal: lunch · dietary: nut-free` — **no `allergens`**
- Cards: **Green Bowl Salad Bar only** (the only venue with the `nut-free` dietary label)
- Summary does **not** contain the “For safety, I excluded restaurants containing …” sentence.

## Case D — Explicit gluten-free diet (dietary label)
**Input:** `gluten-free lunch`

**Expected:**
- Parsed badge: `meal: lunch · dietary: gluten-free` — **no `allergens`**
- Cards: lunch venues carrying the `gluten-free` label.
- Summary does **not** contain the allergen safety sentence.

## Case E — Celiac / gluten allergy (allergen)
**Input:** `celiac lunch`

**Expected:**
- Parsed badge: `meal: lunch · allergens: gluten` — **no `dietary: gluten-free`**
- Cards: full-lunch venues with no detected gluten: **Pokfulam Thai & Grill, Green Bowl Salad Bar**. Sweet Corner Desserts is excluded as a dessert venue.
- Summary includes the safety disclosure for gluten.

## Verdict
✅ **Phase 1 behavior** — deterministic allergen extraction + conservative venue detection; dietary labels and allergens are separate; allergen filters are never relaxed.
