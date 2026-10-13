import { writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { test, expect, BLOCK, NETWORKS } from './fixtures'

test('qualification records an actual offline redirect download', async ({
  plexo,
  serve,
  dirs
}) => {
  const header = 'attachment; filename="probe.bin"'
  const origin = await serve({ size: 3 * BLOCK, contentDisposition: header })
  origin.setRule(({ path }) => {
    if (path === '/loop') return { redirect: '/loop' }
    const remaining = Number(/^\/hop\/(\d+)$/.exec(path)?.[1] ?? 0)
    return remaining > 0 ? { redirect: `/hop/${remaining - 1}` } : 'ok'
  })
  const url = origin.url('/hop/5')
  expect(new URL(url).hostname).toBe('127.0.0.1')
  const preview = await plexo.api.probeUrl(url)
  await plexo.start(url, origin.sha256)
  const state = await plexo.waitForHttpStatus('completed')
  let exhaustedProbe: unknown
  try {
    exhaustedProbe = { value: await plexo.api.probeUrl(origin.url('/loop')) }
  } catch (error) {
    exhaustedProbe = { error: String(error) }
  }
  const versions = await plexo.electronApp.evaluate(() => process.versions)
  await writeFile(
    join(process.env.PLEXO_QUALIFICATION_PROOF!, 'offline-download.json'),
    JSON.stringify(
      {
        url,
        header,
        bytes: 3 * BLOCK,
        sha256: origin.sha256,
        networks: NETWORKS,
        preview,
        exhaustedProbe,
        fileName: state.fileName,
        destinationPath: state.destinationPath,
        isolatedDirs: dirs,
        versions
      },
      null,
      2
    )
  )
  expect(state.destinationPath.startsWith(dirs.dest)).toBe(true)
})
