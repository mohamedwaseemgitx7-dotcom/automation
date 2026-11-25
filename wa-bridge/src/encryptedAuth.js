// Baileys auth state stored on disk with AES-256-GCM encryption (key from WA_SESSION_KEY).
// Same shape as Baileys' useMultiFileAuthState, but nothing is written in plaintext.
import { createCipheriv, createDecipheriv, createHash, randomBytes } from 'node:crypto'
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { BufferJSON, initAuthCreds, proto } from 'baileys'


function keyFrom(secret) {
  if (!secret || secret.length < 32) throw new Error('WA_SESSION_KEY missing or too short')
  return createHash('sha256').update(secret).digest()
}

export async function useEncryptedAuthState(folder, secret) {
  const key = keyFrom(secret)
  await mkdir(folder, { recursive: true })
  const file = name => join(folder, `${name.replace(/[^a-zA-Z0-9._-]/g, '_')}.enc`)

  const write = async (data, name) => {
    const iv = randomBytes(12)
    const c = createCipheriv('aes-256-gcm', key, iv)
    const body = Buffer.concat([c.update(JSON.stringify(data, BufferJSON.replacer), 'utf8'), c.final()])
    await writeFile(file(name), Buffer.concat([iv, c.getAuthTag(), body]), { mode: 0o600 })
  }
  const read = async name => {
    try {
      const raw = await readFile(file(name))
      const d = createDecipheriv('aes-256-gcm', key, raw.subarray(0, 12))
      d.setAuthTag(raw.subarray(12, 28))
      const text = Buffer.concat([d.update(raw.subarray(28)), d.final()]).toString('utf8')
      return JSON.parse(text, BufferJSON.reviver)
    } catch {
      return null
    }
  }
  const remove = async name => rm(file(name), { force: true })

  const creds = (await read('creds')) || initAuthCreds()
  return {
    state: {
      creds,
      keys: {
        get: async (type, ids) => {
          const out = {}
          await Promise.all(ids.map(async id => {
            let v = await read(`${type}-${id}`)
            if (type === 'app-state-sync-key' && v) v = proto.Message.AppStateSyncKeyData.fromObject(v)
            out[id] = v
          }))
          return out
        },
        set: async data => {
          const jobs = []
          for (const type in data) {
            for (const id in data[type]) {
              const v = data[type][id]
              jobs.push(v ? write(v, `${type}-${id}`) : remove(`${type}-${id}`))
            }
          }
          await Promise.all(jobs)
        },
      },
    },
    saveCreds: () => write(creds, 'creds'),
  }
}
