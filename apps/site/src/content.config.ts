import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";

const articles = defineCollection({
  loader: glob({
    base: "./src/content/articles",
    pattern: "**/*.md",
    generateId: ({ data, entry }) => {
      const id = data.id;

      if (typeof id !== "string" || id.trim() === "") {
        throw new Error(`${entry}: укажите непустой id статьи`);
      }

      return id.trim();
    },
  }),
  schema: z
    .object({
      title: z.string().trim().min(1),
      schema_version: z.literal(1),
      kind: z.literal("article"),
      slug: z.string().regex(/^[a-z0-9][a-z0-9-]*$/),
      id: z.string().trim().min(1),
    })
    .strict(),
});

export const collections = { articles };
