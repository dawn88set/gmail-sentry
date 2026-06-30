/**
 * ESLint config for the Claritty agentic-app frontend.
 *
 * `root: true` is load-bearing: without it ESLint walks UP the directory tree
 * and picks up whatever stray `.eslintrc.*` happens to live above the repo,
 * then fails with "couldn't find the plugin" because those plugins aren't
 * installed at that level. Keep this here so `npm run lint` resolves the
 * config from the frontend, nowhere else.
 */
module.exports = {
  root: true,
  env: { browser: true, es2020: true, node: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', 'coverage', '.eslintrc.cjs'],
  parser: '@typescript-eslint/parser',
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module' },
  plugins: ['react-refresh'],
  rules: {
    'react-refresh/only-export-components': [
      'warn',
      { allowConstantExport: true },
    ],
  },
  overrides: [
    {
      // Test + visual-audit tooling, not shipped app code. `any` is allowed
      // here: test mocks legitimately cast through it, and tests/visual-audit.ts
      // is shared with clarity-api (no DOM lib) where the browser globals it
      // touches can only be typed as `any`. App code under src/ stays strict.
      files: ['**/*.test.ts', '**/*.test.tsx', 'tests/**/*.ts'],
      rules: {
        '@typescript-eslint/no-explicit-any': 'off',
      },
    },
  ],
}
