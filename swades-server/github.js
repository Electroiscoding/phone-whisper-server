import { execSync } from 'child_process';
import https from 'https';

export function parseGitHubUrl(url) {
  const regex = /^(?:https:\/\/github\.com\/|git@github\.com:)([^/]+)\/([^/]+?)(?:\.git)?$/;
  const match = url.match(regex);
  if (match) {
    return { owner: match[1], repo: match[2] };
  }
  throw new Error(`Invalid GitHub URL: ${url}`);
}

export function cloneRepo(repoUrl, targetDir, pat) {
  try {
    let cloneUrl = repoUrl;
    if (pat && repoUrl.startsWith('https://')) {
      cloneUrl = repoUrl.replace('https://', `https://${pat}@`);
    } else if (pat && repoUrl.startsWith('git@')) {
      const { owner, repo } = parseGitHubUrl(repoUrl);
      cloneUrl = `https://${pat}@github.com/${owner}/${repo}.git`;
    }
    
    execSync(`git clone --depth 50 ${cloneUrl} ${targetDir}`, { stdio: 'pipe' });
    return { success: true };
  } catch (err) {
    return { success: false, error: err.message };
  }
}

export function createBranch(workdir, branchName) {
  execSync(`git checkout -b ${branchName}`, { cwd: workdir, timeout: 60000 });
}

export function configureGit(workdir) {
  try {
    execSync(`git config user.name 'Swades Agent'`, { cwd: workdir, timeout: 60000 });
    execSync(`git config user.email 'swades@phonewhisper.ai'`, { cwd: workdir, timeout: 60000 });
  } catch (e) {}
}

export function commitAll(workdir, message) {
  try {
    execSync(`git add -A && git commit -m "${message.replace(/"/g, '\\"')}"`, { cwd: workdir, timeout: 60000 });
  } catch (e) {
    // might be nothing to commit
  }
}

export function pushBranch(workdir, branchName, pat, repoUrl) {
  if (!pat) {
    console.log("No GitHub PAT provided. Skipping push.");
    return;
  }
  
  let pushUrl = repoUrl;
  if (pat && repoUrl.startsWith('https://')) {
    pushUrl = repoUrl.replace('https://', `https://${pat}@`);
  } else if (pat && repoUrl.startsWith('git@')) {
    const { owner, repo } = parseGitHubUrl(repoUrl);
    pushUrl = `https://${pat}@github.com/${owner}/${repo}.git`;
  }
  
  try {
    execSync(`git push -u origin ${branchName}`, { cwd: workdir, timeout: 60000 });
  } catch (err) {
    console.warn("Git push failed:", err.message);
  }
}

export function openPullRequest({ owner, repo, head, base, title, body, pat }) {
  return new Promise((resolve) => {
    if (!pat) {
      resolve({ pr_url: null, pr_number: null });
      return;
    }

    const payload = JSON.stringify({ title, body, head, base });
    const options = {
      hostname: 'api.github.com',
      port: 443,
      path: `/repos/${owner}/${repo}/pulls`,
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${pat}`,
        'User-Agent': 'SwadesAgent/1.0',
        'Accept': 'application/vnd.github.v3+json',
        'Content-Type': 'application/json',
        'Content-Length': payload.length
      }
    };
    
    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            const json = JSON.parse(data);
            resolve({ pr_url: json.html_url, pr_number: json.number });
          } else {
            resolve({ pr_url: null, pr_number: null, error: `GitHub API error: ${res.statusCode}` });
          }
        } catch (e) {
          resolve({ pr_url: null, pr_number: null });
        }
      });
    });
    
    req.on('error', () => resolve({ pr_url: null, pr_number: null }));
    req.setTimeout(10000, () => {
      req.destroy();
      resolve({ pr_url: null, pr_number: null });
    });
    req.write(payload);
    req.end();
  });
}

export function getDefaultBranch({ owner, repo, pat }) {
  return new Promise((resolve) => {
    const headers = {
      'User-Agent': 'SwadesAgent/1.0',
      'Accept': 'application/vnd.github.v3+json'
    };
    if (pat) headers['Authorization'] = `Bearer ${pat}`;
    
    const options = {
      hostname: 'api.github.com',
      port: 443,
      path: `/repos/${owner}/${repo}`,
      method: 'GET',
      headers: headers
    };
    
    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const json = JSON.parse(data);
          resolve(json.default_branch || 'main');
        } catch (e) {
          resolve('main');
        }
      });
    });
    
    req.on('error', () => resolve('main'));
    req.setTimeout(5000, () => {
      req.destroy();
      resolve('main');
    });
    req.end();
  });
}
