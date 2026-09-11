import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Same toolchain as uis/website (see its README for the reasoning), on a
// different port so both apps can run side by side during development.
export default defineConfig({
    plugins: [react(), tailwindcss()],
    server: {
        port: 3001
    },
    build: {
        outDir: 'dist'
    }
})
