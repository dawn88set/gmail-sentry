/*
 * App identity for Gmail Sentry. The marketplace reads appName + appDescription
 * (also used for the widget/document title below).
 */
export const appName = 'Gmail Sentry';
export const appDescription =
  'Your inbox watchdog: tell the team in plain language what matters, and it learns how you actually communicate. It triages incoming Gmail, pings you on Slack, WhatsApp, or Telegram — with a ready-to-send reply in your voice you can approve in one tap — sends a daily report, and clears Promotions, Social, and Spam in one tap.';

// The marketplace widget host labels the widget from document.title, so set it
// from the app's OWN name (this is what makes the widget announce itself
// correctly instead of the seed/template title).
if (typeof document !== 'undefined' && appName) {
  document.title = appName;
}
