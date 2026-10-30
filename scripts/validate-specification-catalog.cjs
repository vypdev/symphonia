#!/usr/bin/env node

// Invoke the unchanged Copilot validator with this consumer repository as root.
const path = require('node:path');
const fs = require('node:fs');
const validator = require('../tools/copilot-specifications/src/infrastructure/specification_catalog_validator.cjs');

function main(argv = process.argv.slice(2), root = path.resolve(__dirname, '..')) {
  if (argv.includes('--write')) {
    try {
      // lstat also sees dangling links, unlike existsSync. Reuse SDK path checks.
      fs.lstatSync(path.join(root, validator.CATALOG_MARKDOWN));
      if (!validator.isRegularRepositoryFile(root, validator.CATALOG_MARKDOWN)) {
        console.error('Catalog generation refused: existing specs/CATALOG.md must be a regular repository file without symlinks.');
        process.exitCode = 1;
        return;
      }
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
  }
  validator.main(argv, root);
}

if (require.main === module) main();
module.exports = { ...validator, main };
