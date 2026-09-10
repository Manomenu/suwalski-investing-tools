import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
    plugins: [react(), tailwindcss()],
    server: {
        // 3000 is what the API allows as a CORS origin by default — and with this
        // proxy the browser talks to one origin anyway, so CORS never comes up in dev.
        port: 3000,
        proxy: {
            "/api": {
                target: "http://localhost:6100",
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/api/, ""),
            },
        },
    },
});
