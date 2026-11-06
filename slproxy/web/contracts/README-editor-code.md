# Editor code pipeline contract (Issue #16)

Owner: worker A (branch `fix/editor-plugin-code`).

## Data flow that must exist when done

1. `GET /api/plugins` returns plugin metadata; additionally each entry MAY include
   `"code"` (string) with the plugin's current Python source. Implementations may
   omit it for very large sources but MUST provide `"code_available": true|false`.
2. New endpoint `GET /api/templates` already returns full template source under
   `code` (admin_api.list_templates does this today). The union of
   *installed* plugins (`/api/plugins`) and *reference templates* (`/api/templates`)
   forms the editor target list.
3. `populateEditorPluginDropdown()` populates `#editor-plugin-select` with:
   - all installed plugins (from state.plugins), then
   - all reference templates not installed (from state.referenceTemplates),
     marked "template" so the user can see they are editable source templates.
4. Selecting a target loads its code via, in priority order:
   a. in-memory `state.plugins[].code` if fresh,
   b. `GET /api/plugins/{id}/code` (installed plugin),
   c. `state.referenceTemplates[].code` (uninstalled template),
   d. last-resort generic base template, ONLY with a visible indicator
      that real source could not be fetched (editor badge turns amber and
      shows "template fallback").
   Fetching is async and MUST NOT block tab render.
5. "Save & Deploy" must continue to hit `POST /api/plugins/{id}/code`.
   After successful deploy of a template target that wasn't installed, the
   plugin list refresh must include the newly installed plugin.

## Non-goals

- No backend storage changes needed beyond adding `code` to the list endpoint
  and reading from TEMPLATES_DIR as a source-of-truth fallback.
- No changes to the custom dropdown component (worker B owns index.html).

## Touch policy

Worker B owns `index.html` and the dropdown component. Worker A must NOT
restructure dropdown markup; use `populateEditorPluginDropdown()` semantics
(option value = plugin id, text = name) so the component renders the same.
