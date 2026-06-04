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
];

export default eslintConfig;
