import { Pool, types } from "pg"

// Parse PostgreSQL BIGINT (like COUNT) as JavaScript Numbers instead of Strings
types.setTypeParser(20, (val) => parseInt(val, 10))

// Reuse a single pool across API routes for dev hot-reloading
declare global {
  var _pgPool: Pool | undefined
}

function createPool(): Pool {
  const connectionString = process.env.DATABASE_URL
  if (!connectionString) {
    throw new Error("DATABASE_URL environment variable is not set")
  }
  return new Pool({ connectionString })
}

const pool: Pool = globalThis._pgPool ?? createPool()

if (process.env.NODE_ENV !== "production") {
  globalThis._pgPool = pool
}

export default pool
