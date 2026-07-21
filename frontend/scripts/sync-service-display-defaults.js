/**
 * Sync shared display defaults from repo root into frontend/src/data/.
 * Canonical source: data/service_display_defaults.json (also used by app/service_display.py).
 */
const fs = require('fs');
const path = require('path');

const destination = path.join(__dirname, '../src/data/service_display_defaults.json');
const canonicalRelative = path.join('data', 'service_display_defaults.json');

function resolveSourcePath() {
  const candidates = [
    process.env.SERVICE_DISPLAY_DEFAULTS_SOURCE,
    path.join(process.cwd(), canonicalRelative),
    path.join(path.resolve(__dirname, '..'), canonicalRelative),
    '/app/data/service_display_defaults.json',
  ].filter(Boolean);

  for (const candidate of candidates) {
    const resolved = path.resolve(candidate);
    if (fs.existsSync(resolved)) {
      return resolved;
    }
  }

  let dir = path.resolve(__dirname, '..');
  while (true) {
    const candidate = path.join(dir, canonicalRelative);
    if (fs.existsSync(candidate)) {
      return candidate;
    }
    const parent = path.dirname(dir);
    if (parent === dir) {
      break;
    }
    dir = parent;
  }

  if (process.env.SERVICE_DISPLAY_DEFAULTS_SOURCE) {
    return path.resolve(process.env.SERVICE_DISPLAY_DEFAULTS_SOURCE);
  }

  return path.join(process.cwd(), canonicalRelative);
}

const destinationExists = fs.existsSync(destination);
const source = resolveSourcePath();

if (!fs.existsSync(source)) {
  if (destinationExists) {
    console.warn(
      `Canonical defaults file not found at ${source}; using existing ${path.relative(process.cwd(), destination)}`,
    );
    process.exit(0);
  }

  console.error(`Missing canonical defaults file: ${source}`);
  console.error(
    'Provide data/service_display_defaults.json (Docker: mount host data/ at /app/data) ' +
      'or commit frontend/src/data/service_display_defaults.json as a fallback.',
  );
  process.exit(1);
}

fs.mkdirSync(path.dirname(destination), { recursive: true });
fs.copyFileSync(source, destination);
console.log(`Synced service_display_defaults.json -> ${path.relative(process.cwd(), destination)}`);

const diskAssessmentRelative = path.join('data', 'disk-assessment.json');
const diskAssessmentDestination = path.join(
  __dirname,
  '../src/disks/data/disk-assessment.json',
);

function resolveRepoDataFile(relativePath, envOverride) {
  const candidates = [
    envOverride,
    path.join(process.cwd(), relativePath),
    path.join(path.resolve(__dirname, '..'), relativePath),
    path.join('/app', relativePath),
  ].filter(Boolean);

  for (const candidate of candidates) {
    const resolved = path.resolve(candidate);
    if (fs.existsSync(resolved)) {
      return resolved;
    }
  }

  let dir = path.resolve(__dirname, '..');
  while (true) {
    const candidate = path.join(dir, relativePath);
    if (fs.existsSync(candidate)) {
      return candidate;
    }
    const parent = path.dirname(dir);
    if (parent === dir) {
      break;
    }
    dir = parent;
  }

  return path.join(process.cwd(), relativePath);
}

const diskAssessmentSource = resolveRepoDataFile(
  diskAssessmentRelative,
  process.env.DISK_ASSESSMENT_SOURCE,
);
const diskAssessmentExists = fs.existsSync(diskAssessmentDestination);

if (!fs.existsSync(diskAssessmentSource)) {
  if (diskAssessmentExists) {
    console.warn(
      `Canonical disk assessment not found at ${diskAssessmentSource}; using existing ${path.relative(process.cwd(), diskAssessmentDestination)}`,
    );
  } else {
    console.warn(`Missing canonical disk assessment file: ${diskAssessmentSource}`);
  }
} else {
  fs.mkdirSync(path.dirname(diskAssessmentDestination), { recursive: true });
  fs.copyFileSync(diskAssessmentSource, diskAssessmentDestination);
  console.log(`Synced disk-assessment.json -> ${path.relative(process.cwd(), diskAssessmentDestination)}`);
}
