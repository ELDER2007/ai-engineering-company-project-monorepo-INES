import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Same base config as the 4Geeks react-hello-webapp template, with the
// Tailwind Vite plugin added (Tailwind CSS is a hard requirement from the
// stakeholder brief in CONTEXT.md).
export default defineConfig({
    plugins: [react(), tailwindcss()],
    server: {
        port: 3000
    },
    build: {
        outDir: 'dist'
    }
})
