// SPDX-FileCopyrightText: 2026 Curtis Galloway
// SPDX-License-Identifier: Apache-2.0

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// One self-contained dist/index.html: JS, CSS and the order data are all
// inlined so it opens straight from disk with no server. build.py copies it
// to search/index.html.
export default defineConfig({
  plugins: [react(), viteSingleFile()],
  json: { stringify: true },
});
