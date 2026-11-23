import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";

const articles = defineCollection({
    loader: glob({base: "./src/content/articles", pattern: "**/*.md"}),
    schema: z.object({title: z.string().trim().min(1)})
});

export const collections = { articles };