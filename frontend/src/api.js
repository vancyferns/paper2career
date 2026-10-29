// Data access. Uses Appwrite TablesDB when VITE_APPWRITE_* is configured, otherwise a read-only-ish
// demo dataset exported by the worker (`python -m paper2career export-demo`).
// No API keys live here: the browser only reads public rows, and reviewers act through their own session.
import { Account, Client, Permission, Query, Role, Storage, TablesDB, Teams } from 'appwrite';

const endpoint = import.meta.env.VITE_APPWRITE_ENDPOINT;
const projectId = import.meta.env.VITE_APPWRITE_PROJECT_ID;
const databaseId = import.meta.env.VITE_APPWRITE_DATABASE_ID || 'paper2career_db';

export const DEMO = !endpoint || !projectId;

let client, tables, account, teams, storage;
const CROPS_BUCKET = 'ad_crops';
if (!DEMO) {
  client = new Client().setEndpoint(endpoint).setProject(projectId);
  tables = new TablesDB(client);
  account = new Account(client);
  teams = new Teams(client);
  storage = new Storage(client);
}

const REVIEWERS = Role.team('reviewers');
const privatePerms = [Permission.read(REVIEWERS), Permission.update(REVIEWERS)];
const publicPerms = [Permission.read(Role.any()), ...privatePerms];

// ------------------------------------------------------------------ demo store

let demo;
async function demoData() {
  if (!demo) {
    const res = await fetch(`${import.meta.env.BASE_URL}demo-data.json`);
    demo = res.ok ? await res.json() : {};
    for (const t of ['editions', 'jobs', 'job_appearances', 'job_revisions', 'ingestion_runs']) {
      demo[t] = Object.values(demo[t] || {});
    }
  }
  return demo;
}

// ------------------------------------------------------------------ helpers

async function listAll(tableId, queries = [], max = 1000) {
  const rows = [];
  let cursor = null;
  while (rows.length < max) {
    const q = [...queries, Query.limit(100)];
    if (cursor) q.push(Query.cursorAfter(cursor));
    const res = await tables.listRows({ databaseId, tableId, queries: q });
    rows.push(...res.rows);
    if (res.rows.length < 100) break;
    cursor = res.rows[res.rows.length - 1].$id;
  }
  return rows;
}

const byDesc = (key) => (a, b) => (b[key] || '').localeCompare(a[key] || '');

/** URL of the stored evidence crop for an appearance, or null when none was saved. */
export function cropUrl(appearance) {
  const id = appearance?.crop_file_id;
  if (!id) return null;
  if (DEMO) return `${import.meta.env.BASE_URL}crops/${id}.jpg`;
  return storage.getFileView({ bucketId: CROPS_BUCKET, fileId: id });
}

// ------------------------------------------------------------------ public reads

let _cachedJobs = null;
let _cachedJobsPromise = null;

export function getCachedPublishedJobs() {
  return _cachedJobs;
}

export async function listPublishedJobs(forceRefresh = false) {
  if (!forceRefresh && _cachedJobs) {
    return _cachedJobs;
  }
  if (!forceRefresh && _cachedJobsPromise) {
    return _cachedJobsPromise;
  }
  _cachedJobsPromise = (async () => {
    let result;
    if (DEMO) {
      const d = await demoData();
      result = d.jobs.filter((j) => j.review_status === 'published').sort(byDesc('last_seen_at'));
    } else {
      result = await listAll('jobs', [Query.equal('review_status', ['published']), Query.orderDesc('last_seen_at')]);
    }
    _cachedJobs = result;
    _cachedJobsPromise = null;
    return result;
  })();
  return _cachedJobsPromise;
}

export async function getJob(id) {
  if (_cachedJobs) {
    const found = _cachedJobs.find((j) => j.$id === id);
    if (found) return found;
  }
  if (DEMO) return (await demoData()).jobs.find((j) => j.$id === id) || null;
  try {
    return await tables.getRow({ databaseId, tableId: 'jobs', rowId: id });
  } catch (e) {
    if (e.code === 404 || e.code === 401) return null;
    throw e;
  }
}

export async function listAppearances(jobId) {
  if (DEMO) {
    return (await demoData()).job_appearances.filter((a) => a.job_id === jobId).sort(byDesc('publication_date'));
  }
  return listAll('job_appearances', [Query.equal('job_id', [jobId]), Query.orderDesc('publication_date')], 200);
}

