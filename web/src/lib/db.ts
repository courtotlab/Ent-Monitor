import { Pool, types } from "pg"

// Parse PostgreSQL BIGINT (like COUNT) as JavaScript Numbers instead of Strings
types.setTypeParser(20, (val) => parseInt(val, 10))

// Reuse a single pool across API routes for dev hot-reloading
declare global {
  var _pgPool: Pool | undefined
}

function createPool(): Pool {
  // Use a dummy string during Next.js build step when env vars are unavailable
  return new Pool({ 
    connectionString: process.env.DATABASE_URL || "postgres://dummy:dummy@localhost/dummy" 
  })
}

const pool: Pool = globalThis._pgPool ?? createPool()

if (process.env.NODE_ENV !== "production") {
  globalThis._pgPool = pool
}

export default pool
