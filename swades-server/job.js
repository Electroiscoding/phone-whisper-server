import crypto from 'crypto';
import fs from 'fs';
import path from 'path';

let DatabaseClass = null;

try {
  const sqliteModule = await import('node:sqlite');
  DatabaseClass = sqliteModule.DatabaseSync;
} catch (e) {
  try {
    const betterSqlite = await import('better-sqlite3');
    DatabaseClass = betterSqlite.default || betterSqlite;
  } catch (err) {
    console.error('Neither node:sqlite nor better-sqlite3 is available:', err);
  }
}

function getStorageDir() {
  const home = process.env.HOME || (fs.existsSync('/tmp') ? '/tmp' : '/data/data/com.termux/files/home');
  const target = path.join(home, '.swades_jobs');
  try {
    fs.mkdirSync(target, { recursive: true });
    return target;
  } catch (e) {
    const fallback = '/tmp/swades_jobs';
    fs.mkdirSync(fallback, { recursive: true });
    return fallback;
  }
}

const DB_DIR = getStorageDir();
const DB_PATH = path.join(DB_DIR, 'swades.db');

let dbInstance = null;

export function initDatabase() {
  if (dbInstance) return dbInstance;
  
  if (!fs.existsSync(DB_DIR)) {
    fs.mkdirSync(DB_DIR, { recursive: true });
  }
  
  if (!DatabaseClass) {
    throw new Error('No SQLite database driver found (node:sqlite or better-sqlite3)');
  }
  
  const db = new DatabaseClass(DB_PATH);
  
  db.exec(`
    CREATE TABLE IF NOT EXISTS jobs (
      id TEXT PRIMARY KEY,
      repo_url TEXT,
      task TEXT,
      status TEXT,
      branch_name TEXT,
      pr_url TEXT,
      pr_number INTEGER,
      created_at TEXT,
      started_at TEXT,
      completed_at TEXT,
      files_changed TEXT,
      error_message TEXT,
      total_steps INTEGER,
      worker_pid INTEGER,
      github_pat TEXT,
      api_key TEXT,
      api_key_hash TEXT,
      base_url TEXT,
      model TEXT
    );
    
    CREATE TABLE IF NOT EXISTS job_logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      job_id TEXT,
      timestamp TEXT,
      type TEXT,
      data TEXT,
      step_number INTEGER,
      FOREIGN KEY(job_id) REFERENCES jobs(id)
    );
  `);
  
  dbInstance = db;
  return db;
}

function getDb() {
  if (!dbInstance) return initDatabase();
  return dbInstance;
}

export function createJob({ repoUrl, task, githubPat, apiKey, baseUrl, model }) {
  const db = getDb();
  const id = crypto.randomUUID().slice(0, 8);
  const now = new Date().toISOString();
  
  const apiKeyHash = apiKey ? crypto.createHash('sha256').update(apiKey).digest('hex') : null;
  
  const stmt = db.prepare(`
    INSERT INTO jobs (id, repo_url, task, status, created_at, github_pat, api_key_hash, base_url, model)
    VALUES (?, ?, ?, 'QUEUED', ?, ?, ?, ?, ?)
  `);
  
  stmt.run(id, repoUrl, task, now, githubPat || null, apiKeyHash, baseUrl || null, model || null);
  
  return getJob(id);
}

export function getJob(jobId) {
  const db = getDb();
  const row = db.prepare('SELECT * FROM jobs WHERE id = ?').get(jobId);
  return row || null;
}

export function updateJob(jobId, fields) {
  const db = getDb();
  const keys = Object.keys(fields);
  if (keys.length === 0) return;
  
  const setClause = keys.map(k => `${k} = ?`).join(', ');
  const values = Object.values(fields);
  
  const stmt = db.prepare(`UPDATE jobs SET ${setClause} WHERE id = ?`);
  stmt.run(...values, jobId);
}

export function appendLog(jobId, type, data, stepNumber = null) {
  const db = getDb();
  const now = new Date().toISOString();
  const dataStr = typeof data === 'string' ? data : JSON.stringify(data);
  
  const stmt = db.prepare(`
    INSERT INTO job_logs (job_id, timestamp, type, data, step_number)
    VALUES (?, ?, ?, ?, ?)
  `);
  
  stmt.run(jobId, now, type, dataStr, stepNumber);
}

export function getJobLogs(jobId, sinceTimestamp = null) {
  const db = getDb();
  if (sinceTimestamp) {
    return db.prepare('SELECT * FROM job_logs WHERE job_id = ? AND timestamp > ? ORDER BY timestamp ASC').all(jobId, sinceTimestamp);
  }
  return db.prepare('SELECT * FROM job_logs WHERE job_id = ? ORDER BY timestamp ASC').all(jobId);
}

export function listJobs(limit = 20, offset = 0) {
  const db = getDb();
  return db.prepare('SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?').all(limit, offset);
}

export function getQueuePosition(jobId) {
  const db = getDb();
  const job = getJob(jobId);
  if (!job || job.status !== 'QUEUED') return 0;
  
  const row = db.prepare('SELECT COUNT(*) as count FROM jobs WHERE status = "QUEUED" AND created_at < ?').get(job.created_at);
  return row.count;
}

export function getNextQueuedJob() {
  const db = getDb();
  return db.prepare('SELECT * FROM jobs WHERE status = "QUEUED" ORDER BY created_at ASC LIMIT 1').get() || null;
}

export function cleanupOldJobs(maxAgeHours = 24) {
  const db = getDb();
  const threshold = new Date(Date.now() - maxAgeHours * 3600 * 1000).toISOString();
  
  const stmt = db.prepare('DELETE FROM jobs WHERE created_at < ? AND status IN ("COMPLETED", "FAILED", "CANCELLED")');
  const info = stmt.run(threshold);
  return info.changes;
}
