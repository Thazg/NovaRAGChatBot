import path from "path"
import { readFileSync } from "node:fs"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

const { version } = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8")) as { version: string }

export default defineConfig({
  plugins: [react()],
  define: {
    "import.meta.env.VITE_APP_VERSION": JSON.stringify(version),
  },
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: "syntax",
              test: /node_modules[\\/](react-syntax-highlighter|refractor|prismjs)/,
              priority: 40,
            },
            {
              name: "motion",
              test: /node_modules[\\/]framer-motion/,
              priority: 30,
            },
            {
              name: "ui",
              test: /node_modules[\\/](@radix-ui|lucide-react)/,
              priority: 20,
            },
            {
              name: "react-vendor",
              test: /node_modules[\\/](react|react-dom|react-markdown|remark-gfm|zustand)/,
              priority: 10,
            },
          ],
        },
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
})
