import "server-only";

/**
 * Server-only entry to the still blur (PUB-02). Code that runs in the app imports from here, so a
 * future client import fails the build instead of bundling jpeg-js/pngjs. lib/stillBlur.ts stays
 * importable by vitest (the server-only package throws outside a react-server build).
 */
export { blurStill, hasMetadata, StillError, BLUR_METHOD } from "./stillBlur";
