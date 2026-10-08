import { config } from 'zod/v4/core';

// The Content-Security-Policy forbids `eval`, so Zod mustn't try to compile its parsers with
// `new Function`: the browser reports even the attempt. Zod checks once, while it creates the first
// schema, so this module is the first one the entry point imports. Only Zod's small core is
// imported here; the rest loads with the forms that use it.
config({ jitless: true });
