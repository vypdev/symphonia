const fs = require('node:fs');
const path = require('node:path');

const parent = fs.realpathSync(process.env.RUNNER_TEMP);
const profile = process.env.STATE_profile;
const originalHome = process.env.STATE_original_home;
if (!profile || path.dirname(profile) !== parent || !path.basename(profile).startsWith('symphonia-verify-home-')) {
  throw new Error('Refusing cleanup outside the owned smoke profile');
}
if (!originalHome || /[\r\n]/.test(originalHome)) throw new Error('Invalid original HOME');
if (fs.existsSync(profile)) {
  const stat = fs.lstatSync(profile);
  if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error('Unexpected smoke profile type');
  fs.rmSync(profile, { recursive: true });
}
fs.appendFileSync(process.env.GITHUB_ENV, `HOME=${originalHome}\n`);
