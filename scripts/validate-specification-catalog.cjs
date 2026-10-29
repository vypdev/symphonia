#!/usr/bin/env node

// Invoke the unchanged Copilot validator with this consumer repository as root.
const path = require('node:path');
const validator = require('../tools/copilot-specifications/src/infrastructure/specification_catalog_validator.cjs');

if (require.main === module) validator.main(process.argv.slice(2), path.resolve(__dirname, '..'));
module.exports = validator;
