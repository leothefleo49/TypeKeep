#!/usr/bin/env node
/**
 * TypeKeep — Local Build & GitHub Release Script
 *
 * Builds for Windows (PyInstaller), packages into an installer,
 * creates a GitHub Release, and uploads all artifacts.
 *
 * Usage:
 *   node scripts/release-github.js                    # auto-version from date
 *   node scripts/release-github.js --version 3.2.0    # explicit version
 *   node scripts/release-github.js --dry-run           # simulate only
 *   node scripts/release-github.js --skip-build        # skip PyInstaller
 *   node scripts/release-github.js --skip-commit       # don't commit/push
 *   node scripts/release-github.js --notes "Fix X"     # custom release notes
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const CONFIG_PY = path.join(ROOT, 'config.py');
const DIST_DIR = path.join(ROOT, 'dist');

const args = process.argv.slice(2);
const flag = (name) => args.includes(`--${name}`);
const flagVal = (name) => {
  const idx = args.indexOf(`--${name}`);
  return idx >= 0 && idx + 1 < args.length ? args[idx + 1] : null;
};

const DRY_RUN = flag('dry-run');
const SKIP_BUILD = flag('skip-build');
const SKIP_COMMIT = flag('skip-commit');
const NOTES = flagVal('notes') || '';

function run(cmd, opts = {}) {
  console.log(`  > ${cmd}`);
  if (DRY_RUN && !opts.force) {
    console.log('    [dry-run] skipped');
    return '';
  }
  try {
    return execSync(cmd, {
      cwd: ROOT,
      stdio: opts.silent ? 'pipe' : 'inherit',
      encoding: 'utf-8',
      ...opts,
    }) || '';
  } catch (e) {
    if (opts.ignoreError) return '';
    console.error(`Command failed: ${cmd}`);
    process.exit(1);
  }
}

function getVersion() {
  let v = flagVal('version');
  if (v) return v.replace(/^v/i, '');

  const content = fs.readFileSync(CONFIG_PY, 'utf-8');
  const match = content.match(/APP_VERSION\s*=\s*['"]([^'"]+)['"]/);
  if (match) return match[1];

  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth() + 1;
  const d = now.getDate();
  return `${y}.${m}.${d}`;
}

function updateVersion(version) {
  console.log(`\n[1/6] Updating version to ${version}...`);
  let content = fs.readFileSync(CONFIG_PY, 'utf-8');
  content = content.replace(
    /APP_VERSION\s*=\s*['"][^'"]+['"]/,
    `APP_VERSION = '${version}'`
  );
  fs.writeFileSync(CONFIG_PY, content, 'utf-8');

  const pkgPath = path.join(ROOT, 'mobile-app', 'package.json');
  if (fs.existsSync(pkgPath)) {
    const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf-8'));
    pkg.version = version;
    fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + '\n', 'utf-8');
  }

  console.log(`  Version set to ${version} in config.py and package.json`);
}

function commitAndPush(version) {
  if (SKIP_COMMIT) {
    console.log('\n[2/6] Skipping commit (--skip-commit)');
    return;
  }
  console.log('\n[2/6] Committing and pushing...');
  run('git add -A');
  run(`git commit -m "v${version} - Release build"`);
  run('git push');
}

function buildWindows(version) {
  if (SKIP_BUILD) {
    console.log('\n[3/6] Skipping build (--skip-build)');
    return null;
  }
  console.log('\n[3/6] Building Windows executable...');

  const sep = process.platform === 'win32' ? ';' : ':';
  const cmd = [
    'pyinstaller',
    '--onefile',
    '--noconsole',
    '--name TypeKeep',
    `--add-data "templates${sep}templates"`,
    `--add-data "static${sep}static"`,
    `--add-data "mobile${sep}mobile"`,
    '--distpath dist',
    '--workpath build',
    '--specpath build',
    'typekeep.py',
  ].join(' ');

  run(cmd);

  const exePath = path.join(DIST_DIR, 'TypeKeep.exe');
  if (!fs.existsSync(exePath)) {
    console.error('Build failed: TypeKeep.exe not found in dist/');
    process.exit(1);
  }

  const sizeMB = (fs.statSync(exePath).size / (1024 * 1024)).toFixed(1);
  console.log(`  Built: TypeKeep.exe (${sizeMB} MB)`);

  const outName = `TypeKeep-v${version}-windows-setup.exe`;
  const outPath = path.join(DIST_DIR, outName);
  if (outPath !== exePath) {
    fs.copyFileSync(exePath, outPath);
  }
  return outPath;
}

function verifyBuild(artifactPath) {
  console.log('\n[4/6] Verifying build...');
  if (!artifactPath) {
    console.log('  No artifact to verify (build was skipped)');
    return;
  }
  if (!fs.existsSync(artifactPath)) {
    console.error(`  Artifact not found: ${artifactPath}`);
    process.exit(1);
  }
  const sizeMB = (fs.statSync(artifactPath).size / (1024 * 1024)).toFixed(1);
  console.log(`  Verified: ${path.basename(artifactPath)} (${sizeMB} MB)`);
}

function createRelease(version, artifactPath) {
  console.log('\n[5/6] Creating GitHub Release...');
  const tag = `v${version}`;
  const title = tag;
  const notes = NOTES || `TypeKeep ${tag} release`;

  let files = '';
  if (artifactPath && fs.existsSync(artifactPath)) {
    files = `"${artifactPath}"`;
  }

  const cmd = `gh release create ${tag} ${files} --title "${title}" --notes "${notes}" --target main --latest`;
  run(cmd);
}

function verifyRelease(version) {
  console.log('\n[6/6] Verifying release...');
  const tag = `v${version}`;
  const out = run(`gh release view ${tag} --json isDraft,tagName,isLatest`, {
    force: true,
    silent: true,
    ignoreError: true,
  });

  if (out) {
    try {
      const info = JSON.parse(out);
      if (info.isDraft) {
        console.log('  Release is a draft! Publishing...');
        run(`gh release edit ${tag} --draft=false --latest`);
      }
      if (!info.isLatest) {
        console.log('  Release not marked as latest. Fixing...');
        run(`gh release edit ${tag} --latest`);
      }
      console.log(`  Release ${tag} is published and marked as latest.`);
    } catch (_) {
      console.log('  Could not parse release info, assuming OK.');
    }
  }
}

function main() {
  console.log('='.repeat(50));
  console.log('  TypeKeep Release Script');
  console.log('='.repeat(50));

  if (DRY_RUN) console.log('  ** DRY RUN MODE **\n');

  const version = getVersion();
  console.log(`  Target version: v${version}`);

  updateVersion(version);
  commitAndPush(version);
  const artifact = buildWindows(version);
  verifyBuild(artifact);
  createRelease(version, artifact);
  verifyRelease(version);

  console.log('\n' + '='.repeat(50));
  console.log(`  Release v${version} complete!`);
  console.log('='.repeat(50));
}

main();
