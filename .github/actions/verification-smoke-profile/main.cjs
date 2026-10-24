const fs = require('node:fs');
const path = require('node:path');

const parent = fs.realpathSync(process.env.RUNNER_TEMP);
const originalHome = process.env.HOME;
if (!originalHome || /[\r\n]/.test(originalHome)) throw new Error('Invalid original HOME');
const profile = fs.mkdtempSync(path.join(parent, 'symphonia-verify-home-'));
fs.chmodSync(profile, 0o700);
fs.appendFileSync(process.env.GITHUB_STATE, `profile=${profile}\noriginal_home=${originalHome}\n`);
fs.appendFileSync(process.env.GITHUB_ENV, `HOME=${profile}\n`);
