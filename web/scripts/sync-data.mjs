// Copy the repo-level data/ into static/data/ so every published JSON file is
// downloadable from the site (the pages themselves import data/ at build time).
import { cpSync, rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const src = fileURLToPath(new URL('../../data', import.meta.url));
const dest = fileURLToPath(new URL('../static/data', import.meta.url));
rmSync(dest, { recursive: true, force: true });
cpSync(src, dest, { recursive: true });
