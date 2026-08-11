import path from "path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
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
