/**
 * ⚡ Swades Cloud Client SDK — Hyper-Fast Sovereign Firebase Alternative
 * Features: 1-line CRUD, S3 Object Storage with instant CDN, Auth & Scoped Keys.
 * 10,000% safe, project-isolated, sub-millisecond local reflection.
 */

class SwadesClient {
  constructor(options = {}) {
    this.endpoint = (options.endpoint || (typeof window !== 'undefined' ? window.location.origin : 'https://phone-whisper-server.pages.dev')).replace(/\/+$/, '');
    this.apiKey = options.apiKey || '';
    this.projectId = options.projectId || options.project || 'default';
  }

  // Set active project
  project(projectId) {
    this.projectId = projectId;
    return this;
  }

  // Set active key
  setKey(key) {
    this.apiKey = key;
    return this;
  }

  // --- DATABASE (SQL & FIRESTORE-LIKE CRUD) ---
  db = {
    // 1-line SQL query
    query: async (sqlQuery, params = {}) => {
      const res = await fetch(`${this.endpoint}/v1/dashboard/db/sql`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': this.apiKey,
          'x-project-id': this.projectId
        },
        body: JSON.stringify({ query: sqlQuery, project_id: this.projectId, ...params })
      });
      const data = await res.json();
      if (!res.ok || data.status === 'error') throw new Error(data.error || 'SQL Query Failed');
      return data.result?.rows || [];
    },

    // List all tables
    tables: async () => {
      const res = await fetch(`${this.endpoint}/v1/dashboard/db/tables`, {
        headers: {
          'x-api-key': this.apiKey,
          'x-project-id': this.projectId
        }
      });
      const data = await res.json();
      return data.tables || [];
    },

    // Insert record into table
    insert: async (table, recordData) => {
      const res = await fetch(`${this.endpoint}/v1/dashboard/db/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': this.apiKey,
          'x-project-id': this.projectId
        },
        body: JSON.stringify({
          action: 'insert_row',
          table: table,
          data: recordData,
          project_id: this.projectId
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Insert Failed');
      return data;
    },

    // Delete record by primary key
    delete: async (table, pkCol, pkVal) => {
      const res = await fetch(`${this.endpoint}/v1/dashboard/db/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': this.apiKey,
          'x-project-id': this.projectId
        },
        body: JSON.stringify({
          action: 'delete_row',
          table: table,
          pk_col: pkCol,
          pk_val: pkVal,
          project_id: this.projectId
        })
      });
      return await res.json();
    },

    // Update single cell
    update: async (table, pkCol, pkVal, column, newVal) => {
      const res = await fetch(`${this.endpoint}/v1/dashboard/db/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': this.apiKey,
          'x-project-id': this.projectId
        },
        body: JSON.stringify({
          action: 'update_cell',
          table: table,
          pk_col: pkCol,
          pk_val: pkVal,
          column: column,
          new_val: newVal,
          project_id: this.projectId
        })
      });
      return await res.json();
    }
  };

  // --- STORAGE (FILES, MEDIA, IMAGES & DOCUMENTS) ---
  storage = {
    // Upload any file or blob, returns public CDN URL
    upload: async (file, customKey = null) => {
      const key = customKey || `uploads/${Date.now()}_${file.name || 'file.bin'}`;
      const res = await fetch(`${this.endpoint}/v1/storage/objects/${key}`, {
        method: 'PUT',
        headers: {
          'x-api-key': this.apiKey,
          'x-project-id': this.projectId,
          'Content-Type': file.type || 'application/octet-stream'
        },
        body: file
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Upload failed');
      return {
        key: key,
        url: data.object?.url || `${this.endpoint}/s/${this.projectId}/${key}`,
        size: file.size || data.object?.size
      };
    },

    // List all files in project
    list: async () => {
      const res = await fetch(`${this.endpoint}/v1/storage/objects`, {
        headers: {
          'x-api-key': this.apiKey,
          'x-project-id': this.projectId
        }
      });
      const data = await res.json();
      return data.objects || [];
    },

    // Delete file
    delete: async (key) => {
      const res = await fetch(`${this.endpoint}/v1/storage/objects/${key}`, {
        method: 'DELETE',
        headers: {
          'x-api-key': this.apiKey,
          'x-project-id': this.projectId
        }
      });
      return await res.json();
    }
  };

  // --- AUTH (USERS & API KEYS) ---
  auth = {
    login: async (username, password) => {
      const res = await fetch(`${this.endpoint}/v1/storage/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      const data = await res.json();
      if (data.api_key) this.apiKey = data.api_key;
      return data;
    },

    register: async (username, password, email = null) => {
      const res = await fetch(`${this.endpoint}/v1/storage/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, email })
      });
      const data = await res.json();
      if (data.api_key) this.apiKey = data.api_key;
      return data;
    },

    createKey: async (name, scope = 'full', ttlDays = null) => {
      const res = await fetch(`${this.endpoint}/v1/storage/auth/keys`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': this.apiKey
        },
        body: JSON.stringify({ name, restrictions: scope, ttl_days: ttlDays })
      });
      return await res.json();
    }
  };
}

const Swades = {
  init: (options) => new SwadesClient(options)
};

if (typeof window !== 'undefined') {
  window.Swades = Swades;
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { Swades, SwadesClient };
}
