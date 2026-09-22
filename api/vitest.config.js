import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

// The report routes run against Miniflare's local R2; account routes are not
// covered here. A synced folder (Dropbox) can lock Vite's dependency cache
// mid-rename; point VITEST_CACHE_DIR somewhere local when that happens.
const cacheDir = process.env.VITEST_CACHE_DIR || 'node_modules/.vite';

export default defineWorkersConfig({
  cacheDir,
  test: {
    include: ['test/**/*.test.js'],
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
        miniflare: { bindings: { REPORTS_TOKEN: 'test-admin-token', REPORTS_ENABLED: '1', REPORT_MAX_BYTES: '524288' } },
      },
    },
  },
});
