/*
 * App identity for Gmail Sentry. The marketplace reads appName + appDescription
 * (also used for the widget/document title below).
 */
export const appName = 'Gmail Sentry';
export const appDescription =
  'Know what your inbox needs from you. Tell it in plain language what matters and it triages incoming Gmail, tracks what you owe people and who has gone quiet, files whole conversations into folders you approve, and drafts replies in your own voice — you approve, it sends. Pings you on Slack, WhatsApp or Telegram, and reports daily on what needs answering and what is going cold.';

// The marketplace widget host labels the widget from document.title, so set it
// from the app's OWN name (this is what makes the widget announce itself
// correctly instead of the seed/template title).
if (typeof document !== 'undefined' && appName) {
  document.title = appName;
}
