import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  esbuild: { jsx: "automatic" }, // component tests render TSX without importing React
  resolve: { alias: { "@": path.resolve(__dirname, ".") } },
  test: { include: ["lib/**/*.test.ts", "components/**/*.test.{ts,tsx}"], environment: "node" },
});
