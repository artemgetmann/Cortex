import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Allow importing ../agi-ideas.jsx from this nested viewer project.
export default defineConfig({
  plugins: [react()],
  server: {
    fs: {
      allow: [".."],
    },
  },
});
