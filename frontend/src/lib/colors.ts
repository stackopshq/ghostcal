/**
 * The colours a calendar can be given.
 *
 * One list, shared by the two creation forms and by the picker that recolours an existing
 * calendar. It was declared inside `dashboard/calendar/page.tsx` while it only served the forms;
 * the moment a third caller needed it, a copy would have been the easy thing and a second palette
 * the result.
 *
 * The server accepts any `#rrggbb`, so this list constrains the interface rather than the data —
 * which is the right way round: someone importing from another tool keeps their colour.
 */
// Typed `readonly string[]` and not `as const`: with literal types, `useState(CAL_COLORS[0])`
// narrows to that one colour and refuses every other member of its own palette.
export const CAL_COLORS: readonly string[] = [
  "#00f0ff",
  "#a3ff00",
  "#ff2d95",
  "#ffb020",
  "#8b5cff",
  "#ff5c5c",
  "#00d68f",
];
