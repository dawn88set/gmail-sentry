/*
 * App identity. The platform overwrites this file per generated app with the
 * real name + description. THIS file is the un-customized template default —
 * so it intentionally names the template itself ("Claritty Template"). A
 * generated app never ships these values; generation replaces them with the
 * app's own name, so there's no risk of a real app announcing itself as the
 * template.
 */
export const appName = 'Claritty Template';
export const appDescription = 'A starter template for Claritty agentic apps.';

// The marketplace widget host labels the widget from document.title, so set it
// from the app's OWN name (this is what makes the widget announce itself
// correctly instead of the seed/template title).
if (typeof document !== 'undefined' && appName) {
  document.title = appName;
}
