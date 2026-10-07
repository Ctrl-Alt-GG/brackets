import { defineConfig } from '@hey-api/openapi-ts';

export default defineConfig({
  input: '../backend/openapi/openapi.json',
  output: 'src/openapi',
  plugins: [
    '@hey-api/client-axios',
    // Request schemas for the forms, and query/mutation options for TanStack Query.
    { name: 'zod', compatibilityVersion: 4 },
    '@tanstack/react-query',
  ],
});
