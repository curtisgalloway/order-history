// SPDX-FileCopyrightText: 2026 Curtis Galloway
// SPDX-License-Identifier: Apache-2.0

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// One self-contained dist/index.html with the JS and CSS inlined, so it opens
// straight from disk with no server. It is the page shell: its
// <script id="order-data"> element is empty, and order-history's page.py
// fills it with the order data. Releases publish it as page-shell.html.
export default defineConfig({
  plugins: [react(), viteSingleFile()],
});
