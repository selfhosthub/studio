// ui/eslint.config.mjs

// eslint.config.mjs - ESLint Flat Config for Next.js 16+
import coreWebVitals from 'eslint-config-next/core-web-vitals';

const eslintConfig = [
  {
    ignores: [
      '.next/**',
      'node_modules/**',
      'out/**',
      'build/**',
      'coverage/**',
      'playwright-report/**',
      'e2e/**',
    ],
  },
  ...coreWebVitals,
  // Browser-native dialogs are banned in UI source; use useConfirm from @/shared/ui/ConfirmDialog
  {
    files: ['**/*.{ts,tsx,js,jsx,mjs}'],
    ignores: ['__tests__/**'],
    rules: {
      'no-restricted-globals': [
        'error',
        ...['confirm', 'alert', 'prompt'].map((name) => ({
          name,
          message: 'Native dialogs show the host name. Use useConfirm from @/shared/ui/ConfirmDialog.',
        })),
      ],
      'no-restricted-properties': [
        'error',
        ...['window', 'globalThis', 'self'].flatMap((object) =>
          ['confirm', 'alert', 'prompt'].map((property) => ({
            object,
            property,
            message: 'Native dialogs show the host name. Use useConfirm from @/shared/ui/ConfirmDialog.',
          })),
        ),
      ],
    },
  },
];

export default eslintConfig;
