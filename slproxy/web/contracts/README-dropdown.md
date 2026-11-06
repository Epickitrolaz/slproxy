/**
 * SLProxy Custom Dropdown Component (obsidian style)
 * ---------------------------------------------------
 * Issue #17 contract. Fully replaces native <select> elements in the UI.
 *
 * Public API (the ONLY contract other code may rely on):
 *
 *   const dd = CustomDropdown.create({
 *     el:              HTMLElement,   // element to render into (replaces any <select> child)
 *     options:         Array<{value, label, group?, disabled?}> | null,
 *     value:           string,        // initial value ('' = none)
 *     placeholder:     string,        // label when no value selected
 *     onChange:        (value, option)=>void,
 *     id:              string,        // optional, forwarded to trigger button (data-dd-id)
 *     className:       string,        // extra classes on the trigger button
 *     disabled:        boolean,
 *   });
 *
 *   dd.setValue(value)                  // programmatic set; fires onChange unless silent
 *   dd.getValue() -> string             // '' when nothing selected
 *   dd.setOptions(options)              // replace list, preserves selection when possible
 *   dd.setDisabled(bool)
 *
 * Adapter for legacy code paths (keeps `.value` reads/writes working):
 *
 *   CustomDropdown.bindSelect(selectEl, {onChange})  // upgrades an existing native
 *     <select> in place: hides it, renders the custom control, and proxies
 *     value get/set + 'change' events so existing code
 *     (`document.getElementById('x').value = v`, `addEventListener('change', ...)`)
 *     keeps working unchanged. Returns the same dd instance.
 *
 * Behavior requirements (verify each):
 *   - Click trigger toggles panel; click outside closes; Escape closes without
 *     bubbling to modal-close handlers.
 *   - Keyboard: Enter/Space opens, ArrowUp/Down move highlight, Enter selects,
 *     Escape closes, Tab closes. Focus is trapped to the panel while open.
 *   - Grouped options (option.group) render sticky group headers.
 *   - Long lists scroll (max-height); selected item auto-scrolls into view.
 *   - Panel layers above modals (z-index > 80); not clipped by overflow ancestors.
 *   - Selected option shows a check mark; hover/active states use the design
 *     system (bg-white/5, border-white/10, text zinc palette).
 *   - ARIA: role="listbox"/"option", aria-expanded, aria-activedescendant.
 *   - Matches surrounding trigger sizing (min-height 38-44px per original selects).
 */
