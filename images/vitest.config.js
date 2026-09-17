import { defineWorkersProject } from '@cloudflare/vitest-pool-workers/config';
import { defineConfig } from 'vitest/config';

// Two projects because the upstream toggle is a binding, fixed per runtime:
// the seed-only behaviour and the miss path each get their own. EDGE_CACHE
// is off in both: the Cache API write does not settle in the test runtime.
// A synced folder (Dropbox) can lock Vite's dependency cache mid-rename; point
// VITEST_CACHE_DIR somewhere local when that happens.
const cacheDir = process.env.VITEST_CACHE_DIR || 'node_modules/.vite';

const project = (name, include, bindings) => defineWorkersProject({
  cacheDir,
  test: {
    name, include,
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
        miniflare: {
          bindings: { EDGE_CACHE: '0', UPSTREAM_HOURLY_CAP: '2', NEG_TTL_DAYS: '30', NEG_MAX_TRIES: '3', LOCK_SECONDS: '30', ...bindings },
        },
      },
    },
  },
});

export default defineConfig({
  cacheDir,
  test: {
    projects: [
      project('seed', ['test/worker.test.js'], { UPSTREAM_ENABLED: '0' }),
      project('upstream', ['test/upstream.test.js'], { UPSTREAM_ENABLED: '1' }),
    ],
  },
});
