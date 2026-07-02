/*
 * App identity for Gmail Sentry. The marketplace reads appName + appDescription
 * (also used for the widget/document title below).
 */
export const appName = 'Gmail Sentry';
export const appDescription =
  'Your inbox watchdog: it triages incoming Gmail against rules you define, pings you on Slack with a deep link when something needs attention, and clears Promotions, Social, and Spam in one tap.';

// The marketplace widget host labels the widget from document.title, so set it
// from the app's OWN name (this is what makes the widget announce itself
// correctly instead of the seed/template title).
if (typeof document !== 'undefined' && appName) {
  document.title = appName;
}
