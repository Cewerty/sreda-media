import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * Конфиг production-сборки.
 *
 * Намеренно не импортирует `vitest/config`: `tsc -b` и `vite build` не должны
 * зависеть от devDependency `vitest`. Иначе сборка при `pnpm install --prod`
 * падала бы на резолве типов. Конфиг тестов — отдельный файл `vitest.config.ts`.
 *
 * Публичный base для развёртывания (`/cms/` по ADR 0006) задаётся в #14/#30,
 * а не хардкодится здесь.
 */
export default defineConfig({
  base: "/",
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
