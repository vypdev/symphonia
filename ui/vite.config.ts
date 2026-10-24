import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  build: {
    outDir: "../src/symphonia/runtime/ui_assets",
    emptyOutDir: true,
  },
});