export async function listRuns() {
  if (DEMO) return (await demoData()).ingestion_runs.sort(byDesc('started_at')).slice(0, 50);
  const res = await tables.listRows({
    databaseId, tableId: 'ingestion_runs', queries: [Query.orderDesc('started_at'), Query.limit(50)],
  });
  return res.rows;
}

// ------------------------------------------------------------------ reviewer session

export async function currentReviewer() {
  if (DEMO) return { name: 'Demo reviewer', email: 'demo', demo: true };
  try {
    const user = await account.get();
    const memberships = await teams.list();
    const isReviewer = memberships.teams.some((t) => t.$id === 'reviewers');
    return { name: user.name || user.email, email: user.email, isReviewer };
  } catch {
    return null;
  }
}

export async function login(email, password) {
  await account.createEmailPasswordSession({ email, password });
  return currentReviewer();
}

export async function logout() {
  if (!DEMO) await account.deleteSession({ sessionId: 'current' });
}

// ------------------------------------------------------------------ review actions

export async function reviewQueue() {
  if (DEMO) {
    const d = await demoData();
    return {
      jobs: d.jobs.filter((j) => j.review_status === 'needs_review').sort(byDesc('last_seen_at')),
      revisions: d.job_revisions.filter((r) => r.status === 'pending').sort(byDesc('created_at')),
    };
  }
  const [jobs, revisions] = await Promise.all([
    listAll('jobs', [Query.equal('review_status', ['needs_review']), Query.orderDesc('last_seen_at')]),
    listAll('job_revisions', [Query.equal('status', ['pending']), Query.orderDesc('created_at')]),
  ]);
  return { jobs, revisions };
}

const stamp = (who) => ({ reviewed_by: who.email, reviewed_at: new Date().toISOString() });

async function setAppearanceVisibility(jobId, isPublic) {
  if (DEMO) return;
  const apps = await listAll('job_appearances', [Query.equal('job_id', [jobId])], 200);
  const permissions = isPublic ? publicPerms : privatePerms;
  const crops = [...new Set(apps.map((a) => a.crop_file_id).filter(Boolean))];
  await Promise.all([
    ...apps.map((a) => tables.updateRow({ databaseId, tableId: 'job_appearances', rowId: a.$id, data: {}, permissions })),
    ...crops.map((fileId) => storage.updateFile({
      bucketId: CROPS_BUCKET, fileId, permissions: isPublic ? [Permission.read(Role.any()), Permission.read(REVIEWERS)] : [Permission.read(REVIEWERS)],
    })),
  ]);
}

/** Publish a job (optionally with reviewer corrections) and make its source appearances publicly readable. */
export async function publishJob(job, edits, who) {
  const data = { ...edits, review_status: 'published', ...stamp(who) };
  if (DEMO) return Object.assign(job, data);
  const row = await tables.updateRow({ databaseId, tableId: 'jobs', rowId: job.$id, data, permissions: publicPerms });
  await setAppearanceVisibility(job.$id, true);
  return row;
}

export async function rejectJob(job, who) {
  const data = { review_status: 'rejected', ...stamp(who) };
  if (DEMO) return Object.assign(job, data);
  const row = await tables.updateRow({ databaseId, tableId: 'jobs', rowId: job.$id, data, permissions: privatePerms });
  await setAppearanceVisibility(job.$id, false);
  return row;
}

/** Accept applies the newer edition's values to the canonical job; reject keeps the current values. */
export async function resolveRevision(rev, accept, who) {
  const job = await getJob(rev.job_id);
  const newValues = JSON.parse(rev.new_values || '{}');
  const revData = { status: accept ? 'accepted' : 'rejected', resolved_by: who.email, resolved_at: new Date().toISOString() };
  const { revisions } = await reviewQueue();
  const othersPending = revisions.some((r) => r.job_id === rev.job_id && r.$id !== rev.$id);
  const jobData = { ...(accept ? newValues : {}), has_pending_revision: othersPending };
  if (DEMO) {
    Object.assign(rev, revData);
    if (job) Object.assign(job, jobData);
    return;
  }
  await tables.updateRow({ databaseId, tableId: 'job_revisions', rowId: rev.$id, data: revData });
  if (job) await tables.updateRow({ databaseId, tableId: 'jobs', rowId: job.$id, data: jobData });
}


export async function publishAllJobs(jobs, who) {
  for (const job of jobs) {
    await publishJob(job, {}, who);
  }
}

export async function acceptAllRevisions(revisions, who) {
  for (const rev of revisions) {
    await resolveRevision(rev, true, who);
  }
}
